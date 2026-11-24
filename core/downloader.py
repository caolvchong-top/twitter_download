import asyncio
import os
import pickle
from typing import Callable, Optional, Set
import httpx

from .models import MediaItem


class DownloadCache:
    """崩溃安全的增量去重缓存（每完成一条实时追加写盘，并兼容读取旧版 cache_data.log）。"""

    def __init__(self, save_dir: str, enabled: bool = True):
        self.enabled = enabled
        self.log_path = os.path.join(save_dir, 'downloaded_urls.log')
        self.legacy_pickle_path = os.path.join(save_dir, 'cache_data.log')
        self._seen: Set[str] = set()
        if enabled:
            self._load()

    def _load(self):
        # 兼容旧版 pickle 缓存
        if os.path.isfile(self.legacy_pickle_path):
            try:
                with open(self.legacy_pickle_path, 'rb') as f:
                    legacy_set = pickle.load(f)
                if isinstance(legacy_set, set):
                    self._seen.update(str(x) for x in legacy_set)
            except Exception:
                pass

        if os.path.isfile(self.log_path):
            try:
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        val = line.strip()
                        if val:
                            self._seen.add(val)
            except Exception:
                pass

    def contains(self, url: str) -> bool:
        return self.enabled and url in self._seen

    def mark(self, url: str):
        if not self.enabled or url in self._seen:
            return
        self._seen.add(url)
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(url + '\n')


class AsyncMediaDownloader:
    """
    基于 asyncio.Queue 的生产者-消费者异步下载器：
    - 复用单个 httpx.AsyncClient 连接池
    - 流式分块写 .part 临时文件再原子重命名，防大视频占内存与残缺文件
    - 支持指数退避重试、404 降级/跳过、取消信号与实时回调
    """

    def __init__(
        self,
        save_dir: str,
        *,
        concurrency: int = 8,
        proxy: Optional[str] = None,
        skip_downloaded: bool = True,
        max_retries: int = 4,
        on_item_done: Optional[Callable[[MediaItem, str], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ):
        self.save_dir = save_dir
        self.concurrency = max(1, concurrency)
        self.proxy = proxy
        self.skip_downloaded = skip_downloaded
        self.max_retries = max_retries
        self.on_item_done = on_item_done
        self.on_log = on_log
        self.cancel_event = cancel_event

        os.makedirs(save_dir, exist_ok=True)
        self.cache = DownloadCache(save_dir, enabled=skip_downloaded)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max(32, self.concurrency * 8))
        self._client: Optional[httpx.AsyncClient] = None
        self._workers: list = []

        self.downloaded = 0
        self.skipped = 0
        self.failed = 0

    async def __aenter__(self) -> 'AsyncMediaDownloader':
        self._client = httpx.AsyncClient(
            proxy=self.proxy,
            timeout=httpx.Timeout(connect=8.0, read=60.0, write=30.0, pool=30.0),
            limits=httpx.Limits(max_connections=self.concurrency + 8, max_keepalive_connections=self.concurrency),
        )
        self._workers = [
            asyncio.create_task(self._worker())
            for _ in range(self.concurrency)
        ]
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.finish()

    async def submit(self, item: MediaItem):
        if self.cancel_event and self.cancel_event.is_set():
            return
        await self._queue.put(item)

    async def finish(self):
        if self._workers:
            for _ in self._workers:
                await self._queue.put(None)
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers = []
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _emit_done(self, item: MediaItem, status: str):
        if self.on_item_done:
            self.on_item_done(item, status)

    async def _worker(self):
        while True:
            item = await self._queue.get()
            try:
                if item is None:
                    return
                if self.cancel_event and self.cancel_event.is_set():
                    continue
                await self._process_item(item)
            finally:
                self._queue.task_done()

    async def _process_item(self, item: MediaItem):
        dest_path = os.path.join(self.save_dir, item.filename)
        item.saved_path = dest_path

        # 跳过已下载（缓存命中或本地已有非空文件）
        if self.skip_downloaded and (
            self.cache.contains(item.url)
            or (os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0)
        ):
            self.skipped += 1
            self.cache.mark(item.url)
            self._emit_done(item, 'skipped')
            return

        url = item.download_url or item.url
        part_path = dest_path + '.part'

        for attempt in range(self.max_retries + 1):
            if self.cancel_event and self.cancel_event.is_set():
                self._remove_part(part_path)
                return

            try:
                async with self._client.stream('GET', url) as resp:
                    if resp.status_code == 404:
                        # 若 orig 不可用则回退 4096x4096 再试一次，否则直接跳过
                        if 'name=orig' in url:
                            url = url.replace('name=orig', 'name=4096x4096')
                            continue
                        self.failed += 1
                        if self.on_log:
                            self.on_log(f'[跳过 404] {item.filename}')
                        self._emit_done(item, 'failed')
                        return

                    if resp.status_code != 200:
                        raise RuntimeError(f'HTTP {resp.status_code}')

                    with open(part_path, 'wb') as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            if self.cancel_event and self.cancel_event.is_set():
                                break
                            f.write(chunk)

                if self.cancel_event and self.cancel_event.is_set():
                    self._remove_part(part_path)
                    return

                os.replace(part_path, dest_path)
                self.downloaded += 1
                self.cache.mark(item.url)
                if self.on_log:
                    self.on_log(f'[已下载] {item.filename}')
                self._emit_done(item, 'downloaded')
                return

            except Exception as e:
                self._remove_part(part_path)
                if attempt >= self.max_retries:
                    self.failed += 1
                    if self.on_log:
                        self.on_log(f'[下载失败已跳过] {item.filename}: {e}')
                    self._emit_done(item, 'failed')
                    return
                await asyncio.sleep(min(10, 2 ** attempt))

    @staticmethod
    def _remove_part(path: str):
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
