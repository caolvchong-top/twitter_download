import argparse
import asyncio
import sys
from typing import List

from core import (
    AppConfig,
    DownloadProgress,
    TaskResult,
    VALID_MODES,
    download_replies,
    download_search,
    download_tweet,
    download_user_media,
    download_user_profile,
    download_user_text,
    load_config,
)


MODE_LABELS = {
    'media': '仅本人媒体（图片/视频）',
    'retweet': '包含转推媒体',
    'highlights': '亮点 (Highlights)',
    'likes': '喜欢 (Likes，仅限登录账号本人)',
}


def make_cli_progress():
    def _on_progress(p: DownloadProgress):
        line = (
            f'\r[{p.phase}] 页数:{p.pages_fetched} | 发现:{p.items_found} '
            f'| 已下:{p.downloaded} | 跳过:{p.skipped} | 失败:{p.failed} | API:{p.api_calls}'
        )
        if p.message:
            line += f' | {p.message}'
        sys.stdout.write(line + '   ')
        sys.stdout.flush()
        if p.phase in ('done', 'cancelled', 'error'):
            sys.stdout.write('\n')
            sys.stdout.flush()

    return _on_progress


def print_result(res: TaskResult):
    status = '完成' if res.success else f'失败 ({res.error})'
    print(
        f'>>> 任务 [{res.task}] {status} | 耗时 {res.elapsed_seconds}s | API {res.api_calls} 次 '
        f'| 已下 {res.downloaded} | 跳过 {res.skipped} | 失败 {res.failed}'
    )
    if res.save_dir:
        print(f'    保存目录: {res.save_dir}')


async def run_config_batch(config: AppConfig):
    if not config.users:
        print('settings.json 中未配置任何用户 (users 为空)。')
        return
    print(f'开始按 settings.json 批量下载 ({len(config.users)} 个用户，模式: {MODE_LABELS.get(config.mode, config.mode)})')
    for u in config.users:
        print(f'\n--- 处理用户: @{u} ---')
        res = await download_user_media(
            config,
            u,
            on_progress=make_cli_progress(),
            on_log=print,
        )
        print_result(res)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='main.py',
        description='Twitter / X 命令行下载工具（无参数直接按 settings.json 批量运行；图形界面请运行 webui.py 或双击 start_webui.bat）',
    )
    parser.add_argument('--config-file', default='settings.json', help='配置文件路径（默认 settings.json）')
    parser.add_argument('--cookie', default='', help='临时覆盖 Cookie（文件路径或字符串）')
    parser.add_argument('--proxy', default='', help='临时覆盖代理地址')
    parser.add_argument('--save-path', default='', help='临时覆盖保存目录')

    sub = parser.add_subparsers(dest='command')

    sub.add_parser('run', help='按 settings.json 批量运行（默认行为）')

    p_user = sub.add_parser('user', help='下载指定用户媒体')
    p_user.add_argument('users', nargs='+', help='用户名列表（可带或不带 @）')
    p_user.add_argument('--mode', choices=VALID_MODES, default=None, help='下载模式')
    p_user.add_argument('--time-range', default=None, help='时间范围 YYYY-MM-DD:YYYY-MM-DD')

    p_tweet = sub.add_parser('tweet', help='下载单条或多条推文媒体')
    p_tweet.add_argument('targets', nargs='+', help='推文链接或推文 ID')

    p_search = sub.add_parser('search', help='按标签 / 关键词搜索下载')
    p_search.add_argument('query', help='标签或搜索词（如 #ヨルクラ）')
    p_search.add_argument('--filter', default='', help='附加高级搜索条件')
    p_search.add_argument('--type', dest='search_mode', choices=('media', 'media_latest', 'text'), default='media')
    p_search.add_argument('--limit', type=int, default=100, help='抓取数量上限（默认 100）')

    p_reply = sub.add_parser('reply', help='下载推文或用户评论区')
    p_reply.add_argument('targets', nargs='+', help='推文链接或 @用户名')
    p_reply.add_argument('--time-range', default='', help='时间范围（对用户生效）')
    p_reply.add_argument('--no-media', action='store_true', help='仅导出评论文本 CSV，不下载评论媒体')

    p_text = sub.add_parser('text', help='下载指定用户纯文本推文')
    p_text.add_argument('users', nargs='+', help='用户名列表')
    p_text.add_argument('--time-range', default=None, help='时间范围 YYYY-MM-DD:YYYY-MM-DD')
    p_text.add_argument('--retweet', action='store_true', help='包含转推')

    p_profile = sub.add_parser('profile', help='下载用户头像 / Banner / 简介')
    p_profile.add_argument('users', nargs='+', help='用户名列表')

    return parser


async def run_cli(argv: List[str] = None):
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config_file)
    if args.cookie:
        config.cookie = args.cookie
    if args.proxy:
        config.proxy = args.proxy
    if args.save_path:
        config.save_path = args.save_path

    if not args.command or args.command == 'run':
        await run_config_batch(config)
    elif args.command == 'user':
        for u in args.users:
            res = await download_user_media(
                config, u, mode=args.mode, time_range=args.time_range,
                on_progress=make_cli_progress(), on_log=print,
            )
            print_result(res)
    elif args.command == 'tweet':
        for t in args.targets:
            res = await download_tweet(
                config, t, on_progress=make_cli_progress(), on_log=print,
            )
            print_result(res)
    elif args.command == 'search':
        res = await download_search(
            config, args.query, filter_query=args.filter, search_mode=args.search_mode, limit=args.limit,
            on_progress=make_cli_progress(), on_log=print,
        )
        print_result(res)
    elif args.command == 'reply':
        for t in args.targets:
            res = await download_replies(
                config, t, time_range=args.time_range, media_down=not args.no_media,
                on_progress=make_cli_progress(), on_log=print,
            )
            print_result(res)
    elif args.command == 'text':
        for u in args.users:
            res = await download_user_text(
                config, u, time_range=args.time_range, include_retweet=args.retweet,
                on_progress=make_cli_progress(), on_log=print,
            )
            print_result(res)
    elif args.command == 'profile':
        for u in args.users:
            res = await download_user_profile(
                config, u, on_progress=make_cli_progress(), on_log=print,
            )
            print_result(res)


if __name__ == '__main__':
    try:
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        print('\n已取消任务。')
