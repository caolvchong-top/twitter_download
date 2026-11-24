import asyncio
from datetime import datetime
import json
import re
import time
from typing import Callable, Dict, List, Optional, Tuple
import httpx

from .config import build_image_download_url, format_timestamp
from .models import MediaItem, ReplyRecord, TweetRecord, UserProfile
from .transaction import TransactionProvider


DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/127.0.0.0 Safari/537.36'
)
DEFAULT_BEARER_TOKEN = (
    'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs'
    '%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA'
)

# ==================== GraphQL 端点与公共 Features 集中定义 ====================

_TIMELINE_FEATURES_BASE = {
    'responsive_web_graphql_exclude_directive_enabled': True,
    'verified_phone_label_enabled': False,
    'creator_subscriptions_tweet_preview_api_enabled': True,
    'responsive_web_graphql_timeline_navigation_enabled': True,
    'responsive_web_graphql_skip_user_profile_image_extensions_enabled': False,
    'tweetypie_unmention_optimization_enabled': True,
    'responsive_web_edit_tweet_api_enabled': True,
    'graphql_is_translatable_rweb_tweet_is_translatable_enabled': True,
    'view_counts_everywhere_api_enabled': True,
    'longform_notetweets_consumption_enabled': True,
    'responsive_web_twitter_article_tweet_consumption_enabled': False,
    'tweet_awards_web_tipping_enabled': False,
    'freedom_of_speech_not_reach_fetch_enabled': True,
    'standardized_nudges_misinfo': True,
    'tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled': True,
    'longform_notetweets_rich_text_read_enabled': True,
    'longform_notetweets_inline_media_enabled': True,
    'responsive_web_media_download_video_enabled': False,
    'responsive_web_enhance_cards_enabled': False,
}

_SEARCH_DETAIL_FEATURES = {
    'rweb_video_screen_enabled': False,
    'profile_label_improvements_pcf_label_in_post_enabled': True,
    'rweb_tipjar_consumption_enabled': True,
    'verified_phone_label_enabled': False,
    'creator_subscriptions_tweet_preview_api_enabled': True,
    'responsive_web_graphql_timeline_navigation_enabled': True,
    'responsive_web_graphql_skip_user_profile_image_extensions_enabled': False,
    'premium_content_api_read_enabled': False,
    'communities_web_enable_tweet_community_results_fetch': True,
    'c9s_tweet_anatomy_moderator_badge_enabled': True,
    'responsive_web_grok_analyze_button_fetch_trends_enabled': False,
    'responsive_web_grok_analyze_post_followups_enabled': True,
    'responsive_web_jetfuel_frame': False,
    'responsive_web_grok_share_attachment_enabled': True,
    'articles_preview_enabled': True,
    'responsive_web_edit_tweet_api_enabled': True,
    'graphql_is_translatable_rweb_tweet_is_translatable_enabled': True,
    'view_counts_everywhere_api_enabled': True,
    'longform_notetweets_consumption_enabled': True,
    'responsive_web_twitter_article_tweet_consumption_enabled': True,
    'tweet_awards_web_tipping_enabled': False,
    'responsive_web_grok_show_grok_translated_post': False,
    'responsive_web_grok_analysis_button_from_backend': False,
    'creator_subscriptions_quote_tweet_preview_enabled': False,
    'freedom_of_speech_not_reach_fetch_enabled': True,
    'standardized_nudges_misinfo': True,
    'tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled': True,
    'longform_notetweets_rich_text_read_enabled': True,
    'longform_notetweets_inline_media_enabled': True,
    'responsive_web_grok_image_annotation_enabled': True,
    'responsive_web_enhance_cards_enabled': False,
}

ENDPOINTS = {
    'user_profile': {
        'url': 'https://twitter.com/i/api/graphql/gEyDv8Fmv2BVTYIAf32nbA/UserByScreenName',
        'features': {
            'hidden_profile_subscriptions_enabled': True,
            'payments_enabled': False,
            'rweb_xchat_enabled': False,
            'profile_label_improvements_pcf_label_in_post_enabled': True,
            'rweb_tipjar_consumption_enabled': True,
            'verified_phone_label_enabled': False,
            'subscriptions_verification_info_is_identity_verified_enabled': True,
            'subscriptions_verification_info_verified_since_enabled': True,
            'highlights_tweets_tab_ui_enabled': True,
            'responsive_web_twitter_article_notes_tab_enabled': True,
            'subscriptions_feature_can_gift_premium': True,
            'creator_subscriptions_tweet_preview_api_enabled': True,
            'responsive_web_graphql_skip_user_profile_image_extensions_enabled': False,
            'responsive_web_graphql_timeline_navigation_enabled': True,
        },
        'field_toggles': {'withAuxiliaryUserLabels': True},
    },
    'user_media': {
        'url': 'https://twitter.com/i/api/graphql/Le6KlbilFmSu-5VltFND-Q/UserMedia',
        'features': _TIMELINE_FEATURES_BASE,
    },
    'user_tweets': {
        'url': 'https://twitter.com/i/api/graphql/2GIWTr7XwadIixZDtyXd4A/UserTweets',
        'features': {**_TIMELINE_FEATURES_BASE, 'rweb_lists_timeline_redesign_enabled': True},
        'field_toggles': {'withAuxiliaryUserLabels': False, 'withArticleRichContentState': False},
    },
    'user_text': {
        'url': 'https://twitter.com/i/api/graphql/9zyyd1hebl7oNWIPdA8HRw/UserTweets',
        'features': {
            **_TIMELINE_FEATURES_BASE,
            'rweb_tipjar_consumption_enabled': True,
            'communities_web_enable_tweet_community_results_fetch': True,
            'c9s_tweet_anatomy_moderator_badge_enabled': True,
            'articles_preview_enabled': True,
            'responsive_web_twitter_article_tweet_consumption_enabled': True,
            'creator_subscriptions_quote_tweet_preview_enabled': False,
            'tweet_with_visibility_results_prefer_gql_media_interstitial_enabled': True,
            'rweb_video_timestamps_enabled': True,
        },
        'field_toggles': {'withArticlePlainText': False},
    },
    'user_highlights': {
        'url': 'https://twitter.com/i/api/graphql/w9-i9VNm_92GYFaiyGT1NA/UserHighlightsTweets',
        'features': {
            **_TIMELINE_FEATURES_BASE,
            'c9s_tweet_anatomy_moderator_badge_enabled': True,
            'rweb_video_timestamps_enabled': True,
        },
    },
    'user_likes': {
        'url': 'https://twitter.com/i/api/graphql/-fbTO1rKPa3nO6-XIRgEFQ/Likes',
        'features': {
            **_TIMELINE_FEATURES_BASE,
            'c9s_tweet_anatomy_moderator_badge_enabled': True,
            'rweb_video_timestamps_enabled': True,
        },
    },
    'search': {
        'url': 'https://x.com/i/api/graphql/AIdc203rPpK_k_2KWSdm7g/SearchTimeline',
        'features': _SEARCH_DETAIL_FEATURES,
        'require_tid': True,
    },
    'search_reply': {
        'url': 'https://x.com/i/api/graphql/yiE17ccAAu3qwM34bPYZkQ/SearchTimeline',
        'features': _SEARCH_DETAIL_FEATURES,
        'require_tid': True,
    },
    'tweet_detail': {
        'url': 'https://x.com/i/api/graphql/_8aYOgEDz35BrBcBal1-_w/TweetDetail',
        'features': _SEARCH_DETAIL_FEATURES,
        'field_toggles': {
            'withArticleRichContentState': True,
            'withArticlePlainText': False,
            'withGrokAnalyze': False,
            'withDisallowedReplyControls': False,
        },
        'require_tid': True,
    },
}


class TwitterAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, rate_limit_reset: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.rate_limit_reset = rate_limit_reset


# ==================== GraphQL 通用解析工具（兼容新旧两套字段） ====================

def unwrap_tweet(obj: dict) -> dict:
    if not isinstance(obj, dict):
        return {}
    if 'tweet' in obj and isinstance(obj['tweet'], dict):
        return obj['tweet']
    return obj


def extract_user_names(user_res: dict) -> Tuple[str, str]:
    if not isinstance(user_res, dict):
        return '', ''
    core = user_res.get('core') or {}
    legacy = user_res.get('legacy') or {}
    name = core.get('name') if core.get('name') is not None else legacy.get('name', '')
    screen_name = (
        core.get('screen_name')
        if core.get('screen_name') is not None
        else legacy.get('screen_name', '')
    )
    return name, screen_name


def extract_user_counts(user_res: dict) -> Tuple[int, int]:
    legacy = user_res.get('legacy') or {}
    tweet_counts = user_res.get('tweet_counts') or {}
    return (
        int(legacy.get('statuses_count', tweet_counts.get('statuses_count', 0)) or 0),
        int(legacy.get('media_count', tweet_counts.get('media_count', 0)) or 0),
    )


def extract_timeline_instructions(user_res: dict) -> list:
    if not isinstance(user_res, dict):
        return []
    tl_wrapper = user_res.get('timeline_v2') or user_res.get('timeline') or {}
    tl = tl_wrapper.get('timeline') or tl_wrapper
    instructions = tl.get('instructions')
    return instructions if isinstance(instructions, list) else []


def extract_entries(instructions: list) -> list:
    for inst in reversed(instructions or []):
        if isinstance(inst, dict) and inst.get('type') == 'TimelineAddEntries' and 'entries' in inst:
            return inst['entries']
    for inst in reversed(instructions or []):
        if isinstance(inst, dict) and 'entries' in inst:
            return inst['entries']
    return []


def extract_module_items(instructions: list) -> list:
    for inst in instructions or []:
        if isinstance(inst, dict) and 'moduleItems' in inst:
            return inst['moduleItems']
    return []


def is_terminated_bottom(instructions: list) -> bool:
    return any(
        isinstance(inst, dict)
        and inst.get('type') == 'TimelineTerminateTimeline'
        and inst.get('direction') == 'Bottom'
        for inst in (instructions or [])
    )


def extract_bottom_cursor(instructions: list) -> Optional[str]:
    for inst in reversed(instructions or []):
        if isinstance(inst, dict) and inst.get('type') == 'TimelineReplaceEntry':
            entry = inst.get('entry') or {}
            content = entry.get('content') or {}
            ctype = str(content.get('cursorType', '')).lower()
            eid = str(entry.get('entryId', '')).lower()
            if (ctype == 'bottom' or 'cursor-bottom' in eid) and content.get('value'):
                return content['value']

    for entry in reversed(extract_entries(instructions)):
        if not isinstance(entry, dict):
            continue
        eid = str(entry.get('entryId', '')).lower()
        content = entry.get('content') or {}
        ctype = str(content.get('cursorType', '')).lower()
        if ctype == 'bottom' or 'cursor-bottom' in eid or 'bottom' in eid or 'showmorethreads' in eid:
            val = content.get('value') or (content.get('itemContent') or {}).get('value')
            if val:
                return val
    return None


def extract_tweet_timestamp_msecs(tweet_obj: dict) -> Optional[int]:
    tweet_obj = unwrap_tweet(tweet_obj)
    legacy = tweet_obj.get('legacy') or {}
    created_at = legacy.get('created_at')
    if created_at:
        try:
            dt = datetime.strptime(created_at, '%a %b %d %H:%M:%S %z %Y')
            return int(dt.timestamp() * 1000)
        except Exception:
            pass

    ec = tweet_obj.get('edit_control') or {}
    if 'editable_until_msecs' in ec:
        return int(ec['editable_until_msecs']) - 3600000
    init_ec = ec.get('edit_control_initial') or {}
    if 'editable_until_msecs' in init_ec:
        return int(init_ec['editable_until_msecs']) - 3600000
    return None


def get_best_video_url(variants: list) -> Optional[str]:
    if not variants:
        return None
    if len(variants) == 1:
        return variants[0].get('url')
    best_url = None
    max_bitrate = -1
    for item in variants:
        if 'bitrate' in item and int(item['bitrate']) > max_bitrate:
            max_bitrate = int(item['bitrate'])
            best_url = item.get('url')
    if best_url:
        return best_url
    for item in variants:
        if '.mp4' in item.get('url', ''):
            return item['url']
    return variants[0].get('url')


def extract_full_text(tweet_obj: dict, strip_trailing_tco: bool = False) -> str:
    note = tweet_obj.get('note_tweet', {}).get('note_tweet_results', {}).get('result', {})
    text = note.get('text') or (tweet_obj.get('legacy') or {}).get('full_text', '')
    if strip_trailing_tco:
        text = re.sub(r'https?://t\.co/\w+\s*$', '', text).strip()
    return text


def parse_tweet_id_from_input(text: str) -> Tuple[Optional[str], str]:
    """从推文链接或纯数字 ID 提取 (tweet_id, user_name)。"""
    raw = text.strip()
    if raw.isdigit():
        return raw, ''
    m = re.search(r'(?:x|twitter)\.com/([^/]+)/status/(\d+)', raw)
    if m:
        return m.group(2), m.group(1)
    m2 = re.search(r'/status/(\d+)', raw)
    if m2:
        return m2.group(1), ''
    return None, ''


def extract_media_from_tweet(
    tweet_obj: dict,
    *,
    owner_screen_name: str = '',
    owner_name: str = '',
    has_video: bool = True,
    image_format: str = 'orig',
    include_retweet: bool = False,
    use_tweet_author: bool = False,
    filename_style: str = 'user',  # 'user' | 'search' | 'reply' | 'tweet'
    strip_trailing_tco: bool = False,
) -> List[MediaItem]:
    """统一抽取单条推文中的所有图片/视频 MediaItem（兼容原创、转推、喜欢、搜索、单推文）。"""
    tweet_obj = unwrap_tweet(tweet_obj)
    legacy = tweet_obj.get('legacy')
    if not isinstance(legacy, dict):
        return []

    tweet_msecs = extract_tweet_timestamp_msecs(tweet_obj)
    if tweet_msecs is None:
        return []

    is_retweet = 'retweeted_status_result' in legacy
    if is_retweet:
        if not include_retweet:
            return []
        rt_obj = unwrap_tweet(legacy['retweeted_status_result'].get('result', {}))
        rt_legacy = rt_obj.get('legacy') or {}
        author_name, author_sn = extract_user_names(
            rt_obj.get('core', {}).get('user_results', {}).get('result', {})
        )
        if owner_screen_name and author_sn.lower() == owner_screen_name.lower():
            return []
        target_obj = rt_obj
        target_legacy = rt_legacy
        fav = legacy.get('favorite_count', rt_legacy.get('favorite_count', 0))
        rt_cnt = legacy.get('retweet_count', rt_legacy.get('retweet_count', 0))
        rep_cnt = legacy.get('reply_count', rt_legacy.get('reply_count', 0))
    else:
        target_obj = tweet_obj
        target_legacy = legacy
        user_res = tweet_obj.get('core', {}).get('user_results', {}).get('result', {})
        parsed_name, parsed_sn = extract_user_names(user_res)
        if use_tweet_author or not owner_screen_name:
            author_name = parsed_name or owner_name
            author_sn = parsed_sn or owner_screen_name
        else:
            author_name = owner_name or parsed_name
            author_sn = owner_screen_name or parsed_sn
        fav = legacy.get('favorite_count', 0)
        rt_cnt = legacy.get('retweet_count', 0)
        rep_cnt = legacy.get('reply_count', 0)

    media_list = target_legacy.get('extended_entities', {}).get('media')
    if not media_list:
        return []

    tweet_id = target_obj.get('rest_id') or target_legacy.get('id_str') or ''
    full_text = extract_full_text(target_obj, strip_trailing_tco=strip_trailing_tco)
    time_str = format_timestamp(tweet_msecs, '%Y-%m-%d %H-%M')

    items: List[MediaItem] = []
    for idx, media in enumerate(media_list, start=1):
        is_vid = 'video_info' in media
        if is_vid and not has_video:
            continue

        if is_vid:
            raw_url = get_best_video_url(media['video_info'].get('variants', []))
            if not raw_url:
                continue
            download_url = raw_url
            media_type = 'Video'
            ext = 'mp4'
            tag_kind = 'vid'
        else:
            raw_url = media.get('media_url_https', '')
            if not raw_url:
                continue
            download_url, ext = build_image_download_url(raw_url, image_format)
            media_type = 'Image'
            tag_kind = 'img'

        tweet_url = media.get('expanded_url') or f'https://x.com/{author_sn}/status/{tweet_id}'
        if filename_style == 'search':
            fname = f'{time_str}_@{author_sn}_{tweet_id}_{idx}.{ext}'
        elif filename_style == 'reply':
            fname = f'{time_str}_@{author_sn}_{tweet_id}_{idx}_reply.{ext}'
        elif filename_style == 'tweet':
            fname = f'{time_str}_@{author_sn}_{tweet_id}_{idx}.{ext}'
        else:
            suffix = '-retweet' if is_retweet else ''
            fname = f'{time_str}-{tag_kind}{suffix}_{tweet_id}_{idx}.{ext}'

        items.append(
            MediaItem(
                url=raw_url,
                media_type=media_type,
                tweet_id=tweet_id,
                tweet_url=tweet_url,
                tweet_msecs=tweet_msecs,
                author_name=author_name,
                author_screen_name=author_sn,
                text=full_text,
                favorite_count=fav,
                retweet_count=rt_cnt,
                reply_count=rep_cnt,
                is_retweet=is_retweet,
                download_url=download_url,
                filename=fname,
            )
        )
    return items


def extract_text_record(tweet_obj: dict, *, include_retweet: bool = False) -> Optional[TweetRecord]:
    tweet_obj = unwrap_tweet(tweet_obj)
    legacy = tweet_obj.get('legacy')
    if not isinstance(legacy, dict):
        return None
    tweet_msecs = extract_tweet_timestamp_msecs(tweet_obj)
    if tweet_msecs is None:
        return None

    is_retweet = 'retweeted_status_result' in legacy
    if is_retweet:
        if not include_retweet:
            return None
        target = unwrap_tweet(legacy['retweeted_status_result'].get('result', {}))
        target_legacy = target.get('legacy') or {}
    else:
        target = tweet_obj
        target_legacy = legacy

    author_name, author_sn = extract_user_names(
        target.get('core', {}).get('user_results', {}).get('result', {})
    )
    if not author_sn:
        return None
    tweet_id = target.get('rest_id') or target_legacy.get('id_str') or target_legacy.get('conversation_id_str', '')
    text = extract_full_text(target, strip_trailing_tco=True)
    return TweetRecord(
        tweet_id=tweet_id,
        tweet_url=f'https://x.com/{author_sn}/status/{tweet_id}',
        tweet_msecs=tweet_msecs,
        author_name=author_name,
        author_screen_name=author_sn,
        text=text,
        favorite_count=target_legacy.get('favorite_count', 0),
        retweet_count=target_legacy.get('retweet_count', 0),
        reply_count=target_legacy.get('reply_count', 0),
        is_retweet=is_retweet,
    )


def extract_reply_from_entry(
    entry: dict,
    parent_tweet_url: str,
    *,
    media_down: bool = True,
    image_format: str = 'orig',
) -> Tuple[Optional[ReplyRecord], List[MediaItem]]:
    if 'conversationthread' not in entry.get('entryId', ''):
        return None, []
    items = entry.get('content', {}).get('items') or []
    if not items:
        return None, []
    first = items[0]
    if 'conversationthread' not in first.get('entryId', ''):
        return None, []

    reply_obj = unwrap_tweet(first.get('item', {}).get('itemContent', {}).get('tweet_results', {}).get('result', {}))
    legacy = reply_obj.get('legacy') or {}
    reply_msecs = extract_tweet_timestamp_msecs(reply_obj)
    if reply_msecs is None or not legacy:
        return None, []

    replier_name, replier_sn = extract_user_names(
        reply_obj.get('core', {}).get('user_results', {}).get('result', {})
    )
    if not replier_sn:
        return None, []

    reply_id = reply_obj.get('rest_id') or legacy.get('id_str', '')
    record = ReplyRecord(
        parent_tweet_url=parent_tweet_url,
        replier_name=replier_name,
        replier_screen_name=replier_sn,
        reply_msecs=reply_msecs,
        reply_text=extract_full_text(reply_obj, strip_trailing_tco=False),
        reply_url=f'https://x.com/{replier_sn}/status/{reply_id}',
        favorite_count=legacy.get('favorite_count', 0),
        retweet_count=legacy.get('retweet_count', 0),
        reply_count=legacy.get('reply_count', 0),
    )

    media_items: List[MediaItem] = []
    if media_down:
        media_items = extract_media_from_tweet(
            reply_obj,
            has_video=True,
            image_format=image_format,
            use_tweet_author=True,
            filename_style='reply',
        )
    return record, media_items


# ==================== 统一异步 Twitter API 客户端 ====================

class TwitterAPI:
    def __init__(
        self,
        cookie_str: str,
        ct0: str,
        *,
        proxy: Optional[str] = None,
        wait_on_rate_limit: bool = False,
        tx_provider: Optional[TransactionProvider] = None,
    ):
        self.cookie_str = cookie_str
        self.ct0 = ct0
        self.proxy = proxy
        self.wait_on_rate_limit = wait_on_rate_limit
        self.tx_provider = tx_provider or TransactionProvider(cookie=cookie_str, proxy=proxy)
        self.api_calls = 0
        self._base_headers = {
            'user-agent': DEFAULT_USER_AGENT,
            'authorization': DEFAULT_BEARER_TOKEN,
            'cookie': cookie_str,
            'x-csrf-token': ct0,
        }
        self._client = httpx.AsyncClient(
            proxy=proxy,
            timeout=httpx.Timeout(connect=8.0, read=25.0, write=15.0, pool=20.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )

    async def __aenter__(self) -> 'TwitterAPI':
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def close(self):
        await self._client.aclose()

    def build_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        h = dict(self._base_headers)
        if referer:
            h['referer'] = referer
        return h

    async def _graphql_get(
        self,
        endpoint_key: str,
        variables: dict,
        *,
        referer: Optional[str] = None,
        on_rate_limit: Optional[Callable[[int, int], None]] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> dict:
        ep = ENDPOINTS[endpoint_key]
        url = ep['url']
        require_tid = ep.get('require_tid', False)

        params = {
            'variables': json.dumps(variables, separators=(',', ':')),
            'features': json.dumps(ep['features'], separators=(',', ':')),
        }
        if 'field_toggles' in ep:
            params['fieldToggles'] = json.dumps(ep['field_toggles'], separators=(',', ':'))

        headers = self.build_headers(referer)
        if require_tid:
            headers['x-client-transaction-id'] = await self.tx_provider.async_generate_id('GET', url)

        tid_retries = 0
        while True:
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError()

            self.api_calls += 1
            response = await self._client.get(url, params=params, headers=headers)

            # 404 时尝试刷新 x-client-transaction-id 重试（最多 2 次）
            if response.status_code == 404 and tid_retries < 2:
                tid_retries += 1
                await self.tx_provider.async_refresh()
                headers['x-client-transaction-id'] = await self.tx_provider.async_generate_id('GET', url)
                continue

            # 429 限流处理（解析 x-rate-limit-reset）
            if response.status_code == 429 or 'Rate limit exceeded' in response.text:
                reset_raw = response.headers.get('x-rate-limit-reset')
                reset_ts = int(reset_raw) if reset_raw and reset_raw.isdigit() else None
                wait_secs = max(1, reset_ts - int(time.time()) + 2) if reset_ts else 900
                if self.wait_on_rate_limit:
                    if on_rate_limit:
                        on_rate_limit(reset_ts or int(time.time()) + wait_secs, wait_secs)
                    for _ in range(wait_secs):
                        if cancel_event and cancel_event.is_set():
                            raise asyncio.CancelledError()
                        await asyncio.sleep(1)
                    continue
                reset_hint = (
                    f'，预计重置时间 {time.strftime("%H:%M:%S", time.localtime(reset_ts))}'
                    if reset_ts else ''
                )
                raise TwitterAPIError(
                    f'API 调用次数已超限 (HTTP 429{reset_hint})',
                    status_code=429,
                    rate_limit_reset=reset_ts,
                )

            if response.status_code in (401, 403):
                raise TwitterAPIError(
                    f'Cookie 无效、已过期或无权访问 (HTTP {response.status_code})',
                    status_code=response.status_code,
                )
            if response.status_code != 200:
                raise TwitterAPIError(
                    f'接口 [{endpoint_key}] 请求失败 (HTTP {response.status_code}): {response.text[:200]}',
                    status_code=response.status_code,
                )

            try:
                data = response.json()
            except Exception as e:
                raise TwitterAPIError(f'接口 [{endpoint_key}] 返回非 JSON 内容: {e}') from e

            if 'errors' in data and not data.get('data'):
                raise TwitterAPIError(f'GraphQL 错误: {data["errors"]}')
            return data

    async def get_user_profile(self, screen_name: str, **kwargs) -> UserProfile:
        clean_sn = screen_name.strip().lstrip('@')
        data = await self._graphql_get(
            'user_profile',
            {'screen_name': clean_sn, 'withGrokTranslatedBio': False},
            referer=f'https://x.com/{clean_sn}',
            **kwargs,
        )
        user_res = data.get('data', {}).get('user', {}).get('result')
        if not user_res or 'rest_id' not in user_res:
            raise TwitterAPIError(f'未找到用户 @{clean_sn}（可能账号不存在、被冻结或已改名）')

        name, real_sn = extract_user_names(user_res)
        statuses_count, media_count = extract_user_counts(user_res)
        avatar_raw = (user_res.get('avatar') or {}).get('image_url') or (user_res.get('legacy') or {}).get('profile_image_url_https', '')
        avatar_url = re.sub(r'_normal(\.\w+)$', r'_400x400\1', avatar_raw) if avatar_raw else ''
        banner_url = (user_res.get('banner') or {}).get('image_url') or (user_res.get('legacy') or {}).get('profile_banner_url')
        description = (user_res.get('legacy') or {}).get('description')
        if description is None:
            description = (user_res.get('profile_bio') or {}).get('description', '')

        return UserProfile(
            screen_name=real_sn or clean_sn,
            rest_id=user_res['rest_id'],
            name=name,
            statuses_count=statuses_count,
            media_count=media_count,
            avatar_url=avatar_url,
            banner_url=banner_url,
            description=description or '',
        )

    async def fetch_user_timeline_page(
        self,
        user: UserProfile,
        *,
        mode: str = 'media',  # 'media' | 'retweet' | 'highlights' | 'likes' | 'text'
        cursor: str = '',
        first_page: bool = True,
        **kwargs,
    ) -> Tuple[List[dict], Optional[str], bool]:
        """返回 (本页推文条目列表, next_cursor, is_done)。"""
        if mode == 'highlights':
            ep_key = 'user_highlights'
            variables = {'userId': user.rest_id, 'count': 20, 'includePromotedContent': True, 'withVoice': True}
        elif mode == 'likes':
            ep_key = 'user_likes'
            variables = {
                'userId': user.rest_id, 'count': 200, 'includePromotedContent': False,
                'withClientEventToken': False, 'withBirdwatchNotes': False, 'withVoice': True, 'withV2Timeline': True,
            }
        elif mode == 'retweet':
            ep_key = 'user_tweets'
            variables = {
                'userId': user.rest_id, 'count': 20, 'includePromotedContent': False,
                'withQuickPromoteEligibilityTweetFields': True, 'withVoice': True, 'withV2Timeline': True,
            }
        elif mode == 'text':
            ep_key = 'user_text'
            variables = {
                'userId': user.rest_id, 'count': 20, 'cursor': cursor, 'includePromotedContent': True,
                'withQuickPromoteEligibilityTweetFields': True, 'withVoice': True, 'withV2Timeline': True,
            }
        else:
            ep_key = 'user_media'
            variables = {
                'userId': user.rest_id, 'count': 500, 'includePromotedContent': False,
                'withClientEventToken': False, 'withBirdwatchNotes': False, 'withVoice': True, 'withV2Timeline': True,
            }

        if cursor and mode != 'text':
            variables['cursor'] = cursor

        data = await self._graphql_get(ep_key, variables, referer=f'https://x.com/{user.screen_name}', **kwargs)
        user_res = data.get('data', {}).get('user', {}).get('result', {})
        instructions = extract_timeline_instructions(user_res)
        if not instructions:
            return [], None, True

        next_cursor = extract_bottom_cursor(instructions)
        terminated = is_terminated_bottom(instructions)

        if mode == 'media':
            if first_page:
                items = []
                for entry in extract_entries(instructions):
                    cand = entry.get('content', {}).get('items')
                    if isinstance(cand, list):
                        items = cand
                        break
            else:
                items = extract_module_items(instructions)
            is_done = not items or terminated or not next_cursor or next_cursor == cursor
            return items, next_cursor, is_done

        entries = extract_entries(instructions)
        if not entries or 'cursor-top' in entries[0].get('entryId', ''):
            return [], None, True
        is_done = terminated or not next_cursor or next_cursor == cursor
        return entries, next_cursor, is_done

    async def fetch_search_page(
        self,
        query: str,
        *,
        product: str = 'Media',
        cursor: str = '',
        count: int = 50,
        endpoint_key: str = 'search',
        first_page: bool = True,
        **kwargs,
    ) -> Tuple[List[dict], Optional[str], bool]:
        variables = {
            'rawQuery': query,
            'count': str(count) if endpoint_key == 'search_reply' else count,
            'cursor': cursor,
            'querySource': 'typed_query',
            'product': product,
        }
        data = await self._graphql_get(
            endpoint_key,
            variables,
            referer='https://x.com/search?src=typed_query&f=media',
            **kwargs,
        )
        instructions = (
            data.get('data', {})
            .get('search_by_raw_query', {})
            .get('search_timeline', {})
            .get('timeline', {})
            .get('instructions', [])
        )
        if not instructions:
            return [], None, True

        next_cursor = extract_bottom_cursor(instructions)
        terminated = is_terminated_bottom(instructions)

        if product == 'Media':
            if first_page:
                items = []
                for entry in extract_entries(instructions):
                    cand = entry.get('content', {}).get('items')
                    if isinstance(cand, list):
                        items = cand
                        break
            else:
                items = extract_module_items(instructions)
            is_done = not items or terminated or not next_cursor or next_cursor == cursor
            return items, next_cursor, is_done

        entries = [
            e for e in extract_entries(instructions)
            if 'tweet-' in e.get('entryId', '') and 'promoted' not in e.get('entryId', '')
        ]
        is_done = not entries or terminated or not next_cursor or next_cursor == cursor
        return entries, next_cursor, is_done

    async def fetch_tweet_detail_page(
        self,
        tweet_id: str,
        *,
        cursor: str = '',
        **kwargs,
    ) -> Tuple[Optional[dict], List[dict], Optional[str], bool]:
        variables = {
            'focalTweetId': tweet_id,
            'cursor': cursor,
            'referrer': 'tweet',
            'with_rux_injections': False,
            'rankingMode': 'Relevance',
            'includePromotedContent': False,
            'withCommunity': True,
            'withQuickPromoteEligibilityTweetFields': True,
            'withBirdwatchNotes': True,
            'withVoice': True,
        }
        data = await self._graphql_get(
            'tweet_detail',
            variables,
            referer=f'https://x.com/i/web/status/{tweet_id}',
            **kwargs,
        )
        instructions = (
            data.get('data', {})
            .get('threaded_conversation_with_injections_v2', {})
            .get('instructions', [])
        )
        entries = extract_entries(instructions)
        if not entries:
            return None, [], None, True

        focal_tweet = None
        reply_entries = []
        for entry in entries:
            eid = entry.get('entryId', '')
            if eid == f'tweet-{tweet_id}':
                focal_tweet = unwrap_tweet(
                    entry.get('content', {}).get('itemContent', {}).get('tweet_results', {}).get('result', {})
                )
            elif 'conversationthread' in eid:
                reply_entries.append(entry)

        terminated = is_terminated_bottom(instructions)
        next_cursor = extract_bottom_cursor(instructions)
        is_done = terminated or not next_cursor or next_cursor == cursor
        return focal_tweet, reply_entries, next_cursor, is_done

    async def download_bytes(self, url: str, referer: Optional[str] = None) -> bytes:
        resp = await self._client.get(url, headers=self.build_headers(referer))
        if resp.status_code != 200:
            raise TwitterAPIError(f'下载失败 (HTTP {resp.status_code}): {url}', status_code=resp.status_code)
        return resp.content
