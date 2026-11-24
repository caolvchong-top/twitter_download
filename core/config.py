from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
import re
import time
from typing import List, Optional, Tuple
from urllib.parse import urlparse


MIN_TIMESTAMP_MS = 655028357000   # 1990-10-04
MAX_TIMESTAMP_MS = 2548484357000  # 2050-10-04
VALID_MODES = ('media', 'retweet', 'highlights', 'likes')
VALID_IMAGE_FORMATS = ('orig', 'jpg', 'png')


def _is_placeholder_cookie(value: str) -> bool:
    if not value or not value.strip():
        return True
    return 'xxxxxxxxxxx' in value


def parse_netscape_cookie_file(file_path: str) -> str:
    """解析 Netscape HTTP Cookie File (如 cookies.txt)，提取 x.com / twitter.com 的 auth_token 和 ct0。"""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f'未找到 Cookie 文件: {file_path}')

    x_cookies = {}
    twitter_cookies = {}

    with open(file_path, 'r', encoding='utf-8-sig') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith('#HttpOnly_'):
                line = line[len('#HttpOnly_'):]
            elif line.startswith('#'):
                continue

            parts = line.split('\t')
            if len(parts) < 7:
                continue

            domain = parts[0].lstrip('.').lower()
            name = parts[5].strip()
            value = parts[6].strip()

            if domain == 'x.com' or domain.endswith('.x.com'):
                x_cookies[name] = value
            elif domain == 'twitter.com' or domain.endswith('.twitter.com'):
                twitter_cookies[name] = value

    auth_token = x_cookies.get('auth_token') or twitter_cookies.get('auth_token')
    ct0 = x_cookies.get('ct0') or twitter_cookies.get('ct0')

    if not auth_token or not ct0:
        raise ValueError(
            f'Cookie 文件 "{file_path}" 中缺少 auth_token 或 ct0 字段，'
            '请确认已在浏览器登录 x.com 后再导出 Netscape 格式 Cookie。'
        )

    return f'auth_token={auth_token}; ct0={ct0};'


def extract_cookie_pair(cookie_str: str) -> Tuple[str, str]:
    auth_match = re.search(r'(?:^|;\s*)auth_token=([^;\s]+)', cookie_str)
    ct0_match = re.search(r'(?:^|;\s*)ct0=([^;\s]+)', cookie_str)
    if not auth_match or not ct0_match:
        raise ValueError(
            'Cookie 格式不正确，缺少 auth_token 或 ct0。'
            '请填入 Netscape 格式文件路径（如 cookies.txt）或 "auth_token=xxx; ct0=xxx;"。'
        )
    auth_token = auth_match.group(1)
    ct0 = ct0_match.group(1)
    return f'auth_token={auth_token}; ct0={ct0};', ct0


def resolve_cookie(
    raw_cookie: str = '',
    fallback_cookie: str = '',
    default_cookie_file: str = 'cookies.txt',
) -> Tuple[str, str]:
    """
    统一解析 Cookie，返回 (规范化 cookie 字符串, ct0)。
    优先级：raw_cookie -> fallback_cookie -> 默认 cookies.txt。
    """
    candidates = []
    if not _is_placeholder_cookie(raw_cookie):
        candidates.append(raw_cookie.strip())
    if not _is_placeholder_cookie(fallback_cookie):
        candidates.append(fallback_cookie.strip())
    if default_cookie_file and os.path.isfile(default_cookie_file):
        candidates.append(default_cookie_file)

    for source in candidates:
        if os.path.isfile(source):
            return extract_cookie_pair(parse_netscape_cookie_file(source))
        if source.lower().endswith('.txt'):
            # 如果显式指定了不存在的 .txt 路径，继续尝试下一个候选；若没有下一个候选则报明确错误
            continue
        return extract_cookie_pair(source)

    # 若指定了 .txt 但文件不存在，给出更精准提示
    for source in candidates:
        if source.lower().endswith('.txt'):
            raise FileNotFoundError(
                f'未找到 Cookie 文件 "{source}"。请将导出的 Netscape 格式 Cookie 保存为该路径，或直接在配置中填入 auth_token 与 ct0。'
            )

    raise ValueError(
        '未检测到有效 Cookie！请任选一种方式配置：\n'
        '1. 将导出的 Netscape 格式 cookies.txt 放到项目根目录；\n'
        '2. 在 settings.json 的 "cookie" 中填入 cookies.txt 路径或 "auth_token=...; ct0=...;"。'
    )


def parse_time_range(time_range: str) -> Tuple[int, int]:
    """解析 YYYY-MM-DD:YYYY-MM-DD 为毫秒时间戳区间。留空则返回无限制区间。"""
    if not time_range or not time_range.strip():
        return MIN_TIMESTAMP_MS, MAX_TIMESTAMP_MS

    parts = [p.strip() for p in time_range.split(':')]
    if len(parts) != 2:
        raise ValueError(f'时间范围格式应为 YYYY-MM-DD:YYYY-MM-DD，当前值: {time_range}')

    start_ms = MIN_TIMESTAMP_MS
    end_ms = MAX_TIMESTAMP_MS
    if parts[0]:
        dt = datetime.strptime(parts[0], '%Y-%m-%d')
        start_ms = int(time.mktime(dt.timetuple()) * 1000)
    if parts[1]:
        dt = datetime.strptime(parts[1], '%Y-%m-%d')
        # 包含结束日期当天（加到 23:59:59.999）
        end_ms = int(time.mktime(dt.timetuple()) * 1000) + 86399999
    return start_ms, end_ms


def sanitize_filename(name: str, allow_hash: bool = True) -> str:
    pattern = r'[^#\u4e00-\u9fa50-9A-Za-z\u3040-\u31FF._-]' if allow_hash else r'[^\u4e00-\u9fa50-9A-Za-z\u3040-\u31FF._-]'
    cleaned = re.sub(pattern, '', name).strip('.')
    return cleaned or 'output'


def format_timestamp(msecs: int, fmt: str = '%Y-%m-%d %H-%M') -> str:
    return time.strftime(fmt, time.localtime(msecs / 1000))


def short_hash(text: str, length: int = 6) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:length]


def get_image_extension(media_url: str, default: str = 'jpg') -> str:
    ext = os.path.splitext(urlparse(media_url).path)[1].lstrip('.').lower()
    return ext if ext in ('jpg', 'jpeg', 'png', 'webp', 'gif') else default


def build_image_download_url(media_url: str, image_format: str = 'orig') -> Tuple[str, str]:
    """返回 (下载 URL, 保存扩展名)。默认 orig 原图，避免强制转 PNG 导致体积翻倍。"""
    fmt = (image_format or 'orig').lower()
    if fmt == 'orig':
        return f'{media_url}?name=orig', get_image_extension(media_url)
    if fmt == 'png':
        return f'{media_url}?format=png&name=4096x4096', 'png'
    return f'{media_url}?format=jpg&name=4096x4096', 'jpg'


@dataclass
class AppConfig:
    cookie: str = 'cookies.txt'
    users: List[str] = field(default_factory=lambda: ['lilmonix3', 'matchach'])
    mode: str = 'media'  # 'media' | 'retweet' | 'highlights' | 'likes'
    save_path: str = ''
    time_range: str = ''
    has_video: bool = True
    image_format: str = 'orig'  # 'orig' | 'jpg' | 'png'
    skip_downloaded: bool = True
    md_output: bool = False
    media_count_limit: int = 350
    concurrency: int = 8
    proxy: str = ''
    wait_on_rate_limit: bool = False
    log_output: bool = False

    def resolved_save_root(self) -> str:
        root = self.save_path.strip() if self.save_path else os.getcwd()
        return os.path.abspath(root)

    def resolved_proxy(self) -> Optional[str]:
        p = self.proxy.strip() if self.proxy else ''
        return p or None

    def resolve_auth(self, override_cookie: str = '') -> Tuple[str, str]:
        return resolve_cookie(override_cookie, self.cookie)

    def to_settings_dict(self) -> dict:
        """导出为简洁分层的 settings.json 结构（同时便于 WebUI 读取和保存）。"""
        return {
            'cookie': self.cookie,
            'users': list(self.users),
            'mode': self.mode if self.mode in VALID_MODES else 'media',
            'save_path': self.save_path,
            'advanced': {
                'time_range': self.time_range,
                'has_video': self.has_video,
                'image_format': self.image_format if self.image_format in VALID_IMAGE_FORMATS else 'orig',
                'skip_downloaded': self.skip_downloaded,
                'md_output': self.md_output,
                'media_count_limit': self.media_count_limit,
                'concurrency': self.concurrency,
                'proxy': self.proxy,
                'wait_on_rate_limit': self.wait_on_rate_limit,
                'log_output': self.log_output,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AppConfig':
        """兼容新版分层 settings.json 与历史扁平 settings.json。"""
        if not isinstance(data, dict):
            return cls()

        adv = data.get('advanced') if isinstance(data.get('advanced'), dict) else {}

        # users: 兼容 list 或逗号字符串或旧字段 user_lst
        raw_users = data.get('users', data.get('user_lst', []))
        if isinstance(raw_users, str):
            users = [u.strip().lstrip('@') for u in raw_users.split(',') if u.strip()]
        elif isinstance(raw_users, list):
            users = [str(u).strip().lstrip('@') for u in raw_users if str(u).strip()]
        else:
            users = []

        # mode: 兼容新字段 mode 与旧三选一布尔值
        mode = data.get('mode', '')
        if mode not in VALID_MODES:
            if data.get('likes'):
                mode = 'likes'
            elif data.get('high_lights'):
                mode = 'highlights'
            elif data.get('has_retweet'):
                mode = 'retweet'
            else:
                mode = 'media'

        def _get(key, old_key=None, default=None):
            if key in adv:
                return adv[key]
            if key in data:
                return data[key]
            if old_key and old_key in data:
                return data[old_key]
            return default

        skip_downloaded = _get('skip_downloaded', None, None)
        if skip_downloaded is None:
            if 'down_log' in data or 'autoSync' in data:
                skip_downloaded = bool(data.get('down_log') or data.get('autoSync'))
            else:
                skip_downloaded = True

        concurrency = int(_get('concurrency', 'max_concurrent_requests', 8) or 8)
        concurrency = max(1, min(concurrency, 64))

        image_format = str(_get('image_format', None, 'orig') or 'orig').lower()
        if image_format not in VALID_IMAGE_FORMATS:
            image_format = 'orig'

        cookie_val = data.get('cookie', '')
        if _is_placeholder_cookie(cookie_val) and data.get('cookie_file'):
            cookie_val = str(data['cookie_file'])
        if not cookie_val:
            cookie_val = 'cookies.txt'

        return cls(
            cookie=str(cookie_val),
            users=users,
            mode=mode,
            save_path=str(data.get('save_path', '') or ''),
            time_range=str(_get('time_range', None, '') or ''),
            has_video=bool(_get('has_video', None, True)),
            image_format=image_format,
            skip_downloaded=bool(skip_downloaded),
            md_output=bool(_get('md_output', None, False)),
            media_count_limit=int(_get('media_count_limit', None, 350) or 0),
            concurrency=concurrency,
            proxy=str(_get('proxy', None, '') or ''),
            wait_on_rate_limit=bool(_get('wait_on_rate_limit', None, False)),
            log_output=bool(_get('log_output', None, False)),
        )


def load_config(path: str = 'settings.json') -> AppConfig:
    if not os.path.isfile(path):
        return AppConfig()
    with open(path, 'r', encoding='utf-8-sig') as f:
        return AppConfig.from_dict(json.load(f))


def save_config(config: AppConfig, path: str = 'settings.json') -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config.to_settings_dict(), f, ensure_ascii=False, indent=4)
