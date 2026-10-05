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

## Use the computer dashboard

Start the backend and open `http://127.0.0.1:8000` in Chrome on the same computer. Enter the `GAMECLIP_API_KEY` from the private `.env` file. The browser dashboard supports video upload and clip creation, account connections, the clip library, and scheduled uploads. The access key is held in the open browser tab and is not saved. To open the dashboard from another device, use the computer's Tailscale Funnel HTTPS address and keep Funnel and the backend running.

Docker alternatively packages FFmpeg with Python. `render.yaml` uses Render's Python runtime, which includes FFmpeg, with a generated `GAMECLIP_API_KEY` and `/health` health check. The Dockerfile remains available for deployments elsewhere. Enter that generated value into the phone settings; never put it in EXPO_PUBLIC variables or Git.

## Run the phone app

```sh
cd mobile
npm ci
npx expo start
```

Use a matching Expo Go version for SDK 57 or a development build. In Settings, enter your HTTPS server URL and access key. For local development use the computer's LAN IP or its Tailscale Funnel URL, not localhost (which points to the phone). Server settings are stored securely on the phone; the current clip list remains in memory. Select a video and create clips; tap a result to download/share it.

## Limits and remaining work

This is a single-user prototype. The phone streams source files to the backend without loading the whole video into app memory. Uploads default to 2 GiB; change `MAX_VIDEO_UPLOAD_BYTES` on the server to set another size limit. The backend accepts the upload, then analyzes the source in sequential 10-minute batches in a background job, so long processing does not hold one HTTP request open. The server needs enough free disk space and must remain running until processing finishes. One video is processed at a time. Short videos produce one clip rather than duplicates. Outputs are 720x1280 or 1280x720.

On the free demonstration service, clips are temporary: they disappear on restart/redeploy and older job folders are cleaned on subsequent uploads after 24 hours. Download important clips immediately. Free Render compute has not yet been benchmarked for this processing load.

Social OAuth connections, encrypted token persistence, platform upload adapters and a publishing scheduler are implemented. See [SOCIAL_SETUP.md](SOCIAL_SETUP.md) for activation, required developer credentials and platform restrictions. The current free Render instance deliberately disables account connections/scheduling until persistent storage is configured. A single always-on laptop can store its queue in a stable local `DATA_DIR`; enable `PERSISTENT_STORAGE_CONFIRMED=true` and `SCHEDULER_ENABLED=true` in its private `.env` file to run scheduled jobs there. No platform credentials or live posting tests are included.

Scheduled jobs apply the title, caption and platform settings supported by each connected platform when their due time arrives. TikTok currently uses inbox drafts: the scheduled job uploads the draft at the due time, then the creator must finish its caption and publish in TikTok. Instagram and Facebook publish Reels to professional accounts/Pages. YouTube supports selected privacy and audience. Direct Post on TikTok is not implemented. An Android APK build workflow is provided; its native build result and phone testing must be checked separately.

## Verify

```sh
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
cd mobile
npx expo export --platform android
```

The integration test generates a real video, uploads it, renders it, downloads it and checks duration. A successful Android bundle export does not replace testing the picker/upload/share flow on a physical phone.
