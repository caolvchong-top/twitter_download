"""
WebUI 后端：FastAPI + SSE。

  - /api/config        读取 / 保存 settings.json
  - /api/cookie/*      检查 / 上传 Cookie
  - /api/user/{name}   预览用户资料（同时可在线校验 Cookie）
  - /api/tasks         创建 / 列出 / 取消 / 重试 / 删除任务
  - /api/events        SSE 实时推送任务进度与日志
  - /api/gallery       浏览已下载的文件夹与媒体
"""

import asyncio
import dataclasses
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from core import (
    AppConfig,
    TwitterAPI,
    VALID_IMAGE_FORMATS,
    VALID_MODES,
    load_config,
    parse_netscape_cookie_file,
    save_config,
)
from core.config import extract_cookie_pair

from .task_manager import JOB_TYPES, TaskManager

try:  # 可选依赖：用于生成图库缩略图
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
THUMB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.thumbs')
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
VIDEO_EXTS = {'.mp4', '.mov', '.webm', '.m4v'}
DOC_EXTS = {'.csv', '.md', '.txt'}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS
IGNORED_DIRS = {'core', 'webui', 'docs', 'assets', '__pycache__', 'node_modules', 'venv'}
MASK_MARK = '••••'


def create_app(config_path: str = 'settings.json', max_parallel: int = 1) -> FastAPI:
    config_path = os.path.abspath(config_path)
    manager = TaskManager(max_parallel=max_parallel)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        manager.start()
        yield
        await manager.stop()

    app = FastAPI(title='Twitter / X Downloader WebUI', lifespan=lifespan)

    # ------------------------------------------------------------------ helpers
    def get_config() -> AppConfig:
        return load_config(config_path)

    def mask_cookie(cookie: str) -> str:
        """若 cookie 是原始 auth_token 字符串则脱敏，文件路径原样返回。"""
        if 'auth_token=' not in cookie:
            return cookie
        try:
            normalized, _ = extract_cookie_pair(cookie)
        except ValueError:
            return cookie
        auth = normalized.split('auth_token=')[1].split(';')[0]
        return f'auth_token={auth[:4]}{MASK_MARK}{auth[-4:]}; ct0={MASK_MARK};'

    def cookie_status(cfg: AppConfig) -> Dict[str, Any]:
        try:
            cfg.resolve_auth()
            is_manual = 'auth_token=' in cfg.cookie
            src = '手动填写的 auth_token' if is_manual else cfg.cookie
            return {
                'ok': True,
                'source': '' if is_manual else cfg.cookie,
                'is_manual': is_manual,
                'message': f'已就绪（{src}）',
            }
        except Exception as e:  # noqa: BLE001
            return {'ok': False, 'message': str(e)}

    def save_root(cfg: Optional[AppConfig] = None) -> str:
        return (cfg or get_config()).resolved_save_root()

    def is_within_root(target: str, root: str) -> bool:
        try:
            return os.path.commonpath([os.path.abspath(target), os.path.abspath(root)]) == os.path.abspath(root)
        except ValueError:
            # Windows 跨盘符路径（如 C:\ 与 D:\）
            return False

    def safe_join(root: str, *parts: str) -> str:
        path = os.path.abspath(os.path.join(root, *parts))
        if not is_within_root(path, root):
            raise HTTPException(403, '非法路径')
        return path

    def thumb_cache_stats() -> Dict[str, Any]:
        files = 0
        total_bytes = 0
        if os.path.isdir(THUMB_DIR):
            for dirpath, _dirnames, filenames in os.walk(THUMB_DIR):
                for name in filenames:
                    files += 1
                    try:
                        total_bytes += os.path.getsize(os.path.join(dirpath, name))
                    except OSError:
                        pass
        return {'files': files, 'bytes': total_bytes, 'path': THUMB_DIR}

    def config_payload(cfg: AppConfig, thumb_cache: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = cfg.to_settings_dict()
        data['cookie'] = mask_cookie(cfg.cookie)
        return {
            'config': data,
            'cookie_status': cookie_status(cfg),
            'resolved_save_root': cfg.resolved_save_root(),
            'config_path': config_path,
            'valid_modes': list(VALID_MODES),
            'valid_image_formats': list(VALID_IMAGE_FORMATS),
            'job_types': JOB_TYPES,
            'thumb_cache': thumb_cache if thumb_cache is not None else thumb_cache_stats(),
        }

    # ------------------------------------------------------------------ config
    @app.get('/api/config')
    async def api_get_config():
        cache = await asyncio.to_thread(thumb_cache_stats)
        return config_payload(get_config(), thumb_cache=cache)

    @app.put('/api/config')
    async def api_put_config(payload: Dict[str, Any] = Body(...)):
        old = get_config()
        incoming = dict(payload)
        cookie_val = str(incoming.get('cookie', '') or '')
        if MASK_MARK in cookie_val:
            incoming['cookie'] = old.cookie  # 前端未修改脱敏值，保留原值
        try:
            cfg = AppConfig.from_dict(incoming)
        except (TypeError, ValueError) as e:
            raise HTTPException(400, f'配置格式错误: {e}') from e
        save_config(cfg, config_path)
        cache = await asyncio.to_thread(thumb_cache_stats)
        return config_payload(cfg, thumb_cache=cache)

    # ------------------------------------------------------------------ cache
    @app.get('/api/cache/thumbs')
    async def api_thumb_cache():
        return await asyncio.to_thread(thumb_cache_stats)

    @app.post('/api/cache/thumbs/clear')
    async def api_clear_thumb_cache():
        def clear():
            before = thumb_cache_stats()
            if os.path.isdir(THUMB_DIR):
                shutil.rmtree(THUMB_DIR, ignore_errors=True)
            after = thumb_cache_stats()
            return before, after

        before, after = await asyncio.to_thread(clear)
        return {
            'ok': True,
            'cleared_files': max(0, before['files'] - after['files']),
            'cleared_bytes': max(0, before['bytes'] - after['bytes']),
            'thumb_cache': after,
        }

    # ------------------------------------------------------------------ cookie
    @app.post('/api/cookie/upload')
    async def api_cookie_upload(payload: Dict[str, Any] = Body(...)):
        """接收前端读取的 cookies.txt 文本，校验后保存为项目根目录 cookies.txt 并写入配置。"""
        content = str(payload.get('content', ''))
        filename = os.path.basename(str(payload.get('filename') or 'cookies.txt')) or 'cookies.txt'
        if not filename.lower().endswith('.txt'):
            filename += '.txt'
        if not content.strip():
            raise HTTPException(400, '文件内容为空')

        fd, tmp = tempfile.mkstemp(suffix='.txt')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            parse_netscape_cookie_file(tmp)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

        dest = os.path.join(os.path.dirname(config_path), filename)
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(content)
        cfg = get_config()
        cfg.cookie = filename
        save_config(cfg, config_path)
        return config_payload(cfg)

    @app.post('/api/cookie/verify')
    async def api_cookie_verify(payload: Dict[str, Any] = Body(default={})):
        """在线校验 Cookie：支持直接校验表单中尚未保存的临时 Cookie 与代理。"""
        cfg = get_config()
        if 'cookie' in payload:
            raw_cookie = str(payload.get('cookie') or '').strip()
            if raw_cookie and MASK_MARK not in raw_cookie:
                cfg = dataclasses.replace(cfg, cookie=raw_cookie)
        if 'proxy' in payload:
            cfg = dataclasses.replace(cfg, proxy=str(payload.get('proxy') or '').strip())
        username = str(payload.get('username') or (cfg.users[0] if cfg.users else 'X')).lstrip('@')
        try:
            cookie_str, ct0 = cfg.resolve_auth()
        except Exception as e:  # noqa: BLE001
            return {'ok': False, 'message': str(e)}
        api = TwitterAPI(cookie_str, ct0, proxy=cfg.resolved_proxy())
        try:
            prof = await asyncio.wait_for(api.get_user_profile(username), timeout=30)
            return {'ok': True, 'message': f'Cookie 有效，成功获取 @{prof.screen_name}', 'profile': prof.to_dict()}
        except Exception as e:  # noqa: BLE001
            return {'ok': False, 'message': f'{type(e).__name__}: {e}'}
        finally:
            await api.close()

    @app.get('/api/user/{username}')
    async def api_user_profile(username: str):
        cfg = get_config()
        try:
            cookie_str, ct0 = cfg.resolve_auth()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, str(e)) from e
        api = TwitterAPI(cookie_str, ct0, proxy=cfg.resolved_proxy())
        try:
            prof = await asyncio.wait_for(api.get_user_profile(username), timeout=30)
            return prof.to_dict()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f'{e}') from e
        finally:
            await api.close()

    # ------------------------------------------------------------------ tasks
    @app.get('/api/tasks')
    async def api_list_tasks():
        return manager.list_jobs()

    @app.post('/api/tasks')
    async def api_create_task(payload: Dict[str, Any] = Body(...)):
        job_type = str(payload.get('type', ''))
        params = payload.get('params') or {}
        cfg = get_config()
        if job_type == 'batch':
            if not cfg.users:
                raise HTTPException(400, '设置中未配置批量下载用户 (users 为空)')
            job_type = 'user_media'
            params = {'targets': list(cfg.users), 'mode': cfg.mode}
        try:
            job = manager.create_job(job_type, params, cfg)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return job.summary()

    @app.post('/api/tasks/{job_id}/cancel')
    async def api_cancel_task(job_id: str):
        if not manager.cancel_job(job_id):
            raise HTTPException(400, '任务不存在或已结束')
        return {'ok': True}

    @app.post('/api/tasks/{job_id}/retry')
    async def api_retry_task(job_id: str):
        try:
            job = manager.retry_job(job_id, get_config())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return job.summary()

    @app.delete('/api/tasks/{job_id}')
    async def api_delete_task(job_id: str):
        if not manager.remove_job(job_id):
            raise HTTPException(400, '任务不存在或仍在运行')
        return {'ok': True}

    @app.post('/api/tasks/clear')
    async def api_clear_tasks():
        return {'removed': manager.clear_finished()}

    @app.get('/api/tasks/{job_id}/logs')
    async def api_task_logs(job_id: str, limit: int = 1000):
        return manager.get_logs(job_id, limit)

    @app.get('/api/events')
    async def api_events(request: Request):
        queue = manager.subscribe()

        async def gen():
            try:
                yield _sse('snapshot', manager.list_jobs())
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event, data = await asyncio.wait_for(queue.get(), timeout=15)
                        yield _sse(event, data)
                    except asyncio.TimeoutError:
                        yield ': ping\n\n'
            finally:
                manager.unsubscribe(queue)

        return StreamingResponse(
            gen(),
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )

    # ------------------------------------------------------------------ gallery
    @app.get('/api/gallery')
    async def api_gallery():
        root = save_root()

        def scan() -> List[Dict[str, Any]]:
            folders = []
            if not os.path.isdir(root):
                return folders
            for entry in os.scandir(root):
                if not entry.is_dir() or entry.name.startswith('.') or entry.name in IGNORED_DIRS:
                    continue
                images = videos = docs = 0
                cover = None
                latest = 0.0
                try:
                    for f in os.scandir(entry.path):
                        if not f.is_file():
                            continue
                        ext = os.path.splitext(f.name)[1].lower()
                        if ext in IMAGE_EXTS:
                            images += 1
                        elif ext in VIDEO_EXTS:
                            videos += 1
                        elif ext in DOC_EXTS:
                            docs += 1
                        else:
                            continue
                        mtime = f.stat().st_mtime
                        if mtime > latest:
                            latest = mtime
                        if ext in IMAGE_EXTS and (cover is None or f.name > cover):
                            cover = f.name
                except OSError:
                    continue
                if images or videos or docs:
                    folders.append({
                        'name': entry.name,
                        'images': images,
                        'videos': videos,
                        'docs': docs,
                        'cover': cover,
                        'mtime': latest,
                    })
            folders.sort(key=lambda x: x['mtime'], reverse=True)
            return folders

        return {'root': root, 'folders': await asyncio.to_thread(scan)}

    @app.get('/api/gallery/{folder}')
    async def api_gallery_folder(
        folder: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(60, ge=1, le=500),
        kind: str = Query('media'),  # media | image | video | doc | all
        q: str = Query(''),
    ):
        root = save_root()
        path = safe_join(root, folder)
        if not os.path.isdir(path):
            raise HTTPException(404, '文件夹不存在')

        def scan():
            items = []
            for f in os.scandir(path):
                if not f.is_file():
                    continue
                ext = os.path.splitext(f.name)[1].lower()
                if ext in IMAGE_EXTS:
                    t = 'image'
                elif ext in VIDEO_EXTS:
                    t = 'video'
                elif ext in DOC_EXTS:
                    t = 'doc'
                else:
                    continue
                if kind == 'media' and t == 'doc':
                    continue
                if kind in ('image', 'video', 'doc') and t != kind:
                    continue
                if q and q.lower() not in f.name.lower():
                    continue
                st = f.stat()
                items.append({'name': f.name, 'type': t, 'size': st.st_size, 'mtime': st.st_mtime})
            items.sort(key=lambda x: (x['name']), reverse=True)
            return items

        items = await asyncio.to_thread(scan)
        return {'folder': folder, 'total': len(items), 'items': items[offset:offset + limit]}

    @app.get('/media/{folder}/{filename}')
    async def api_media(folder: str, filename: str):
        path = safe_join(save_root(), folder, filename)
        if not os.path.isfile(path):
            raise HTTPException(404, '文件不存在')
        media_type, _ = mimetypes.guess_type(path)
        if path.lower().endswith(('.csv', '.md', '.txt')):
            media_type = 'text/plain; charset=utf-8'
        return FileResponse(path, media_type=media_type)

    @app.get('/thumb/{folder}/{filename}')
    async def api_thumb(folder: str, filename: str, size: int = Query(400, ge=64, le=1024)):
        """图库缩略图：安装了 Pillow 时生成并缓存 JPEG 缩略图，否则直接返回原图。"""
        path = safe_join(save_root(), folder, filename)
        if not os.path.isfile(path):
            raise HTTPException(404, '文件不存在')
        if Image is None or os.path.splitext(path)[1].lower() not in IMAGE_EXTS:
            return FileResponse(path)

        st = os.stat(path)
        key = hashlib.md5(f'{path}|{st.st_mtime_ns}|{st.st_size}|{size}'.encode('utf-8')).hexdigest()
        thumb_path = os.path.join(THUMB_DIR, key[:2], key + '.jpg')
        if not os.path.isfile(thumb_path):
            def make():
                os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
                with Image.open(path) as im:
                    im.thumbnail((size, size))
                    if im.mode not in ('RGB', 'L'):
                        im = im.convert('RGB')
                    tmp = thumb_path + '.tmp'
                    im.save(tmp, 'JPEG', quality=82, optimize=True)
                    os.replace(tmp, thumb_path)
            try:
                await asyncio.to_thread(make)
            except Exception:  # noqa: BLE001 损坏或不支持的图片直接回退原图
                return FileResponse(path)
        return FileResponse(thumb_path, media_type='image/jpeg', headers={'Cache-Control': 'public, max-age=604800'})

    @app.post('/api/open-folder')
    async def api_open_folder(payload: Dict[str, Any] = Body(...)):
        """在系统文件管理器中打开目录（仅限保存根目录内，且仅本机访问时有意义）。"""
        root = save_root()
        rel = str(payload.get('path', '') or '')
        target = os.path.abspath(rel) if os.path.isabs(rel) else safe_join(root, rel)
        if not is_within_root(target, root):
            raise HTTPException(403, '只能打开保存目录内的文件夹')
        if not os.path.exists(target):
            raise HTTPException(404, '目录不存在')
        try:
            if sys.platform.startswith('win'):
                os.startfile(target)  # type: ignore[attr-defined]
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', target])
            else:
                subprocess.Popen(['xdg-open', target])
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f'无法打开目录: {e}') from e
        return {'ok': True}

    # ------------------------------------------------------------------ errors & static
    @app.exception_handler(HTTPException)
    async def http_exc_handler(_req: Request, exc: HTTPException):
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)

    @app.get('/')
    async def index():
        return FileResponse(os.path.join(STATIC_DIR, 'index.html'))

    app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
    return app


def _sse(event: str, data: Any) -> str:
    return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'
