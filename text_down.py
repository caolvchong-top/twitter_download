"""
兼容入口：用户纯文本推文下载（推荐使用 WebUI 或 `python main.py text` 命令行）。
"""
import asyncio
from core import TwitterAPI, download_user_text, load_config
from main import make_cli_progress, print_result

########## 配置区域 ##########
cookie = ''              # 留空自动使用 settings.json 或根目录 cookies.txt
user_lst = ['jeleechandayo', 'yorukura_anime']
time_range = '2024-04-21:2030-01-01'
has_retweet = False
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
        for user in user_lst:
            res = await download_user_text(
                config,
                user,
                time_range=time_range,
                include_retweet=has_retweet,
                api=api,
                on_progress=make_cli_progress(),
                on_log=print,
            )
            print_result(res)


if __name__ == '__main__':
    asyncio.run(run())
