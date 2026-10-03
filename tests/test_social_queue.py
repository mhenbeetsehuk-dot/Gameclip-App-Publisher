import time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from backend.main import app
from backend import store,social,queue,publishers,clips

AUTH={'X-API-Key':'test-key'}

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DATA_DIR',str(tmp_path/'data'))
    monkeypatch.setenv('TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('GAMECLIP_API_KEY','test-key')
    monkeypatch.setenv('PUBLIC_BASE_URL','https://example.org')
    monkeypatch.setenv('GOOGLE_CLIENT_ID','client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET','secret')
    monkeypatch.setenv('TIKTOK_CLIENT_KEY','client')
    monkeypatch.setenv('TIKTOK_CLIENT_SECRET','secret')
    monkeypatch.setenv('PERSISTENT_STORAGE_CONFIRMED','true')
    monkeypatch.setenv('SCHEDULER_ENABLED','true')
    return TestClient(app)


def token(platform='youtube'):
    store.save_account(platform,'My account',{'access_token':'access-secret','refresh_token':'refresh-secret','expires_at':time.time()+3600,'open_id':'tiktok-user' if platform=='tiktok' else 'youtube'})


def seed_clip(tmp_path):
    path=tmp_path/'clip.mp4';path.write_bytes(b'fake-test-media')
    with store.db() as c:c.execute('INSERT INTO clips VALUES(?,?,?,?)',('clip1','clip.mp4',str(path),time.time()))
    return path


def scheduled_body():
    return {'clip_ids':['clip1'],'platforms':['youtube'],'title':'Approved title','caption':'Approved caption','first_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'interval_hours':3,'made_for_kids':False,'consent':True}


def test_credentials_encrypted(client):
    token()
    with store.db() as c:raw=c.execute('SELECT secret FROM accounts').fetchone()['secret']
    assert 'access-secret' not in raw and 'refresh-secret' not in raw
    assert store.account('youtube')['refresh_token']=='refresh-secret'
    assert 'access-secret' not in client.get('/api/social',headers=AUTH).text


def test_oauth_state_is_single_use(client,monkeypatch):
    url=client.post('/api/social/youtube/connect',headers=AUTH).json()['url']
    state=parse_qs(urlparse(url).query)['state'][0]
    assert client.get('/auth/youtube/callback',params={'state':'wrong','code':'code'}).status_code==400
    original_client=httpx.Client
    monkeypatch.setattr(social.httpx,'Client',lambda **kw:original_client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'access_token':'access','refresh_token':'refresh','expires_in':3600})),**kw))
    assert client.get('/auth/youtube/callback',params={'state':state,'code':'code'}).status_code==200
    assert client.get('/auth/youtube/callback',params={'state':state,'code':'code'}).status_code==400
    assert store.account('youtube')['refresh_token']=='refresh'


def test_expired_state(client):
    url=client.post('/api/social/youtube/connect',headers=AUTH).json()['url']
    state=parse_qs(urlparse(url).query)['state'][0]
    with store.db() as c:c.execute('UPDATE states SET expires=0')
    assert client.get('/auth/youtube/callback',params={'state':state,'code':'code'}).status_code==400


def test_refresh_rotates_token(client,monkeypatch):
    store.save_account('tiktok','TikTok',{'access_token':'old','refresh_token':'old-refresh','expires_at':0,'open_id':'tiktok-user'})
    original=httpx.Client
    monkeypatch.setattr(social.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'access_token':'new','refresh_token':'new-refresh','expires_in':86400})),**kw))
    assert social.access_token('tiktok')==('new','tiktok-user')
    assert store.account('tiktok')['refresh_token']=='new-refresh'


def test_schedule_consent_and_cancel(client,tmp_path,monkeypatch):
    token();seed_clip(tmp_path)
    monkeypatch.setattr('backend.clipper.media_info',lambda p:{'streams':[{'codec_type':'video','width':720,'height':1280}],'format':{'duration':'30'}})
    body=scheduled_body();body['consent']=False
    assert client.post('/api/queue',headers=AUTH,json=body).status_code==400
    body['consent']=True
    r=client.post('/api/queue',headers=AUTH,json=body)
    assert r.status_code==200,r.text
    job_id=r.json()['job_ids'][0]
    assert client.post('/api/queue',headers=AUTH,json=body).status_code==409
    assert client.delete('/api/queue/'+job_id,headers=AUTH).status_code==200
    assert client.get('/api/queue',headers=AUTH).json()[0]['status']=='cancelled'


def test_queue_disabled_on_ephemeral_storage(client,monkeypatch):
    monkeypatch.setenv('PERSISTENT_STORAGE_CONFIRMED','false')
    assert client.post('/api/social/youtube/connect',headers=AUTH).status_code==503
    assert client.post('/api/queue',headers=AUTH,json=scheduled_body()).status_code==503


def test_restart_preserves_queue_and_no_double_submit(client,tmp_path,monkeypatch):
    token();seed_clip(tmp_path)
    with store.db() as c:
        c.execute("INSERT INTO jobs(id,clip_id,platform,account_id,title,caption,privacy,due,status,updated) VALUES('job','clip1','youtube','youtube','title','','private',0,'queued',0)")
    called=[]
    monkeypatch.setattr(publishers,'submit',lambda job,path:(called.append(job['id']) or ('submitted','remote-id')))
    queue.tick();queue.tick()
    assert called==['job']
    with store.db() as c:row=c.execute('SELECT * FROM jobs').fetchone()
    assert row['status']=='submitted' and row['remote_id']=='remote-id'
    store.job_update('job',status='submitting')
    queue.recover();queue.tick()
    with store.db() as c:assert c.execute('SELECT status FROM jobs').fetchone()['status']=='needs_review'
    assert called==['job']


def test_ambiguous_write_is_not_retried(client,tmp_path,monkeypatch):
    seed_clip(tmp_path)
    with store.db() as c:c.execute("INSERT INTO jobs(id,clip_id,platform,account_id,title,caption,privacy,due,status,updated) VALUES('job','clip1','youtube','youtube','title','','private',0,'queued',0)")
    called=[]
    def broken(job,path):
        called.append(job['id']);raise httpx.ReadTimeout('unknown upstream outcome')
    monkeypatch.setattr(publishers,'submit',broken)
    queue.tick();queue.tick()
    assert called==['job']
    assert client.get('/api/queue',headers=AUTH).json()[0]['status']=='needs_review'


def test_signed_media_is_temporary(client,tmp_path):
    seed_clip(tmp_path)
    url=publishers.media_url('clip1')
    relative=url.replace('https://example.org','')
    assert client.get(relative).status_code==200
    assert client.get('/media/clip1').status_code==403
    assert client.get(relative.replace('signature=','signature=bad')).status_code==403


def test_meta_account_selection_does_not_guess(client):
    store.save_account('facebook','Select an account',{'pages':[{'id':'page1','name':'My page','access_token':'secret'}]})
    with pytest.raises(ValueError):social.access_token('facebook')
    assert 'secret' not in client.get('/api/social/facebook/choices',headers=AUTH).text
    assert client.post('/api/social/facebook/select',headers=AUTH,json={'page_id':'unknown'}).status_code==400
    assert client.post('/api/social/facebook/select',headers=AUTH,json={'page_id':'page1'}).status_code==200
    assert social.access_token('facebook')==('secret','page1')


def test_adapter_youtube_resumable_request(client,tmp_path,monkeypatch):
    token();path=seed_clip(tmp_path);requests=[]
    original=httpx.Client
    def handle(r):
        requests.append(r)
        if r.method=='POST':return httpx.Response(200,headers={'Location':'https://www.googleapis.com/upload/test'})
        return httpx.Response(201,json={'id':'video-id'})
    monkeypatch.setattr(publishers.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    assert publishers.submit({'id':'job','clip_id':'clip1','platform':'youtube','account_id':'youtube','title':'Title','caption':'Caption','privacy':'private'},path)==('submitted','video-id')
    assert requests[1].method=='PUT' and requests[1].content==path.read_bytes()
    assert b'private' in requests[0].content


def test_untrusted_upload_host_rejected():
    with pytest.raises(ValueError):publishers.checked_upload_url('https://evil.example/upload',['googleapis.com'])

def test_tiktok_upload_and_inbox_status(client,tmp_path,monkeypatch):
    token('tiktok');path=seed_clip(tmp_path);requests=[]
    with store.db() as c:c.execute("INSERT INTO jobs(id,clip_id,platform,status) VALUES('job','clip1','tiktok','submitting')")
    original=httpx.Client
    def handle(r):
        requests.append(r)
        if '/init/' in str(r.url):return httpx.Response(200,json={'data':{'publish_id':'inbox-id','upload_url':'https://open-upload.tiktokapis.com/upload'},'error':{'code':'ok'}})
        if r.method=='PUT':return httpx.Response(201)
        return httpx.Response(200,json={'data':{'status':'SEND_TO_USER_INBOX'},'error':{'code':'ok'}})
    monkeypatch.setattr(publishers.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    job={'id':'job','clip_id':'clip1','platform':'tiktok','account_id':'tiktok-user'}
    assert publishers.submit(job,path)==('processing','inbox-id')
    assert requests[1].headers['Content-Range']==f'bytes 0-{path.stat().st_size-1}/{path.stat().st_size}'
    job.update(remote_id='inbox-id',status='processing')
    assert publishers.poll(job)==('awaiting_user','inbox-id')


def test_instagram_processing_then_publish(client,tmp_path,monkeypatch):
    path=seed_clip(tmp_path);requests=[]
    monkeypatch.setenv('META_API_VERSION','v99.0')
    store.save_account('instagram','Page',{'selected':{'id':'ig-id','token':'page-token'}})
    with store.db() as c:c.execute("INSERT INTO jobs(id,clip_id,platform,status) VALUES('job','clip1','instagram','processing')")
    original=httpx.Client
    def handle(r):
        requests.append(r)
        if r.method=='GET':return httpx.Response(200,json={'status_code':'FINISHED'})
        if str(r.url).endswith('media_publish'):return httpx.Response(200,json={'id':'published-id'})
        return httpx.Response(200,json={'id':'container-id'})
    monkeypatch.setattr(publishers.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    job={'id':'job','clip_id':'clip1','platform':'instagram','account_id':'ig-id','caption':'Approved caption'}
    assert publishers.submit(job,path)==('processing','container-id')
    assert b'media_type=REELS' in requests[0].content
    job.update(remote_id='container-id',status='processing')
    assert publishers.poll(job)==('published','published-id')
    assert b'creation_id=container-id' in requests[-1].content


def test_facebook_reel_submission_and_confirmation(client,tmp_path,monkeypatch):
    path=seed_clip(tmp_path);requests=[]
    monkeypatch.setenv('META_API_VERSION','v99.0')
    store.save_account('facebook','Page',{'selected':{'id':'page-id','token':'page-token'}})
    with store.db() as c:c.execute("INSERT INTO jobs(id,clip_id,platform,status) VALUES('job','clip1','facebook','submitting')")
    original=httpx.Client
    def handle(r):
        requests.append(r)
        if r.method=='GET':return httpx.Response(200,json={'status':{'publishing_phase':{'status':'complete'}}})
        if b'upload_phase=start' in r.content:return httpx.Response(200,json={'video_id':'fb-video','upload_url':'https://rupload.facebook.com/upload'})
        return httpx.Response(200,json={'success':True})
    monkeypatch.setattr(publishers.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    job={'id':'job','clip_id':'clip1','platform':'facebook','account_id':'page-id','title':'Approved','caption':'Caption'}
    assert publishers.submit(job,path)==('submitted','fb-video')
    assert requests[1].content==path.read_bytes()
    assert b'video_state=PUBLISHED' in requests[2].content
    job.update(remote_id='fb-video',status='submitted')
    assert publishers.poll(job)==('published','fb-video')


def test_changing_selected_page_blocks_queued_destination(client,tmp_path):
    store.save_account('facebook','New page',{'selected':{'id':'new-page','token':'token'}})
    with pytest.raises(ValueError,match='Account changed'):
        publishers.submit({'platform':'facebook','account_id':'original-page'},tmp_path/'unused.mp4')
