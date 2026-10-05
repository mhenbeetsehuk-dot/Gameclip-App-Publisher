"""Bounded video uploads and sequential, asynchronous clip creation."""
import math
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import store
from .clipper import action_windows, duration, render

router = APIRouter()
ROOT = Path(os.getenv('CLIP_DIR', str(store.data_dir() / 'clips')))
LOCK = threading.Lock()
JOBS_LOCK = threading.Lock()
JOBS = {}
MAX_BYTES = int(os.getenv('MAX_VIDEO_UPLOAD_BYTES', str(2 * 1024 * 1024 * 1024)))
SEGMENT_SECONDS = 10 * 60
TTL = 24 * 3600


def authorize(x_api_key: str = Header(default='')):
    expected = os.getenv('GAMECLIP_API_KEY', '')
    if not expected:
        raise HTTPException(503, 'Set GAMECLIP_API_KEY on the server before creating clips.')
    if not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(401, 'Enter the correct access key in Settings.')


def _set_job(job_id, **updates):
    with JOBS_LOCK:
        JOBS[job_id].update(updates)


def _prune_jobs():
    cutoff = time.time() - TTL
    with JOBS_LOCK:
        for job_id, job in list(JOBS.items()):
            if job.get('status') != 'processing' and job.get('created', 0) < cutoff:
                JOBS.pop(job_id, None)


def _clip_quotas(segment_count, clip_count):
    """Spread the requested clip count across the source, preserving order."""
    quotas = [0] * segment_count
    for clip_index in range(clip_count):
        segment_index = min(segment_count - 1, int((clip_index + 0.5) * segment_count / clip_count))
        quotas[segment_index] += 1
    return quotas


def _process_video(job_id, work, src, seconds, clip_count, clip_duration, vertical):
    try:
        segment_count = max(1, math.ceil(seconds / SEGMENT_SECONDS))
        quotas = _clip_quotas(segment_count, clip_count)
        clips = []
        segment_start = 0
        for segment_index, quota in enumerate(quotas):
            segment_end = min(seconds, segment_start + SEGMENT_SECONDS)
            _set_job(job_id, progress=segment_index / segment_count,
                     message=f'Processing 10-minute batch {segment_index + 1} of {segment_count}…')
            if quota:
                windows = action_windows(
                    src, quota, clip_duration,
                    region_start=segment_start, region_end=segment_end,
                )
                for _, start in windows:
                    name = f'clip_{len(clips) + 1:02d}.mp4'
                    render(src, start, work / name, min(seconds - start, clip_duration), vertical=vertical)
                    clip_id = secrets.token_hex(16)
                    clips.append({'id': clip_id, 'name': name, 'start': round(start, 2),
                                  'download_path': f'/api/clips/{work.name}/{name}'})
            segment_start = segment_end
            _set_job(job_id, progress=(segment_index + 1) / segment_count)

        if not clips:
            raise ValueError('No usable clips were found in this video.')
        if store.durable():
            with store.db() as c:
                for clip in clips:
                    c.execute('INSERT INTO clips VALUES(?,?,?,?)',
                              (clip['id'], clip['name'], str(work / clip['name']), time.time()))
        src.unlink(missing_ok=True)
        _set_job(job_id, status='completed', progress=1, clips=clips,
                 storage='persistent' if store.durable() else 'temporary',
                 message='Clips saved for scheduling.' if store.durable() else
                 'Download clips before the server restarts. Scheduling requires persistent storage.')
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        shutil.rmtree(work, ignore_errors=True)
        _set_job(job_id, status='failed', message=str(exc) or 'Video processing failed. Try a shorter MP4 video.')
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        _set_job(job_id, status='failed', message='Video processing failed. Try a shorter MP4 video.')
    finally:
        LOCK.release()


@router.post('/api/create-clips', status_code=202, dependencies=[Depends(authorize)])
def create_clips(video: UploadFile = File(...), clip_count: int = Form(6, ge=1, le=15),
                 clip_duration: int = Form(30, ge=5, le=60), vertical: bool = Form(True)):
    if not LOCK.acquire(blocking=False):
        raise HTTPException(409, 'Another video is processing. Please try again shortly.')
    work = None
    handed_off = False
    try:
        if not all(shutil.which(x) for x in ('ffmpeg', 'ffprobe')):
            raise HTTPException(503, 'The server needs FFmpeg and ffprobe installed.')
        _prune_jobs()
        ROOT.mkdir(parents=True, exist_ok=True)
        for old in ROOT.iterdir():
            if not store.durable() and old.is_dir() and old.stat().st_mtime < time.time() - TTL:
                shutil.rmtree(old)
        received_size = getattr(video, 'size', None)
        if received_size is not None and received_size > MAX_BYTES:
            limit_mb = MAX_BYTES // (1024 * 1024)
            raise HTTPException(413, f'Choose a video no larger than {limit_mb} MB.')
        required_free = 600 * 1024 * 1024 + (received_size or 0)
        if shutil.disk_usage(ROOT).free < required_free:
            raise HTTPException(507, 'The server needs more free disk space to process this video. Free up space and try again.')
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
                    limit_mb = MAX_BYTES // (1024 * 1024)
                    raise HTTPException(413, f'Choose a video no larger than {limit_mb} MB.')
                dest.write(chunk)
        if not size:
            raise HTTPException(400, 'The selected video is empty.')
        try:
            seconds = duration(src)
            if not math.isfinite(seconds) or seconds <= 0:
                raise ValueError('invalid duration')
        except (ValueError, subprocess.SubprocessError):
            raise HTTPException(400, 'Use a readable video file.')

        job_id = work.name
        with JOBS_LOCK:
            JOBS[job_id] = {'status': 'processing', 'progress': 0,
                            'message': 'Upload complete. Preparing 10-minute processing batches…',
                            'clips': [], 'created': time.time()}
        video.file.close()
        worker = threading.Thread(
            target=_process_video,
            args=(job_id, work, src, seconds, clip_count, clip_duration, vertical),
            daemon=True,
        )
        worker.start()
        handed_off = True
        return {'job_id': job_id, 'status': 'processing', 'progress': 0,
                'message': 'Upload complete. Processing the video in 10-minute batches.'}
    except HTTPException:
        if work:
            shutil.rmtree(work, ignore_errors=True)
        raise
    except OSError:
        if work:
            shutil.rmtree(work, ignore_errors=True)
        raise HTTPException(500, 'The video could not be saved on the server. Check its free disk space and try again.')
    finally:
        video.file.close()
        if not handed_off:
            LOCK.release()


@router.get('/api/create-clips/{job_id}', dependencies=[Depends(authorize)])
def clip_job_status(job_id: str):
    if not job_id.startswith('job-') or Path(job_id).name != job_id:
        raise HTTPException(404, 'Clip job not found.')
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, 'Clip job not found. The server may have restarted; submit the video again.')
        return {key: value for key, value in job.items() if key != 'created'}


@router.get('/api/clips/{job}/{name}', dependencies=[Depends(authorize)])
def download_clip(job: str, name: str):
    if not job.startswith('job-') or Path(job).name != job or Path(name).name != name:
        raise HTTPException(404, 'Clip not found.')
    path = ROOT / job / name
    if not name.startswith('clip_') or not name.endswith('.mp4') or not path.is_file():
        raise HTTPException(404, 'Clip not found. Create it again if the server restarted.')
    return FileResponse(path, media_type='video/mp4', filename=name)
