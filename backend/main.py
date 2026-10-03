import os
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from .clips import router as clips_router

app = FastAPI(title="GameClip Publisher API", version="0.2.0")
app.include_router(clips_router)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.upload"

@app.get("/")
def root():
    return {"app": "GameClip Publisher", "status": "ok", "version": "0.2.0"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/auth/youtube")
def youtube_auth():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not client_id or not redirect_uri:
        raise HTTPException(503, "Google OAuth is not configured yet.")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": YOUTUBE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    return RedirectResponse(GOOGLE_AUTH_URL + "?" + urlencode(params))

@app.get("/auth/youtube/callback")
async def youtube_callback(code: str | None = None, error: str | None = None):
    if error:
        raise HTTPException(400, f"Google OAuth error: {error}")
    if not code:
        raise HTTPException(400, "Missing authorization code.")
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not all([client_id, client_secret, redirect_uri]):
        raise HTTPException(503, "Google OAuth is not configured yet.")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
    if response.status_code >= 400:
        raise HTTPException(response.status_code, "Google token exchange failed.")
    token = response.json()
    return {
        "status": "authorized",
        "token_type": token.get("token_type"),
        "expires_in": token.get("expires_in"),
        "refresh_token_received": bool(token.get("refresh_token")),
    }
