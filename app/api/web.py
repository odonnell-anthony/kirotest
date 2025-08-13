"""
Web routes for server-side rendered pages.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.core.database import get_db
from app.core.auth import get_current_user_optional, get_current_user
from app.models.user import User
from app.models.document import Document
from app.models.folder import Folder
from app.models.tag import Tag
from app.models.audit import AuditLog
from app.services.document import DocumentService
from app.services.folder import FolderService
from app.services.tag import TagService
from app.services.timeline import TimelineService
from app.templates import render_template, FolderTreeBuilder, build_breadcrumbs
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional)
):
    """Home page with dashboard or welcome screen."""
    try:
        # Get folder tree for navigation
        folder_service = FolderService(db)
        document_service = DocumentService(db)
        
        folders = await folder_service.get_all_folders()
        documents = await document_service.get_all_documents_summary()
        
        folder_tree = FolderTreeBuilder.build_tree(
            [{"name": f.name, "path": f.path, "parent_path": f.parent_path} for f in folders],
            [{"title": d.title, "path": f"/{d.slug}", "folder_path": d.folder_path} for d in documents]
        )
        
        context = {
            "folder_tree": folder_tree,
            "has_documents": len(documents) > 0
        }
        
        if user and len(documents) > 0:
            # Get dashboard data
            tag_service = TagService(db)
            timeline_service = TimelineService(db)
            
            # Get stats
            stats = {
                "total_documents": len(documents),
                "total_folders": len(folders),
                "total_tags": await tag_service.get_tag_count(),
                "total_users": await db.scalar(select(func.count(User.id)))
            }
            
            # Get recent activity
            recent_activity = await timeline_service.get_recent_activity(limit=10)
            
            # Get popular tags
            popular_tags = await tag_service.get_popular_tags(limit=20)
            max_tag_usage = max([tag.usage_count for tag in popular_tags], default=1)
            
            context.update({
                "stats": stats,
                "recent_activity": recent_activity,
                "popular_tags": popular_tags,
                "max_tag_usage": max_tag_usage
            })
        
        return render_template(request, "home.html", **context)
        
    except Exception as e:
        await logger.aerror("Error rendering home page", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
):
    """Login page."""
    if user:
        return RedirectResponse(url="/", status_code=302)
    
    return render_template(request, "auth/login.html")

@router.get("/logout")
async def logout(request: Request):
    """Logout and redirect to home."""
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response

@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: Optional[str] = None,
    tags: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional)
):
    """Search page with results."""
    try:
        # Get folder tree for navigation
        folder_service = FolderService(db)
        document_service = DocumentService(db)
        
        folders = await folder_service.get_all_folders()
        documents = await document_service.get_all_documents_summary()
        
        folder_tree = FolderTreeBuilder.build_tree(
            [{"name": f.name, "path": f.path, "parent_path": f.parent_path} for f in folders],
            [{"title": d.title, "path": f"/{d.slug}", "folder_path": d.folder_path} for d in documents]
        )
        
        search_results = []
        if q or tags:
            # Perform search (simplified for now)
            search_service = DocumentService(db)  # Would use SearchService in full implementation
            # search_results = await search_service.search(q, tags, user)
        
        context = {
            "folder_tree": folder_tree,
            "query": q,
            "selected_tags": tags.split(",") if tags else [],
            "search_results": search_results,
            "breadcrumbs": [
                {"title": "Home", "url": "/"},
                {"title": "Search", "url": None}
            ]
        }
        
        return render_template(request, "search.html", **context)
        
    except Exception as e:
        await logger.aerror("Error rendering search page", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/timeline", response_class=HTMLResponse)
async def timeline_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Timeline page showing recent activity."""
    try:
        # Get folder tree for navigation
        folder_service = FolderService(db)
        document_service = DocumentService(db)
        
        folders = await folder_service.get_all_folders()
        documents = await document_service.get_all_documents_summary()
        
        folder_tree = FolderTreeBuilder.build_tree(
            [{"name": f.name, "path": f.path, "parent_path": f.parent_path} for f in folders],
            [{"title": d.title, "path": f"/{d.slug}", "folder_path": d.folder_path} for d in documents]
        )
        
        # Get timeline data
        timeline_service = TimelineService(db)
        activities = await timeline_service.get_recent_activity(limit=50)
        
        context = {
            "folder_tree": folder_tree,
            "activities": activities,
            "breadcrumbs": [
                {"title": "Home", "url": "/"},
                {"title": "Timeline", "url": None}
            ]
        }
        
        return render_template(request, "timeline.html", **context)
        
    except Exception as e:
        await logger.aerror("Error rendering timeline page", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/editor", response_class=HTMLResponse)
async def editor_page(
    request: Request,
    folder: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Document editor page for creating new documents."""
    try:
        # Get folder tree for navigation
        folder_service = FolderService(db)
        document_service = DocumentService(db)
        tag_service = TagService(db)
        
        folders = await folder_service.get_all_folders()
        documents = await document_service.get_all_documents_summary()
        all_tags = await tag_service.get_all_tags()
        
        folder_tree = FolderTreeBuilder.build_tree(
            [{"name": f.name, "path": f.path, "parent_path": f.parent_path} for f in folders],
            [{"title": d.title, "path": f"/{d.slug}", "folder_path": d.folder_path} for d in documents]
        )
        
        context = {
            "folder_tree": folder_tree,
            "selected_folder": folder or "/",
            "all_tags": [{"name": tag.name, "id": tag.id} for tag in all_tags],
            "breadcrumbs": [
                {"title": "Home", "url": "/"},
                {"title": "New Document", "url": None}
            ]
        }
        
        return render_template(request, "editor.html", **context)
        
    except Exception as e:
        await logger.aerror("Error rendering editor page", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/editor/{path:path}", response_class=HTMLResponse)
async def edit_document_page(
    request: Request,
    path: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Document editor page for editing existing documents."""
    try:
        # Get document
        document_service = DocumentService(db)
        document = await document_service.get_document_by_path(f"/{path}")
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get folder tree for navigation
        folder_service = FolderService(db)
        tag_service = TagService(db)
        
        folders = await folder_service.get_all_folders()
        documents = await document_service.get_all_documents_summary()
        all_tags = await tag_service.get_all_tags()
        
        folder_tree = FolderTreeBuilder.build_tree(
            [{"name": f.name, "path": f.path, "parent_path": f.parent_path} for f in folders],
            [{"title": d.title, "path": f"/{d.slug}", "folder_path": d.folder_path} for d in documents],
            current_path=f"/{path}"
        )
        
        context = {
            "folder_tree": folder_tree,
            "document": document,
            "all_tags": [{"name": tag.name, "id": tag.id} for tag in all_tags],
            "breadcrumbs": build_breadcrumbs(f"/{path}")
        }
        
        return render_template(request, "editor.html", **context)
        
    except HTTPException:
        raise
    except Exception as e:
        await logger.aerror("Error rendering edit document page", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{path:path}", response_class=HTMLResponse)
async def view_document(
    request: Request,
    path: str,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional)
):
    """View a document page."""
    try:
        # Get document
        document_service = DocumentService(db)
        document = await document_service.get_document_by_path(f"/{path}")
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Check permissions
        if document.status == "draft" and (not user or (user.id != document.author_id and user.role != "admin")):
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get folder tree for navigation
        folder_service = FolderService(db)
        
        folders = await folder_service.get_all_folders()
        documents = await document_service.get_all_documents_summary()
        
        folder_tree = FolderTreeBuilder.build_tree(
            [{"name": f.name, "path": f.path, "parent_path": f.parent_path} for f in folders],
            [{"title": d.title, "path": f"/{d.slug}", "folder_path": d.folder_path} for d in documents],
            current_path=f"/{path}"
        )
        
        # Get comments if user is authenticated
        comments = []
        if user:
            from app.services.comment import CommentService
            comment_service = CommentService(db)
            try:
                comments = await comment_service.list_document_comments(
                    document.id, user, include_replies=True
                )
            except Exception as e:
                await logger.aerror("Error loading comments", error=str(e))
                comments = []
        
        context = {
            "folder_tree": folder_tree,
            "document": document,
            "comments": comments,
            "can_edit": user and (user.id == document.author_id or user.role == "admin"),
            "breadcrumbs": build_breadcrumbs(f"/{path}")
        }
        
        return render_template(request, "document.html", **context)
        
    except HTTPException:
        raise
    except Exception as e:
        await logger.aerror("Error rendering document page", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/api/v1/auth/theme")
async def update_theme_preference(
    request: Request,
    theme: str = Form(...),
    user: User = Depends(get_current_user)
):
    """Update user's theme preference."""
    if theme not in ["light", "dark"]:
        raise HTTPException(status_code=400, detail="Invalid theme")
    
    # Update user's theme preference in database
    # For now, just return success
    return {"success": True}