import subprocess
import time
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend import clips

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('GAMECLIP_API_KEY', 'test-key')
    monkeypatch.setattr(clips, 'ROOT', tmp_path / 'clips')
    return TestClient(app)

AUTH = {'X-API-Key': 'test-key'}

def test_health_and_access_control(client):
    assert client.get('/health').status_code == 200
    dashboard = client.get('/')
    assert dashboard.status_code == 200
    assert 'Connect to your server' in dashboard.text
    assert 'sequential 10-minute batches' in dashboard.text
    assert client.get('/api/clips/job-abc/clip_01.mp4').status_code == 401
    assert client.post('/api/create-clips', files={'video': ('v.mp4', b'bad')}).status_code == 401

def test_bad_video_and_settings(client):
    assert client.post('/api/create-clips', headers=AUTH, files={'video': ('bad.txt', b'bad')}).status_code == 400
    assert client.post('/api/create-clips', headers=AUTH, files={'video': ('bad.mp4', b'bad')}).status_code == 400
    assert client.post('/api/create-clips', headers=AUTH, files={'video': ('v.mp4', b'bad')}, data={'clip_count': 99}).status_code == 422
    assert not list(clips.ROOT.iterdir())

def test_create_and_download_real_video(client, tmp_path):
    source = tmp_path / 'sample.mp4'
    subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10', '-t', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(source)], check=True, capture_output=True)
    with source.open('rb') as f:
        response = client.post('/api/create-clips', headers=AUTH, files={'video': ('sample.mp4', f, 'video/mp4')}, data={'clip_count':3, 'clip_duration':5})
    assert response.status_code == 202, response.text
    job_id = response.json()['job_id']
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status = client.get(f'/api/create-clips/{job_id}', headers=AUTH)
        assert status.status_code == 200
        if status.json()['status'] != 'processing':
            break
        time.sleep(0.1)
    assert status.json()['status'] == 'completed', status.json()
    created = status.json()['clips']
    assert len(created) == 1  # Do not duplicate short videos to fill the requested count.
    result = client.get(created[0]['download_path'], headers=AUTH)
    assert result.status_code == 200
    assert result.headers['content-type'] == 'video/mp4'
    output = tmp_path / 'result.mp4'
    output.write_bytes(result.content)
    assert 1.5 < clips.duration(output) <= 2.5
    assert not list(clips.ROOT.glob('*/source*'))


def test_clip_quotas_cover_video_across_sequential_batches():
    quotas = clips._clip_quotas(12, 6)
    assert len(quotas) == 12
    assert sum(quotas) == 6
    assert [i for i, count in enumerate(quotas) if count] == [1, 3, 5, 7, 9, 11]

def test_busy_and_upload_limit(client, monkeypatch):
    clips.LOCK.acquire()
    try:
        assert client.post('/api/create-clips', headers=AUTH, files={'video':('v.mp4',b'bad')}).status_code == 409
    finally:
        clips.LOCK.release()
    monkeypatch.setattr(clips, 'MAX_BYTES', 2)
    assert client.post('/api/create-clips', headers=AUTH, files={'video':('v.mp4',b'123')}).status_code == 413
