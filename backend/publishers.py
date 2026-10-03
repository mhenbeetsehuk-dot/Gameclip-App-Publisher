"""Official API adapters. Never call these from an unauthenticated route."""
import hashlib
import hmac
import os
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse
import httpx
from . import store
from .social import access_token, base, graph, reply


def media_url(clip_id):
    expires=int(time.time())+3600
    key=os.environ['GAMECLIP_API_KEY'].encode()
    signature=hmac.new(key,f'{clip_id}:{expires}'.encode(),hashlib.sha256).hexdigest()
    return base()+f'/media/{clip_id}?'+urlencode({'expires':expires,'signature':signature})


def checked_upload_url(url, domains):
    parsed=urlparse(url)
    if parsed.scheme!='https' or not any(parsed.hostname==d or parsed.hostname.endswith('.'+d) for d in domains if parsed.hostname):
        raise ValueError('Platform returned an unexpected upload host.')
    return url


def stream(path):
    with open(path,'rb') as f:
        while data:=f.read(1024*1024):
            yield data


def submit(job,path):
    platform=job['platform']
    token,identity=access_token(platform)
    if identity!=job['account_id']:
        raise ValueError('Account changed since scheduling. Cancel and schedule again.')
    headers={'Authorization':'Bearer '+token}
    size=Path(path).stat().st_size
    with httpx.Client(timeout=180) as client:
        if platform=='youtube':
            r=client.post('https://www.googleapis.com/upload/youtube/v3/videos',params={'uploadType':'resumable','part':'snippet,status'},headers={**headers,'X-Upload-Content-Type':'video/mp4','X-Upload-Content-Length':str(size)},json={'snippet':{'title':job['title'],'description':job['caption']},'status':{'privacyStatus':job['privacy'],'selfDeclaredMadeForKids':bool(job.get('made_for_kids',0))}})
            r.raise_for_status()
            url=checked_upload_url(r.headers['Location'],['googleapis.com'])
            result=reply(client.put(url,headers={**headers,'Content-Type':'video/mp4','Content-Length':str(size)},content=stream(path)))
            return 'submitted',result['id']
        if platform=='tiktok':
            if size>64*1024*1024:
                raise ValueError('TikTok inbox uploads in this version must be under 64 MB.')
            data=reply(client.post('https://open.tiktokapis.com/v2/post/publish/inbox/video/init/',headers=headers,json={'source_info':{'source':'FILE_UPLOAD','video_size':size,'chunk_size':size,'total_chunk_count':1}}))['data']
            store.job_update(job['id'],remote_id=data['publish_id'])
            url=checked_upload_url(data['upload_url'],['tiktokapis.com'])
            client.put(url,headers={'Content-Type':'video/mp4','Content-Length':str(size),'Content-Range':f'bytes 0-{size-1}/{size}'},content=stream(path)).raise_for_status()
            return 'processing',data['publish_id']
        if platform=='instagram':
            result=reply(client.post(graph()+f'/{identity}/media',headers=headers,data={'media_type':'REELS','video_url':media_url(job['clip_id']),'caption':job['caption'],'share_to_feed':'true'}))
            return 'processing',result['id']
        result=reply(client.post(graph()+f'/{identity}/video_reels',headers=headers,data={'upload_phase':'start'}))
        video_id=result['video_id']
        store.job_update(job['id'],remote_id=video_id)
        url=checked_upload_url(result['upload_url'],['rupload.facebook.com'])
        reply(client.post(url,headers={'Authorization':'OAuth '+token,'offset':'0','file_size':str(size),'Content-Length':str(size)},content=stream(path)))
        reply(client.post(graph()+f'/{identity}/video_reels',headers=headers,data={'upload_phase':'finish','video_id':video_id,'video_state':'PUBLISHED','title':job['title'],'description':job['caption']}))
        return 'submitted',video_id


def poll(job):
    token,identity=access_token(job['platform'])
    if identity!=job['account_id']:
        raise ValueError('Account changed. Check the originally selected account.')
    headers={'Authorization':'Bearer '+token}
    with httpx.Client(timeout=30) as client:
        if job['platform']=='tiktok':
            data=reply(client.post('https://open.tiktokapis.com/v2/post/publish/status/fetch/',headers=headers,json={'publish_id':job['remote_id']}))['data']
            status=data['status']
            if status=='PUBLISH_COMPLETE':return 'published',job['remote_id']
            if status=='SEND_TO_USER_INBOX':return 'awaiting_user',job['remote_id']
            if status=='FAILED':raise ValueError('TikTok rejected processing. Check the account and uploaded video.')
            return job['status'],job['remote_id']
        if job['platform']=='instagram':
            data=reply(client.get(graph()+'/'+job['remote_id'],headers=headers,params={'fields':'status_code'}))
            if data['status_code']=='FINISHED':
                # Mark submitting before an irreversible API call. On ambiguous failure, require review.
                store.job_update(job['id'],status='submitting')
                result=reply(client.post(graph()+f'/{identity}/media_publish',headers=headers,data={'creation_id':job['remote_id']}))
                return 'published',result['id']
            if data['status_code']=='PUBLISHED':return 'published',job['remote_id']
            if data['status_code'] in ('ERROR','EXPIRED'):raise ValueError('Instagram could not process this clip.')
            return 'processing',job['remote_id']
        if job['platform']=='facebook':
            data=reply(client.get(graph()+'/'+job['remote_id'],headers=headers,params={'fields':'status'}))['status']
            if data.get('video_status')=='error':raise ValueError('Facebook could not process this clip.')
            if data.get('publishing_phase',{}).get('status')=='complete':return 'published',job['remote_id']
            return 'submitted',job['remote_id']
        data=reply(client.get('https://www.googleapis.com/youtube/v3/videos',headers=headers,params={'id':job['remote_id'],'part':'status'}))
        items=data.get('items',[])
        if items and items[0]['status'].get('uploadStatus')=='processed':return 'published',job['remote_id']
        if items and items[0]['status'].get('uploadStatus') in ('failed','rejected'):raise ValueError('YouTube rejected processing.')
        return 'submitted',job['remote_id']
