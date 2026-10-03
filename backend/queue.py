"""One-instance publishing scheduler. Queuing is explicit user consent."""
import hashlib
import hmac
import os
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .clips import authorize
from . import store, publishers
from .social import PLATFORMS, access_token

router=APIRouter()
RUN_LOCK=threading.Lock()


class Schedule(BaseModel):
    clip_ids:list[str]=Field(min_length=1,max_length=15)
    platforms:list[str]=Field(min_length=1,max_length=4)
    title:str=Field(min_length=1,max_length=100)
    caption:str=Field(default='',max_length=2200)
    first_at:datetime
    interval_hours:int=Field(default=3,ge=1,le=168)
    youtube_privacy:str='private'
    made_for_kids:bool
    consent:bool=False


@router.get('/api/library',dependencies=[Depends(authorize)])
def library():
    with store.db() as c:
        return [dict(r) for r in c.execute('SELECT id,name,created FROM clips ORDER BY created DESC LIMIT 100')]


@router.get('/api/queue',dependencies=[Depends(authorize)])
def queue():
    with store.db() as c:
        return [dict(r) for r in c.execute('SELECT jobs.*,clips.name FROM jobs JOIN clips ON jobs.clip_id=clips.id ORDER BY due DESC LIMIT 200')]


@router.post('/api/queue',dependencies=[Depends(authorize)])
def schedule(request:Schedule):
    if not store.durable():raise HTTPException(503,'Persistent storage is required for scheduled posts.')
    if os.getenv('SCHEDULER_ENABLED','false')!='true':raise HTTPException(503,'The always-on publishing scheduler is not enabled yet.')
    if not request.consent:raise HTTPException(400,'Approve the selected accounts, captions and publishing times first.')
    if request.first_at.tzinfo is None:raise HTTPException(400,'Include a timezone in the first upload time.')
    start=request.first_at.timestamp()
    if start<time.time()-60:raise HTTPException(400,'Choose a future upload time.')
    if len(set(request.platforms))!=len(request.platforms) or len(set(request.clip_ids))!=len(request.clip_ids):raise HTTPException(400,'Remove duplicate selections.')
    if request.youtube_privacy not in ('private','unlisted','public'):raise HTTPException(400,'Invalid YouTube visibility.')
    identities={}
    for p in request.platforms:
        if p not in PLATFORMS:raise HTTPException(400,'Unknown platform.')
        try:_,identities[p]=access_token(p)
        except (ValueError,KeyError,httpx.HTTPError):raise HTTPException(400,f'Connect and select your {p} account first.')
    ids=[]
    with store.db() as c:
        # Validate all clips before inserting any jobs.
        for clip_id in request.clip_ids:
            clip=c.execute('SELECT * FROM clips WHERE id=?',(clip_id,)).fetchone()
            if not clip or not Path(clip['path']).is_file():raise HTTPException(400,'A selected clip is unavailable. Create it again.')
            from .clipper import media_info
            info=media_info(clip['path']);v=next(s for s in info['streams'] if s['codec_type']=='video')
            if any(p in request.platforms for p in ('facebook','instagram')) and (v['width']*16!=v['height']*9 or float(info['format']['duration'])<4):
                raise HTTPException(400,'Meta Reels require a portrait clip at least 4 seconds long.')
        for i,clip_id in enumerate(request.clip_ids):
            for p in request.platforms:
                c.execute("DELETE FROM jobs WHERE clip_id=? AND platform=? AND status='cancelled'",(clip_id,p))
                if c.execute('SELECT id FROM jobs WHERE clip_id=? AND platform=?',(clip_id,p)).fetchone():raise HTTPException(409,'This clip is already scheduled for that platform.')
                job_id=secrets.token_hex(16);ids.append(job_id)
                c.execute('INSERT INTO jobs(id,clip_id,platform,account_id,title,caption,privacy,made_for_kids,due,status,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(job_id,clip_id,p,identities[p],request.title,request.caption,request.youtube_privacy,int(request.made_for_kids),start+i*request.interval_hours*3600,'queued',time.time()))
    return {'job_ids':ids}


@router.delete('/api/queue/{job_id}',dependencies=[Depends(authorize)])
def cancel(job_id:str):
    with store.db() as c:
        n=c.execute("UPDATE jobs SET status='cancelled',updated=? WHERE id=? AND status='queued'",(time.time(),job_id)).rowcount
    if not n:raise HTTPException(409,'Only a queued job can be cancelled; submitted media must be managed on the platform.')
    return {'ok':True}


@router.get('/media/{clip_id}')
def media(clip_id:str,expires:int=0,signature:str=''):
    expected=hmac.new(os.getenv('GAMECLIP_API_KEY','').encode(),f'{clip_id}:{expires}'.encode(),hashlib.sha256).hexdigest()
    if not os.getenv('GAMECLIP_API_KEY') or expires<time.time() or expires>time.time()+3700 or not hmac.compare_digest(signature,expected):
        raise HTTPException(403,'Media link expired or invalid.')
    with store.db() as c:
        row=c.execute('SELECT path,name FROM clips WHERE id=?',(clip_id,)).fetchone()
    if not row or not Path(row['path']).is_file():raise HTTPException(404,'Clip unavailable.')
    return FileResponse(row['path'],media_type='video/mp4',headers={'Cache-Control':'private, no-store'})


def recover():
    with store.db() as c:
        c.execute("UPDATE jobs SET status='needs_review',error='Server stopped during submission. Check the platform before posting this clip again.',updated=? WHERE status='submitting'",(time.time(),))


def tick():
    if not store.durable() or os.getenv('SCHEDULER_ENABLED','false')!='true' or not RUN_LOCK.acquire(False):return
    try:
        with store.db() as c:
            rows=[dict(r) for r in c.execute("SELECT jobs.*, clips.path FROM jobs JOIN clips ON jobs.clip_id=clips.id WHERE (status='queued' AND due<=?) OR (status IN ('processing','submitted','awaiting_user') AND updated<?) ORDER BY due LIMIT 10",(time.time(),time.time()-30))]
        for job in rows:
            try:
                if job['status']=='queued':
                    with store.db() as c:
                        claimed=c.execute("UPDATE jobs SET status='submitting',updated=? WHERE id=? AND status='queued'",(time.time(),job['id'])).rowcount
                    if not claimed:continue
                    status,remote_id=publishers.submit(job,job['path'])
                else:status,remote_id=publishers.poll(job)
                store.job_update(job['id'],status=status,remote_id=remote_id,error=None)
            except Exception:
                # Never auto retry an uncertain write: the platform may have accepted it.
                with store.db() as c:
                    current=c.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()['status']
                store.job_update(job['id'],status='needs_review' if current=='submitting' else 'failed',error='Could not confirm this upload. Check the platform and account permissions before scheduling again.')
    finally:RUN_LOCK.release()


def run(stop):
    recover()
    while not stop.is_set():
        try:tick()
        except Exception:pass  # A temporary database error must not kill the scheduler.
        stop.wait(30)
