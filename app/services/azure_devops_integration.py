"""
Azure DevOps integration service for repository events and work item linking.
"""
import uuid
import logging
import re
from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import aiohttp
import base64

from app.models.user import User
from app.models.document import Document
from app.core.exceptions import NotFoundError, ValidationError, InternalError
from app.services.document import DocumentService
from app.services.auth import AuthService

logger = logging.getLogger(__name__)


class AzureWorkItem:
    """Azure DevOps work item representation."""
    def __init__(self, id: int, title: str, work_item_type: str, state: str, 
                 url: str, description: Optional[str] = None, tags: Optional[List[str]] = None,
                 assigned_to: Optional[str] = None, created_date: Optional[datetime] = None,
                 changed_date: Optional[datetime] = None):
        self.id = id
        self.title = title
        self.work_item_type = work_item_type
        self.state = state
        self.url = url
        self.description = description or ""
        self.tags = tags or []
        self.assigned_to = assigned_to
        self.created_date = created_date
        self.changed_date = changed_date


class AzureBuild:
    """Azure DevOps build representation."""
    def __init__(self, id: int, build_number: str, status: str, result: str,
                 source_branch: str, url: str, started_time: Optional[datetime] = None,
                 finished_time: Optional[datetime] = None, requested_for: Optional[str] = None):
        self.id = id
        self.build_number = build_number
        self.status = status
        self.result = result
        self.source_branch = source_branch
        self.url = url
        self.started_time = started_time
        self.finished_time = finished_time
        self.requested_for = requested_for


class AzureDevOpsIntegrationService:
    """Service for Azure DevOps integration and webhook processing."""
    
    def __init__(self, db: AsyncSession, organization: Optional[str] = None, 
                 personal_access_token: Optional[str] = None):
        self.db = db
        self.organization = organization
        self.pat = personal_access_token
        self.document_service = DocumentService(db)
        self.auth_service = AuthService(db)
    
    async def process_git_push_event(self, payload: Dict[str, Any]) -> None:
        """
        Process Azure DevOps git push event for automatic documentation updates.
        
        Args:
            payload: Azure DevOps git push event payload
        """
        try:
            resource = payload.get("resource", {})
            repository = resource.get("repository", {})
            ref_updates = resource.get("refUpdates", [])
            commits = resource.get("commits", [])
            
            repo_name = repository.get("name", "")
            project_name = repository.get("project", {}).get("name", "")
            
            logger.info(f"Processing Azure DevOps push to {project_name}/{repo_name} with {len(commits)} commits")
            
            # Process each commit for documentation updates
            for commit_data in commits:
                commit_id = commit_data.get("commitId", "")
                comment = commit_data.get("comment", "")
                author = commit_data.get("author", {}).get("name", "")
                url = commit_data.get("url", "")
                
                await self._process_commit_for_docs(commit_id, comment, author, url, repo_name, project_name)
            
            # Update repository information in linked documents
            await self._update_repository_info(repo_name, project_name, commits)
            
        except Exception as e:
            logger.error(f"Error processing Azure DevOps push event: {e}")
            raise
    
    async def process_pull_request_event(self, payload: Dict[str, Any]) -> None:
        """
        Process Azure DevOps pull request event for documentation reviews.
        
        Args:
            payload: Azure DevOps pull request event payload
        """
        try:
            resource = payload.get("resource", {})
            repository = resource.get("repository", {})
            
            pr_id = resource.get("pullRequestId")
            title = resource.get("title", "")
            description = resource.get("description", "")
            status = resource.get("status", "")
            url = resource.get("url", "")
            repo_name = repository.get("name", "")
            project_name = repository.get("project", {}).get("name", "")
            
            logger.info(f"Processing Azure DevOps PR: {project_name}/{repo_name}#{pr_id}")
            
            if status == "active":
                # Check for documentation changes in PR
                await self._analyze_pr_for_docs(pr_id, repo_name, project_name, title, description, url)
            
            elif status == "completed":
                # Update documentation when PR is completed
                await self._handle_completed_pr(pr_id, repo_name, project_name, resource)
            
        except Exception as e:
            logger.error(f"Error processing Azure DevOps PR event: {e}")
            raise
    
    async def process_work_item_event(self, payload: Dict[str, Any]) -> None:
        """
        Process Azure DevOps work item event for work item linking and documentation tasks.
        
        Args:
            payload: Azure DevOps work item event payload
        """
        try:
            resource = payload.get("resource", {})
            fields = resource.get("fields", {})
            
            work_item_id = resource.get("id")
            work_item_type = fields.get("System.WorkItemType", {}).get("newValue", "")
            title = fields.get("System.Title", {}).get("newValue", "")
            state = fields.get("System.State", {}).get("newValue", "")
            description = fields.get("System.Description", {}).get("newValue", "")
            tags = fields.get("System.Tags", {}).get("newValue", "")
            assigned_to = fields.get("System.AssignedTo", {}).get("newValue", {}).get("displayName", "")
            
            # Parse tags
            tag_list = [tag.strip() for tag in tags.split(";")] if tags else []
            
            work_item = AzureWorkItem(
                id=work_item_id,
                title=title,
                work_item_type=work_item_type,
                state=state,
                url=resource.get("url", ""),
                description=description,
                tags=tag_list,
                assigned_to=assigned_to,
                created_date=self._parse_timestamp(fields.get("System.CreatedDate", {}).get("newValue")),
                changed_date=self._parse_timestamp(fields.get("System.ChangedDate", {}).get("newValue"))
            )
            
            logger.info(f"Processing Azure DevOps work item {work_item_type} #{work_item_id}: {state}")
            
            # Create or update documentation tasks from work items
            await self._create_docs_from_work_item(work_item)
            
            # Update work item status in linked documents
            await self._update_work_item_status_in_docs(work_item)
            
        except Exception as e:
            logger.error(f"Error processing Azure DevOps work item event: {e}")
            raise
    
    async def process_build_event(self, payload: Dict[str, Any]) -> None:
        """
        Process Azure DevOps build event for build status updates.
        
        Args:
            payload: Azure DevOps build event payload
        """
        try:
            resource = payload.get("resource", {})
            
            build_id = resource.get("id")
            build_number = resource.get("buildNumber", "")
            status = resource.get("status", "")
            result = resource.get("result", "")
            source_branch = resource.get("sourceBranch", "")
            url = resource.get("url", "")
            requested_for = resource.get("requestedFor", {}).get("displayName", "")
            
            build = AzureBuild(
                id=build_id,
                build_number=build_number,
                status=status,
                result=result,
                source_branch=source_branch,
                url=url,
                started_time=self._parse_timestamp(resource.get("startTime")),
                finished_time=self._parse_timestamp(resource.get("finishTime")),
                requested_for=requested_for
            )
            
            logger.info(f"Processing Azure DevOps build #{build_number}: {status} - {result}")
            
            # Update build status in documentation
            await self._update_build_status_in_docs(build)
            
        except Exception as e:
            logger.error(f"Error processing Azure DevOps build event: {e}")
            raise
    
    async def link_work_item_to_document(self, document_id: uuid.UUID, work_item_id: int, 
                                       user: User) -> None:
        """
        Link an Azure DevOps work item to a documentation page.
        
        Args:
            document_id: Document ID to link to
            work_item_id: Azure DevOps work item ID
            user: User creating the link
        """
        try:
            # Get document
            document = await self.document_service.get_document(document_id, user)
            
            # Fetch work item information from Azure DevOps API
            work_item = await self._fetch_work_item(work_item_id)
            
            # Add work item link to document metadata
            metadata = document.custom_metadata or {}
            linked_work_items = metadata.get("azure_work_items", [])
            
            # Check if work item is already linked
            existing_link = next(
                (link for link in linked_work_items if link.get("id") == work_item_id),
                None
            )
            
            if existing_link:
                # Update existing link
                existing_link.update({
                    "title": work_item.title,
                    "state": work_item.state,
                    "type": work_item.work_item_type,
                    "url": work_item.url,
                    "updated_at": datetime.utcnow().isoformat()
                })
            else:
                # Add new link
                linked_work_items.append({
                    "id": work_item_id,
                    "title": work_item.title,
                    "state": work_item.state,
                    "type": work_item.work_item_type,
                    "url": work_item.url,
                    "assigned_to": work_item.assigned_to,
                    "tags": work_item.tags,
                    "linked_at": datetime.utcnow().isoformat(),
                    "linked_by": user.username
                })
            
            metadata["azure_work_items"] = linked_work_items
            
            # Update document
            await self.document_service.update_document_metadata(document_id, metadata, user)
            
            logger.info(f"Linked Azure DevOps work item #{work_item_id} to document {document_id}")
            
        except Exception as e:
            logger.error(f"Error linking Azure DevOps work item to document: {e}")
            raise
    
    async def get_work_item_status(self, work_item_id: int) -> Dict[str, Any]:
        """
        Get current status of an Azure DevOps work item.
        
        Args:
            work_item_id: Azure DevOps work item ID
            
        Returns:
            Work item status information
        """
        try:
            work_item = await self._fetch_work_item(work_item_id)
            
            return {
                "id": work_item.id,
                "title": work_item.title,
                "type": work_item.work_item_type,
                "state": work_item.state,
                "url": work_item.url,
                "assigned_to": work_item.assigned_to,
                "tags": work_item.tags,
                "created_date": work_item.created_date.isoformat() if work_item.created_date else None,
                "changed_date": work_item.changed_date.isoformat() if work_item.changed_date else None
            }
            
        except Exception as e:
            logger.error(f"Error fetching Azure DevOps work item status: {e}")
            raise
    
    async def process_mentions(self, content: str, project_name: str) -> str:
        """
        Process @mentions in content and convert to Azure DevOps user links.
        
        Args:
            content: Content with potential @mentions
            project_name: Azure DevOps project name for context
            
        Returns:
            Content with processed mentions
        """
        try:
            # Find @mentions in content
            mention_pattern = r'@([a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+\.[a-zA-Z]{2,}|[a-zA-Z0-9_.-]+)'
            mentions = re.findall(mention_pattern, content)
            
            if not mentions:
                return content
            
            # Get project team members
            team_members = await self._fetch_project_team_members(project_name)
            member_emails = {member.lower() for member in team_members}
            
            # Replace valid mentions with Azure DevOps profile links
            processed_content = content
            for mention in set(mentions):
                if mention.lower() in member_emails or '@' in mention:
                    # Create Azure DevOps user link
                    ado_link = f"[@{mention}](https://dev.azure.com/{self.organization}/_settings/users)"
                    processed_content = processed_content.replace(f"@{mention}", ado_link)
            
            return processed_content
            
        except Exception as e:
            logger.error(f"Error processing mentions: {e}")
            return content  # Return original content on error
    
    async def _process_commit_for_docs(self, commit_id: str, message: str, author: str, 
                                     url: str, repo_name: str, project_name: str) -> None:
        """Process a commit for potential documentation updates."""
        try:
            # Check if commit message indicates documentation changes
            doc_keywords = ["docs", "documentation", "readme", "wiki", "guide"]
            message_lower = message.lower()
            
            has_doc_changes = any(keyword in message_lower for keyword in doc_keywords)
            
            if has_doc_changes:
                # Find documents that reference this repository
                documents = await self._find_documents_by_repository(repo_name, project_name)
                
                for document in documents:
                    # Add commit information to document metadata
                    await self._add_commit_to_document(document, commit_id, message, author, url)
            
        except Exception as e:
            logger.error(f"Error processing commit for docs: {e}")
    
    async def _analyze_pr_for_docs(self, pr_id: int, repo_name: str, project_name: str,
                                 title: str, description: str, url: str) -> None:
        """Analyze PR for documentation-related changes."""
        try:
            # Check if PR affects documentation
            doc_keywords = ["docs", "documentation", "readme", "wiki"]
            affects_docs = any(keyword in title.lower() or keyword in description.lower() 
                             for keyword in doc_keywords)
            
            if affects_docs:
                # Find related documents and add PR reference
                documents = await self._find_documents_by_repository(repo_name, project_name)
                
                for document in documents:
                    await self._add_pr_reference_to_document(document, pr_id, title, url)
            
        except Exception as e:
            logger.error(f"Error analyzing PR for docs: {e}")
    
    async def _create_docs_from_work_item(self, work_item: AzureWorkItem) -> None:
        """Create documentation tasks from Azure DevOps work items."""
        try:
            # Check if work item is documentation-related
            doc_tags = {"documentation", "docs", "wiki", "guide", "readme"}
            doc_types = {"User Story", "Task", "Bug"}
            
            is_doc_work_item = (
                any(tag.lower() in doc_tags for tag in work_item.tags) or
                work_item.work_item_type in doc_types and 
                any(keyword in work_item.title.lower() for keyword in ["docs", "documentation", "wiki"])
            )
            
            if is_doc_work_item:
                # Create a documentation task or update existing documents
                logger.info(f"Creating documentation task from work item #{work_item.id}")
                
                # This would integrate with a task management system
                # For now, we'll log the action
                
        except Exception as e:
            logger.error(f"Error creating docs from work item: {e}")
    
    async def _fetch_work_item(self, work_item_id: int) -> AzureWorkItem:
        """Fetch work item information from Azure DevOps API."""
        if not self.organization or not self.pat:
            raise ValidationError("Azure DevOps organization and PAT not configured")
        
        url = f"https://dev.azure.com/{self.organization}/_apis/wit/workitems/{work_item_id}?api-version=6.0"
        
        # Create basic auth header
        auth_string = f":{self.pat}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Accept": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 404:
                    raise NotFoundError(f"Azure DevOps work item #{work_item_id} not found")
                elif response.status != 200:
                    raise InternalError(f"Azure DevOps API error: {response.status}")
                
                data = await response.json()
                fields = data.get("fields", {})
                
                return AzureWorkItem(
                    id=data["id"],
                    title=fields.get("System.Title", ""),
                    work_item_type=fields.get("System.WorkItemType", ""),
                    state=fields.get("System.State", ""),
                    url=data.get("url", ""),
                    description=fields.get("System.Description", ""),
                    tags=fields.get("System.Tags", "").split(";") if fields.get("System.Tags") else [],
                    assigned_to=fields.get("System.AssignedTo", {}).get("displayName", "") if fields.get("System.AssignedTo") else None,
                    created_date=self._parse_timestamp(fields.get("System.CreatedDate")),
                    changed_date=self._parse_timestamp(fields.get("System.ChangedDate"))
                )
    
    async def _fetch_project_team_members(self, project_name: str) -> List[str]:
        """Fetch project team members from Azure DevOps API."""
        if not self.organization or not self.pat:
            return []
        
        url = f"https://dev.azure.com/{self.organization}/_apis/projects/{project_name}/teams?api-version=6.0"
        
        # Create basic auth header
        auth_string = f":{self.pat}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Accept": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        # This is a simplified implementation
                        # In practice, you'd need to fetch team members for each team
                        return []
                    else:
                        logger.warning(f"Failed to fetch team members for {project_name}: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error fetching project team members: {e}")
            return []
    
    async def _find_documents_by_repository(self, repo_name: str, project_name: str) -> List[Document]:
        """Find documents that reference a specific Azure DevOps repository."""
        try:
            # Search for documents that mention the repository in metadata or content
            stmt = select(Document).where(
                Document.custom_metadata.op('?')('azure_repository')
            )
            result = await self.db.execute(stmt)
            documents = result.scalars().all()
            
            # Filter documents that reference this specific repository
            matching_docs = []
            for doc in documents:
                if doc.custom_metadata:
                    azure_repo = doc.custom_metadata.get('azure_repository', {})
                    if (azure_repo.get('name') == repo_name and 
                        azure_repo.get('project') == project_name):
                        matching_docs.append(doc)
            
            return matching_docs
            
        except Exception as e:
            logger.error(f"Error finding documents by repository: {e}")
            return []
    
    async def _add_commit_to_document(self, document: Document, commit_id: str, 
                                    message: str, author: str, url: str) -> None:
        """Add commit information to document metadata."""
        try:
            metadata = document.custom_metadata or {}
            commits = metadata.get("azure_commits", [])
            
            # Add new commit (keep only last 10 commits)
            commits.insert(0, {
                "id": commit_id,
                "message": message,
                "author": author,
                "url": url,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Keep only the last 10 commits
            metadata["azure_commits"] = commits[:10]
            
            # Update document metadata
            document.custom_metadata = metadata
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error adding commit to document: {e}")
    
    async def _add_pr_reference_to_document(self, document: Document, pr_id: int, 
                                          title: str, url: str) -> None:
        """Add PR reference to document metadata."""
        try:
            metadata = document.custom_metadata or {}
            prs = metadata.get("azure_prs", [])
            
            # Check if PR is already referenced
            existing_pr = next((pr for pr in prs if pr.get("id") == pr_id), None)
            
            if not existing_pr:
                prs.append({
                    "id": pr_id,
                    "title": title,
                    "url": url,
                    "referenced_at": datetime.utcnow().isoformat()
                })
                
                metadata["azure_prs"] = prs
                document.custom_metadata = metadata
                await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error adding PR reference to document: {e}")
    
    async def _update_repository_info(self, repo_name: str, project_name: str, commits: List[Dict]) -> None:
        """Update repository information in linked documents."""
        try:
            documents = await self._find_documents_by_repository(repo_name, project_name)
            
            for document in documents:
                metadata = document.custom_metadata or {}
                repo_info = metadata.get("azure_repository_info", {})
                
                repo_info.update({
                    "last_push_at": datetime.utcnow().isoformat(),
                    "last_commit_count": len(commits),
                    "last_commit_id": commits[0].get("commitId") if commits else None
                })
                
                metadata["azure_repository_info"] = repo_info
                document.custom_metadata = metadata
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error updating repository info: {e}")
    
    async def _update_work_item_status_in_docs(self, work_item: AzureWorkItem) -> None:
        """Update work item status in all linked documents."""
        try:
            # Find documents that reference this work item
            stmt = select(Document).where(
                Document.custom_metadata.op('?')('azure_work_items')
            )
            result = await self.db.execute(stmt)
            documents = result.scalars().all()
            
            for document in documents:
                metadata = document.custom_metadata or {}
                linked_work_items = metadata.get("azure_work_items", [])
                
                # Find and update the work item
                for linked_item in linked_work_items:
                    if linked_item.get("id") == work_item.id:
                        linked_item.update({
                            "title": work_item.title,
                            "state": work_item.state,
                            "type": work_item.work_item_type,
                            "assigned_to": work_item.assigned_to,
                            "tags": work_item.tags,
                            "updated_at": datetime.utcnow().isoformat()
                        })
                
                metadata["azure_work_items"] = linked_work_items
                document.custom_metadata = metadata
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error updating work item status in docs: {e}")
    
    async def _update_build_status_in_docs(self, build: AzureBuild) -> None:
        """Update build status in documentation."""
        try:
            # Find documents that might be interested in build status
            # This could be based on repository references or specific metadata
            stmt = select(Document).where(
                Document.custom_metadata.op('?')('azure_builds')
            )
            result = await self.db.execute(stmt)
            documents = result.scalars().all()
            
            for document in documents:
                metadata = document.custom_metadata or {}
                builds = metadata.get("azure_builds", [])
                
                # Add new build info (keep only last 5 builds)
                builds.insert(0, {
                    "id": build.id,
                    "build_number": build.build_number,
                    "status": build.status,
                    "result": build.result,
                    "source_branch": build.source_branch,
                    "url": build.url,
                    "requested_for": build.requested_for,
                    "started_time": build.started_time.isoformat() if build.started_time else None,
                    "finished_time": build.finished_time.isoformat() if build.finished_time else None
                })
                
                metadata["azure_builds"] = builds[:5]
                document.custom_metadata = metadata
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error updating build status in docs: {e}")
    
    async def _handle_completed_pr(self, pr_id: int, repo_name: str, project_name: str, resource: Dict) -> None:
        """Handle completed pull request for documentation updates."""
        try:
            # Update documents with completed PR information
            documents = await self._find_documents_by_repository(repo_name, project_name)
            
            for document in documents:
                metadata = document.custom_metadata or {}
                completed_prs = metadata.get("azure_completed_prs", [])
                
                completed_prs.append({
                    "id": pr_id,
                    "title": resource.get("title", ""),
                    "url": resource.get("url", ""),
                    "completed_at": datetime.utcnow().isoformat(),
                    "merge_status": resource.get("mergeStatus", "")
                })
                
                # Keep only last 20 completed PRs
                metadata["azure_completed_prs"] = completed_prs[-20:]
                document.custom_metadata = metadata
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error handling completed PR: {e}")
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse Azure DevOps timestamp string to datetime."""
        if not timestamp_str:
            return None
        
        try:
            # Azure DevOps uses ISO 8601 format
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None