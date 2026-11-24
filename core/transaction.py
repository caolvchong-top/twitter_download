import asyncio
import re
from typing import Optional
from urllib.parse import urlparse
import bs4
import httpx
from x_client_transaction import ClientTransaction
from x_client_transaction.utils import (
    generate_headers,
    get_ondemand_file_url,
    handle_x_migration,
)


def get_url_path(url: str) -> str:
    parsed = urlparse(url)
    if parsed.path:
        return parsed.path
    match = re.findall(r'https?://(?:x|twitter)\.com(.*?)(?:\?|$)', url)
    return match[0] if match else ''


def _extract_ondemand_url(home_page_response: bs4.BeautifulSoup) -> str:
    try:
        return get_ondemand_file_url(response=home_page_response)
    except Exception:
        html = str(home_page_response)
        direct_match = re.search(r'["\']ondemand\.s["\']\s*:\s*["\']([0-9a-f]+)["\']', html)
        if direct_match:
            return f'https://abs.twimg.com/responsive-web/client-web/ondemand.s.{direct_match.group(1)}a.js'

        idx_match = re.search(r'[\{,](\d+):["\']ondemand\.s["\']', html)
        if idx_match:
            chunk_id = idx_match.group(1)
            hash_match = re.search(rf'[\{{,]{chunk_id}:["\']([0-9a-f]+)["\']', html)
            if hash_match:
                return f'https://abs.twimg.com/responsive-web/client-web/ondemand.s.{hash_match.group(1)}a.js'

        raise RuntimeError(
            '无法从 x.com 页面提取 ondemand.s 脚本链接，请检查 Cookie 是否有效或网络是否可访问 x.com。'
        )


def create_client_transaction(cookie: Optional[str] = None, proxy: Optional[str] = None) -> ClientTransaction:
    """
    初始化 XClientTransaction 生成器（统一使用 httpx，自动支持 HTTP / SOCKS5 与系统代理）。
    传入已登录 cookie 后请求 https://x.com/home 获取完整页面与 ondemand.s 映射，
    避开未登录访问 https://x.com 返回精简落地页的问题。
    """
    headers = generate_headers()
    if cookie:
        headers['Cookie'] = cookie

    with httpx.Client(
        headers=headers,
        proxy=proxy,
        follow_redirects=True,
        timeout=httpx.Timeout(20.0, connect=8.0),
    ) as client:
        if cookie:
            home_page = client.get('https://x.com/home')
            home_page.raise_for_status()
            home_page_response = bs4.BeautifulSoup(home_page.content, 'html.parser')
        else:
            home_page_response = handle_x_migration(session=client)

        ondemand_file_url = _extract_ondemand_url(home_page_response)
        ondemand_file = client.get(ondemand_file_url)
        ondemand_file.raise_for_status()
        return ClientTransaction(home_page_response, ondemand_file)


class TransactionProvider:
    """线程与协程安全的 X-Client-Transaction-ID 提供器（按需初始化，支持 404 刷新）。"""

    def __init__(self, cookie: Optional[str] = None, proxy: Optional[str] = None):
        self.cookie = cookie
        self.proxy = proxy
        self._ct: Optional[ClientTransaction] = None
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def generate_id(self, method: str, url: str) -> str:
        if self._ct is None:
            self._ct = create_client_transaction(cookie=self.cookie, proxy=self.proxy)
        return self._ct.generate_transaction_id(method=method, path=get_url_path(url))

    def refresh(self) -> ClientTransaction:
        self._ct = create_client_transaction(cookie=self.cookie, proxy=self.proxy)
        return self._ct

    async def async_generate_id(self, method: str, url: str) -> str:
        if self._ct is None:
            async with self._get_lock():
                if self._ct is None:
                    self._ct = await asyncio.to_thread(
                        create_client_transaction, self.cookie, self.proxy
                    )
        return self._ct.generate_transaction_id(method=method, path=get_url_path(url))

    async def async_refresh(self) -> ClientTransaction:
        async with self._get_lock():
            self._ct = await asyncio.to_thread(
                create_client_transaction, self.cookie, self.proxy
            )
            return self._ct
