# Activate social connections and scheduled uploads

This build adds OAuth connections, encrypted token storage, a saved clip library, scheduling, cancellation and platform status checks. No developer credentials are included. No social account has been connected or live post published during development.

## Hosting prerequisite

The free Render instance can demonstrate clipping and account setup status, but it sleeps and loses local data. Scheduled posting is intentionally disabled on it. Use one always-on instance with a persistent disk; do not run multiple Uvicorn workers or multiple service instances with this SQLite design.

`render.production.yaml` describes an OPTIONAL PAID Starter service with a 5 GB persistent disk. Review the current Render price before applying it. Update the existing service in the Dashboard rather than creating another service unintentionally. Set:

```
DATA_DIR=/var/data/gameclip
PERSISTENT_STORAGE_CONFIRMED=true
SCHEDULER_ENABLED=true
PUBLIC_BASE_URL=https://gameclip-publisher.onrender.com
```

Mount the disk at `/var/data` before enabling these flags. Generate `TOKEN_ENCRYPTION_KEY` once using `cryptography.fernet.Fernet.generate_key()`. Keep it stable and secret; losing it makes saved account tokens unreadable. Keep `GAMECLIP_API_KEY` stable too. Neither key belongs in the APK, Git or EXPO_PUBLIC variables. Back up the disk and encryption key independently. Files remain until manually removed; monitor disk capacity.

Publishing runs every 30 seconds while the server is running, so due times are best-effort rather than exact. Downtime delays due posts until the service restarts. A network failure during a submit can have an unknown outcome; the queue shows `needs_review` rather than automatically posting again. Check the destination platform before creating a new post. No automatic retries for uncertain submissions are performed.

## YouTube

1. In Google Cloud, enable YouTube Data API v3 and configure the OAuth consent screen (add test users during testing).
2. Create a Web application OAuth client.
3. Register this exact authorized redirect URI:
   `https://gameclip-publisher.onrender.com/auth/youtube/callback`
4. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` on Render.
5. Connect YouTube in the APK's Accounts tab and authorize your intended channel.
6. Review the title, description, audience and visibility before scheduling. Initial testing should use private visibility.

Uploads from unverified API projects can be restricted to private viewing until Google's audit requirements are satisfied. The OAuth request includes youtube.upload and youtube.readonly so processing status can be checked. Tokens are stored encrypted and refreshed before expiry. Reconnecting cancels queued jobs for that platform; schedule them again deliberately for the newly authorized account.

## TikTok

1. Register a TikTok developer app with Login Kit and Content Posting API Upload permissions.
2. Register `https://gameclip-publisher.onrender.com/auth/tiktok/callback` as a Web redirect URI.
3. Set `TIKTOK_CLIENT_KEY` and `TIKTOK_CLIENT_SECRET` on Render.
4. Request/authorize `video.upload`, then connect from Accounts.

This integration schedules uploads to the TikTok INBOX, not unattended public posts. TikTok requires the creator to open the notification, edit and finish the post. The title/caption in this app is not transmitted by the inbox API; apply it in TikTok. The queue distinguishes processing, awaiting_user and published. The current uploader supports a single chunk up to 64 MB. Direct Post is not included: it needs video.publish approval, creator-info/privacy controls and TikTok's required audited posting experience. Do not present inbox uploads as automatic publishing.

## Instagram and Facebook

This implementation uses Meta's Facebook Login route. Instagram must be a Professional (Business or Creator) account linked to a Facebook Page; Facebook publishing targets Pages, not personal profiles.

1. Create/configure your Meta developer app for Facebook Login and required APIs.
2. Register both callback URLs:
   - `https://gameclip-publisher.onrender.com/auth/instagram/callback`
   - `https://gameclip-publisher.onrender.com/auth/facebook/callback`
3. Set `META_APP_ID`, `META_APP_SECRET` and `META_API_VERSION` (the supported version selected for your app, formatted `vNN.N`).
4. Request Instagram scopes: pages_show_list, pages_read_engagement, instagram_basic, instagram_content_publish.
5. Request Facebook scopes: pages_show_list, pages_read_engagement, pages_manage_posts. Complete app review/advanced access requirements for your intended users.
6. Connect each platform, then explicitly select the correct Page/account in the phone app. The backend never guesses among Pages.

Meta can fetch a clip through a short-lived signed media link. The app submits Reel containers and checks processing/publishing state. Meta tokens can be revoked or expire; reconnect if permissions stop working. Queue portrait clips at least 4 seconds long. Output is H.264/AAC, 30 FPS and 720x1280 for portrait. Signed URLs are not public library listings, but anyone with a valid link can fetch the specific clip until expiry.

## Scheduling in the APK

Create clips after persistent storage is enabled. In Queue, select clips and connected platforms, enter title/caption, set the first ISO timestamp including timezone and the hours between clips (default 3). Choose YouTube privacy and audience. Review and approve the displayed schedule. Queued jobs can be cancelled. Submitted posts must be managed on the platform. Duplicate scheduling of the same clip to the same platform is blocked unless its earlier queued job was cancelled.

Each approved clip/platform pair is a separate job. Clip 1 goes at the first time, clip 2 three hours later by default, etc. Selected platforms for the same clip share a due time. Queue/account/clip records survive process restarts only when the disk is correctly mounted.

## APK

`.github/workflows/android-apk.yml` builds a standalone APK without an Expo account. It runs Expo prebuild and Android Gradle assembleRelease and uploads the APK as `GameClip-Publisher-APK` under the GitHub Actions run. This is an internal testing build with the generated template's debug signing key, not a Play Store release. Add protected production signing credentials before commercial distribution. The API access key is entered by the user and stored with Expo SecureStore on the phone.

An Android bundle export only checks JavaScript compilation. A native APK build and physical-device testing are separate requirements. No social post has been live-tested until credentials and a test destination are provided.

Official references:
- https://developers.google.com/youtube/v3/docs/videos/insert
- https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol
- https://developers.tiktok.com/docs/en/content-posting-api-reference-upload-video
- https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status
- https://www.postman.com/meta/instagram/collection/6yqw8pt/instagram-api
- https://www.postman.com/meta/facebook/folder/simabyk/reels-publishing
- https://render.com/docs/free
- https://render.com/docs/disks
