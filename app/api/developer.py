"""
Developer-focused documentation features API endpoints.
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
from app.services.developer_features import DeveloperFeaturesService, APIExample
from app.core.exceptions import NotFoundError, ValidationError, InternalError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/developer", tags=["developer"])


class CodeExecutionRequest(BaseModel):
    """Schema for code execution request."""
    language: str = Field(..., description="Programming language")
    code: str = Field(..., description="Code to execute")


class CodeExecutionResponse(BaseModel):
    """Schema for code execution response."""
    success: bool
    output: str
    error: Optional[str] = None
    execution_time: float


class APIExampleRequest(BaseModel):
    """Schema for API example request."""
    method: str = Field(..., description="HTTP method")
    url: str = Field(..., description="API endpoint URL")
    headers: Optional[Dict[str, str]] = Field(None, description="Request headers")
    body: Optional[str] = Field(None, description="Request body")
    description: Optional[str] = Field(None, description="Example description")


class APIExampleResponse(BaseModel):
    """Schema for API example response."""
    success: bool
    status_code: Optional[int] = None
    headers: Optional[Dict[str, str]] = None
    body: Optional[str] = None
    error: Optional[str] = None
    execution_time: float
    content_type: Optional[str] = None
    size: Optional[int] = None


class RepositoryLinkRequest(BaseModel):
    """Schema for repository link request."""
    document_id: uuid.UUID = Field(..., description="Document ID to link to")
    repo_url: str = Field(..., description="Repository URL")
    file_path: str = Field(..., description="Path to file in repository")
    start_line: Optional[int] = Field(None, description="Start line number")
    end_line: Optional[int] = Field(None, description="End line number")


class RepositoryInfoResponse(BaseModel):
    """Schema for repository information response."""
    provider: str
    url: str
    file_path: str
    owner: Optional[str] = None
    repo: Optional[str] = None
    last_commit: Optional[str] = None
    size: Optional[int] = None
    download_url: Optional[str] = None
    error: Optional[str] = None


@router.get("/languages", response_model=List[str])
async def get_supported_languages():
    """
    Get list of supported programming languages for syntax highlighting.
    
    Returns a list of all supported language identifiers.
    """
    service = DeveloperFeaturesService(None)  # No DB needed for this
    return sorted(list(service.SUPPORTED_LANGUAGES))


@router.get("/executable-languages", response_model=List[str])
async def get_executable_languages():
    """
    Get list of programming languages that support code execution.
    
    Returns a list of language identifiers that can be executed safely.
    """
    service = DeveloperFeaturesService(None)  # No DB needed for this
    return sorted(list(service.SAFE_EXECUTABLE_LANGUAGES))


@router.post("/execute-code", response_model=CodeExecutionResponse)
async def execute_code(
    request: CodeExecutionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Execute code snippet in a sandboxed environment.
    
    - **language**: Programming language (must be in executable languages list)
    - **code**: Code to execute
    
    Supports safe execution of JavaScript, Python, SQL validation, and data format validation.
    """
    try:
        service = DeveloperFeaturesService(db)
        result = await service.execute_code_snippet(request.language, request.code, current_user)
        
        return CodeExecutionResponse(
            success=result["success"],
            output=result["output"],
            error=result.get("error"),
            execution_time=result["execution_time"]
        )
        
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/api-example", response_model=APIExampleResponse)
async def execute_api_example(
    request: APIExampleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Execute a live API example with "Try it" functionality.
    
    - **method**: HTTP method (GET, POST, PUT, DELETE, etc.)
    - **url**: API endpoint URL
    - **headers**: Optional request headers
    - **body**: Optional request body
    - **description**: Optional description
    
    Executes the API request and returns the response with metadata.
    """
    try:
        service = DeveloperFeaturesService(db)
        
        # Create API example
        api_example = await service.create_api_example(
            method=request.method,
            url=request.url,
            headers=request.headers,
            body=request.body,
            description=request.description
        )
        
        # Execute the API example
        result = await service.execute_api_example(api_example, current_user)
        
        return APIExampleResponse(
            success=result["success"],
            status_code=result.get("status_code"),
            headers=result.get("headers"),
            body=result.get("body"),
            error=result.get("error"),
            execution_time=result["execution_time"],
            content_type=result.get("content_type"),
            size=result.get("size")
        )
        
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/link-repository", status_code=status.HTTP_201_CREATED)
async def link_repository_code(
    request: RepositoryLinkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Link documentation to specific code in a repository.
    
    - **document_id**: UUID of the document to link to
    - **repo_url**: Repository URL (GitHub, GitLab, Azure DevOps)
    - **file_path**: Path to file in repository
    - **start_line**: Optional start line number for specific code section
    - **end_line**: Optional end line number for specific code section
    
    Creates a link between documentation and repository code with line-level precision.
    """
    try:
        service = DeveloperFeaturesService(db)
        
        await service.link_repository_code(
            document_id=request.document_id,
            repo_url=request.repo_url,
            file_path=request.file_path,
            start_line=request.start_line,
            end_line=request.end_line,
            user=current_user
        )
        
        return {
            "status": "success",
            "message": f"Linked repository code {request.repo_url}:{request.file_path} to document"
        }
        
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/repository-info", response_model=RepositoryInfoResponse)
async def get_repository_info(
    repo_url: str,
    file_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get repository information for documentation display.
    
    - **repo_url**: Repository URL
    - **file_path**: Path to file in repository
    
    Returns repository metadata including last commit, file size, and provider information.
    """
    try:
        service = DeveloperFeaturesService(db)
        info = await service.get_repository_info(repo_url, file_path)
        
        return RepositoryInfoResponse(**info)
        
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/process-content", status_code=status.HTTP_200_OK)
async def process_content_for_syntax_highlighting(
    content: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Process markdown content for enhanced syntax highlighting and code execution.
    
    - **content**: Markdown content with code blocks
    
    Returns processed content with enhanced code blocks that support:
    - Syntax highlighting for 100+ languages
    - Line numbers
    - Copy to clipboard functionality
    - Code execution for safe languages
    """
    try:
        service = DeveloperFeaturesService(db)
        processed_content = await service.process_code_blocks(content)
        
        return {
            "status": "success",
            "processed_content": processed_content
        }
        
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/syntax-highlighting-demo", status_code=status.HTTP_200_OK)
async def get_syntax_highlighting_demo():
    """
    Get a demonstration of syntax highlighting capabilities.
    
    Returns sample code in various languages to showcase syntax highlighting features.
    """
    demo_code = {
        "python": '''def fibonacci(n):
    """Generate Fibonacci sequence up to n terms."""
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

# Example usage
for num in fibonacci(10):
    print(num)''',
        
        "javascript": '''// Async function with modern JavaScript features
async function fetchUserData(userId) {
    try {
        const response = await fetch(`/api/users/${userId}`);
        const userData = await response.json();
        
        return {
            ...userData,
            lastLogin: new Date(userData.lastLogin)
        };
    } catch (error) {
        console.error('Failed to fetch user data:', error);
        throw error;
    }
}''',
        
        "sql": '''-- Complex query with joins and window functions
SELECT 
    u.username,
    u.email,
    COUNT(d.id) as document_count,
    AVG(d.view_count) as avg_views,
    ROW_NUMBER() OVER (ORDER BY COUNT(d.id) DESC) as rank
FROM users u
LEFT JOIN documents d ON u.id = d.author_id
WHERE u.is_active = true
    AND d.status = 'published'
    AND d.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY u.id, u.username, u.email
HAVING document_count > 0
ORDER BY document_count DESC
LIMIT 10;''',
        
        "yaml": '''# Kubernetes deployment configuration
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wiki-app
  labels:
    app: wiki-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: wiki-app
  template:
    metadata:
      labels:
        app: wiki-app
    spec:
      containers:
      - name: wiki-app
        image: wiki-app:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: wiki-secrets
              key: database-url''',
        
        "json": '''{
  "openapi": "3.0.0",
  "info": {
    "title": "Wiki Documentation API",
    "version": "1.0.0",
    "description": "API for managing wiki documentation"
  },
  "paths": {
    "/api/v1/documents": {
      "get": {
        "summary": "List documents",
        "parameters": [
          {
            "name": "limit",
            "in": "query",
            "schema": {
              "type": "integer",
              "default": 20
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
          }
        }
      }
    }
  }
}'''
    }
    
    return {
        "status": "success",
        "demo_code": demo_code,
        "supported_languages_count": len(DeveloperFeaturesService.SUPPORTED_LANGUAGES),
        "executable_languages_count": len(DeveloperFeaturesService.SAFE_EXECUTABLE_LANGUAGES)
    }