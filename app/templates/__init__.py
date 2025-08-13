# Template utilities
from typing import Dict, List, Any, Optional
from fastapi.templating import Jinja2Templates
from fastapi import Request
import os
import markdown
from markdown.extensions import codehilite, toc, tables, fenced_code
import re

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="app/templates")

# Configure markdown processor
md = markdown.Markdown(extensions=[
    'codehilite',
    'toc',
    'tables',
    'fenced_code',
    'attr_list',
    'def_list',
    'footnotes',
    'md_in_html'
], extension_configs={
    'codehilite': {
        'css_class': 'highlight',
        'use_pygments': True
    },
    'toc': {
        'permalink': True,
        'permalink_class': 'heading-anchor',
        'permalink_title': 'Link to this heading'
    }
})

def markdown_filter(text: str) -> str:
    """Convert markdown text to HTML."""
    if not text:
        return ""
    
    # Process Mermaid diagrams
    text = process_mermaid_diagrams(text)
    
    # Convert markdown to HTML
    html = md.convert(text)
    
    # Reset markdown processor for next use
    md.reset()
    
    return html

def process_mermaid_diagrams(text: str) -> str:
    """Process Mermaid diagram code blocks."""
    # Pattern to match mermaid code blocks
    pattern = r'```mermaid\n(.*?)\n```'
    
    def replace_mermaid(match):
        diagram_code = match.group(1)
        return f'<div class="mermaid">\n{diagram_code}\n</div>'
    
    return re.sub(pattern, replace_mermaid, text, flags=re.DOTALL)

# Add custom filters to Jinja2
templates.env.filters['markdown'] = markdown_filter

def get_template_context(request: Request, **kwargs) -> Dict[str, Any]:
    """Get base template context with common variables."""
    context = {
        "request": request,
        "user": getattr(request.state, "user", None),
        "theme": getattr(request.state, "theme", "light"),
        "messages": getattr(request.state, "messages", []),
        "flash_messages": getattr(request.state, "flash_messages", []),
        **kwargs
    }
    return context

def render_template(request: Request, template_name: str, **kwargs):
    """Render template with base context."""
    context = get_template_context(request, **kwargs)
    return templates.TemplateResponse(template_name, context)

class FolderTreeBuilder:
    """Helper class to build folder tree structure for navigation."""
    
    @staticmethod
    def build_tree(folders: List[Dict], documents: List[Dict], current_path: str = None) -> List[Dict]:
        """Build hierarchical folder tree with documents."""
        tree = []
        folder_map = {}
        
        # Create folder structure
        for folder in folders:
            folder_item = {
                "type": "folder",
                "name": folder["name"],
                "path": folder["path"],
                "children": [],
                "expanded": FolderTreeBuilder._should_expand(folder["path"], current_path)
            }
            folder_map[folder["path"]] = folder_item
            
            # Find parent and add to tree
            parent_path = folder.get("parent_path")
            if parent_path and parent_path in folder_map:
                folder_map[parent_path]["children"].append(folder_item)
            else:
                tree.append(folder_item)
        
        # Add documents to their folders
        for doc in documents:
            doc_item = {
                "type": "document",
                "title": doc["title"],
                "path": doc["path"],
                "active": doc["path"] == current_path
            }
            
            folder_path = doc.get("folder_path", "/")
            if folder_path in folder_map:
                folder_map[folder_path]["children"].append(doc_item)
            else:
                tree.append(doc_item)
        
        # Sort children (folders first, then documents, both alphabetically)
        FolderTreeBuilder._sort_tree(tree)
        
        return tree
    
    @staticmethod
    def _should_expand(folder_path: str, current_path: str = None) -> bool:
        """Determine if folder should be expanded based on current path."""
        if not current_path:
            return False
        return current_path.startswith(folder_path)
    
    @staticmethod
    def _sort_tree(tree: List[Dict]):
        """Sort tree items recursively."""
        tree.sort(key=lambda x: (x["type"] == "document", x.get("name", x.get("title", ""))))
        
        for item in tree:
            if item.get("children"):
                FolderTreeBuilder._sort_tree(item["children"])

def build_breadcrumbs(path: str, folders: List[Dict] = None) -> List[Dict]:
    """Build breadcrumb navigation for a given path."""
    if not path or path == "/":
        return [{"title": "Home", "url": "/"}]
    
    breadcrumbs = [{"title": "Home", "url": "/"}]
    
    # Split path and build breadcrumbs
    parts = [p for p in path.split("/") if p]
    current_path = ""
    
    for i, part in enumerate(parts):
        current_path += "/" + part
        is_last = i == len(parts) - 1
        
        breadcrumbs.append({
            "title": part.replace("-", " ").replace("_", " ").title(),
            "url": current_path if not is_last else None
        })
    
    return breadcrumbs