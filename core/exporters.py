import csv
from datetime import datetime
import os
from typing import List, Optional, Sequence

from .config import format_timestamp
from .models import MediaItem, ReplyRecord, TweetRecord


class CSVExporter:
    """统一 CSV 导出器，替代原先 4 份重复实现的 csv_gen。"""

    def __init__(self, file_path: str, headers: Sequence[str], preamble_rows: Optional[List[Sequence[str]]] = None):
        self.file_path = file_path
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        self._f = open(file_path, 'w', encoding='utf-8-sig', newline='')
        self._writer = csv.writer(self._f)
        for row in (preamble_rows or []):
            self._writer.writerow(row)
        self._writer.writerow(headers)
        self.row_count = 0

    def write_row(self, row: Sequence):
        self._writer.writerow(row)
        self.row_count += 1

    def write_media(self, item: MediaItem, *, full_saved_path: bool = False):
        self.write_row([
            format_timestamp(item.tweet_msecs, '%Y-%m-%d %H:%M'),
            item.author_name,
            f'@{item.author_screen_name}',
            item.tweet_url,
            item.media_type,
            item.url,
            item.saved_path if full_saved_path else item.filename,
            item.text,
            item.favorite_count,
            item.retweet_count,
            item.reply_count,
        ])

    def write_tweet(self, rec: TweetRecord):
        self.write_row([
            rec.author_name if rec.is_retweet else '',
            f'@{rec.author_screen_name}' if rec.is_retweet else '',
            format_timestamp(rec.tweet_msecs, '%Y-%m-%d %H:%M'),
            rec.tweet_url,
            rec.text,
            rec.favorite_count,
            rec.retweet_count,
            rec.reply_count,
        ])

    def write_search_text(self, rec: TweetRecord):
        self.write_row([
            format_timestamp(rec.tweet_msecs, '%Y-%m-%d %H:%M'),
            rec.author_name,
            f'@{rec.author_screen_name}',
            rec.tweet_url,
            rec.text,
            rec.favorite_count,
            rec.retweet_count,
            rec.reply_count,
        ])

    def write_reply(self, rec: ReplyRecord):
        self.write_row([
            rec.parent_tweet_url,
            rec.replier_name,
            f'@{rec.replier_screen_name}',
            format_timestamp(rec.reply_msecs, '%Y-%m-%d %H:%M'),
            rec.reply_text,
            rec.reply_url,
            rec.favorite_count,
            rec.retweet_count,
            rec.reply_count,
        ])

    def close(self):
        if self._f and not self._f.closed:
            self._f.close()

    def __enter__(self) -> 'CSVExporter':
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


MEDIA_CSV_HEADERS = [
    'Tweet Date', 'Display Name', 'User Name', 'Tweet URL', 'Media Type',
    'Media URL', 'Saved Filename', 'Tweet Content', 'Favorite Count',
    'Retweet Count', 'Reply Count',
]

TEXT_CSV_HEADERS = [
    'Display Name', 'User Name', 'Tweet Date', 'Tweet URL', 'Tweet Content',
    'Favorite Count', 'Retweet Count', 'Reply Count',
]

SEARCH_TEXT_CSV_HEADERS = [
    'Tweet Date', 'Display Name', 'User Name', 'Tweet URL', 'Tweet Content',
    'Favorite Count', 'Retweet Count', 'Reply Count',
]

REPLY_CSV_HEADERS = [
    'Parent Tweet URL', 'Replier Display Name', 'Replier User Name', 'Reply Date',
    'Reply Content', 'Reply URL', 'Reply Favorite Count', 'Reply Retweet Count',
    'Reply Reply Count',
]


class MarkdownExporter:
    """Markdown 推文归档导出器，支持按媒体数量自动分卷。"""

    def __init__(
        self,
        save_dir: str,
        user_name: str,
        screen_name: str,
        tweet_range: str,
        *,
        is_likes: bool = False,
        media_count_limit: int = 350,
    ):
        self.save_dir = save_dir
        self.user_name = user_name
        self.screen_name = screen_name
        self.tweet_range = tweet_range or 'unlimited'
        self.is_likes = is_likes
        self.media_count_limit = media_count_limit

        self._run_tag = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        self.file_count = 1
        self.file_media_count = 0
        self._current_tweet_id = ''
        self._current_stats = ''
        self._current_ym = ''
        self.md_paths: List[str] = []
        self._f = None
        self._open_new_file(f'{self.screen_name}-{self._run_tag}_1.md')

    def _open_new_file(self, filename: str):
        if self._f and not self._f.closed:
            self._f.close()
        path = os.path.join(self.save_dir, filename)
        self.md_paths.append(path)
        self._f = open(path, 'w', encoding='utf-8-sig', newline='')
        self._f.write(f'{self.user_name} @{self.screen_name}\n')
        self._f.write(f'Tweet Range: {self.tweet_range}\n')
        self._f.write(f'Save Path: {self.save_dir}\n\n')

    def write_media(self, item: MediaItem):
        fixed_filename = item.filename.replace(' ', '%20')
        time_str = format_timestamp(item.tweet_msecs, '%Y-%m-%d %H:%M')
        ym = time_str[:7]

        if self._current_tweet_id != item.tweet_id:
            if self._current_stats:
                self._f.write(f'\n{self._current_stats}\n\n')

            if self.media_count_limit > 0 and self.file_media_count >= self.media_count_limit:
                self.file_media_count = 0
                self.file_count += 1
                if self.is_likes:
                    new_name = f'{self.screen_name}-{self._run_tag}_{self.file_count}.md'
                elif item.is_retweet:
                    new_name = f'{self.screen_name}-{self._run_tag}_{self.file_count}_{self._current_ym}.md'
                else:
                    new_name = f'{self.screen_name}-{self._run_tag}_{self.file_count}_{ym}.md'
                self._open_new_file(new_name)

            if not self.is_likes and not item.is_retweet and ym != self._current_ym:
                self._f.write(f'## {ym}\n')
                self._current_ym = ym

            rt_prefix = f'*{self.user_name} retweeted*\n' if item.is_retweet else ''
            self._f.write(f'{rt_prefix}{item.author_name} @{item.author_screen_name} · {time_str} [src]({item.tweet_url})\n')
            self._f.write(item.text + '\n')
            self._current_tweet_id = item.tweet_id
            self._current_stats = f'{item.favorite_count} Likes, {item.retweet_count} Retweets, {item.reply_count} Replies'

        if item.media_type == 'Video':
            self._f.write(f'<video src="{fixed_filename}" controls></video>')
        else:
            self._f.write(f'[![]({fixed_filename})]({item.url})')
        self.file_media_count += 1

    def close(self):
        if self._f and not self._f.closed:
            if self._current_stats:
                self._f.write(f'\n{self._current_stats}\n')
            self._f.close()

    def __enter__(self) -> 'MarkdownExporter':
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
