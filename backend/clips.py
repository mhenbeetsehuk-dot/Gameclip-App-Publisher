"""Bounded, single-user clip creation and temporary downloads."""
import os
from . import store
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from .clipper import action_windows, render, duration

router = APIRouter()
ROOT = Path(os.getenv('CLIP_DIR', str(store.data_dir() / 'clips')))
LOCK = threading.Lock()
MAX_BYTES = 200 * 1024 * 1024
TTL = 24 * 3600


def authorize(x_api_key: str = Header(default='')):
    expected = os.getenv('GAMECLIP_API_KEY', '')
    if not expected:
        raise HTTPException(503, 'Set GAMECLIP_API_KEY on the server before creating clips.')
    if not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(401, 'Enter the correct access key in Settings.')


@router.post('/api/create-clips', dependencies=[Depends(authorize)])
def create_clips(video: UploadFile = File(...), clip_count: int = Form(6, ge=1, le=15),
                 clip_duration: int = Form(30, ge=5, le=60), vertical: bool = Form(True)):
    if not LOCK.acquire(blocking=False):
        raise HTTPException(409, 'Another video is processing. Please try again shortly.')
    work = None
    try:
        if not all(shutil.which(x) for x in ('ffmpeg', 'ffprobe')):
            raise HTTPException(503, 'The server needs FFmpeg and ffprobe installed.')
        ROOT.mkdir(parents=True, exist_ok=True)
        for old in ROOT.iterdir():
            if not store.durable() and old.is_dir() and old.stat().st_mtime < time.time() - TTL:
                shutil.rmtree(old)
        if shutil.disk_usage(ROOT).free < 600*1024*1024:
            raise HTTPException(507,'Server storage is nearly full. Remove downloaded clips before uploading more.')
        ext = Path(video.filename or '').suffix.lower()
        if ext not in {'.mp4', '.mov', '.mkv', '.webm', '.m4v'}:
            raise HTTPException(400, 'Choose an MP4, MOV, MKV, WebM or M4V video.')
        work = Path(tempfile.mkdtemp(dir=ROOT, prefix='job-'))
        src = work / ('source' + ext)
        size = 0
        with src.open('wb') as dest:
            while chunk := video.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, 'Choose a video smaller than 200 MB.')
                dest.write(chunk)
        if not size:
            raise HTTPException(400, 'The selected video is empty.')
        try:
            seconds = duration(src)
            if not 0 < seconds <= 1800:
                raise ValueError('invalid duration')
            windows = action_windows(src, clip_count, clip_duration)
        except (ValueError, subprocess.SubprocessError):
            raise HTTPException(400, 'Use a readable video no longer than 30 minutes.')
        clips = []
        for i, (_, start) in enumerate(windows, 1):
            name = f'clip_{i:02d}.mp4'
            render(src, start, work / name, min(seconds, clip_duration), vertical=vertical)
            clip_id = secrets.token_hex(16)
            clips.append({'id': clip_id, 'name': name, 'start': round(start, 2),
                          'download_path': f'/api/clips/{work.name}/{name}'})
        if store.durable():
            with store.db() as c:
                for clip in clips:
                    c.execute('INSERT INTO clips VALUES(?,?,?,?)',(clip['id'],clip['name'],str(work/clip['name']),time.time()))
        src.unlink()
        return {'clips': clips, 'status': 'created', 'storage': 'persistent' if store.durable() else 'temporary',
                'message': 'Clips saved for scheduling.' if store.durable() else 'Download clips before the server restarts. Scheduling requires persistent storage.'}
    except HTTPException:
        if work:
            shutil.rmtree(work, ignore_errors=True)
        raise
    except (subprocess.SubprocessError, OSError):
        if work:
            shutil.rmtree(work, ignore_errors=True)
        raise HTTPException(500, 'Video processing failed. Try a shorter MP4 video.')
    finally:
        video.file.close()
        LOCK.release()


@router.get('/api/clips/{job}/{name}', dependencies=[Depends(authorize)])
def download_clip(job: str, name: str):
    if not job.startswith('job-') or Path(job).name != job or Path(name).name != name:
        raise HTTPException(404, 'Clip not found.')
    path = ROOT / job / name
    if not name.startswith('clip_') or not name.endswith('.mp4') or not path.is_file():
        raise HTTPException(404, 'Clip not found. Create it again if the server restarted.')
    return FileResponse(path, media_type='video/mp4', filename=name)
