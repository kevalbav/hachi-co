# hachico/app/routers/references.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel
from typing import List
from uuid import uuid4

from ..deps import get_db
from ..models import Reference
from urllib.parse import urlparse

import re

class ReferenceCreate(BaseModel):
    url: str
    note: str = None


class ReferenceUpdate(BaseModel):
    note: str = None
    tags: List[str] = None


def detect_platform(url: str) -> str:
    """Detect platform from URL"""
    try:
        domain = urlparse(url).netloc.lower()
        
        # Remove www. prefix
        domain = domain.replace('www.', '')
        
        # Platform patterns
        if re.search(r'youtube\.com|youtu\.be', domain):
            return 'youtube'
        elif re.search(r'instagram\.com', domain):
            return 'instagram'
        elif re.search(r'tiktok\.com', domain):
            return 'tiktok'
        elif re.search(r'twitter\.com|x\.com', domain):
            return 'twitter'
        elif re.search(r'linkedin\.com', domain):
            return 'linkedin'
        elif re.search(r'pinterest\.com', domain):
            return 'pinterest'
        elif re.search(r'facebook\.com|fb\.com', domain):
            return 'facebook'
        else:
            return 'website'
            
    except Exception:
        return 'unknown'

# Predefined tags for social media professionals
PREDEFINED_TAGS = [
    # Content Types
    "tutorial", "inspiration", "example", "case-study", "template", "how-to", "behind-the-scenes",
    
    # Creative Elements  
    "design", "copywriting", "video-style", "photography", "animation", "color-palette", "typography",
    
    # Business Functions
    "marketing", "branding", "sales", "customer-service", "product-launch", "campaign",
    
    # Content Formats
    "reel", "story", "carousel", "single-post", "video", "live-stream", "ugc",
    
    # Industry/Niche
    "fashion", "tech", "food", "fitness", "beauty", "b2b", "saas", "ecommerce", "healthcare", "finance",
    
    # Campaign Types
    "seasonal", "holiday", "trending", "evergreen", "promotional", "educational",
    
    # Intent/Action
    "steal-this", "avoid-this", "show-client", "study-later", "competitor-analysis"
]


router = APIRouter(prefix="/references", tags=["references"])


class ReferenceCreate(BaseModel):
    url: str
    note: str = None


@router.post("/")
async def create_reference(
    reference_data: ReferenceCreate,
    db: Session = Depends(get_db)
):
    """Create a new reference - just URL and note for now"""
    try:
        # Create basic reference with platform detection
        reference = Reference(
            id=str(uuid4()),
            workspace_id="w_001",  # Hardcoded for now, like your other routes
            url=reference_data.url,
            note=reference_data.note,
            platform=detect_platform(reference_data.url)
        )
        
        db.add(reference)
        db.commit()
        db.refresh(reference)
        
        return {
            "ok": True,
            "reference": {
                "id": reference.id,
                "url": reference.url,
                "note": reference.note,
                "platform": reference.platform,
                "created_at": reference.created_at
            }
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create reference: {str(e)}")


@router.get("/")
async def get_references(db: Session = Depends(get_db)):
    """Get all references for workspace"""
    try:
        references = db.query(Reference).filter(
            Reference.workspace_id == "w_001"
        ).order_by(Reference.created_at.desc()).all()
        
        return {
            "ok": True,
            "references": [
                {
                    "id": ref.id,
                    "url": ref.url,
                    "note": ref.note,
                    "title": ref.title,
                    "platform": ref.platform,
                    "tags": ref.tags or [],
                    "created_at": ref.created_at
                }
                for ref in references
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get references: {str(e)}")


@router.put("/{reference_id}")
async def update_reference(
    reference_id: str,
    update_data: ReferenceUpdate,
    db: Session = Depends(get_db)
):
    """Update reference tags and note"""
    try:
        reference = db.query(Reference).filter(
            and_(
                Reference.id == reference_id,
                Reference.workspace_id == "w_001"
            )
        ).first()
        
        if not reference:
            raise HTTPException(status_code=404, detail="Reference not found")
        
        # Update fields if provided
        if update_data.note is not None:
            reference.note = update_data.note
        
        if update_data.tags is not None:
            reference.tags = update_data.tags
        
        db.commit()
        db.refresh(reference)
        
        return {
            "ok": True,
            "reference": {
                "id": reference.id,
                "url": reference.url,
                "note": reference.note,
                "platform": reference.platform,
                "tags": reference.tags or [],
                "created_at": reference.created_at
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update reference: {str(e)}")


@router.get("/tags")
async def get_available_tags():
    """Get list of predefined tags for references"""
    return {
        "ok": True,
        "tags": sorted(PREDEFINED_TAGS)
    }
