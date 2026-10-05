"""Public product information and legal pages for TikTok app registration."""
from fastapi.responses import HTMLResponse


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — GameClip Publisher</title><style>
body{{font:16px/1.65 system-ui,-apple-system,Segoe UI,sans-serif;color:#192033;background:#f5f7fb;margin:0}}
main{{max-width:780px;margin:48px auto;padding:32px;background:white;border-radius:16px;box-shadow:0 8px 32px #14274a12}}
h1,h2{{line-height:1.25;color:#111a31}}h1{{font-size:2rem}}a{{color:#2455d6}}.brand{{font-weight:700;color:#555}}
footer{{margin-top:40px;border-top:1px solid #e4e8f0;padding-top:18px;color:#596174}}
@media(max-width:700px){{main{{margin:16px;padding:22px}}}}
</style></head><body><main><p class="brand"><a href="/">GameClip Publisher</a></p>{body}
<footer>GameClip Publisher · <a href="/terms">Terms of Service</a> · <a href="/privacy">Privacy Policy</a></footer></main></body></html>''')


def home() -> HTMLResponse:
    return _page('GameClip Publisher', '''<h1>GameClip Publisher</h1>
<p>GameClip Publisher helps creators turn gaming videos into short clips and prepare them for sharing on connected social platforms.</p>
<p>Creators choose their clips and destinations. TikTok uploads are sent as drafts to the creator’s TikTok inbox; the creator reviews and finishes publishing in TikTok. Other connected platforms have their own upload and scheduling options.</p>
<p>For support or privacy requests, contact <a href="mailto:mhenslp@gmail.com">mhenslp@gmail.com</a>.</p>
<p><a href="/terms">Terms of Service</a> · <a href="/privacy">Privacy Policy</a></p>''')


def terms() -> HTMLResponse:
    return _page('Terms of Service', '''<h1>Terms of Service</h1>
<p><strong>Effective date: 5 October 2026</strong></p>
<p>These Terms govern your use of GameClip Publisher, a service that helps you create short clips from video files and prepare content for connected social platforms. By using the service, you agree to these Terms.</p>
<h2>Your content and accounts</h2>
<p>You must have the rights and permissions needed to upload, edit, store, and share each video and any audio or other material in it. You are responsible for your content, captions, audience settings, destinations, and scheduled times. Do not upload unlawful content or content that infringes another person’s rights.</p>
<p>When you connect a social account, you authorize GameClip Publisher to use the permissions shown in that platform’s consent screen to provide the features you choose. You can disconnect an account in the app. You may also need to revoke access in the platform’s own settings.</p>
<h2>Uploads and scheduling</h2>
<p>You must review and approve each upload or schedule. Scheduled times are estimates and depend on service availability and the connected platform. GameClip Publisher does not guarantee a post will publish at an exact time or be accepted, displayed, or kept available by a platform.</p>
<p>TikTok uploads are sent to your TikTok inbox as drafts. You must open TikTok, review the draft, and finish publishing there. GameClip Publisher does not directly publish TikTok posts.</p>
<h2>Availability and changes</h2>
<p>We may update, suspend, or discontinue features to maintain or improve the service. Social platforms can change their APIs, permissions, or terms, which may affect integrations. Do not rely on the service as the sole copy of your videos; keep your own backups.</p>
<h2>Liability</h2>
<p>Nothing in these Terms excludes or limits liability where applicable law does not allow it, including liability for death or personal injury caused by negligence, fraud, or your statutory consumer rights. Subject to that, the service is provided without a guarantee of uninterrupted availability, and we are not responsible for decisions or outages of third-party platforms.</p>
<h2>Contact</h2><p>Questions about these Terms: <a href="mailto:mhenslp@gmail.com">mhenslp@gmail.com</a>.</p>''')


def privacy() -> HTMLResponse:
    return _page('Privacy Policy', '''<h1>Privacy Policy</h1>
<p><strong>Effective date: 5 October 2026</strong></p>
<p>This notice explains how GameClip Publisher handles information when you use the app. The service operator is the data controller for this information. Contact: <a href="mailto:mhenslp@gmail.com">mhenslp@gmail.com</a>.</p>
<h2>Information we handle</h2>
<ul><li>Video files you upload and the clips created from them.</li>
<li>Social account authorization data, such as platform account identifiers and access or refresh tokens needed to connect and publish. Tokens are encrypted when stored by the backend.</li>
<li>Clip names, titles, captions, destination choices, audience and privacy settings, scheduled times, and upload status.</li>
<li>Technical request and error information processed by our hosting provider to operate and secure the service.</li></ul>
<h2>How we use it</h2>
<p>We use this information to create and store clips, connect the social account you select, upload content when you approve it, run your scheduled jobs, show job status, secure the service, and respond to support or privacy requests. We do not sell personal information or use it for advertising.</p>
<h2>Sharing and service providers</h2>
<p>We process app data using Render for hosting and storage. When you request a social connection or upload, relevant account data and content are sent to the social platform you chose (such as Google/YouTube, TikTok, or Meta). Those platforms process data under their own privacy notices. Their systems may process information in countries outside the UK.</p>
<h2>Storage and retention</h2>
<p>Account tokens, clip records, and scheduled-job records are stored on the app backend; tokens are encrypted at rest. Videos are stored on the backend’s configured disk. We keep these items while needed to provide the service and until they are deleted or the service is discontinued. Disconnecting a social account removes its locally stored credentials and cancels queued jobs for that platform; it does not delete clips or revoke permission inside the social platform. Contact us to request deletion of data associated with your use.</p>
<h2>Your choices and rights</h2>
<p>You can disconnect a social account in the app and can revoke the app’s access in the social platform’s settings. Depending on your location and applicable law, you may have rights to access, correct, delete, restrict, or object to processing, and to request a copy of your information. Contact us to make a request. You may also complain to the UK Information Commissioner’s Office (ICO).</p>
<h2>Children and changes</h2>
<p>The service is not designed for children under 13. We may update this notice when the service or its data practices change; the effective date above will be updated.</p>
<h2>Contact</h2><p>Privacy requests and questions: <a href="mailto:mhenslp@gmail.com">mhenslp@gmail.com</a>.</p>''')
