import asyncio
from datetime import datetime
import os
import time
from typing import Callable, List, Optional

from .api import (
    TwitterAPI,
    TwitterAPIError,
    extract_media_from_tweet,
    extract_reply_from_entry,
    extract_text_record,
    parse_tweet_id_from_input,
    unwrap_tweet,
)
from .config import (
    AppConfig,
    MAX_TIMESTAMP_MS,
    MIN_TIMESTAMP_MS,
    parse_time_range,
    sanitize_filename,
)
from .downloader import AsyncMediaDownloader
from .exporters import (
    CSVExporter,
    MEDIA_CSV_HEADERS,
    MarkdownExporter,
    REPLY_CSV_HEADERS,
    SEARCH_TEXT_CSV_HEADERS,
    TEXT_CSV_HEADERS,
)
from .models import DownloadProgress, MediaItem, TaskResult


ProgressCallback = Optional[Callable[[DownloadProgress], None]]
LogCallback = Optional[Callable[[str], None]]


def _emit_progress(cb: ProgressCallback, progress: DownloadProgress):
    if cb:
        cb(progress)


def _emit_log(cb: LogCallback, msg: str):
    if cb:
        cb(msg)


def _make_api(config: AppConfig, override_cookie: str = '', override_proxy: str = '') -> TwitterAPI:
    cookie_str, ct0 = config.resolve_auth(override_cookie)
    proxy = override_proxy.strip() if override_proxy and override_proxy.strip() else config.resolved_proxy()
    return TwitterAPI(
        cookie_str,
        ct0,
        proxy=proxy,
        wait_on_rate_limit=config.wait_on_rate_limit,
    )


def _make_rate_limit_handler(progress: DownloadProgress, on_progress: ProgressCallback, on_log: LogCallback):
    def _handler(reset_ts: int, wait_secs: int):
        reset_str = time.strftime('%H:%M:%S', time.localtime(reset_ts))
        progress.phase = 'waiting_rate_limit'
        progress.rate_limit_reset = reset_ts
        progress.message = f'触发限流，等待至 {reset_str}（约 {wait_secs} 秒）'
        _emit_log(on_log, progress.message)
        _emit_progress(on_progress, progress)

    return _handler


async def download_user_media(
    config: AppConfig,
    username: str,
    *,
    mode: Optional[str] = None,
    time_range: Optional[str] = None,
    max_pages: Optional[int] = None,
    api: Optional[TwitterAPI] = None,
    on_progress: ProgressCallback = None,
    on_log: LogCallback = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> TaskResult:
    """下载指定用户的媒体文件，mode 可选: media / retweet / highlights / likes。"""
    t0 = time.time()
    use_mode = mode or config.mode or 'media'
    use_range = config.time_range if time_range is None else time_range
    is_likes = use_mode == 'likes'
    start_ms, end_ms = (MIN_TIMESTAMP_MS, MAX_TIMESTAMP_MS) if is_likes else parse_time_range(use_range)

    clean_user = username.strip().lstrip('@')
    progress = DownloadProgress(task=f'user:{clean_user}({use_mode})', phase='init')
    own_api = api is None
    if own_api:
        api = _make_api(config)
    api_calls_before = api.api_calls

    csv_paths: List[str] = []
    md_paths: List[str] = []
    save_dir = ''

    try:
        rl_cb = _make_rate_limit_handler(progress, on_progress, on_log)
        profile = await api.get_user_profile(clean_user, on_rate_limit=rl_cb, cancel_event=cancel_event)
        save_dir = os.path.join(config.resolved_save_root(), profile.screen_name)
        os.makedirs(save_dir, exist_ok=True)

        _emit_log(
            on_log,
            f'用户: {profile.name} (@{profile.screen_name}) | ID: {profile.rest_id} '
            f'| 总推数: {profile.statuses_count} | 媒体推数: {profile.media_count}',
        )

        run_tag = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        csv_path = os.path.join(save_dir, f'{profile.screen_name}-{run_tag}.csv')
        csv_exp = None
        if not is_likes:
            csv_exp = CSVExporter(
                csv_path,
                MEDIA_CSV_HEADERS,
                preamble_rows=[
                    [profile.name, profile.screen_name],
                    ['Tweet Range : ' + (use_range or 'unlimited')],
                    ['Save Path : ' + save_dir],
                ],
            )
            csv_paths.append(csv_path)

        md_exp = None
        if config.md_output:
            md_exp = MarkdownExporter(
                save_dir,
                profile.name,
                profile.screen_name,
                use_range,
                is_likes=is_likes,
                media_count_limit=config.media_count_limit,
            )

        def _on_item_done(item: MediaItem, status: str):
            if status == 'downloaded':
                progress.downloaded += 1
                if csv_exp is not None:
                    csv_exp.write_media(item)
            elif status == 'skipped':
                progress.skipped += 1
            else:
                progress.failed += 1
            progress.api_calls = api.api_calls - api_calls_before
            _emit_progress(on_progress, progress)

        try:
            async with AsyncMediaDownloader(
                save_dir,
                concurrency=config.concurrency,
                proxy=config.resolved_proxy(),
                skip_downloaded=config.skip_downloaded,
                on_item_done=_on_item_done,
                on_log=on_log if config.log_output else None,
                cancel_event=cancel_event,
            ) as downloader:
                cursor = ''
                first_page = True
                while True:
                    if cancel_event and cancel_event.is_set():
                        progress.phase = 'cancelled'
                        break
                    if max_pages is not None and progress.pages_fetched >= max_pages:
                        break

                    progress.phase = 'fetching'
                    progress.api_calls = api.api_calls - api_calls_before
                    _emit_progress(on_progress, progress)

                    raw_entries, next_cursor, is_done = await api.fetch_user_timeline_page(
                        profile,
                        mode=use_mode,
                        cursor=cursor,
                        first_page=first_page,
                        on_rate_limit=rl_cb,
                        cancel_event=cancel_event,
                    )
                    first_page = False
                    progress.pages_fetched += 1
                    progress.api_calls = api.api_calls - api_calls_before

                    out_of_range = False
                    for entry in raw_entries:
                        eid = entry.get('entryId', '')
                        if 'promoted-tweet' in eid:
                            continue

                        tweet_obj = None
                        if 'tweet' in eid:
                            container = entry.get('item') if use_mode == 'media' else entry.get('content')
                            tweet_obj = (container or {}).get('itemContent', {}).get('tweet_results', {}).get('result')
                        elif 'profile-conversation' in eid:
                            items = (entry.get('content') or {}).get('items') or []
                            if items:
                                tweet_obj = items[0].get('item', {}).get('itemContent', {}).get('tweet_results', {}).get('result')

                        if not tweet_obj:
                            continue

                        media_items = extract_media_from_tweet(
                            tweet_obj,
                            owner_screen_name=profile.screen_name,
                            owner_name=profile.name,
                            has_video=config.has_video,
                            image_format=config.image_format,
                            include_retweet=(use_mode == 'retweet'),
                            use_tweet_author=is_likes,
                            filename_style='user',
                        )
                        if not media_items:
                            # 即便推文无媒体，也检查时间是否早于起点以提前结束
                            from .api import extract_tweet_timestamp_msecs
                            ts = extract_tweet_timestamp_msecs(tweet_obj)
                            if not is_likes and ts is not None and ts < start_ms:
                                out_of_range = True
                                break
                            continue

                        ts = media_items[0].tweet_msecs
                        if not is_likes and ts < start_ms:
                            out_of_range = True
                            break
                        if not is_likes and ts > end_ms:
                            continue

                        progress.phase = 'downloading'
                        for item in media_items:
                            progress.items_found += 1
                            if md_exp is not None:
                                md_exp.write_media(item)
                            await downloader.submit(item)

                    _emit_progress(on_progress, progress)
                    if out_of_range or is_done or not next_cursor:
                        break
                    cursor = next_cursor

            if md_exp is not None:
                md_paths = list(md_exp.md_paths)
        finally:
            if csv_exp is not None:
                csv_exp.close()
            if md_exp is not None:
                md_exp.close()

        cancelled = bool(cancel_event and cancel_event.is_set())
        progress.phase = 'cancelled' if cancelled else 'done'
        progress.api_calls = api.api_calls - api_calls_before
        _emit_progress(on_progress, progress)
        return TaskResult(
            task=progress.task,
            success=not cancelled,
            save_dir=save_dir,
            downloaded=progress.downloaded,
            skipped=progress.skipped,
            failed=progress.failed,
            records_count=progress.items_found,
            api_calls=progress.api_calls,
            elapsed_seconds=round(time.time() - t0, 2),
            csv_paths=csv_paths,
            md_paths=md_paths,
        )
    except (TwitterAPIError, ValueError, FileNotFoundError) as e:
        progress.phase = 'error'
        progress.message = str(e)
        _emit_progress(on_progress, progress)
        _emit_log(on_log, f'[错误] {e}')
        return TaskResult(
            task=progress.task,
            success=False,
            save_dir=save_dir,
            downloaded=progress.downloaded,
            skipped=progress.skipped,
            failed=progress.failed,
            api_calls=api.api_calls - api_calls_before,
            elapsed_seconds=round(time.time() - t0, 2),
            csv_paths=csv_paths,
            md_paths=md_paths,
            error=str(e),
        )
    finally:
        if own_api:
            await api.close()


async def download_tweet(
    config: AppConfig,
    tweet_url_or_id: str,
    *,
    api: Optional[TwitterAPI] = None,
    on_progress: ProgressCallback = None,
    on_log: LogCallback = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> TaskResult:
    """快速下载单条推文中的所有原图 / 视频。"""
    t0 = time.time()
    tweet_id, _ = parse_tweet_id_from_input(tweet_url_or_id)
    if not tweet_id:
        return TaskResult(task='tweet', success=False, error=f'无法识别推文链接或 ID: {tweet_url_or_id}')

    progress = DownloadProgress(task=f'tweet:{tweet_id}', phase='fetching')
    own_api = api is None
    if own_api:
        api = _make_api(config)
    api_calls_before = api.api_calls
    save_dir = os.path.join(config.resolved_save_root(), 'tweets')

    try:
        rl_cb = _make_rate_limit_handler(progress, on_progress, on_log)
        focal_tweet, _, _, _ = await api.fetch_tweet_detail_page(
            tweet_id,
            on_rate_limit=rl_cb,
            cancel_event=cancel_event,
        )
        progress.pages_fetched = 1
        progress.api_calls = api.api_calls - api_calls_before

        if not focal_tweet:
            raise TwitterAPIError(f'未获取到推文 {tweet_id}（可能已删除、私密或无权查看）')

        media_items = extract_media_from_tweet(
            focal_tweet,
            has_video=config.has_video,
            image_format=config.image_format,
            use_tweet_author=True,
            filename_style='tweet',
        )
        if not media_items:
            _emit_log(on_log, f'推文 {tweet_id} 不包含可下载的图片或视频。')
            progress.phase = 'done'
            _emit_progress(on_progress, progress)
            return TaskResult(
                task=progress.task,
                success=True,
                save_dir=save_dir,
                api_calls=progress.api_calls,
                elapsed_seconds=round(time.time() - t0, 2),
            )

        def _on_item_done(item: MediaItem, status: str):
            if status == 'downloaded':
                progress.downloaded += 1
            elif status == 'skipped':
                progress.skipped += 1
            else:
                progress.failed += 1
            _emit_progress(on_progress, progress)

        async with AsyncMediaDownloader(
            save_dir,
            concurrency=config.concurrency,
            proxy=config.resolved_proxy(),
            skip_downloaded=config.skip_downloaded,
            on_item_done=_on_item_done,
            on_log=on_log if config.log_output else None,
            cancel_event=cancel_event,
        ) as downloader:
            progress.phase = 'downloading'
            for item in media_items:
                progress.items_found += 1
                await downloader.submit(item)

        progress.phase = 'done'
        _emit_progress(on_progress, progress)
        return TaskResult(
            task=progress.task,
            success=True,
            save_dir=save_dir,
            downloaded=progress.downloaded,
            skipped=progress.skipped,
            failed=progress.failed,
            records_count=progress.items_found,
            api_calls=api.api_calls - api_calls_before,
            elapsed_seconds=round(time.time() - t0, 2),
        )
    except (TwitterAPIError, ValueError, FileNotFoundError) as e:
        progress.phase = 'error'
        progress.message = str(e)
        _emit_progress(on_progress, progress)
        _emit_log(on_log, f'[错误] {e}')
        return TaskResult(
            task=progress.task,
            success=False,
            save_dir=save_dir,
            api_calls=api.api_calls - api_calls_before,
            elapsed_seconds=round(time.time() - t0, 2),
            error=str(e),
        )
    finally:
        if own_api:
            await api.close()


async def download_search(
    config: AppConfig,
    tag: str = '',
    *,
    filter_query: str = '',
    search_mode: str = 'media',  # 'media' | 'media_latest' | 'text'
    limit: int = 100,
    api: Optional[TwitterAPI] = None,
    on_progress: ProgressCallback = None,
    on_log: LogCallback = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> TaskResult:
    """按 Tag 或高级搜索条件下载媒体或纯文本。"""
    t0 = time.time()
    query_str = f'{tag} {filter_query}'.strip()
    if not query_str:
        return TaskResult(task='search', success=False, error='搜索关键词或标签不能为空')

    is_text = search_mode == 'text'
    product = 'Media' if search_mode == 'media' else 'Latest'
    entries_per_page = 50 if product == 'Media' else 20
    max_pages = max(1, (limit + entries_per_page - 1) // entries_per_page)

    folder_name = sanitize_filename(tag or filter_query, allow_hash=True)
    save_dir = os.path.join(config.resolved_save_root(), folder_name)
    os.makedirs(save_dir, exist_ok=True)

    progress = DownloadProgress(task=f'search:{query_str}({search_mode})', phase='init')
    own_api = api is None
    if own_api:
        api = _make_api(config)
    api_calls_before = api.api_calls

    run_tag = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    csv_path = os.path.join(save_dir, f'{run_tag}-{search_mode}.csv')
    csv_headers = SEARCH_TEXT_CSV_HEADERS if is_text else MEDIA_CSV_HEADERS
    csv_paths = [csv_path]

    try:
        rl_cb = _make_rate_limit_handler(progress, on_progress, on_log)
        with CSVExporter(csv_path, csv_headers, preamble_rows=[[f'Run Time : {run_tag}']]) as csv_exp:
            if is_text:
                cursor = ''
                first_page = True
                for _ in range(max_pages):
                    if cancel_event and cancel_event.is_set():
                        break
                    progress.phase = 'fetching'
                    _emit_progress(on_progress, progress)
                    entries, next_cursor, is_done = await api.fetch_search_page(
                        query_str,
                        product='Latest',
                        cursor=cursor,
                        count=entries_per_page,
                        first_page=first_page,
                        on_rate_limit=rl_cb,
                        cancel_event=cancel_event,
                    )
                    first_page = False
                    progress.pages_fetched += 1
                    progress.api_calls = api.api_calls - api_calls_before

                    for entry in entries:
                        tweet_obj = entry.get('content', {}).get('itemContent', {}).get('tweet_results', {}).get('result')
                        rec = extract_text_record(tweet_obj, include_retweet=False)
                        if rec:
                            csv_exp.write_search_text(rec)
                            progress.items_found += 1

                    _emit_progress(on_progress, progress)
                    if is_done or not next_cursor:
                        break
                    cursor = next_cursor
            else:
                def _on_item_done(item: MediaItem, status: str):
                    if status == 'downloaded':
                        progress.downloaded += 1
                        csv_exp.write_media(item, full_saved_path=True)
                    elif status == 'skipped':
                        progress.skipped += 1
                    else:
                        progress.failed += 1
                    progress.api_calls = api.api_calls - api_calls_before
                    _emit_progress(on_progress, progress)

                async with AsyncMediaDownloader(
                    save_dir,
                    concurrency=config.concurrency,
                    proxy=config.resolved_proxy(),
                    skip_downloaded=config.skip_downloaded,
                    on_item_done=_on_item_done,
                    on_log=on_log if config.log_output else None,
                    cancel_event=cancel_event,
                ) as downloader:
                    cursor = ''
                    first_page = True
                    for _ in range(max_pages):
                        if cancel_event and cancel_event.is_set():
                            break
                        progress.phase = 'fetching'
                        _emit_progress(on_progress, progress)
                        entries, next_cursor, is_done = await api.fetch_search_page(
                            query_str,
                            product=product,
                            cursor=cursor,
                            count=entries_per_page,
                            first_page=first_page,
                            on_rate_limit=rl_cb,
                            cancel_event=cancel_event,
                        )
                        first_page = False
                        progress.pages_fetched += 1
                        progress.api_calls = api.api_calls - api_calls_before

                        for entry in entries:
                            container = entry.get('item') if product == 'Media' else entry.get('content')
                            tweet_obj = (container or {}).get('itemContent', {}).get('tweet_results', {}).get('result')
                            if not tweet_obj:
                                continue
                            media_items = extract_media_from_tweet(
                                tweet_obj,
                                has_video=config.has_video,
                                image_format=config.image_format,
                                use_tweet_author=True,
                                filename_style='search',
                                strip_trailing_tco=True,
                            )
                            progress.phase = 'downloading'
                            for item in media_items:
                                progress.items_found += 1
                                await downloader.submit(item)

                        _emit_progress(on_progress, progress)
                        if is_done or not next_cursor:
                            break
                        cursor = next_cursor

        cancelled = bool(cancel_event and cancel_event.is_set())
        progress.phase = 'cancelled' if cancelled else 'done'
        progress.api_calls = api.api_calls - api_calls_before
        _emit_progress(on_progress, progress)
        return TaskResult(
            task=progress.task,
            success=not cancelled,
            save_dir=save_dir,
            downloaded=progress.downloaded,
            skipped=progress.skipped,
            failed=progress.failed,
            records_count=progress.items_found,
            api_calls=progress.api_calls,
            elapsed_seconds=round(time.time() - t0, 2),
            csv_paths=csv_paths,
        )
    except (TwitterAPIError, ValueError, FileNotFoundError) as e:
        progress.phase = 'error'
        progress.message = str(e)
        _emit_progress(on_progress, progress)
        _emit_log(on_log, f'[错误] {e}')
        return TaskResult(
            task=progress.task,
            success=False,
            save_dir=save_dir,
            downloaded=progress.downloaded,
            skipped=progress.skipped,
            failed=progress.failed,
            api_calls=api.api_calls - api_calls_before,
            elapsed_seconds=round(time.time() - t0, 2),
            csv_paths=csv_paths,
            error=str(e),
        )
    finally:
        if own_api:
            await api.close()


async def download_replies(
    config: AppConfig,
    target: str,
    *,
    time_range: str = '',
    media_down: bool = True,
    min_replies: int = 1,
    min_faves: int = 0,
    min_retweets: int = 0,
    search_advanced: str = '',
    max_reply_pages: Optional[int] = None,
    api: Optional[TwitterAPI] = None,
    on_progress: ProgressCallback = None,
    on_log: LogCallback = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> TaskResult:
    """下载指定推文链接或指定用户推文的评论区（文本 CSV + 可选评论媒体）。"""
    t0 = time.time()
    tweet_id, user_from_url = parse_tweet_id_from_input(target) if not search_advanced else (None, '')
    is_single_tweet = bool(tweet_id)

    if search_advanced:
        folder_name = sanitize_filename(search_advanced, allow_hash=True)
        query_str = search_advanced
        user_name = ''
    elif is_single_tweet:
        folder_name = sanitize_filename(tweet_id, allow_hash=False)
        query_str = ''
        user_name = user_from_url
    else:
        user_name = target.strip().lstrip('@')
        folder_name = sanitize_filename(user_name, allow_hash=False)
        if time_range:
            since_t, until_t = [p.strip() for p in time_range.split(':')]
            query_str = (
                f'(from:{user_name}) min_replies:{min_replies} min_faves:{min_faves} '
                f'min_retweets:{min_retweets} until:{until_t} since:{since_t}'
            )
        else:
            query_str = (
                f'(from:{user_name}) min_replies:{min_replies} min_faves:{min_faves} '
                f'min_retweets:{min_retweets}'
            )

    save_dir = os.path.join(config.resolved_save_root(), folder_name)
    os.makedirs(save_dir, exist_ok=True)
    progress = DownloadProgress(task=f'reply:{target}', phase='init')

    own_api = api is None
    if own_api:
        api = _make_api(config)
    api_calls_before = api.api_calls

    run_tag = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    csv_path = os.path.join(save_dir, f'{run_tag}-Reply.csv')
    csv_paths = [csv_path]

    try:
        rl_cb = _make_rate_limit_handler(progress, on_progress, on_log)

        def _on_item_done(item: MediaItem, status: str):
            if status == 'downloaded':
                progress.downloaded += 1
            elif status == 'skipped':
                progress.skipped += 1
            else:
                progress.failed += 1
            progress.api_calls = api.api_calls - api_calls_before
            _emit_progress(on_progress, progress)

        async def _crawl_one_tweet_replies(tid: str, owner_sn: str, csv_exp: CSVExporter, downloader: AsyncMediaDownloader):
            parent_url = f'https://x.com/{owner_sn or "i/web"}/status/{tid}'
            _cursor = ''
            pages = 0
            while True:
                if cancel_event and cancel_event.is_set():
                    break
                if max_reply_pages is not None and pages >= max_reply_pages:
                    break
                progress.phase = 'fetching'
                _emit_progress(on_progress, progress)
                _, reply_entries, next_cursor, is_done = await api.fetch_tweet_detail_page(
                    tid,
                    cursor=_cursor,
                    on_rate_limit=rl_cb,
                    cancel_event=cancel_event,
                )
                pages += 1
                progress.pages_fetched += 1
                progress.api_calls = api.api_calls - api_calls_before

                for entry in reply_entries:
                    rec, media_items = extract_reply_from_entry(
                        entry,
                        parent_url,
                        media_down=media_down,
                        image_format=config.image_format,
                    )
                    if rec:
                        csv_exp.write_reply(rec)
                        progress.items_found += 1
                    for item in media_items:
                        progress.phase = 'downloading'
                        await downloader.submit(item)

                _emit_progress(on_progress, progress)
                if is_done or not next_cursor:
                    break
                _cursor = next_cursor

        with CSVExporter(csv_path, REPLY_CSV_HEADERS, preamble_rows=[[f'Run Time : {run_tag}']]) as csv_exp:
            async with AsyncMediaDownloader(
                save_dir,
                concurrency=config.concurrency,
                proxy=config.resolved_proxy(),
                skip_downloaded=config.skip_downloaded,
                on_item_done=_on_item_done,
                on_log=on_log if config.log_output else None,
                cancel_event=cancel_event,
            ) as downloader:
                if is_single_tweet:
                    await _crawl_one_tweet_replies(tweet_id, user_name, csv_exp, downloader)
                else:
                    search_cursor = ''
                    first_page = True
                    while True:
                        if cancel_event and cancel_event.is_set():
                            break
                        entries, next_cursor, is_done = await api.fetch_search_page(
                            query_str,
                            product='Latest',
                            cursor=search_cursor,
                            count=20,
                            endpoint_key='search_reply',
                            first_page=first_page,
                            on_rate_limit=rl_cb,
                            cancel_event=cancel_event,
                        )
                        first_page = False
                        for entry in entries:
                            tid = entry.get('entryId', '').split('tweet-')[-1]
                            if tid.isdigit():
                                await _crawl_one_tweet_replies(tid, user_name, csv_exp, downloader)
                        if is_done or not next_cursor:
                            break
                        search_cursor = next_cursor

        cancelled = bool(cancel_event and cancel_event.is_set())
        progress.phase = 'cancelled' if cancelled else 'done'
        progress.api_calls = api.api_calls - api_calls_before
        _emit_progress(on_progress, progress)
        return TaskResult(
            task=progress.task,
            success=not cancelled,
            save_dir=save_dir,
            downloaded=progress.downloaded,
            skipped=progress.skipped,
            failed=progress.failed,
            records_count=progress.items_found,
            api_calls=progress.api_calls,
            elapsed_seconds=round(time.time() - t0, 2),
            csv_paths=csv_paths,
        )
    except (TwitterAPIError, ValueError, FileNotFoundError) as e:
        progress.phase = 'error'
        progress.message = str(e)
        _emit_progress(on_progress, progress)
        _emit_log(on_log, f'[错误] {e}')
        return TaskResult(
            task=progress.task,
            success=False,
            save_dir=save_dir,
            downloaded=progress.downloaded,
            skipped=progress.skipped,
            failed=progress.failed,
            api_calls=api.api_calls - api_calls_before,
            elapsed_seconds=round(time.time() - t0, 2),
            csv_paths=csv_paths,
            error=str(e),
        )
    finally:
        if own_api:
            await api.close()


async def download_user_text(
    config: AppConfig,
    username: str,
    *,
    time_range: Optional[str] = None,
    include_retweet: bool = False,
    max_pages: Optional[int] = None,
    api: Optional[TwitterAPI] = None,
    on_progress: ProgressCallback = None,
    on_log: LogCallback = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> TaskResult:
    """下载指定用户的纯文本推文（导出 CSV）。"""
    t0 = time.time()
    use_range = config.time_range if time_range is None else time_range
    start_ms, end_ms = parse_time_range(use_range)
    clean_user = username.strip().lstrip('@')
    progress = DownloadProgress(task=f'text:{clean_user}', phase='init')

    own_api = api is None
    if own_api:
        api = _make_api(config)
    api_calls_before = api.api_calls
    save_dir = ''
    csv_paths: List[str] = []

    try:
        rl_cb = _make_rate_limit_handler(progress, on_progress, on_log)
        profile = await api.get_user_profile(clean_user, on_rate_limit=rl_cb, cancel_event=cancel_event)
        save_dir = os.path.join(config.resolved_save_root(), profile.screen_name)
        os.makedirs(save_dir, exist_ok=True)
        _emit_log(on_log, f'用户: {profile.name} (@{profile.screen_name}) | 总推数: {profile.statuses_count}')

        run_tag = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        csv_path = os.path.join(save_dir, f'{profile.screen_name}-{run_tag}-text.csv')
        csv_paths.append(csv_path)

        with CSVExporter(
            csv_path,
            TEXT_CSV_HEADERS,
            preamble_rows=[
                [profile.name, '@' + profile.screen_name],
                ['Tweet Range : ' + (use_range or 'unlimited')],
                ['Save Path : ' + save_dir],
            ],
        ) as csv_exp:
            cursor = ''
            while True:
                if cancel_event and cancel_event.is_set():
                    break
                if max_pages is not None and progress.pages_fetched >= max_pages:
                    break

                progress.phase = 'fetching'
                _emit_progress(on_progress, progress)
                entries, next_cursor, is_done = await api.fetch_user_timeline_page(
                    profile,
                    mode='text',
                    cursor=cursor,
                    on_rate_limit=rl_cb,
                    cancel_event=cancel_event,
                )
                progress.pages_fetched += 1
                progress.api_calls = api.api_calls - api_calls_before

                out_of_range = False
                for entry in entries:
                    eid = entry.get('entryId', '')
                    if 'promoted-tweet' in eid or 'tweet' not in eid:
                        continue
                    tweet_obj = entry.get('content', {}).get('itemContent', {}).get('tweet_results', {}).get('result')
                    rec = extract_text_record(tweet_obj, include_retweet=include_retweet)
                    if not rec:
                        continue
                    if rec.tweet_msecs < start_ms:
                        out_of_range = True
                        break
                    if rec.tweet_msecs > end_ms:
                        continue
                    csv_exp.write_tweet(rec)
                    progress.items_found += 1

                _emit_progress(on_progress, progress)
                if out_of_range or is_done or not next_cursor:
                    break
                cursor = next_cursor

        cancelled = bool(cancel_event and cancel_event.is_set())
        progress.phase = 'cancelled' if cancelled else 'done'
        progress.api_calls = api.api_calls - api_calls_before
        _emit_progress(on_progress, progress)
        return TaskResult(
            task=progress.task,
            success=not cancelled,
            save_dir=save_dir,
            records_count=progress.items_found,
            api_calls=progress.api_calls,
            elapsed_seconds=round(time.time() - t0, 2),
            csv_paths=csv_paths,
        )
    except (TwitterAPIError, ValueError, FileNotFoundError) as e:
        progress.phase = 'error'
        progress.message = str(e)
        _emit_progress(on_progress, progress)
        _emit_log(on_log, f'[错误] {e}')
        return TaskResult(
            task=progress.task,
            success=False,
            save_dir=save_dir,
            records_count=progress.items_found,
            api_calls=api.api_calls - api_calls_before,
            elapsed_seconds=round(time.time() - t0, 2),
            csv_paths=csv_paths,
            error=str(e),
        )
    finally:
        if own_api:
            await api.close()


async def download_user_profile(
    config: AppConfig,
    username: str,
    *,
    api: Optional[TwitterAPI] = None,
    on_progress: ProgressCallback = None,
    on_log: LogCallback = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> TaskResult:
    """下载指定用户的头像、Banner 与简介。"""
    t0 = time.time()
    clean_user = username.strip().lstrip('@')
    progress = DownloadProgress(task=f'profile:{clean_user}', phase='fetching')
    save_dir = os.path.join(config.resolved_save_root(), 'profile')
    os.makedirs(save_dir, exist_ok=True)

    own_api = api is None
    if own_api:
        api = _make_api(config)
    api_calls_before = api.api_calls

    try:
        rl_cb = _make_rate_limit_handler(progress, on_progress, on_log)
        profile = await api.get_user_profile(clean_user, on_rate_limit=rl_cb, cancel_event=cancel_event)
        referer = f'https://x.com/{profile.screen_name}'

        async def _save_asset(url: str, filename: str):
            data = await api.download_bytes(url, referer=referer)
            with open(os.path.join(save_dir, filename), 'wb') as f:
                f.write(data)
            progress.downloaded += 1

        tasks = []
        if profile.avatar_url:
            tasks.append(_save_asset(profile.avatar_url, f'{profile.screen_name}_avatar.jpg'))
        if profile.banner_url:
            tasks.append(_save_asset(profile.banner_url, f'{profile.screen_name}_banner.jpg'))
        if tasks:
            progress.phase = 'downloading'
            await asyncio.gather(*tasks)

        with open(os.path.join(save_dir, f'{profile.screen_name}_description.txt'), 'w', encoding='utf-8') as f:
            f.write(profile.description)
        progress.downloaded += 1
        progress.items_found = progress.downloaded
        progress.phase = 'done'
        progress.api_calls = api.api_calls - api_calls_before
        _emit_progress(on_progress, progress)
        _emit_log(on_log, f'用户资料已保存: @{profile.screen_name} -> {save_dir}')

        return TaskResult(
            task=progress.task,
            success=True,
            save_dir=save_dir,
            downloaded=progress.downloaded,
            records_count=1,
            api_calls=progress.api_calls,
            elapsed_seconds=round(time.time() - t0, 2),
        )
    except (TwitterAPIError, ValueError, FileNotFoundError) as e:
        progress.phase = 'error'
        progress.message = str(e)
        _emit_progress(on_progress, progress)
        _emit_log(on_log, f'[错误] {e}')
        return TaskResult(
            task=progress.task,
            success=False,
            save_dir=save_dir,
            api_calls=api.api_calls - api_calls_before,
            elapsed_seconds=round(time.time() - t0, 2),
            error=str(e),
        )
    finally:
        if own_api:
            await api.close()
