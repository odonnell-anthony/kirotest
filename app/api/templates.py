"""
Templates and automation features API endpoints.
"""
import uuid
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.services.templates_automation import TemplatesAutomationService, DocumentTemplate, GlossaryTerm, StaleDocument
from app.core.exceptions import NotFoundError, ValidationError, InternalError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


class TemplateResponse(BaseModel):
    """Schema for template response."""
    id: str
    name: str
    description: str
    category: str
    variables: List[str]
    tags: List[str]


class CreateFromTemplateRequest(BaseModel):
    """Schema for creating document from template."""
    template_id: str = Field(..., description="Template ID to use")
    title: str = Field(..., description="Document title")
    folder_path: str = Field("/", description="Folder path for the document")
    variables: Dict[str, str] = Field(..., description="Template variable values")


class OpenAPIGenerationRequest(BaseModel):
    """Schema for OpenAPI documentation generation."""
    openapi_spec: Dict[str, Any] = Field(..., description="OpenAPI specification")
    title: str = Field(..., description="Document title")
    folder_path: str = Field("/", description="Folder path for the document")


class GlossaryTermRequest(BaseModel):
    """Schema for glossary term request."""
    term: str = Field(..., description="Glossary term")
    definition: str = Field(..., description="Term definition")
    aliases: Optional[List[str]] = Field(None, description="Term aliases")
    category: Optional[str] = Field(None, description="Term category")


class GlossaryTermResponse(BaseModel):
    """Schema for glossary term response."""
    term: str
    definition: str
    aliases: List[str]
    category: Optional[str] = None


class StaleDocumentResponse(BaseModel):
    """Schema for stale document response."""
    document_id: str
    title: str
    last_updated: str
    days_stale: int
    staleness_score: float
    reasons: List[str]


class ProcessContentRequest(BaseModel):
    """Schema for content processing request."""
    content: str = Field(..., description="Content to process")


@router.get("/", response_model=List[TemplateResponse])
async def get_templates(
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get available document templates.
    
    - **category**: Optional category filter (API, Operations, Architecture, Documentation)
    
    Returns a list of available templates with their metadata.
    """
    try:
        service = TemplatesAutomationService(db)
        templates = await service.get_templates(category)
        
        return [
            TemplateResponse(
                id=template.id,
                name=template.name,
                description=template.description,
                category=template.category,
                variables=template.variables,
                tags=template.tags
            )
            for template in templates
        ]
        
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific template by ID.
    
    - **template_id**: Template ID to retrieve
    
    Returns template details including variables and content structure.
    """
    try:
        service = TemplatesAutomationService(db)
        template = await service.get_template(template_id)
        
        return TemplateResponse(
            id=template.id,
            name=template.name,
            description=template.description,
            category=template.category,
            variables=template.variables,
            tags=template.tags
        )
        
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/create-document", status_code=status.HTTP_201_CREATED)
async def create_document_from_template(
    request: CreateFromTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new document from a template.
    
    - **template_id**: Template ID to use
    - **title**: Document title
    - **folder_path**: Folder path for the document
    - **variables**: Template variable values (key-value pairs)
    
    Creates a new document with content generated from the template and provided variables.
    """
    try:
        service = TemplatesAutomationService(db)
        document = await service.create_document_from_template(
            template_id=request.template_id,
            title=request.title,
            variables=request.variables,
            folder_path=request.folder_path,
            user=current_user
        )
        
        return {
            "status": "success",
            "message": "Document created from template",
            "document_id": str(document.id),
            "title": document.title
        }
        
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/generate-openapi", status_code=status.HTTP_201_CREATED)
async def generate_from_openapi_schema(
    request: OpenAPIGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate API documentation from OpenAPI/Swagger schema.
    
    - **openapi_spec**: OpenAPI specification (JSON object)
    - **title**: Document title
    - **folder_path**: Folder path for the document
    
    Automatically generates comprehensive API documentation from the provided OpenAPI specification.
    """
    try:
        service = TemplatesAutomationService(db)
        document = await service.generate_from_openapi_schema(
            openapi_spec=request.openapi_spec,
            title=request.title,
            folder_path=request.folder_path,
            user=current_user
        )
        
        return {
            "status": "success",
            "message": "API documentation generated from OpenAPI schema",
            "document_id": str(document.id),
            "title": document.title
        }
        
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/stale-documents/detect", response_model=List[StaleDocumentResponse])
async def detect_stale_documents(
    days_threshold: int = 90,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Detect stale documents that need attention.
    
    - **days_threshold**: Number of days to consider a document stale (default: 90)
    
    Returns a list of documents that haven't been updated recently and may need attention.
    """
    try:
        service = TemplatesAutomationService(db)
        stale_documents = await service.detect_stale_documents(days_threshold)
        
        return [
            StaleDocumentResponse(
                document_id=str(doc.document_id),
                title=doc.title,
                last_updated=doc.last_updated.isoformat(),
                days_stale=doc.days_stale,
                staleness_score=doc.staleness_score,
                reasons=doc.reasons
            )
            for doc in stale_documents
        ]
        
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/glossary/terms", status_code=status.HTTP_201_CREATED)
async def add_glossary_term(
    request: GlossaryTermRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a term to the glossary.
    
    - **term**: Glossary term
    - **definition**: Term definition
    - **aliases**: Optional aliases for the term
    - **category**: Optional category for the term
    
    Adds a new term to the glossary for automatic linking in documentation.
    """
    try:
        service = TemplatesAutomationService(db)
        await service.add_glossary_term(
            term=request.term,
            definition=request.definition,
            aliases=request.aliases,
            category=request.category
        )
        
        return {
            "status": "success",
            "message": f"Added glossary term: {request.term}"
        }
        
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/glossary/terms", response_model=List[GlossaryTermResponse])
async def get_glossary_terms(
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get glossary terms.
    
    - **category**: Optional category filter
    
    Returns a list of glossary terms with their definitions and metadata.
    """
    try:
        service = TemplatesAutomationService(db)
        terms = await service.get_glossary_terms(category)
        
        return [
            GlossaryTermResponse(
                term=term.term,
                definition=term.definition,
                aliases=term.aliases,
                category=term.category
            )
            for term in terms
        ]
        
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/process-glossary-links", status_code=status.HTTP_200_OK)
async def process_glossary_links(
    request: ProcessContentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Process content to add automatic glossary term links.
    
    - **content**: Content to process
    
    Returns processed content with automatic links to glossary terms.
    """
    try:
        service = TemplatesAutomationService(db)
        processed_content = await service.process_glossary_links(request.content)
        
        return {
            "status": "success",
            "processed_content": processed_content
        }
        
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/categories", response_model=List[str])
async def get_template_categories():
    """
    Get available template categories.
    
    Returns a list of available template categories.
    """
    return ["API", "Operations", "Architecture", "Documentation"]


@router.get("/demo/openapi-spec", status_code=status.HTTP_200_OK)
async def get_demo_openapi_spec():
    """
    Get a demo OpenAPI specification for testing.
    
    Returns a sample OpenAPI specification that can be used to test the auto-generation feature.
    """
    demo_spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Wiki Documentation API",
            "version": "1.0.0",
            "description": "API for managing wiki documentation and content"
        },
        "servers": [
            {
                "url": "https://api.wiki-app.com/v1",
                "description": "Production server"
            }
        ],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT"
                }
            },
            "schemas": {
                "Document": {
                    "type": "object",
                    "required": ["title", "content"],
                    "properties": {
                        "id": {
                            "type": "string",
                            "format": "uuid",
                            "description": "Document ID"
                        },
                        "title": {
                            "type": "string",
                            "description": "Document title"
                        },
                        "content": {
                            "type": "string",
                            "description": "Document content in markdown"
                        },
                        "status": {
                            "type": "string",
                            "enum": ["draft", "published"],
                            "description": "Document status"
                        },
                        "created_at": {
                            "type": "string",
                            "format": "date-time",
                            "description": "Creation timestamp"
                        }
                    }
                },
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {
                            "type": "string",
                            "description": "Error message"
                        },
                        "code": {
                            "type": "string",
                            "description": "Error code"
                        }
                    }
                }
            }
        },
        "security": [
            {
                "bearerAuth": []
            }
        ],
        "paths": {
            "/documents": {
                "get": {
                    "summary": "List documents",
                    "description": "Retrieve a list of documents with optional filtering",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "description": "Maximum number of documents to return",
                            "schema": {
                                "type": "integer",
                                "default": 20,
                                "minimum": 1,
                                "maximum": 100
                            }
                        },
                        {
                            "name": "status",
                            "in": "query",
                            "description": "Filter by document status",
                            "schema": {
                                "type": "string",
                                "enum": ["draft", "published"]
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "List of documents",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "$ref": "#/components/schemas/Document"
                                        }
                                    }
                                }
                            }
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Error"
                                    }
                                }
                            }
                        }
                    }
                },
                "post": {
                    "summary": "Create document",
                    "description": "Create a new document",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/Document"
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Document created",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Document"
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Bad request",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Error"
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/documents/{id}": {
                "get": {
                    "summary": "Get document",
                    "description": "Retrieve a specific document by ID",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "description": "Document ID",
                            "schema": {
                                "type": "string",
                                "format": "uuid"
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Document details",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Document"
                                    }
                                }
                            }
                        },
                        "404": {
                            "description": "Document not found",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Error"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    return {
        "status": "success",
        "demo_spec": demo_spec,
        "description": "Demo OpenAPI specification for testing auto-generation"
    }