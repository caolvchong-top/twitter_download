"""
启动 WebUI（仅本机 127.0.0.1 可访问）：

    python webui.py                    # 默认 http://127.0.0.1:7860 并自动打开浏览器
    python webui.py --port 8080 --no-browser
    python webui.py --max-parallel 2   # 同时运行 2 个任务（默认 1，避免触发限流）
"""

import argparse
import os
import sys
import threading
import webbrowser


def main():
    parser = argparse.ArgumentParser(description='Twitter / X 下载器 WebUI（仅限本机访问）')
    parser.add_argument('--port', type=int, default=7860, help='监听端口（默认 7860）')
    parser.add_argument('--config-file', default='settings.json', help='配置文件路径（默认 settings.json）')
    parser.add_argument('--max-parallel', type=int, default=1, help='同时运行的任务数（默认 1，避免触发限流）')
    parser.add_argument('--no-browser', action='store_true', help='启动后不自动打开浏览器')
    args = parser.parse_args()

    # 与 CLI 保持一致：相对路径（cookies.txt / 保存目录）均以项目根目录为基准
    project_root = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.abspath(args.config_file)
    os.chdir(project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        import uvicorn
    except ImportError:
        print('缺少依赖：请先执行  pip install -r requirements.txt')
        sys.exit(1)

    from webui import create_app

    host = '127.0.0.1'
    app = create_app(config_path=config_path, max_parallel=args.max_parallel)
    url = f'http://{host}:{args.port}'
    print(f'WebUI 已启动（仅本机可访问）: {url}  (Ctrl+C 退出)')

    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=host, port=args.port, log_level='warning', timeout_graceful_shutdown=3)


if __name__ == '__main__':
    main()
