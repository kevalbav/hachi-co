# hachico/app/routers/references.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel
from typing import List
from uuid import uuid4
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import re
from sqlalchemy import and_, or_

from ..deps import get_db
from ..models import Reference

router = APIRouter(prefix="/references", tags=["references"])


class ReferenceCreate(BaseModel):
    url: str
    note: str = None


class ReferenceUpdate(BaseModel):
    note: str = None
    tags: List[str] = None


# Predefined tags for social media professionals
PREDEFINED_TAGS = [
    # Content Types
    "tutorial", "inspiration", "example", "case-study", "behind-the-scenes",
    
    # Creative Elements  
    "design", "copywriting", "video-style", "photography", "color-palette",
    
    # Business Functions
    "marketing", "branding", "campaign",
    
    # Content Formats
    "reel", "story", "carousel", "video", "ugc",
    
    # Key Industries
    "fashion", "beauty", "food", "fitness", "tech", "b2b",
    
    # Campaign Types
    "trending", "seasonal", "promotional",
    
    # Intent/Action
    "steal-this", "avoid-this", "show-client", "competitor-analysis"
]


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


async def scrape_metadata(url: str) -> dict:
    """Scrape basic metadata including thumbnail and title"""
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; Hachico/1.0)'}
        
        # Create SSL context that doesn't verify certificates (for development)
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return {"title": None, "thumbnail": None}
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Extract title
                title = None
                og_title = soup.find('meta', property='og:title')
                if og_title:
                    title = og_title.get('content')
                else:
                    title_tag = soup.find('title')
                    if title_tag:
                        title = title_tag.text.strip()
                
                # Extract thumbnail
                thumbnail = None
                og_image = soup.find('meta', property='og:image')
                if og_image:
                    thumbnail = og_image.get('content')
                else:
                    twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
                    if twitter_image:
                        thumbnail = twitter_image.get('content')
                
                # Make thumbnail URL absolute if it's relative
                if thumbnail and not thumbnail.startswith('http'):
                    thumbnail = urljoin(url, thumbnail)
                
                return {
                    "title": title[:200] if title else None,  # Limit title length
                    "thumbnail": thumbnail
                }
                
    except Exception as e:
        print(f"Scraping failed for {url}: {e}")
        return {"title": None, "thumbnail": None}


@router.post("/")
async def create_reference(
    reference_data: ReferenceCreate,
    db: Session = Depends(get_db)
):
    """Create a new reference with auto-scraped metadata"""
    try:
        # Detect platform
        platform_detected = detect_platform(reference_data.url)
        
        # Scrape metadata (title and thumbnail)
        metadata = await scrape_metadata(reference_data.url)
        
        # Create reference with scraped data
        reference = Reference(
            id=str(uuid4()),
            workspace_id="w_001",  # Hardcoded for now
            url=reference_data.url,
            note=reference_data.note,
            platform=platform_detected,
            title=metadata["title"],
            thumbnail=metadata["thumbnail"]
        )
        existing = db.query(Reference).filter(
            and_(
                Reference.workspace_id == "w_001",
                Reference.url == reference_data.url
            )
        ).first()

        if existing:
         raise HTTPException(
             status_code=409, 
             detail=f"URL already saved! Add tags to existing reference instead."
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
                "title": reference.title,
                "thumbnail": reference.thumbnail,
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
                    "thumbnail": ref.thumbnail,
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
                "title": reference.title,
                "thumbnail": reference.thumbnail,
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

@router.delete("/{reference_id}")
async def delete_reference(
    reference_id: str,
    db: Session = Depends(get_db)
):
    """Delete a reference"""
    try:
        reference = db.query(Reference).filter(
            and_(
                Reference.id == reference_id,
                Reference.workspace_id == "w_001"
            )
        ).first()
        
        if not reference:
            raise HTTPException(status_code=404, detail="Reference not found")
        
        db.delete(reference)
        db.commit()
        
        return {"ok": True, "message": "Reference deleted"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")
    

@router.get("/categories")
async def get_tag_categories():
    """Get organized tag categories for filtering"""
    categories = {
        "Content Types": ["tutorial", "inspiration", "example", "case-study", "behind-the-scenes"],
        "Creative Elements": ["design", "copywriting", "video-style", "photography", "color-palette"],
        "Business": ["marketing", "branding", "campaign"],
        "Content Formats": ["reel", "story", "carousel", "video", "ugc"],
        "Industries": ["fashion", "beauty", "food", "fitness", "tech", "b2b"],
        "Campaign Types": ["trending", "seasonal", "promotional"],
        "Actions": ["steal-this", "avoid-this", "show-client", "competitor-analysis"]
    }
    
    return {
        "ok": True,
        "categories": categories
    }