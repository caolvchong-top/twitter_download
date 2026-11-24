from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class UserProfile:
    screen_name: str
    rest_id: str = ''
    name: str = ''
    statuses_count: int = 0
    media_count: int = 0
    avatar_url: str = ''
    banner_url: Optional[str] = None
    description: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MediaItem:
    url: str
    media_type: str  # 'Image' | 'Video'
    tweet_id: str
    tweet_url: str
    tweet_msecs: int
    author_name: str
    author_screen_name: str  # without leading '@'
    text: str
    favorite_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    is_retweet: bool = False
    download_url: str = ''
    filename: str = ''
    saved_path: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TweetRecord:
    tweet_id: str
    tweet_url: str
    tweet_msecs: int
    author_name: str
    author_screen_name: str  # without leading '@'
    text: str
    favorite_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    is_retweet: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReplyRecord:
    parent_tweet_url: str
    replier_name: str
    replier_screen_name: str  # without leading '@'
    reply_msecs: int
    reply_text: str
    reply_url: str
    favorite_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DownloadProgress:
    task: str
    phase: str = 'running'  # 'init' | 'fetching' | 'downloading' | 'waiting_rate_limit' | 'done' | 'cancelled' | 'error'
    pages_fetched: int = 0
    items_found: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    api_calls: int = 0
    message: str = ''
    rate_limit_reset: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TaskResult:
    task: str
    success: bool = True
    save_dir: str = ''
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    records_count: int = 0
    api_calls: int = 0
    elapsed_seconds: float = 0.0
    csv_paths: List[str] = field(default_factory=list)
    md_paths: List[str] = field(default_factory=list)
    error: str = ''

    def to_dict(self) -> dict:
        return asdict(self)
