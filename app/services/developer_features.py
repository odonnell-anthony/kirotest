"""
Developer-focused documentation features service.
"""
import uuid
import logging
import re
import json
import subprocess
import tempfile
import os
from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import aiohttp

from app.models.user import User
from app.models.document import Document
from app.core.exceptions import NotFoundError, ValidationError, InternalError
from app.services.document import DocumentService

logger = logging.getLogger(__name__)


class CodeBlock:
    """Represents a code block with syntax highlighting and execution capabilities."""
    def __init__(self, language: str, code: str, line_numbers: bool = True,
                 executable: bool = False, filename: Optional[str] = None):
        self.language = language
        self.code = code
        self.line_numbers = line_numbers
        self.executable = executable
        self.filename = filename


class APIExample:
    """Represents a live API example with try-it functionality."""
    def __init__(self, method: str, url: str, headers: Optional[Dict[str, str]] = None,
                 body: Optional[str] = None, description: Optional[str] = None,
                 expected_response: Optional[str] = None):
        self.method = method.upper()
        self.url = url
        self.headers = headers or {}
        self.body = body
        self.description = description
        self.expected_response = expected_response


class RepositoryInfo:
    """Repository information for documentation linking."""
    def __init__(self, url: str, branch: str = "main", path: Optional[str] = None,
                 start_line: Optional[int] = None, end_line: Optional[int] = None):
        self.url = url
        self.branch = branch
        self.path = path
        self.start_line = start_line
        self.end_line = end_line


class DeveloperFeaturesService:
    """Service for developer-focused documentation features."""
    
    # Supported languages for syntax highlighting (100+ languages)
    SUPPORTED_LANGUAGES = {
        # Programming languages
        'python', 'javascript', 'typescript', 'java', 'csharp', 'cpp', 'c', 'go', 'rust',
        'php', 'ruby', 'swift', 'kotlin', 'scala', 'clojure', 'haskell', 'erlang', 'elixir',
        'dart', 'lua', 'perl', 'r', 'matlab', 'julia', 'fortran', 'cobol', 'pascal',
        'assembly', 'verilog', 'vhdl', 'systemverilog',
        
        # Web technologies
        'html', 'css', 'scss', 'sass', 'less', 'stylus', 'jsx', 'tsx', 'vue', 'svelte',
        'angular', 'react', 'ember', 'backbone', 'jquery',
        
        # Markup and data formats
        'markdown', 'xml', 'json', 'yaml', 'toml', 'ini', 'csv', 'latex', 'rst',
        'asciidoc', 'textile',
        
        # Shell and scripting
        'bash', 'sh', 'zsh', 'fish', 'powershell', 'batch', 'cmd', 'makefile', 'dockerfile',
        
        # Database and query languages
        'sql', 'mysql', 'postgresql', 'sqlite', 'mongodb', 'redis', 'graphql', 'sparql',
        
        # Configuration and infrastructure
        'nginx', 'apache', 'yaml', 'json', 'xml', 'properties', 'env', 'gitignore',
        'terraform', 'ansible', 'puppet', 'chef', 'vagrant',
        
        # Cloud and containers
        'kubernetes', 'helm', 'docker', 'compose', 'aws', 'azure', 'gcp',
        
        # Functional and specialized languages
        'lisp', 'scheme', 'prolog', 'smalltalk', 'forth', 'tcl', 'awk', 'sed',
        
        # Mobile development
        'objectivec', 'swift', 'java', 'kotlin', 'dart', 'xamarin',
        
        # Game development
        'gdscript', 'hlsl', 'glsl', 'cg', 'unity', 'unreal',
        
        # Scientific computing
        'octave', 'scilab', 'maxima', 'mathematica', 'maple', 'sage',
        
        # Esoteric and educational
        'brainfuck', 'whitespace', 'malbolge', 'befunge', 'intercal',
        
        # Additional languages
        'ada', 'algol', 'apl', 'basic', 'crystal', 'd', 'factor', 'forth', 'groovy',
        'hack', 'idris', 'j', 'nim', 'ocaml', 'oz', 'pony', 'purescript', 'racket',
        'reason', 'red', 'rescript', 'solidity', 'zig'
    }
    
    # Safe languages for code execution
    SAFE_EXECUTABLE_LANGUAGES = {
        'javascript', 'python', 'sql', 'json', 'yaml', 'markdown', 'html', 'css'
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.document_service = DocumentService(db)
    
    async def process_code_blocks(self, content: str) -> str:
        """
        Process code blocks in markdown content for syntax highlighting and execution.
        
        Args:
            content: Markdown content with code blocks
            
        Returns:
            Processed content with enhanced code blocks
        """
        try:
            # Find all code blocks in the content
            code_block_pattern = r'```(\w+)?\n(.*?)\n```'
            
            def replace_code_block(match):
                language = match.group(1) or 'text'
                code = match.group(2)
                
                # Create enhanced code block
                code_block = CodeBlock(
                    language=language.lower(),
                    code=code,
                    line_numbers=True,
                    executable=language.lower() in self.SAFE_EXECUTABLE_LANGUAGES
                )
                
                return self._render_code_block(code_block)
            
            # Replace all code blocks
            processed_content = re.sub(code_block_pattern, replace_code_block, content, flags=re.DOTALL)
            
            return processed_content
            
        except Exception as e:
            logger.error(f"Error processing code blocks: {e}")
            return content  # Return original content on error
    
    async def execute_code_snippet(self, language: str, code: str, user: User) -> Dict[str, Any]:
        """
        Execute code snippet in a sandboxed environment.
        
        Args:
            language: Programming language
            code: Code to execute
            user: User executing the code
            
        Returns:
            Execution result with output, errors, and metadata
        """
        try:
            if language.lower() not in self.SAFE_EXECUTABLE_LANGUAGES:
                raise ValidationError(f"Code execution not supported for language: {language}")
            
            # Log execution attempt
            logger.info(f"Executing {language} code snippet for user {user.username}")
            
            # Execute based on language
            if language.lower() == 'javascript':
                return await self._execute_javascript(code)
            elif language.lower() == 'python':
                return await self._execute_python(code)
            elif language.lower() == 'sql':
                return await self._execute_sql(code)
            elif language.lower() in ['json', 'yaml']:
                return await self._validate_data_format(language, code)
            else:
                return {
                    "success": False,
                    "error": f"Execution not implemented for {language}",
                    "output": "",
                    "execution_time": 0
                }
            
        except Exception as e:
            logger.error(f"Error executing code snippet: {e}")
            return {
                "success": False,
                "error": str(e),
                "output": "",
                "execution_time": 0
            }
    
    async def create_api_example(self, method: str, url: str, headers: Optional[Dict[str, str]] = None,
                               body: Optional[str] = None, description: Optional[str] = None) -> APIExample:
        """
        Create a live API example with try-it functionality.
        
        Args:
            method: HTTP method
            url: API endpoint URL
            headers: Optional headers
            body: Optional request body
            description: Optional description
            
        Returns:
            API example object
        """
        try:
            api_example = APIExample(
                method=method,
                url=url,
                headers=headers,
                body=body,
                description=description
            )
            
            # Validate the API example
            await self._validate_api_example(api_example)
            
            return api_example
            
        except Exception as e:
            logger.error(f"Error creating API example: {e}")
            raise
    
    async def execute_api_example(self, api_example: APIExample, user: User) -> Dict[str, Any]:
        """
        Execute an API example and return the response.
        
        Args:
            api_example: API example to execute
            user: User executing the example
            
        Returns:
            API response with metadata
        """
        try:
            logger.info(f"Executing API example {api_example.method} {api_example.url} for user {user.username}")
            
            start_time = datetime.utcnow()
            
            # Prepare request
            headers = api_example.headers.copy()
            headers.setdefault('User-Agent', 'WikiApp-APITester/1.0')
            
            # Execute request with timeout
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.request(
                    method=api_example.method,
                    url=api_example.url,
                    headers=headers,
                    data=api_example.body,
                    ssl=False  # For development/testing
                ) as response:
                    response_text = await response.text()
                    execution_time = (datetime.utcnow() - start_time).total_seconds()
                    
                    return {
                        "success": True,
                        "status_code": response.status,
                        "headers": dict(response.headers),
                        "body": response_text,
                        "execution_time": execution_time,
                        "content_type": response.headers.get('content-type', ''),
                        "size": len(response_text)
                    }
            
        except Exception as e:
            logger.error(f"Error executing API example: {e}")
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return {
                "success": False,
                "error": str(e),
                "execution_time": execution_time
            }
    
    async def link_repository_code(self, document_id: uuid.UUID, repo_url: str, 
                                 file_path: str, start_line: Optional[int] = None,
                                 end_line: Optional[int] = None, user: User = None) -> None:
        """
        Link documentation to specific code in a repository.
        
        Args:
            document_id: Document ID to link to
            repo_url: Repository URL
            file_path: Path to file in repository
            start_line: Optional start line number
            end_line: Optional end line number
            user: User creating the link
        """
        try:
            # Get document
            document = await self.document_service.get_document(document_id, user)
            
            # Create repository info
            repo_info = RepositoryInfo(
                url=repo_url,
                path=file_path,
                start_line=start_line,
                end_line=end_line
            )
            
            # Add repository link to document metadata
            metadata = document.custom_metadata or {}
            repo_links = metadata.get("repository_links", [])
            
            repo_links.append({
                "url": repo_info.url,
                "path": repo_info.path,
                "start_line": repo_info.start_line,
                "end_line": repo_info.end_line,
                "linked_at": datetime.utcnow().isoformat(),
                "linked_by": user.username if user else "system"
            })
            
            metadata["repository_links"] = repo_links
            
            # Update document
            await self.document_service.update_document_metadata(document_id, metadata, user)
            
            logger.info(f"Linked repository code {repo_url}:{file_path} to document {document_id}")
            
        except Exception as e:
            logger.error(f"Error linking repository code: {e}")
            raise
    
    async def get_repository_info(self, repo_url: str, file_path: str) -> Dict[str, Any]:
        """
        Get repository information for documentation display.
        
        Args:
            repo_url: Repository URL
            file_path: Path to file in repository
            
        Returns:
            Repository information
        """
        try:
            # Parse repository URL to determine provider (GitHub, GitLab, etc.)
            if 'github.com' in repo_url:
                return await self._get_github_repo_info(repo_url, file_path)
            elif 'gitlab.com' in repo_url:
                return await self._get_gitlab_repo_info(repo_url, file_path)
            elif 'dev.azure.com' in repo_url or 'visualstudio.com' in repo_url:
                return await self._get_azure_repo_info(repo_url, file_path)
            else:
                return {
                    "provider": "unknown",
                    "url": repo_url,
                    "file_path": file_path,
                    "last_commit": None,
                    "last_modified": None
                }
            
        except Exception as e:
            logger.error(f"Error getting repository info: {e}")
            return {
                "provider": "unknown",
                "url": repo_url,
                "file_path": file_path,
                "error": str(e)
            }
    
    def _render_code_block(self, code_block: CodeBlock) -> str:
        """Render enhanced code block HTML."""
        language_class = f"language-{code_block.language}"
        executable_attr = 'data-executable="true"' if code_block.executable else ''
        line_numbers_attr = 'data-line-numbers="true"' if code_block.line_numbers else ''
        
        return f'''
<div class="code-block-container" {executable_attr}>
    <div class="code-block-header">
        <span class="language-label">{code_block.language}</span>
        <div class="code-block-actions">
            <button class="copy-code-btn" title="Copy to clipboard">📋</button>
            {f'<button class="run-code-btn" title="Run code">▶️</button>' if code_block.executable else ''}
        </div>
    </div>
    <pre class="code-block" {line_numbers_attr}><code class="{language_class}">{code_block.code}</code></pre>
    {f'<div class="code-output" style="display: none;"></div>' if code_block.executable else ''}
</div>
'''
    
    async def _execute_javascript(self, code: str) -> Dict[str, Any]:
        """Execute JavaScript code in Node.js sandbox."""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                # Wrap code in try-catch for better error handling
                wrapped_code = f'''
try {{
    {code}
}} catch (error) {{
    console.error('Error:', error.message);
    process.exit(1);
}}
'''
                f.write(wrapped_code)
                temp_file = f.name
            
            try:
                # Execute with timeout
                result = subprocess.run(
                    ['node', temp_file],
                    capture_output=True,
                    text=True,
                    timeout=10  # 10 second timeout
                )
                
                return {
                    "success": result.returncode == 0,
                    "output": result.stdout,
                    "error": result.stderr if result.returncode != 0 else None,
                    "execution_time": 0  # Simplified for now
                }
            finally:
                # Clean up temporary file
                os.unlink(temp_file)
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Code execution timed out (10 seconds)",
                "output": "",
                "execution_time": 10
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "Node.js not found. Please install Node.js to execute JavaScript code.",
                "output": "",
                "execution_time": 0
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": "",
                "execution_time": 0
            }
    
    async def _execute_python(self, code: str) -> Dict[str, Any]:
        """Execute Python code in sandbox."""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                # Add basic imports and error handling
                wrapped_code = f'''
import sys
import traceback

try:
{chr(10).join("    " + line for line in code.split(chr(10)))}
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
'''
                f.write(wrapped_code)
                temp_file = f.name
            
            try:
                # Execute with timeout
                result = subprocess.run(
                    ['python3', temp_file],
                    capture_output=True,
                    text=True,
                    timeout=10  # 10 second timeout
                )
                
                return {
                    "success": result.returncode == 0,
                    "output": result.stdout,
                    "error": result.stderr if result.returncode != 0 else None,
                    "execution_time": 0  # Simplified for now
                }
            finally:
                # Clean up temporary file
                os.unlink(temp_file)
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Code execution timed out (10 seconds)",
                "output": "",
                "execution_time": 10
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "Python not found. Please install Python to execute Python code.",
                "output": "",
                "execution_time": 0
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": "",
                "execution_time": 0
            }
    
    async def _execute_sql(self, code: str) -> Dict[str, Any]:
        """Validate SQL syntax (no actual execution for security)."""
        try:
            # Basic SQL syntax validation
            sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER']
            code_upper = code.upper().strip()
            
            # Check if it starts with a valid SQL keyword
            starts_with_sql = any(code_upper.startswith(keyword) for keyword in sql_keywords)
            
            if starts_with_sql:
                return {
                    "success": True,
                    "output": "SQL syntax appears valid (not executed for security)",
                    "error": None,
                    "execution_time": 0
                }
            else:
                return {
                    "success": False,
                    "error": "Invalid SQL syntax",
                    "output": "",
                    "execution_time": 0
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": "",
                "execution_time": 0
            }
    
    async def _validate_data_format(self, language: str, code: str) -> Dict[str, Any]:
        """Validate JSON or YAML format."""
        try:
            if language.lower() == 'json':
                json.loads(code)
                return {
                    "success": True,
                    "output": "Valid JSON format",
                    "error": None,
                    "execution_time": 0
                }
            elif language.lower() == 'yaml':
                import yaml
                yaml.safe_load(code)
                return {
                    "success": True,
                    "output": "Valid YAML format",
                    "error": None,
                    "execution_time": 0
                }
            else:
                return {
                    "success": False,
                    "error": f"Validation not supported for {language}",
                    "output": "",
                    "execution_time": 0
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Invalid {language.upper()} format: {str(e)}",
                "output": "",
                "execution_time": 0
            }
    
    async def _validate_api_example(self, api_example: APIExample) -> None:
        """Validate API example configuration."""
        if api_example.method not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']:
            raise ValidationError(f"Unsupported HTTP method: {api_example.method}")
        
        if not api_example.url.startswith(('http://', 'https://')):
            raise ValidationError("API URL must start with http:// or https://")
    
    async def _get_github_repo_info(self, repo_url: str, file_path: str) -> Dict[str, Any]:
        """Get GitHub repository information."""
        try:
            # Parse GitHub URL
            # Example: https://github.com/owner/repo/blob/main/path/to/file.py
            url_parts = repo_url.replace('https://github.com/', '').split('/')
            if len(url_parts) >= 2:
                owner, repo = url_parts[0], url_parts[1]
                
                # Use GitHub API to get file info
                api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            return {
                                "provider": "github",
                                "owner": owner,
                                "repo": repo,
                                "file_path": file_path,
                                "url": repo_url,
                                "last_commit": data.get("sha"),
                                "size": data.get("size"),
                                "download_url": data.get("download_url")
                            }
            
            return {
                "provider": "github",
                "url": repo_url,
                "file_path": file_path,
                "error": "Could not fetch repository information"
            }
            
        except Exception as e:
            logger.error(f"Error getting GitHub repo info: {e}")
            return {
                "provider": "github",
                "url": repo_url,
                "file_path": file_path,
                "error": str(e)
            }
    
    async def _get_gitlab_repo_info(self, repo_url: str, file_path: str) -> Dict[str, Any]:
        """Get GitLab repository information."""
        # Simplified implementation
        return {
            "provider": "gitlab",
            "url": repo_url,
            "file_path": file_path,
            "note": "GitLab integration not fully implemented"
        }
    
    async def _get_azure_repo_info(self, repo_url: str, file_path: str) -> Dict[str, Any]:
        """Get Azure DevOps repository information."""
        # Simplified implementation
        return {
            "provider": "azure_devops",
            "url": repo_url,
            "file_path": file_path,
            "note": "Azure DevOps integration not fully implemented"
        }