"""
Twitter / X 下载器核心引擎（供 CLI 与 WebUI 共同调用）。
"""

from .api import TwitterAPI, TwitterAPIError, parse_tweet_id_from_input
from .config import (
    AppConfig,
    VALID_IMAGE_FORMATS,
    VALID_MODES,
    load_config,
    parse_netscape_cookie_file,
    parse_time_range,
    resolve_cookie,
    save_config,
)
from .downloader import AsyncMediaDownloader, DownloadCache
from .exporters import CSVExporter, MarkdownExporter
from .models import (
    DownloadProgress,
    MediaItem,
    ReplyRecord,
    TaskResult,
    TweetRecord,
    UserProfile,
)
from .tasks import (
    download_replies,
    download_search,
    download_tweet,
    download_user_media,
    download_user_profile,
    download_user_text,
)
from .transaction import TransactionProvider, create_client_transaction, get_url_path

__all__ = [
    'AppConfig',
    'AsyncMediaDownloader',
    'CSVExporter',
    'DownloadCache',
    'DownloadProgress',
    'MarkdownExporter',
    'MediaItem',
    'ReplyRecord',
    'TaskResult',
    'TransactionProvider',
    'TweetRecord',
    'TwitterAPI',
    'TwitterAPIError',
    'UserProfile',
    'VALID_IMAGE_FORMATS',
    'VALID_MODES',
    'create_client_transaction',
    'download_replies',
    'download_search',
    'download_tweet',
    'download_user_media',
    'download_user_profile',
    'download_user_text',
    'get_url_path',
    'load_config',
    'parse_netscape_cookie_file',
    'parse_time_range',
    'parse_tweet_id_from_input',
    'resolve_cookie',
    'save_config',
]
