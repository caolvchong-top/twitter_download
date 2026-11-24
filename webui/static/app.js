/* X Downloader WebUI — vanilla JS, no build step */
(() => {
  'use strict';

  // ------------------------------------------------------------------ i18n
  const I18N = window.XD_I18N;
  const t = (key, vars) => I18N.t(key, vars);

  // ------------------------------------------------------------------ utils
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (name, cls = '') => `<svg class="${cls}"><use href="#i-${name}"/></svg>`;
  const fmtNum = (n) => Number(n || 0).toLocaleString();
  const pad = (n) => String(n).padStart(2, '0');
  const fmtClock = (ts) => { if (!ts) return '-'; const d = new Date(ts * 1000); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };
  const fmtDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const fmtDur = (sec) => {
    sec = Math.max(0, Math.round(sec));
    if (sec < 60) return `${sec}s`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m ${pad(sec % 60)}s`;
    return `${Math.floor(sec / 3600)}h ${pad(Math.floor((sec % 3600) / 60))}m`;
  };
  const fmtSize = (b) => (b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1048576).toFixed(1)} MB`);
  const splitList = (s) => String(s || '').split(/[\n,，]+/).map((x) => x.trim()).filter(Boolean);
  const mediaUrl = (folder, name) => `/media/${encodeURIComponent(folder)}/${encodeURIComponent(name)}`;
  const thumbUrl = (folder, name) => `/thumb/${encodeURIComponent(folder)}/${encodeURIComponent(name)}`;
  const isTyping = (el) => el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable);

  async function api(path, opts = {}) {
    const init = { method: opts.method || 'GET', headers: {} };
    if (opts.body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, init);
    let data = null;
    try { data = await res.json(); } catch (_) { /* empty */ }
    if (!res.ok) throw new Error((data && data.detail) || `HTTP ${res.status}`);
    return data;
  }

  const TOAST_ICON = { info: 'alert', success: 'check-circle', error: 'x-circle', warn: 'alert' };
  function toast(msg, type = 'info', ms = 4000) {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `${icon(TOAST_ICON[type] || 'alert')}<span>${esc(msg)}</span>`;
    el.title = t('toast.close');
    const close = () => { el.classList.add('out'); setTimeout(() => el.remove(), 260); };
    el.addEventListener('click', close);
    $('#toasts').appendChild(el);
    setTimeout(close, ms);
  }

  const STATUS_ICON = { queued: 'clock', done: 'check-circle', failed: 'x-circle', partial: 'alert', cancelled: 'minus-circle' };
  const statusLabel = (s) => t(`status.${s}`);
  const phaseLabel = (p) => (p ? t(`phase.${p}`) : t('phase.running'));
  const modeLabel = (m) => (m ? t(`mode.${m}`) : '');
  const typeLabel = (tp) => t(`type.${tp}`);
  const typeDesc = (tp) => t(`typeDesc.${tp}`);
  const FINAL = new Set(['done', 'partial', 'failed', 'cancelled']);

  // ------------------------------------------------------------------ state
  const state = {
    cfg: null,
    jobs: new Map(),
    logs: new Map(),
    taskFilter: 'all',
    type: 'user_media',
    connState: 'init',
    previewProfile: null,
    verifyState: null,
    gallery: { folder: null, kind: 'media', q: '', offset: 0, total: 0, items: [], foldersData: null },
    users: [],
    settingsSnapshot: '',
  };

  // ------------------------------------------------------------------ theme
  const themeMq = matchMedia('(prefers-color-scheme: dark)');
  function applyTheme(pref) {
    localStorage.setItem('xd-theme', pref);
    const dark = pref === 'dark' || (pref === 'system' && themeMq.matches);
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    $$('#theme-switch button').forEach((b) => b.classList.toggle('active', b.dataset.themeValue === pref));
  }
  $$('#theme-switch button').forEach((b) => b.addEventListener('click', () => applyTheme(b.dataset.themeValue)));
  themeMq.addEventListener('change', () => { if ((localStorage.getItem('xd-theme') || 'system') === 'system') applyTheme('system'); });
  applyTheme(localStorage.getItem('xd-theme') || 'system');

  // ------------------------------------------------------------------ language
  function renderConn() {
    const ok = state.connState === 'live';
    const bad = state.connState === 'retry';
    $('#conn-dot').className = `live-dot ${ok ? 'ok' : bad ? 'bad' : ''}`;
    $('#conn-text').textContent = state.connState === 'live'
      ? t('sidebar.connLive')
      : state.connState === 'retry'
        ? t('sidebar.connRetry')
        : t('sidebar.connInit');
  }

  function applyLang(lang, rerender = true) {
    const active = I18N.setLang(lang);
    $$('#lang-switch button').forEach((b) => b.classList.toggle('active', b.dataset.langValue === active));
    if (!rerender) return;
    renderConn();
    renderStatus();
    renderEffectiveOpts();
    $('#type-desc').textContent = typeDesc(state.type);
    updateSummary();
    if (state.previewProfile) renderPreviewProfile(state.previewProfile);
    state.jobs.forEach((j) => renderJob(j));
    $$('.log-empty').forEach((el) => { el.textContent = t('task.logEmpty'); });
    renderTaskOverview();
    if (state.gallery.folder) {
      $('#gallery-sub').textContent = t('gallery.filesCount', { n: fmtNum(state.gallery.total) });
      $$('#media-grid .tile-badge').forEach((el) => { el.innerHTML = `${icon('video')}${esc(t('gallery.videoBadge'))}`; });
    } else if (state.gallery.foldersData) {
      renderGalleryFolders(state.gallery.foldersData);
    }
    renderUsers();
    if (state.verifyState) renderVerifyState();
    if (state.cfg?.thumb_cache) renderThumbCache(state.cfg.thumb_cache);
  }
  $$('#lang-switch button').forEach((b) => b.addEventListener('click', () => applyLang(b.dataset.langValue, true)));

  // ------------------------------------------------------------------ navigation
  function currentView() { return ($('.view.active') || {}).id?.replace('view-', ''); }
  function showView(name) {
    if (currentView() === 'settings' && name !== 'settings' && isSettingsDirty()
      && !confirm(t('settings.leaveConfirm'))) return;
    $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
    $$('.view').forEach((v) => v.classList.toggle('active', v.id === `view-${name}`));
    if (name === 'gallery') loadGallery();
    if (name === 'settings') { fillSettings(); loadThumbCache(); }
    history.replaceState(null, '', `#${name}`);
  }
  $$('.nav-item').forEach((b) => b.addEventListener('click', () => showView(b.dataset.view)));
  document.addEventListener('click', (e) => {
    const g = e.target.closest('[data-goto]');
    if (g) showView(g.dataset.goto);
  });
  $('#cookie-card').addEventListener('click', () => showView('settings'));

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.segmented button');
    if (!btn) return;
    const seg = btn.parentElement;
    $$('button', seg).forEach((b) => b.classList.toggle('active', b === btn));
    seg.dispatchEvent(new CustomEvent('change', { detail: btn.dataset.value, bubbles: true }));
  });
  const segValue = (seg) => ($('button.active', seg) || {}).dataset?.value;
  const setSeg = (seg, value) => $$('button', seg).forEach((b) => b.classList.toggle('active', b.dataset.value === value));

  // ------------------------------------------------------------------ config / status
  function formatCookieStatus(st) {
    if (!st) return '';
    if (st.ok) {
      const src = st.is_manual ? t('cookie.manualSource') : (st.source || state.cfg?.config?.cookie || 'cookies.txt');
      return t('cookie.readyDetail', { src });
    }
    return st.message || '';
  }

  async function loadConfig() {
    try {
      state.cfg = await api('/api/config');
      renderStatus();
      renderEffectiveOpts();
      prefillTaskForm();
      if (currentView() === 'settings') fillSettings();
    } catch (e) {
      toast(t('toast.loadCfgFail', { msg: e.message }), 'error');
    }
  }

  function renderStatus() {
    const { cfg } = state;
    if (!cfg) return;
    const st = cfg.cookie_status;
    $('#cookie-dot').className = `status-dot ${st.ok ? 'ok' : 'bad'}`;
    $('#cookie-text').textContent = st.ok ? t('sidebar.cookieReady') : t('sidebar.cookieUnset');
    $('#cookie-card').title = formatCookieStatus(st);
    const root = cfg.resolved_save_root;
    const segs = root.split(/[\\/]/).filter(Boolean);
    $('#save-root').textContent = segs.length > 2 ? `…\\${segs.slice(-2).join('\\')}` : root;
    $('#save-root').title = root;
    $('#proxy-text').textContent = cfg.config.advanced.proxy || t('sidebar.proxyUnset');
  }

  function renderEffectiveOpts() {
    const c = state.cfg?.config;
    if (!c) return;
    const a = c.advanced;
    const yn = (v) => [v ? t('common.on') : t('common.off'), v ? 'on' : ''];
    const rows = [
      [t('opts.imageFormat'), [a.image_format]],
      [t('opts.hasVideo'), yn(a.has_video)],
      [t('opts.skipDownloaded'), yn(a.skip_downloaded)],
      [t('opts.concurrency'), [a.concurrency]],
      [t('opts.waitRateLimit'), yn(a.wait_on_rate_limit)],
      [t('opts.markdown'), yn(a.md_output)],
    ];
    $('#effective-opts').innerHTML = rows.map(([k, [v, cls = '']]) => `<div><dt>${esc(k)}</dt><dd class="${cls}">${esc(v)}</dd></div>`).join('');
  }

  // ------------------------------------------------------------------ new task form
  const form = $('#task-form');

  function setType(type) {
    state.type = type;
    $$('#type-tabs .tab').forEach((c) => c.classList.toggle('active', c.dataset.type === type));
    $$('[data-for]', form).forEach((el) => el.classList.toggle('hidden', !el.dataset.for.split(' ').includes(type)));
    $('#type-desc').textContent = typeDesc(type);
    updateLikesState();
    updateSummary();
  }
  $$('#type-tabs .tab').forEach((c) => c.addEventListener('click', () => setType(c.dataset.type)));

  function updateLikesState() {
    const isLikes = state.type === 'user_media' && segValue($('[data-name=mode]', form)) === 'likes';
    $('#likes-hint').hidden = !isLikes;
    $$('#field-time input, #field-time button').forEach((el) => { el.disabled = isLikes; });
  }
  $('[data-name=mode]', form).addEventListener('change', () => { updateLikesState(); updateSummary(); });
  $('[data-name=search_mode]', form).addEventListener('change', updateSummary);

  function prefillTaskForm() {
    const c = state.cfg?.config;
    if (!c || form.dataset.prefilled) return;
    form.dataset.prefilled = '1';
    const tr = c.advanced.time_range || '';
    if (tr.includes(':')) {
      const [s, e] = tr.split(':');
      form.time_start.value = s || '';
      form.time_end.value = e || '';
    }
    $$('button', $('[data-name=mode]', form)).forEach((b) => b.classList.toggle('active', b.dataset.value === c.mode));
    updateLikesState();
    updateSummary();
  }

  $$('[data-range]').forEach((btn) => btn.addEventListener('click', () => {
    const days = Number(btn.dataset.range);
    if (!days) { form.time_start.value = ''; form.time_end.value = ''; return updateSummary(); }
    form.time_start.value = fmtDate(new Date(Date.now() - days * 86400000));
    form.time_end.value = fmtDate(new Date());
    updateSummary();
  }));

  function timeRangeValue(forReplies = false) {
    let s = form.time_start.value;
    let e = form.time_end.value;
    if (!s && !e) return '';
    if (forReplies) { s = s || '2006-03-21'; e = e || fmtDate(new Date()); }
    return `${s}:${e}`;
  }

  function collectTask() {
    const tType = state.type;
    const params = {};
    if (['user_media', 'user_text', 'profile'].includes(tType)) params.targets = splitList(form.targets_users.value);
    if (tType === 'tweet') params.targets = splitList(form.targets_tweets.value);
    if (tType === 'replies') params.targets = splitList(form.targets_replies.value);
    if (tType === 'user_media') {
      params.mode = segValue($('[data-name=mode]', form));
      params.time_range = params.mode === 'likes' ? '' : timeRangeValue();
    }
    if (tType === 'user_text') { params.time_range = timeRangeValue(); params.include_retweet = form.include_retweet.checked; }
    if (tType === 'replies') { params.time_range = timeRangeValue(true); params.media_down = form.media_down.checked; }
    if (tType === 'search') {
      params.tag = form.tag.value.trim();
      params.filter = form.filter.value.trim();
      params.search_mode = segValue($('[data-name=search_mode]', form));
      params.limit = Number(form.limit.value) || 100;
    }
    return params;
  }

  function updateSummary() {
    const p = collectTask();
    const parts = [];
    if (state.type === 'search') {
      if (p.tag || p.filter) {
        parts.push(
          t('new.summaryQuery', { q: [p.tag, p.filter].filter(Boolean).join(' ') }),
          t('new.summaryLimit', { n: p.limit }),
        );
      } else {
        parts.push(t('new.summaryNeedSearch'));
      }
    } else if (p.targets) {
      parts.push(p.targets.length ? t('new.summaryTargets', { n: p.targets.length }) : t('new.summaryNeedTarget'));
    }
    if (state.type === 'user_media') parts.push(modeLabel(p.mode));
    if (p.time_range) parts.push(p.time_range.replace(':', ' → '));
    $('#form-summary').textContent = parts.filter(Boolean).join(' · ');
    const ready = state.type === 'search' ? !!(p.tag || p.filter) : !!(p.targets && p.targets.length);
    $('#btn-submit').disabled = !ready;
    $('#btn-submit').title = ready ? '' : t('new.submitNeedTarget');
  }
  form.addEventListener('input', updateSummary);

  async function submitTask(e) {
    if (e) e.preventDefault();
    const btn = $('#btn-submit');
    btn.disabled = true;
    try {
      const job = await api('/api/tasks', { method: 'POST', body: { type: state.type, params: collectTask() } });
      upsertJob(job);
      toast(t('toast.queued', { title: job.title }), 'success');
      showView('tasks');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      updateSummary();
    }
  }
  form.addEventListener('submit', submitTask);

  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && currentView() === 'new') return submitTask(e);
    if (!isTyping(document.activeElement) && !e.ctrlKey && !e.metaKey && !e.altKey && e.key.toLowerCase() === 'n'
      && $('#lightbox').classList.contains('hidden')) {
      e.preventDefault();
      showView('new');
      const ta = $$('textarea, input[name=tag]', form).find((x) => !x.closest('.hidden'));
      if (ta) ta.focus();
    }
  });

  $('#btn-batch').addEventListener('click', async () => {
    const users = state.cfg?.config.users || [];
    if (!users.length) { toast(t('toast.batchNoUsers'), 'warn'); return showView('settings'); }
    if (!confirm(t('toast.batchConfirm', {
      n: users.length,
      mode: modeLabel(state.cfg.config.mode),
      users: users.join(', '),
    }))) return;
    try {
      const job = await api('/api/tasks', { method: 'POST', body: { type: 'batch' } });
      upsertJob(job);
      toast(t('toast.batchQueued'), 'success');
      showView('tasks');
    } catch (err) { toast(err.message, 'error'); }
  });

  // user preview
  function renderPreviewProfile(p) {
    const area = $('#preview-area');
    area.className = '';
    area.innerHTML = `
      <div class="profile">
        <div class="profile-banner" style="${p.banner_url ? `background-image:url('${esc(p.banner_url)}')` : ''}"></div>
        <div class="profile-body">
          <img class="profile-avatar" src="${esc(p.avatar_url)}" alt="" referrerpolicy="no-referrer" />
          <div class="profile-name">${esc(p.name)}</div>
          <div class="profile-sn">@${esc(p.screen_name)}</div>
          ${p.description ? `<div class="profile-desc">${esc(p.description)}</div>` : '<div style="height:10px"></div>'}
          <div class="profile-stats"><span><b>${fmtNum(p.statuses_count)}</b>${esc(t('preview.tweets'))}</span><span><b>${fmtNum(p.media_count)}</b>${esc(t('preview.media'))}</span></div>
        </div>
      </div>`;
  }

  $('#btn-preview').addEventListener('click', previewUser);
  $('#preview-name').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); previewUser(); } });
  async function previewUser() {
    let name = $('#preview-name').value.trim();
    if (!name) {
      const src = state.type === 'replies' ? form.targets_replies.value : form.targets_users.value;
      name = splitList(src).find((x) => !/status\/\d+/.test(x)) || '';
      $('#preview-name').value = name;
    }
    name = name.replace(/^@/, '');
    if (!name) { toast(t('preview.needName'), 'warn'); return; }
    state.previewProfile = null;
    const area = $('#preview-area');
    area.className = 'preview-placeholder';
    area.innerHTML = `<span class="spinner"></span><span>${esc(t('preview.loading'))}</span>`;
    try {
      const p = await api(`/api/user/${encodeURIComponent(name)}`);
      state.previewProfile = p;
      renderPreviewProfile(p);
    } catch (err) {
      area.className = 'preview-placeholder error';
      area.innerHTML = `${icon('x-circle')}<span>${esc(err.message)}</span>`;
    }
  }

  // ------------------------------------------------------------------ tasks
  const taskList = $('#task-list');
  const tpl = $('#tpl-task');
  const MEDIA_PCT_TYPES = new Set(['user_media', 'tweet', 'profile']);

  function jobPercent(job) {
    if (FINAL.has(job.status)) return 100;
    if (job.status !== 'running') return 0;
    const n = job.targets.length || 1;
    const p = job.progress;
    const media = MEDIA_PCT_TYPES.has(job.type) || (job.type === 'search' && job.params.search_mode !== 'text');
    if (!media || !p || !p.items_found) return n > 1 ? (job.current_index / n) * 100 : null;
    const frac = Math.min(1, (p.downloaded + p.skipped + p.failed) / p.items_found);
    return ((job.current_index + frac) / n) * 100;
  }

  function jobMatchesFilter(job) {
    const f = state.taskFilter;
    if (f === 'active') return job.status === 'running' || job.status === 'queued';
    if (f === 'done') return job.status === 'done' || job.status === 'partial';
    if (f === 'failed') return job.status === 'failed' || job.status === 'cancelled';
    return true;
  }

  function createJobEl(job) {
    const el = tpl.content.firstElementChild.cloneNode(true);
    el.dataset.id = job.id;
    $('.act-cancel', el).addEventListener('click', async () => {
      try { await api(`/api/tasks/${job.id}/cancel`, { method: 'POST' }); } catch (e) { toast(e.message, 'error'); }
    });
    $('.act-retry', el).addEventListener('click', async () => {
      try { const j = await api(`/api/tasks/${job.id}/retry`, { method: 'POST' }); upsertJob(j); toast(t('toast.requeued'), 'success'); } catch (e) { toast(e.message, 'error'); }
    });
    $('.act-delete', el).addEventListener('click', async () => {
      try { await api(`/api/tasks/${job.id}`, { method: 'DELETE' }); removeJob(job.id); } catch (e) { toast(e.message, 'error'); }
    });
    $('.act-open', el).addEventListener('click', () => {
      const j = state.jobs.get(job.id);
      const dir = [...(j.results || [])].reverse().find((r) => r.save_dir)?.save_dir;
      if (dir) openFolder(dir);
    });
    $('.act-logs', el).addEventListener('click', async (e) => {
      const box = $('.task-logs', el);
      const open = box.classList.toggle('hidden') === false;
      e.currentTarget.classList.toggle('active', open);
      if (!open) return;
      if (!state.logs.has(job.id)) {
        try { state.logs.set(job.id, await api(`/api/tasks/${job.id}/logs`)); } catch (_) { state.logs.set(job.id, []); }
      }
      renderLogs(job.id, true);
    });
    return el;
  }

  function renderJob(job) {
    let el = taskList.querySelector(`[data-id="${job.id}"]`);
    if (!el) {
      el = createJobEl(job);
      const after = $$('.task', taskList).find((c) => c.dataset.id < job.id);
      taskList.insertBefore(el, after || null);
    }
    el.className = `task ${job.status}`;
    el.classList.toggle('hidden', !jobMatchesFilter(job));

    const ic = $('.task-icon', el);
    ic.className = `task-icon ${job.status}`;
    ic.innerHTML = job.status === 'running' ? '<span class="spinner"></span>' : icon(STATUS_ICON[job.status] || 'clock');
    ic.title = job.cancel_requested && job.status === 'running' ? t('status.cancelling') : statusLabel(job.status);

    const label = job.targets.length > 3
      ? t('task.targetsMore', { head: job.targets.slice(0, 3).join(', '), n: job.targets.length })
      : job.targets.join(', ');
    $('.task-title', el).textContent = label;
    $('.task-title', el).title = job.targets.join('\n');
    $('.task-type', el).textContent = typeLabel(job.type) || job.type;

    const p = job.progress || {};
    const meta = [];
    if (job.status === 'running') {
      const phase = job.cancel_requested ? t('status.cancelling') : phaseLabel(p.phase);
      meta.push(`<span class="phase">${esc(phase)}</span>`);
    } else {
      meta.push(esc(statusLabel(job.status)));
    }
    if (job.targets.length > 1) meta.push(esc(t('task.targetIdx', { cur: Math.min(job.current_index + 1, job.targets.length), total: job.targets.length })));
    if (job.type === 'user_media' && job.params.mode) meta.push(esc(modeLabel(job.params.mode)));
    if (job.params.time_range) meta.push(esc(job.params.time_range.replace(':', ' → ')));
    meta.push(`#${job.id} · ${fmtClock(job.created_at)}`);
    if (job.started_at) meta.push(`<span class="elapsed" data-start="${job.started_at}" data-end="${job.finished_at || ''}">${fmtDur((job.finished_at || Date.now() / 1000) - job.started_at)}</span>`);
    if (job.totals.api_calls) meta.push(`API ${fmtNum(job.totals.api_calls)}`);
    $('.task-meta', el).innerHTML = meta.join(' · ');

    const pct = jobPercent(job);
    const prog = $('.task-progress', el);
    prog.classList.toggle('indeterminate', pct === null && job.status === 'running');
    $('.bar', prog).style.width = `${pct ?? 0}%`;

    const tot = job.totals;
    const metrics = [];
    if (job.status === 'running' && pct !== null) metrics.push([t('task.mPct'), `${Math.floor(pct)}%`, 'm-pct']);
    metrics.push([t('task.mDown'), fmtNum(tot.downloaded), tot.downloaded ? 'm-ok' : '']);
    metrics.push([t('task.mSkip'), fmtNum(tot.skipped), '']);
    metrics.push([t('task.mFail'), fmtNum(tot.failed), tot.failed ? 'm-bad' : '']);
    metrics.push([t('task.mRec'), fmtNum(tot.records), '']);
    $('.task-metrics', el).innerHTML = metrics.map(([k, v, c]) => `<span class="${c}"><em>${esc(k)}</em><b>${v}</b></span>`).join('');

    const msgEl = $('.task-message', el);
    let msg = '';
    if (job.status === 'running' && p.message) msg = p.message;
    if (job.status === 'failed' && job.error) msg = job.error;
    msgEl.textContent = msg;
    msgEl.classList.toggle('error', job.status === 'failed');

    $('.task-results', el).innerHTML = job.targets.length > 1
      ? job.targets.map((tg, i) => {
        const r = job.results[i];
        if (r) {
          const tip = r.error || t('task.resultTip', { d: r.downloaded, s: r.skipped, f: r.failed, t: r.elapsed_seconds });
          return `<span class="result ${r.success ? 'ok' : 'bad'}" title="${esc(tip)}">${icon(r.success ? 'check' : 'x')}${esc(tg)}</span>`;
        }
        if (job.status === 'running' && i === job.current_index) return `<span class="result current"><span class="spinner"></span>${esc(tg)}</span>`;
        return `<span class="result pending">${esc(tg)}</span>`;
      }).join('')
      : '';

    const final = FINAL.has(job.status);
    $('.act-cancel', el).classList.toggle('hidden', final || job.cancel_requested);
    $('.act-retry', el).classList.toggle('hidden', !final);
    $('.act-delete', el).classList.toggle('hidden', !final);
    $('.act-open', el).classList.toggle('hidden', !job.results.some((r) => r.save_dir));
    $('.act-open', el).title = t('task.actOpen');
    $('.act-retry', el).title = t('task.actRetry');
    $('.act-cancel', el).title = t('task.actCancel');
    $('.act-delete', el).title = t('task.actDelete');
    $('.act-logs', el).title = job.log_count ? t('task.actLogsCount', { n: job.log_count }) : t('task.actLogs');
  }

  function upsertJob(job) {
    const prev = state.jobs.get(job.id);
    if (prev && prev.seq > job.seq) return; // 过期快照
    state.jobs.set(job.id, job);
    renderJob(job);
    if (prev && !FINAL.has(prev.status) && FINAL.has(job.status)) {
      const tot = job.totals;
      const type = job.status === 'done' ? 'success' : job.status === 'failed' ? 'error' : 'warn';
      toast(t('toast.jobFinished', {
        status: statusLabel(job.status),
        title: job.title,
        d: tot.downloaded,
        s: tot.skipped,
        f: tot.failed,
      }), type, 6000);
    }
    renderTaskOverview();
  }

  function removeJob(id) {
    state.jobs.delete(id);
    state.logs.delete(id);
    taskList.querySelector(`[data-id="${id}"]`)?.remove();
    renderTaskOverview();
  }

  function renderTaskOverview() {
    const jobs = [...state.jobs.values()];
    const running = jobs.filter((j) => j.status === 'running').length;
    const queued = jobs.filter((j) => j.status === 'queued').length;
    const sum = (k) => jobs.reduce((a, j) => a + (j.totals?.[k] || 0), 0);
    const badge = $('#badge-running');
    badge.textContent = running + queued;
    badge.classList.toggle('hidden', running + queued === 0);
    $('#stats-bar').innerHTML = [
      [t('tasks.statActive'), `${running}<span style="color:var(--text-3);font-weight:500"> ${esc(t('tasks.statQueued', { n: queued }))}</span>`, 'var(--accent)'],
      [t('tasks.statDownloaded'), fmtNum(sum('downloaded')), 'var(--success)'],
      [t('tasks.statSkipped'), fmtNum(sum('skipped')), 'var(--text-3)'],
      [t('tasks.statFailed'), fmtNum(sum('failed')), 'var(--danger)'],
      [t('tasks.statApi'), fmtNum(sum('api_calls')), 'var(--info)'],
    ].map(([k, v, c]) => `<div class="metric"><div class="metric-label"><i style="background:${c}"></i>${esc(k)}</div><div class="metric-value">${v}</div></div>`).join('');
    const visible = jobs.filter(jobMatchesFilter).length;
    $('#task-empty').classList.toggle('hidden', visible > 0);
    taskList.classList.toggle('hidden', visible === 0);
    document.title = running ? `(${running}) X Downloader` : 'X Downloader';
  }

  function renderLogs(id, full = false, newLines = null) {
    const el = taskList.querySelector(`[data-id="${id}"]`);
    if (!el || $('.task-logs', el).classList.contains('hidden')) return;
    const box = $('.log-box', el);
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    const line = (l) => `<div class="log-line ${esc(l.level)}"><span class="t">${fmtClock(l.t)}</span>${esc(l.msg)}</div>`;
    if (full) {
      const arr = state.logs.get(id) || [];
      box.innerHTML = arr.length ? arr.map(line).join('') : `<div class="log-empty">${esc(t('task.logEmpty'))}</div>`;
    } else if (newLines) {
      $('.log-empty', box)?.remove();
      box.insertAdjacentHTML('beforeend', newLines.map(line).join(''));
    }
    while (box.childElementCount > 3000) box.firstElementChild.remove();
    if (full || nearBottom) box.scrollTop = box.scrollHeight;
  }

  $('#task-filter').addEventListener('change', (e) => {
    state.taskFilter = e.detail;
    state.jobs.forEach((j) => renderJob(j));
    renderTaskOverview();
  });
  $('#btn-clear').addEventListener('click', async () => {
    try {
      const r = await api('/api/tasks/clear', { method: 'POST' });
      [...state.jobs.values()].filter((j) => FINAL.has(j.status)).forEach((j) => removeJob(j.id));
      toast(t('toast.clearedTasks', { n: r.removed }));
    } catch (e) { toast(e.message, 'error'); }
  });

  setInterval(() => {
    $$('.elapsed').forEach((s) => {
      if (s.dataset.end) return;
      s.textContent = fmtDur(Date.now() / 1000 - Number(s.dataset.start));
    });
  }, 1000);

  // ------------------------------------------------------------------ SSE
  function connectEvents() {
    const es = new EventSource('/api/events');
    es.onopen = () => { state.connState = 'live'; renderConn(); };
    es.onerror = () => { state.connState = 'retry'; renderConn(); };
    es.addEventListener('snapshot', (e) => {
      const jobs = JSON.parse(e.data);
      const ids = new Set(jobs.map((j) => j.id));
      [...state.jobs.keys()].filter((id) => !ids.has(id)).forEach(removeJob);
      jobs.forEach((j) => { state.jobs.set(j.id, j); renderJob(j); });
      state.logs.clear();
      $$('.task-logs').forEach((d) => d.classList.add('hidden'));
      $$('.act-logs.active').forEach((b) => b.classList.remove('active'));
      renderTaskOverview();
    });
    es.addEventListener('job', (e) => upsertJob(JSON.parse(e.data)));
    es.addEventListener('remove', (e) => removeJob(JSON.parse(e.data).id));
    es.addEventListener('log', (e) => {
      const { job_id: id, lines } = JSON.parse(e.data);
      const arr = state.logs.get(id);
      if (arr) { arr.push(...lines); if (arr.length > 3000) arr.splice(0, arr.length - 3000); }
      renderLogs(id, false, arr ? lines : null);
    });
  }

  // ------------------------------------------------------------------ gallery
  const G = state.gallery;
  async function openFolder(path) {
    try { await api('/api/open-folder', { method: 'POST', body: { path } }); } catch (e) { toast(e.message, 'error'); }
  }

  function setGalleryMode(inFolder) {
    $('#crumb-sep').classList.toggle('hidden', !inFolder);
    $('#crumb-folder').classList.toggle('hidden', !inFolder);
    $('#gallery-kind').classList.toggle('hidden', !inFolder);
    $('#gallery-search-box').classList.toggle('hidden', !inFolder);
    $('#folder-grid').classList.toggle('hidden', inFolder);
    $('#media-grid').classList.toggle('hidden', !inFolder);
    if (!inFolder) $('#gallery-more').classList.add('hidden');
  }

  function renderGalleryFolders(data) {
    const grid = $('#folder-grid');
    $('#gallery-sub').textContent = t('gallery.foldersCount', { n: data.folders.length });
    $('#gallery-sub').title = data.root;
    grid.innerHTML = data.folders.map((f) => `
      <div class="folder" data-folder="${esc(f.name)}">
        ${f.cover
          ? `<div class="folder-cover"><img loading="lazy" src="${thumbUrl(f.name, f.cover)}" alt="" /></div>`
          : `<div class="folder-cover placeholder"><div class="ph"><span class="ph-icon">${icon(f.videos ? 'video' : 'file')}</span>${esc(f.videos ? t('gallery.videosCount', { n: fmtNum(f.videos) }) : t('gallery.docsCount', { n: fmtNum(f.docs) }))}</div></div>`}
        <div class="folder-info">
          <div class="folder-name" title="${esc(f.name)}">${esc(f.name)}</div>
          <div class="folder-meta">
            ${f.images ? `<span>${icon('image')}${fmtNum(f.images)}</span>` : ''}
            ${f.videos ? `<span>${icon('video')}${fmtNum(f.videos)}</span>` : ''}
            ${f.docs ? `<span>${icon('file')}${fmtNum(f.docs)}</span>` : ''}
          </div>
        </div>
      </div>`).join('');
    $('#gallery-empty').classList.toggle('hidden', data.folders.length > 0);
  }

  async function loadGallery() {
    if (G.folder) return loadFolder(true);
    setGalleryMode(false);
    try {
      const data = await api('/api/gallery');
      G.foldersData = data;
      renderGalleryFolders(data);
    } catch (e) { toast(e.message, 'error'); }
  }

  $('#folder-grid').addEventListener('click', (e) => {
    const card = e.target.closest('.folder');
    if (!card) return;
    G.folder = card.dataset.folder; G.q = ''; $('#gallery-search').value = '';
    loadFolder(true);
  });

  async function loadFolder(reset) {
    if (reset) { G.offset = 0; G.items = []; $('#media-grid').innerHTML = ''; }
    setGalleryMode(true);
    $('#crumb-folder').textContent = G.folder;
    const grid = $('#media-grid');
    try {
      const qs = new URLSearchParams({ offset: G.offset, limit: 60, kind: G.kind, q: G.q });
      const data = await api(`/api/gallery/${encodeURIComponent(G.folder)}?${qs}`);
      G.total = data.total;
      const start = G.items.length;
      G.items.push(...data.items);
      G.offset += data.items.length;
      $('#gallery-sub').textContent = t('gallery.filesCount', { n: fmtNum(data.total) });
      grid.insertAdjacentHTML('beforeend', data.items.map((it, i) => tileHtml(it, start + i)).join(''));
      $$('img:not([data-bound]), video:not([data-bound])', grid).forEach((m) => {
        m.dataset.bound = '1';
        const done = () => { m.classList.add('loaded'); m.closest('.tile')?.classList.add('ready'); };
        if (m.tagName === 'IMG') {
          if (m.complete && m.naturalWidth) done();
          else { m.addEventListener('load', done, { once: true }); m.addEventListener('error', done, { once: true }); }
        } else {
          m.addEventListener('loadeddata', done, { once: true });
          m.addEventListener('error', done, { once: true });
        }
      });
      $('#gallery-more').classList.toggle('hidden', G.offset >= G.total);
      $('#gallery-empty').classList.toggle('hidden', G.total > 0);
    } catch (e) { toast(e.message, 'error'); }
  }

  function tileHtml(it, idx) {
    const cap = `<div class="tile-cap">${esc(it.name)}</div>`;
    if (it.type === 'image') return `<div class="tile" data-idx="${idx}"><img loading="lazy" decoding="async" src="${thumbUrl(G.folder, it.name)}" alt="" />${cap}</div>`;
    if (it.type === 'video') return `<div class="tile" data-idx="${idx}"><video preload="metadata" muted src="${mediaUrl(G.folder, it.name)}#t=0.1"></video><span class="tile-badge">${icon('video')}${esc(t('gallery.videoBadge'))}</span>${cap}</div>`;
    return `<div class="tile doc" data-idx="${idx}">${icon('file')}<div class="doc-name">${esc(it.name)}</div><div class="doc-size">${fmtSize(it.size)}</div></div>`;
  }

  $('#media-grid').addEventListener('click', (e) => {
    const tile = e.target.closest('.tile');
    if (tile) openLightbox(Number(tile.dataset.idx));
  });
  $('#gallery-more button').addEventListener('click', () => loadFolder(false));
  $('#crumb-gallery').addEventListener('click', () => { G.folder = null; loadGallery(); });
  $('#btn-gallery-refresh').addEventListener('click', () => loadGallery());
  $('#btn-gallery-open').addEventListener('click', () => openFolder(G.folder || ''));
  $('#gallery-kind').addEventListener('change', (e) => { G.kind = e.detail; loadFolder(true); });
  let searchTimer;
  $('#gallery-search').addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { G.q = e.target.value.trim(); loadFolder(true); }, 300);
  });

  // lightbox
  let lbIdx = -1;
  async function openLightbox(idx) {
    const it = G.items[idx];
    if (!it) return;
    lbIdx = idx;
    const url = mediaUrl(G.folder, it.name);
    const stage = $('#lb-stage');
    if (it.type === 'image') stage.innerHTML = `<img src="${url}" alt="" />`;
    else if (it.type === 'video') stage.innerHTML = `<video src="${url}" controls autoplay></video>`;
    else {
      stage.innerHTML = `<pre>${esc(t('lb.loading'))}</pre>`;
      try {
        const txt = await (await fetch(url)).text();
        stage.innerHTML = `<pre>${esc(txt.length > 200000 ? `${txt.slice(0, 200000)}\n\n${t('lb.truncated')}` : txt)}</pre>`;
      } catch (_) { stage.innerHTML = `<pre>${esc(t('lb.readFail'))}</pre>`; }
    }
    $('#lb-caption').textContent = `${idx + 1} / ${G.total}  ·  ${it.name}  ·  ${fmtSize(it.size)}`;
    $('#lightbox').classList.remove('hidden');
  }
  function closeLightbox() { $('#lightbox').classList.add('hidden'); $('#lb-stage').innerHTML = ''; lbIdx = -1; }
  async function stepLightbox(d) {
    const n = lbIdx + d;
    if (n < 0) return;
    if (n >= G.items.length && G.offset < G.total) await loadFolder(false);
    if (n < G.items.length) openLightbox(n);
  }
  $('#lb-close').addEventListener('click', closeLightbox);
  $('#lb-prev').addEventListener('click', () => stepLightbox(-1));
  $('#lb-next').addEventListener('click', () => stepLightbox(1));
  $('#lightbox').addEventListener('click', (e) => { if (e.target.id === 'lightbox') closeLightbox(); });
  document.addEventListener('keydown', (e) => {
    if ($('#lightbox').classList.contains('hidden')) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowLeft') stepLightbox(-1);
    if (e.key === 'ArrowRight') stepLightbox(1);
  });

  // ------------------------------------------------------------------ settings
  const sform = $('#settings-form');
  const usersBox = $('#users-input');
  const usersInput = $('input', usersBox);

  function renderUsers() {
    $$('.chip', usersBox).forEach((el) => el.remove());
    state.users.forEach((u, i) => {
      const chip = document.createElement('span');
      chip.className = 'chip';
      chip.innerHTML = `${esc(u)}<button type="button" title="${esc(t('settings.removeUser'))}">${icon('x')}</button>`;
      $('button', chip).addEventListener('click', (e) => { e.stopPropagation(); state.users.splice(i, 1); renderUsers(); updateDirty(); });
      usersBox.insertBefore(chip, usersInput);
    });
  }
  function commitUserInput() {
    const added = splitList(usersInput.value).map((u) => u.replace(/^@/, ''));
    added.forEach((u) => { if (!state.users.includes(u)) state.users.push(u); });
    usersInput.value = '';
    if (added.length) { renderUsers(); updateDirty(); }
  }
  usersInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',' || e.key === '，') { e.preventDefault(); commitUserInput(); }
    if (e.key === 'Backspace' && !usersInput.value && state.users.length) { state.users.pop(); renderUsers(); updateDirty(); }
  });
  usersInput.addEventListener('blur', commitUserInput);
  usersBox.addEventListener('click', () => usersInput.focus());

  function collectSettings() {
    return {
      cookie: sform.cookie.value.trim(),
      users: [...state.users],
      mode: segValue($('#set-mode')) || 'media',
      save_path: sform.save_path.value.trim(),
      advanced: {
        time_range: sform.time_range.value.trim(),
        has_video: sform.has_video.checked,
        image_format: segValue($('#set-format')) || 'orig',
        skip_downloaded: sform.skip_downloaded.checked,
        md_output: sform.md_output.checked,
        media_count_limit: Number(sform.media_count_limit.value) || 0,
        concurrency: Number(sform.concurrency.value) || 8,
        proxy: sform.proxy.value.trim(),
        wait_on_rate_limit: sform.wait_on_rate_limit.checked,
        log_output: sform.log_output.checked,
      },
    };
  }
  const isSettingsDirty = () => !!state.settingsSnapshot && JSON.stringify(collectSettings()) !== state.settingsSnapshot;
  function updateDirty() {
    const dirty = isSettingsDirty();
    $('#dirty-flag').classList.toggle('hidden', !dirty);
    $('#btn-save-settings').disabled = !dirty;
    $('#btn-reset-settings').disabled = !dirty;
  }
  sform.addEventListener('input', updateDirty);
  sform.addEventListener('change', updateDirty);

  function setVerify(ok, msg) {
    const vr = $('#verify-result');
    vr.className = `verify ${ok === null ? '' : ok ? 'ok' : 'bad'}`;
    vr.innerHTML = ok === null ? `<span class="spinner"></span><span>${esc(msg)}</span>` : `${icon(ok ? 'check-circle' : 'x-circle')}<span>${esc(msg)}</span>`;
  }

  function renderVerifyState() {
    const vs = state.verifyState;
    if (!vs) return;
    if (vs.mode === 'loading') setVerify(null, t('settings.verifying'));
    else if (vs.mode === 'status') setVerify(vs.status.ok, formatCookieStatus(vs.status));
    else if (vs.mode === 'verified') setVerify(true, t('settings.verifyOk', { user: vs.user }));
    else setVerify(vs.ok, vs.msg);
  }

  function fillSettings() {
    const c = state.cfg?.config;
    if (!c) return;
    $('#settings-path').textContent = state.cfg.config_path;
    sform.cookie.value = c.cookie;
    setSeg($('#set-mode'), c.mode);
    sform.save_path.value = c.save_path;
    const a = c.advanced;
    setSeg($('#set-format'), a.image_format);
    ['time_range', 'proxy'].forEach((k) => { sform[k].value = a[k] ?? ''; });
    sform.concurrency.value = a.concurrency;
    syncRange();
    sform.media_count_limit.value = a.media_count_limit;
    ['has_video', 'skip_downloaded', 'md_output', 'wait_on_rate_limit', 'log_output'].forEach((k) => { sform[k].checked = !!a[k]; });
    state.users = [...c.users];
    renderUsers();
    state.settingsSnapshot = JSON.stringify(collectSettings());
    updateDirty();
    state.verifyState = { mode: 'status', status: state.cfg.cookie_status };
    renderVerifyState();
    if (state.cfg.thumb_cache) renderThumbCache(state.cfg.thumb_cache);
  }

  function renderThumbCache(info) {
    const files = Number(info?.files || 0);
    const bytes = Number(info?.bytes || 0);
    $('#thumb-cache-info').textContent = files
      ? t('settings.thumbStats', { files: fmtNum(files), size: fmtSize(bytes) })
      : t('settings.thumbEmpty');
    $('#btn-clear-thumbs').disabled = files === 0;
  }

  async function loadThumbCache() {
    try {
      const info = await api('/api/cache/thumbs');
      if (state.cfg) state.cfg.thumb_cache = info;
      renderThumbCache(info);
    } catch (_) { /* ignore */ }
  }
  const syncRange = () => {
    const r = sform.concurrency;
    $('#concurrency-val').textContent = r.value;
    r.style.setProperty('--pct', `${((r.value - r.min) / (r.max - r.min)) * 100}%`);
  };
  sform.concurrency.addEventListener('input', syncRange);

  $('#btn-reset-settings').addEventListener('click', fillSettings);
  $('#btn-save-settings').addEventListener('click', async () => {
    commitUserInput();
    const body = collectSettings();
    if (body.advanced.time_range && !/^(\d{4}-\d{2}-\d{2})?:(\d{4}-\d{2}-\d{2})?$/.test(body.advanced.time_range)) {
      toast(t('toast.invalidTimeRange'), 'warn');
      return;
    }
    try {
      state.cfg = await api('/api/config', { method: 'PUT', body });
      renderStatus(); renderEffectiveOpts(); fillSettings();
      toast(t('toast.settingsSaved'), 'success');
    } catch (e) { toast(e.message, 'error'); }
  });
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's' && currentView() === 'settings') {
      e.preventDefault();
      if (isSettingsDirty()) $('#btn-save-settings').click();
    }
  });
  window.addEventListener('beforeunload', (e) => { if (isSettingsDirty()) { e.preventDefault(); e.returnValue = ''; } });

  $('#cookie-file').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const content = await file.text();
      state.cfg = await api('/api/cookie/upload', { method: 'POST', body: { content, filename: 'cookies.txt' } });
      renderStatus(); fillSettings();
      toast(t('toast.cookieUploaded'), 'success');
    } catch (err) { toast(err.message, 'error'); }
    e.target.value = '';
  });

  $('#btn-verify').addEventListener('click', async () => {
    state.verifyState = { mode: 'loading' };
    renderVerifyState();
    try {
      const r = await api('/api/cookie/verify', {
        method: 'POST',
        body: {
          cookie: sform.cookie.value.trim(),
          proxy: sform.proxy.value.trim(),
        },
      });
      if (r.ok && r.profile?.screen_name) {
        state.verifyState = { mode: 'verified', user: r.profile.screen_name };
      } else {
        state.verifyState = { mode: 'raw', ok: r.ok, msg: r.message };
      }
      renderVerifyState();
    } catch (e) {
      state.verifyState = { mode: 'raw', ok: false, msg: e.message };
      renderVerifyState();
    }
  });

  $('#btn-clear-thumbs').addEventListener('click', async () => {
    const btn = $('#btn-clear-thumbs');
    btn.disabled = true;
    try {
      const r = await api('/api/cache/thumbs/clear', { method: 'POST' });
      if (state.cfg) state.cfg.thumb_cache = r.thumb_cache;
      renderThumbCache(r.thumb_cache);
      toast(t('toast.cacheCleared', { files: fmtNum(r.cleared_files), size: fmtSize(r.cleared_bytes) }), 'success');
    } catch (e) {
      toast(t('toast.cacheClearFail', { msg: e.message }), 'error');
      loadThumbCache();
    }
  });

  function setThumbHelp(open) {
    $('#thumb-help-pop').classList.toggle('hidden', !open);
    $('#btn-thumb-help').classList.toggle('active', open);
    $('#btn-thumb-help').setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  $('#btn-thumb-help').addEventListener('click', (e) => {
    e.stopPropagation();
    setThumbHelp($('#thumb-help-pop').classList.contains('hidden'));
  });
  document.addEventListener('click', (e) => {
    if (!$('#thumb-help-pop').classList.contains('hidden') && !e.target.closest('.help-wrap')) {
      setThumbHelp(false);
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !$('#thumb-help-pop').classList.contains('hidden')) {
      setThumbHelp(false);
    }
  });

  // ------------------------------------------------------------------ boot
  applyLang(I18N.getLang(), false);
  renderConn();
  setType('user_media');
  renderTaskOverview();
  loadConfig();
  connectEvents();
  const initial = location.hash.replace('#', '');
  if (['new', 'tasks', 'gallery', 'settings'].includes(initial)) showView(initial);
})();
