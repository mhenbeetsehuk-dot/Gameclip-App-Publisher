"""OAuth connections for a single private publisher instance."""
import hashlib
import os
import re
import secrets
import time
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from .clips import authorize
from . import store

router = APIRouter()
PLATFORMS = ('youtube', 'tiktok', 'instagram', 'facebook')


def graph():
    version = os.getenv('META_API_VERSION', '')
    if not re.fullmatch(r'v\d+\.\d+', version):
        raise ValueError('Set META_API_VERSION to the version of your Meta app.')
    return 'https://graph.facebook.com/' + version


def base():
    value = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    if not value.startswith('https://'):
        raise ValueError('Set PUBLIC_BASE_URL to your HTTPS server URL.')
    return value


def config(platform):
    if platform not in PLATFORMS:
        raise HTTPException(404, 'Unknown platform.')
    prefix = {'youtube':'GOOGLE', 'tiktok':'TIKTOK', 'instagram':'META', 'facebook':'META'}[platform]
    id_key = prefix + ('_CLIENT_KEY' if platform == 'tiktok' else '_CLIENT_ID' if platform == 'youtube' else '_APP_ID')
    secret_key = prefix + ('_CLIENT_SECRET' if platform in ('youtube','tiktok') else '_APP_SECRET')
    identity, secret = os.getenv(id_key), os.getenv(secret_key)
    if not identity or not secret:
        raise ValueError(f'Configure {id_key} and {secret_key} on the server.')
    if prefix == 'META':
        graph()
    return identity, secret


def reply(response):
    # Do not include upstream responses or request URLs in errors: they can contain tokens.
    try:
        body = response.json()
    except ValueError:
        raise ValueError('Platform returned an invalid response.')
    error = body.get('error')
    bad = bool(error) and (not isinstance(error, dict) or error.get('code', 'ok') != 'ok')
    if response.is_error or bad:
        raise ValueError('Platform rejected the request. Check app permissions and reconnect.')
    return body


@router.get('/api/social', dependencies=[Depends(authorize)])
def status():
    with store.db() as c:
        connected = {r['platform']:r['label'] for r in c.execute('SELECT platform,label FROM accounts')}
    items=[]
    for p in PLATFORMS:
        try:
            config(p); base(); store.cipher()
            ready = store.durable()
            reason = '' if ready else 'Persistent storage must be configured before connecting accounts.'
        except ValueError as e:
            ready, reason = False, str(e)
        items.append({'platform':p,'configured':ready,'connected':p in connected,'label':connected.get(p),'reason':reason,
                      'mode':'TikTok inbox: finish posting in TikTok' if p=='tiktok' else 'Scheduled publishing'})
    return {'platforms':items,'durable_storage':store.durable(), 'scheduler_enabled':os.getenv('SCHEDULER_ENABLED','false')=='true'}


@router.post('/api/social/{platform}/connect', dependencies=[Depends(authorize)])
def connect(platform:str):
    try:
        identity, _ = config(platform)
        origin = base(); store.cipher()
        if not store.durable():
            raise ValueError('Configure persistent storage before connecting accounts.')
    except ValueError as e:
        raise HTTPException(503,str(e))
    state = secrets.token_urlsafe(32)
    with store.db() as c:
        c.execute('DELETE FROM states WHERE expires<?',(time.time(),))
        c.execute('INSERT INTO states VALUES(?,?,?)',(hashlib.sha256(state.encode()).hexdigest(),platform,time.time()+600))
    params={'redirect_uri':origin+f'/auth/{platform}/callback','state':state,'response_type':'code'}
    if platform=='youtube':
        url='https://accounts.google.com/o/oauth2/v2/auth'
        params.update(client_id=identity,scope='https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly',access_type='offline',prompt='consent')
    elif platform=='tiktok':
        url='https://www.tiktok.com/v2/auth/authorize/'
        params.update(client_key=identity,scope='video.upload',disable_auto_auth=1)
    else:
        url='https://www.facebook.com/'+os.environ['META_API_VERSION']+'/dialog/oauth'
        scopes='pages_show_list,pages_read_engagement,'+('instagram_basic,instagram_content_publish' if platform=='instagram' else 'pages_manage_posts')
        params.update(client_id=identity,scope=scopes)
    return {'url':url+'?'+urlencode(params)}


@router.get('/auth/{platform}/callback')
def callback(platform:str,state:str='',code:str='',error:str=''):
    with store.db() as c:
        key=hashlib.sha256(state.encode()).hexdigest()
        row=c.execute('SELECT * FROM states WHERE id=? AND platform=? AND expires>?',(key,platform,time.time())).fetchone()
        if not row:
            raise HTTPException(400,'Sign-in request expired or invalid. Start again from the app.')
        c.execute('DELETE FROM states WHERE id=?',(key,))
    if error or not code:
        raise HTTPException(400,'Authorization was declined. Try connecting again.')
    try:
        identity, secret = config(platform)
        uri=base()+f'/auth/{platform}/callback'
        with httpx.Client(timeout=30) as client:
            if platform in ('youtube','tiktok'):
                fields={'code':code,'client_secret':secret,'redirect_uri':uri,'grant_type':'authorization_code'}
                fields['client_id' if platform=='youtube' else 'client_key']=identity
                token=reply(client.post('https://oauth2.googleapis.com/token' if platform=='youtube' else 'https://open.tiktokapis.com/v2/oauth/token/',data=fields))
                if not token.get('refresh_token'):
                    previous=store.account(platform) or {}
                    token['refresh_token']=previous.get('refresh_token')
                if not token.get('access_token') or not token.get('refresh_token'):
                    raise ValueError('Offline access was not granted. Reconnect and allow all requested permissions.')
                if platform=='tiktok' and 'video.upload' not in token.get('scope','').split(','):
                    raise ValueError('The video.upload permission was not granted.')
                token['expires_at']=time.time()+token.get('expires_in',3600)
                with store.db() as c:
                    c.execute("UPDATE jobs SET status='cancelled',updated=? WHERE platform=? AND status='queued'",(time.time(),platform))
                store.save_account(platform,platform.title(),token)
            else:
                token=reply(client.get(graph()+'/oauth/access_token',params={'client_id':identity,'client_secret':secret,'redirect_uri':uri,'code':code}))
                token=reply(client.get(graph()+'/oauth/access_token',params={'grant_type':'fb_exchange_token','client_id':identity,'client_secret':secret,'fb_exchange_token':token['access_token']}))
                pages=reply(client.get(graph()+'/me/accounts',params={'fields':'id,name,access_token,instagram_business_account{id,username}','limit':100},headers={'Authorization':'Bearer '+token['access_token']}))
                # Store all choices; never silently choose a Page or account.
                token['pages']=pages.get('data',[])
                token['expires_at']=time.time()+token.get('expires_in',3600)
                with store.db() as c:
                    c.execute("UPDATE jobs SET status='cancelled',updated=? WHERE platform=? AND status='queued'",(time.time(),platform))
                store.save_account(platform,'Select an account in the app',token)
    except (ValueError,KeyError,httpx.HTTPError):
        raise HTTPException(400,'Could not connect. Check developer app permissions and try again.')
    return HTMLResponse('<h2>Account connected</h2><p>Return to GameClip Publisher and refresh Accounts. For Meta, select your Page or Instagram account.</p>',headers={'Cache-Control':'no-store'})


@router.get('/api/social/{platform}/choices',dependencies=[Depends(authorize)])
def choices(platform:str):
    if platform not in ('instagram','facebook'):
        raise HTTPException(400,'No account selection required.')
    a=store.account(platform) or {}
    return [{'id':p['id'],'name':p['name'],'instagram':p.get('instagram_business_account')} for p in a.get('pages',[]) if platform=='facebook' or p.get('instagram_business_account')]


class Selection(BaseModel):
    page_id: str


@router.post('/api/social/{platform}/select',dependencies=[Depends(authorize)])
def select(platform:str,selection:Selection):
    if platform not in ('instagram','facebook'):
        raise HTTPException(400,'Invalid platform.')
    a=store.account(platform) or {}
    page=next((p for p in a.get('pages',[]) if p['id']==selection.page_id),None)
    if not page or platform=='instagram' and not page.get('instagram_business_account'):
        raise HTTPException(400,'Choose an available account.')
    a['selected']={'id':page['id'] if platform=='facebook' else page['instagram_business_account']['id'],
                   'token':page['access_token'],'name':page['name']}
    store.save_account(platform,page['name'],a)
    return {'ok':True}


@router.delete('/api/social/{platform}',dependencies=[Depends(authorize)])
def disconnect(platform:str):
    with store.db() as c:
        c.execute('DELETE FROM accounts WHERE platform=?',(platform,))
        c.execute("UPDATE jobs SET status='cancelled',updated=? WHERE platform=? AND status='queued'",(time.time(),platform))
    return {'ok':True,'message':'Local credentials removed and queued posts cancelled. Revoke app permissions on the platform to fully revoke access.'}


def access_token(platform):
    a=store.account(platform)
    if not a:
        raise ValueError('Account disconnected. Reconnect before publishing.')
    if platform in ('facebook','instagram'):
        if not a.get('selected'):
            raise ValueError('Select a Page or professional account first.')
        return a['selected']['token'], a['selected']['id']
    if a.get('expires_at',0)<time.time()+120:
        identity, secret=config(platform)
        fields={'grant_type':'refresh_token','refresh_token':a['refresh_token'],'client_secret':secret}
        fields['client_id' if platform=='youtube' else 'client_key']=identity
        with httpx.Client(timeout=30) as client:
            new=reply(client.post('https://oauth2.googleapis.com/token' if platform=='youtube' else 'https://open.tiktokapis.com/v2/oauth/token/',data=fields))
        a.update(new);a['expires_at']=time.time()+new.get('expires_in',3600)
        store.save_account(platform,platform.title(),a)
    return a['access_token'],a.get('open_id','youtube')
