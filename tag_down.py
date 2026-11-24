"""
兼容入口：按 Tag / 高级搜索下载（推荐使用 WebUI 或 `python main.py search` 命令行）。
"""
import asyncio
from core import download_search, load_config
from main import make_cli_progress, print_result

########## 配置区域 ##########
cookie = ''              # 留空自动使用 settings.json 或根目录 cookies.txt
tag = '#ヨルクラ'         # 标签（可留空）
_filter = ''             # 高级搜索条件（如 from:xxx）
down_count = 100         # 抓取推文数量上限
media_latest = False     # True=[最新]标签页媒体，False=[媒体]标签页
text_down = False        # True=纯文本导出 CSV
proxy = ''               # 留空自动沿用 settings.json
##############################


def run():
    config = load_config()
    if cookie:
        config.cookie = cookie
    if proxy:
        config.proxy = proxy
    search_mode = 'text' if text_down else ('media_latest' if media_latest else 'media')
    res = asyncio.run(
        download_search(
            config,
            tag,
            filter_query=_filter,
            search_mode=search_mode,
            limit=down_count,
            on_progress=make_cli_progress(),
            on_log=print,
        )
    )
    print_result(res)


if __name__ == '__main__':
    run()
