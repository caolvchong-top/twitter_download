"""
兼容入口：评论区下载（推荐使用 WebUI 或 `python main.py reply` 命令行）。
"""
import asyncio
from core import TwitterAPI, download_replies, load_config
from main import make_cli_progress, print_result

########## 配置区域 ##########
cookie = ''              # 留空自动使用 settings.json 或根目录 cookies.txt
target_user = [
    'https://x.com/matchach/status/1855589540905590962',
    '@lilmonix3',
    'https://x.com/yorukura_anime/status/1895307947950924182',
]
time_range = '2024-02-06:2024-08-06'  # 仅对 @用户名 生效，留空不限
media_down = True
min_replies = 1
min_faves = 0
min_retweets = 0
search_advanced = ''
proxy = ''               # 留空自动沿用 settings.json
##############################


async def run():
    config = load_config()
    if cookie:
        config.cookie = cookie
    if proxy:
        config.proxy = proxy
    cookie_str, ct0 = config.resolve_auth()
    async with TwitterAPI(
        cookie_str, ct0, proxy=config.resolved_proxy(), wait_on_rate_limit=config.wait_on_rate_limit
    ) as api:
        targets = [search_advanced] if search_advanced else target_user
        for target in targets:
            print(f'开始处理: {target}')
            res = await download_replies(
                config,
                target,
                time_range=time_range,
                media_down=media_down,
                min_replies=min_replies,
                min_faves=min_faves,
                min_retweets=min_retweets,
                search_advanced=search_advanced,
                api=api,
                on_progress=make_cli_progress(),
                on_log=print,
            )
            print_result(res)


if __name__ == '__main__':
    asyncio.run(run())
