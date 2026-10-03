# GameClip Publisher

Android control app and Python video-processing API. Recovered from `GameClipPublisher_v2_SDK57_MEDIAFIX.zip` and integrated with the existing backend.

## Working milestone

- Pick a video through Android's document picker, copying it to app cache for readable uploads.
- Upload a video, choose clip count/length and portrait or landscape output.
- Select sections using a simple visual-motion score and render MP4 clips with FFmpeg.
- Download/share generated clips from the phone.
- Protect processing and downloads with a server access key entered in the app.

## Run the server

Install Python 3.12 and FFmpeg (including ffprobe). From the repository root:

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
export GAMECLIP_API_KEY='replace-with-a-long-random-key'
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Windows PowerShell: use `.venv\Scripts\python -m pip install -r requirements.txt`, set `$env:GAMECLIP_API_KEY='your-key'`, then run `.venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000`.

Docker alternatively packages FFmpeg with Python. `render.yaml` uses Render's Python runtime, which includes FFmpeg, with a generated `GAMECLIP_API_KEY` and `/health` health check. The Dockerfile remains available for deployments elsewhere. Enter that generated value into the phone settings; never put it in EXPO_PUBLIC variables or Git.

## Run the phone app

```sh
cd mobile
npm ci
npx expo start
```

Use a matching Expo Go version for SDK 57 or a development build. In Settings, enter your HTTPS Render URL and access key. For local development use the computer's LAN IP, not localhost (which points to the phone). Settings and the clip list are currently held only in memory. Select a small MP4 first and create clips; tap a result to download/share it.

## Limits and remaining work

This is a single-user prototype. Uploads are limited to 200 MB and 30 minutes. One render request is processed at a time. Short videos produce one clip rather than duplicates. Outputs are 720x1280 or 1280x720. Rendering is synchronous; large jobs may exceed hosting request limits. Start with small videos. A durable worker queue is needed for long-running production use.

On the free demonstration service, clips are temporary: they disappear on restart/redeploy and older job folders are cleaned on subsequent uploads after 24 hours. Download important clips immediately. Free Render compute has not yet been benchmarked for this processing load.

Social OAuth connections, encrypted token persistence, platform upload adapters and a publishing scheduler are implemented. See [SOCIAL_SETUP.md](SOCIAL_SETUP.md) for activation, required developer credentials and platform restrictions. The current free Render instance deliberately disables account connections/scheduling until persistent storage is configured. No platform credentials or live posting tests are included.

TikTok uses inbox drafts requiring completion in TikTok. Instagram and Facebook publish Reels to professional accounts/Pages. YouTube supports selected privacy and audience. Direct Post on TikTok is not implemented. An Android APK build workflow is provided; its native build result and phone testing must be checked separately.

## Verify

```sh
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
cd mobile
npx expo export --platform android
```

The integration test generates a real video, uploads it, renders it, downloads it and checks duration. A successful Android bundle export does not replace testing the picker/upload/share flow on a physical phone.
