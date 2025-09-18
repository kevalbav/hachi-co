from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os, json, base64
from ..deps import get_db, require_api_key
from .. import models

router = APIRouter(prefix="/oauth/youtube", tags=["oauth"])

def _client_config():
    return {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [os.environ.get("OAUTH_REDIRECT_BASE", "http://localhost:8000") + "/oauth/youtube/callback"],
        }
    }

SCOPE = ["https://www.googleapis.com/auth/youtube.readonly"]  # read-only

@router.get("/start")
def start(workspace_id: str):
    flow = Flow.from_client_config(_client_config(), scopes=SCOPE, redirect_uri=_client_config()["web"]["redirect_uris"][0])
    # put workspace_id in state
    flow.oauth2session.state = base64.urlsafe_b64encode(json.dumps({"wid": workspace_id}).encode()).decode()
    auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return RedirectResponse(auth_url)

@router.get("/callback", response_class=HTMLResponse)
def callback(request: Request, db: Session = Depends(get_db)):
    # parse state
    state_b64 = request.query_params.get("state") or ""
    try:
        state = json.loads(base64.urlsafe_b64decode(state_b64 + "==").decode())
    except Exception:
        state = {}
    wid = state.get("wid")
    if not wid:
        raise HTTPException(400, "Missing workspace")

    flow = Flow.from_client_config(_client_config(), scopes=SCOPE, redirect_uri=_client_config()["web"]["redirect_uris"][0])
    flow.fetch_token(code=request.query_params.get("code"))
    creds = flow.credentials  # type: Credentials

    # fetch channel to identify the external account
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    me = yt.channels().list(part="id,statistics", mine=True).execute()
    items = me.get("items", [])
    if not items:
        raise HTTPException(400, "No channel found")
    channel_id = items[0]["id"]

    # upsert integration (one per (workspace, provider))
    integ = db.query(models.Integration).filter(
        models.Integration.workspace_id == wid, models.Integration.provider == "youtube"
    ).first()
    if not integ:
        integ = models.Integration(workspace_id=wid, provider="youtube")
        db.add(integ)

    integ.external_account_id = channel_id
    integ.access_token = creds.token
    integ.refresh_token = creds.refresh_token or integ.refresh_token
    integ.scope = " ".join(SCOPE)
    integ.expiry = datetime.fromtimestamp(creds.expiry.timestamp(), tz=timezone.utc) if creds.expiry else None
    db.commit()

    return HTMLResponse("<p>✅ YouTube connected. You can close this window.</p>")
