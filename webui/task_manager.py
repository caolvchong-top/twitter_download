"""
WebUI 任务调度器：把 core 中的下载函数包装成可排队、可取消、可实时推送进度的 Job。
"""

import asyncio
import dataclasses
import itertools
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Set

from core import (
    AppConfig,
    DownloadProgress,
    TaskResult,
    TwitterAPI,
    download_replies,
    download_search,
    download_tweet,
    download_user_media,
    download_user_profile,
    download_user_text,
)


JOB_TYPES = {
    'user_media': '用户媒体',
    'tweet': '单条推文',
    'search': '标签 / 搜索',
    'replies': '评论区',
    'user_text': '纯文本推文',
    'profile': '主页资料',
}

FINAL_STATUSES = ('done', 'partial', 'failed', 'cancelled')
_SEQ = itertools.count(1)  # 全局递增序号：前端据此丢弃过期的任务快照


def _split_targets(raw: Any) -> List[str]:
    if isinstance(raw, str):
        parts = raw.replace('\n', ',').replace('，', ',').split(',')
    elif isinstance(raw, list):
        parts = [str(x) for x in raw]
    else:
        parts = []
    return [p.strip() for p in parts if p and p.strip()]


@dataclasses.dataclass
class Job:
    id: str
    type: str
    params: Dict[str, Any]
    targets: List[str]
    config: AppConfig
    title: str = ''
    status: str = 'queued'  # queued | running | done | partial | failed | cancelled
    created_at: float = dataclasses.field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    current_index: int = 0
    progress: Optional[Dict[str, Any]] = None
    results: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    error: str = ''
    logs: Deque[Dict[str, Any]] = dataclasses.field(default_factory=lambda: deque(maxlen=3000))
    cancel_event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    runner: Optional[asyncio.Task] = None

    def totals(self) -> Dict[str, int]:
        t = {'downloaded': 0, 'skipped': 0, 'failed': 0, 'records': 0, 'api_calls': 0}
        for r in self.results:
            t['downloaded'] += r.get('downloaded', 0)
            t['skipped'] += r.get('skipped', 0)
            t['failed'] += r.get('failed', 0)
            t['records'] += r.get('records_count', 0)
            t['api_calls'] += r.get('api_calls', 0)
        if self.status == 'running' and self.progress and len(self.results) <= self.current_index:
            p = self.progress
            t['downloaded'] += p.get('downloaded', 0)
            t['skipped'] += p.get('skipped', 0)
            t['failed'] += p.get('failed', 0)
            t['records'] += p.get('items_found', 0)
            t['api_calls'] += p.get('api_calls', 0)
        return t

    def summary(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'seq': next(_SEQ),
            'type': self.type,
            'type_label': JOB_TYPES.get(self.type, self.type),
            'title': self.title,
            'params': self.params,
            'targets': self.targets,
            'status': self.status,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
            'current_index': self.current_index,
            'progress': self.progress,
            'results': self.results,
            'totals': self.totals(),
            'error': self.error,
            'cancel_requested': self.cancel_event.is_set(),
            'log_count': len(self.logs),
        }


class TaskManager:
    def __init__(self, max_parallel: int = 1):
        self.jobs: Dict[str, Job] = {}
        self._order: List[str] = []
        self._counter = itertools.count(1)
        self._sem = asyncio.Semaphore(max(1, max_parallel))
        self._subscribers: Set[asyncio.Queue] = set()
        self._dirty: Set[str] = set()
        self._pending_logs: Dict[str, List[Dict[str, Any]]] = {}
        self._flusher: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ pub/sub
    def start(self):
        if self._flusher is None:
            self._flusher = asyncio.create_task(self._flush_loop())

    async def stop(self):
        for job in self.jobs.values():
            job.cancel_event.set()
        if self._flusher:
            self._flusher.cancel()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers.discard(q)

    def _broadcast(self, event: str, data: Any):
        for q in list(self._subscribers):
            try:
                q.put_nowait((event, data))
            except asyncio.QueueFull:
                # 慢客户端：丢弃事件，前端可通过刷新获取快照
                pass

    async def _flush_loop(self):
        """节流推送：进度最多每 300ms 推一次，日志批量推送。"""
        while True:
            await asyncio.sleep(0.3)
            self._flush()

    def _flush(self):
        if self._pending_logs:
            pending, self._pending_logs = self._pending_logs, {}
            for job_id, lines in pending.items():
                self._broadcast('log', {'job_id': job_id, 'lines': lines})
        if self._dirty:
            dirty, self._dirty = self._dirty, set()
            for job_id in dirty:
                job = self.jobs.get(job_id)
                if job:
                    self._broadcast('job', job.summary())

    def _mark(self, job: Job, immediate: bool = False):
        self._dirty.add(job.id)
        if immediate:
            self._flush()

    def _log(self, job: Job, msg: str, level: str = 'info'):
        entry = {'t': time.time(), 'msg': str(msg), 'level': level}
        job.logs.append(entry)
        self._pending_logs.setdefault(job.id, []).append(entry)

    # ------------------------------------------------------------------ CRUD
    def list_jobs(self) -> List[Dict[str, Any]]:
        return [self.jobs[jid].summary() for jid in reversed(self._order) if jid in self.jobs]

    def get_logs(self, job_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        job = self.jobs.get(job_id)
        if not job:
            return []
        return list(job.logs)[-limit:]

    def create_job(self, job_type: str, params: Dict[str, Any], config: AppConfig) -> Job:
        if job_type not in JOB_TYPES:
            raise ValueError(f'未知任务类型: {job_type}')

        params = dict(params or {})
        if job_type == 'search':
            tag = str(params.get('tag', '')).strip()
            flt = str(params.get('filter', '')).strip()
            if not tag and not flt:
                raise ValueError('标签和高级搜索条件不能同时为空')
            targets = [f'{tag} {flt}'.strip()]
        else:
            targets = _split_targets(params.get('targets'))
            if job_type in ('user_media', 'user_text', 'profile'):
                targets = [t.lstrip('@') for t in targets]
            if not targets:
                raise ValueError('请至少输入一个目标（用户名 / 推文链接）')

        # 去重但保持顺序
        targets = list(dict.fromkeys(targets))
        job_id = f'{next(self._counter):04d}'
        title = f'{JOB_TYPES[job_type]} · ' + (', '.join(targets[:3]) + (f' 等 {len(targets)} 个' if len(targets) > 3 else ''))
        job = Job(
            id=job_id,
            type=job_type,
            params=params,
            targets=targets,
            config=dataclasses.replace(config, users=list(config.users)),
            title=title,
        )
        self.jobs[job_id] = job
        self._order.append(job_id)
        job.runner = asyncio.create_task(self._run_job(job))
        self._log(job, f'任务已创建，共 {len(targets)} 个目标，等待执行…')
        self._mark(job, immediate=True)
        return job

    def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.status in FINAL_STATUSES:
            return False
        job.cancel_event.set()
        self._log(job, '已请求取消，正在停止…', 'warn')
        self._mark(job, immediate=True)
        if job.status == 'queued' and job.runner:
            job.runner.cancel()
        else:
            asyncio.create_task(self._force_cancel_later(job))
        return True

    async def _force_cancel_later(self, job: Job, delay: float = 15.0):
        await asyncio.sleep(delay)
        if job.status == 'running' and job.runner and not job.runner.done():
            self._log(job, '任务未能及时响应取消信号，强制终止。', 'warn')
            job.runner.cancel()

    def remove_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.status not in FINAL_STATUSES:
            return False
        del self.jobs[job_id]
        self._order = [j for j in self._order if j != job_id]
        self._broadcast('remove', {'id': job_id})
        return True

    def clear_finished(self) -> int:
        ids = [jid for jid, j in self.jobs.items() if j.status in FINAL_STATUSES]
        for jid in ids:
            self.remove_job(jid)
        return len(ids)

    def retry_job(self, job_id: str, config: AppConfig) -> Job:
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError('任务不存在')
        params = dict(job.params)
        return self.create_job(job.type, params, config)

    # ------------------------------------------------------------------ runner
    async def _run_job(self, job: Job):
        try:
            async with self._sem:
                if job.cancel_event.is_set():
                    raise asyncio.CancelledError()
                job.status = 'running'
                job.started_at = time.time()
                self._mark(job, immediate=True)
                await self._execute(job)
        except asyncio.CancelledError:
            job.status = 'cancelled'
            self._log(job, '任务已取消。', 'warn')
        except Exception as e:  # noqa: BLE001
            job.status = 'failed'
            job.error = f'{type(e).__name__}: {e}'
            self._log(job, f'[异常] {job.error}', 'error')
        else:
            if job.cancel_event.is_set():
                job.status = 'cancelled'
            elif job.results and all(r.get('success') for r in job.results):
                job.status = 'done'
            elif any(r.get('success') for r in job.results):
                job.status = 'partial'
            else:
                job.status = 'failed'
                if not job.error:
                    errs = [r.get('error') for r in job.results if r.get('error')]
                    job.error = errs[0] if errs else '任务失败'
        finally:
            job.finished_at = time.time()
            if job.progress and job.progress.get('phase') not in ('done', 'error', 'cancelled'):
                job.progress['phase'] = 'cancelled' if job.status == 'cancelled' else job.progress.get('phase')
            t = job.totals()
            self._log(
                job,
                f'任务结束 [{job.status}] | 已下 {t["downloaded"]} | 跳过 {t["skipped"]} '
                f'| 失败 {t["failed"]} | 记录 {t["records"]} | API {t["api_calls"]}',
                'success' if job.status == 'done' else ('warn' if job.status in ('partial', 'cancelled') else 'error'),
            )
            self._mark(job, immediate=True)

    async def _execute(self, job: Job):
        cfg = job.config
        p = job.params

        cookie_str, ct0 = cfg.resolve_auth()
        api = TwitterAPI(
            cookie_str,
            ct0,
            proxy=cfg.resolved_proxy(),
            wait_on_rate_limit=cfg.wait_on_rate_limit,
        )

        def on_progress(prog: DownloadProgress):
            job.progress = prog.to_dict()
            self._mark(job)

        def on_log(msg: str):
            level = 'error' if '[错误]' in msg or '失败' in msg else ('warn' if '限流' in msg or '跳过' in msg else 'info')
            self._log(job, msg, level)

        common = dict(api=api, on_progress=on_progress, on_log=on_log, cancel_event=job.cancel_event)

        try:
            for idx, target in enumerate(job.targets):
                if job.cancel_event.is_set():
                    break
                job.current_index = idx
                job.progress = None
                self._log(job, f'—— [{idx + 1}/{len(job.targets)}] 开始处理: {target}')
                self._mark(job, immediate=True)

                try:
                    res = await self._run_one(job.type, cfg, target, p, common)
                except asyncio.CancelledError:
                    if job.cancel_event.is_set():
                        res = TaskResult(task=target, success=False, error='已取消')
                    else:
                        raise
                except Exception as e:  # noqa: BLE001 单个目标异常不影响后续目标
                    res = TaskResult(task=target, success=False, error=f'{type(e).__name__}: {e}')

                job.results.append({**res.to_dict(), 'target': target})
                if res.success:
                    self._log(
                        job,
                        f'完成 {target} | 已下 {res.downloaded} | 跳过 {res.skipped} | 失败 {res.failed} '
                        f'| 记录 {res.records_count} | 耗时 {res.elapsed_seconds}s',
                        'success',
                    )
                elif res.error and res.error != '已取消':
                    self._log(job, f'失败 {target}: {res.error}', 'error')
                self._mark(job, immediate=True)
        finally:
            await api.close()

    @staticmethod
    async def _run_one(job_type: str, cfg: AppConfig, target: str, p: Dict[str, Any], common: dict) -> TaskResult:
        def _tr():
            v = p.get('time_range')
            return None if v is None else str(v).strip()

        if job_type == 'user_media':
            return await download_user_media(cfg, target, mode=p.get('mode') or None, time_range=_tr(), **common)
        if job_type == 'tweet':
            return await download_tweet(cfg, target, **common)
        if job_type == 'search':
            limit = int(p.get('limit') or 100)
            return await download_search(
                cfg,
                str(p.get('tag', '')).strip(),
                filter_query=str(p.get('filter', '')).strip(),
                search_mode=p.get('search_mode') or 'media',
                limit=max(1, limit),
                **common,
            )
        if job_type == 'replies':
            return await download_replies(
                cfg,
                target,
                time_range=_tr() or '',
                media_down=bool(p.get('media_down', True)),
                **common,
            )
        if job_type == 'user_text':
            return await download_user_text(
                cfg, target, time_range=_tr(), include_retweet=bool(p.get('include_retweet', False)), **common,
            )
        if job_type == 'profile':
            return await download_user_profile(cfg, target, **common)
        raise ValueError(f'未知任务类型: {job_type}')
