# hachico/app/routers/oauth_instagram.py

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import requests
import secrets
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta

from ..deps import get_db, settings
from .. import models

router = APIRouter(prefix="/oauth/instagram", tags=["oauth"])

# Store state tokens temporarily (in production, use Redis or database)
oauth_states = {}

@router.get("/start")
async def start_instagram_oauth(workspace_id: str = "w_001", db: Session = Depends(get_db)):
    """Initiate Instagram OAuth flow using Instagram Login"""
    
    # Generate state parameter for security
    state = secrets.token_urlsafe(32)
    oauth_states[state] = {"workspace_id": workspace_id}
    
    # Use Instagram's OAuth URL (matching what Meta generated for you)
    params = {
        "force_reauth": "true",
        "client_id": settings.INSTAGRAM_CLIENT_ID,
        "redirect_uri": f"{settings.OAUTH_REDIRECT_BASE}/oauth/instagram/callback",
        "response_type": "code",
        "scope": "instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments,instagram_business_content_publish,instagram_business_manage_insights",
        "state": state
    }
    
    auth_url = f"https://www.instagram.com/oauth/authorize?{urlencode(params)}"
    return RedirectResponse(url=auth_url)

@router.get("/callback")
async def instagram_oauth_callback(
    code: str = None,
    state: str = None,
    error: str = None,
    db: Session = Depends(get_db)
):
    """Handle Instagram OAuth callback and store credentials"""
    
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")
    
    # Verify state parameter
    if state not in oauth_states:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
    workspace_id = oauth_states[state]["workspace_id"]
    del oauth_states[state]  # Clean up
    
    try:
        # Exchange code for Instagram access token (using Instagram token endpoint)
        token_data = {
            "client_id": settings.INSTAGRAM_CLIENT_ID,
            "client_secret": settings.INSTAGRAM_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": f"{settings.OAUTH_REDIRECT_BASE}/oauth/instagram/callback",
            "code": code
        }
        
        # Instagram token exchange endpoint
        token_response = requests.post(
            "https://api.instagram.com/oauth/access_token",
            data=token_data
        )
        token_response.raise_for_status()
        token_info = token_response.json()
        
        short_lived_token = token_info["access_token"]
        instagram_user_id = token_info["user_id"]
        
        # Exchange short-lived token for long-lived token
        long_lived_params = {
            "grant_type": "ig_exchange_token",
            "client_secret": settings.INSTAGRAM_CLIENT_SECRET,
            "access_token": short_lived_token
        }
        
        long_lived_response = requests.get(
            "https://graph.instagram.com/access_token",
            params=long_lived_params
        )
        long_lived_response.raise_for_status()
        long_lived_token_info = long_lived_response.json()
        
        access_token = long_lived_token_info["access_token"]
        expires_in = long_lived_token_info.get("expires_in", 5184000)  # Default 60 days
        
        # Get Instagram account info to verify connection
        user_info_response = requests.get(
            f"https://graph.instagram.com/me",
            params={
                "fields": "id,username,account_type",
                "access_token": access_token
            }
        )
        user_info_response.raise_for_status()
        user_info = user_info_response.json()
        
        # Store or update integration in database (following YouTube pattern)
        existing_integration = db.query(models.Integration).filter(
            models.Integration.provider == "instagram",
            models.Integration.workspace_id == workspace_id
        ).first()
        
        expiry_date = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        if existing_integration:
            # Update existing integration
            existing_integration.access_token = access_token
            existing_integration.external_account_id = instagram_user_id
            existing_integration.expiry = expiry_date
            print(f"Updated Instagram integration for workspace {workspace_id}")
        else:
            # Create new integration
            integration = models.Integration(
                workspace_id=workspace_id,
                provider="instagram",
                access_token=access_token,
                refresh_token=None,  # Instagram doesn't use refresh tokens
                external_account_id=instagram_user_id,
                expiry=expiry_date
            )
            db.add(integration)
            print(f"Created new Instagram integration for workspace {workspace_id}")
        
        db.commit()
        
        # Redirect back to frontend
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        return RedirectResponse(url=f"{frontend_url}/?instagram=connected&username={user_info.get('username', '')}")
        
    except requests.RequestException as e:
        print(f"Instagram OAuth error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        raise HTTPException(status_code=400, detail=f"Failed to complete Instagram authorization: {str(e)}")
    except Exception as e:
        print(f"Unexpected Instagram OAuth error: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.get("/deauthorize")
async def instagram_deauthorize(db: Session = Depends(get_db)):
    """Handle Instagram app deauthorization (required by Meta)"""
    # This endpoint is called when users revoke access to your app
    # Log the deauthorization and clean up data as needed
    print("Instagram app deauthorized by user")
    return {"status": "ok"}

@router.post("/delete-data")
async def instagram_delete_data(request: Request, db: Session = Depends(get_db)):
    """Handle Instagram data deletion requests (GDPR compliance)"""
    # This endpoint is called when users request data deletion
    # Implement actual data deletion logic here
    print("Instagram data deletion requested")
    return {"status": "ok"}