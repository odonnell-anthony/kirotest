"""
GitHub integration service for repository events and issue linking.
"""
import uuid
import logging
import re
from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import aiohttp

from app.models.user import User
from app.models.document import Document
from app.core.exceptions import NotFoundError, ValidationError, InternalError
from app.services.document import DocumentService
from app.services.auth import AuthService

logger = logging.getLogger(__name__)


class GitHubIssue:
    """GitHub issue representation."""
    def __init__(self, number: int, title: str, state: str, html_url: str, 
                 body: Optional[str] = None, labels: Optional[List[str]] = None,
                 assignees: Optional[List[str]] = None, created_at: Optional[datetime] = None,
                 updated_at: Optional[datetime] = None):
        self.number = number
        self.title = title
        self.state = state
        self.html_url = html_url
        self.body = body or ""
        self.labels = labels or []
        self.assignees = assignees or []
        self.created_at = created_at
        self.updated_at = updated_at


class GitHubCommit:
    """GitHub commit representation."""
    def __init__(self, sha: str, message: str, author: str, html_url: str,
                 timestamp: Optional[datetime] = None, modified_files: Optional[List[str]] = None):
        self.sha = sha
        self.message = message
        self.author = author
        self.html_url = html_url
        self.timestamp = timestamp
        self.modified_files = modified_files or []


class GitHubIntegrationService:
    """Service for GitHub integration and webhook processing."""
    
    def __init__(self, db: AsyncSession, github_token: Optional[str] = None):
        self.db = db
        self.github_token = github_token
        self.document_service = DocumentService(db)
        self.auth_service = AuthService(db)
    
    async def process_push_event(self, payload: Dict[str, Any]) -> None:
        """
        Process GitHub push event for automatic documentation updates.
        
        Args:
            payload: GitHub push event payload
        """
        try:
            repository = payload.get("repository", {})
            commits = payload.get("commits", [])
            ref = payload.get("ref", "")
            
            repo_name = repository.get("full_name", "")
            branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref
            
            logger.info(f"Processing GitHub push to {repo_name}:{branch} with {len(commits)} commits")
            
            # Process each commit for documentation updates
            for commit_data in commits:
                commit = GitHubCommit(
                    sha=commit_data.get("id", ""),
                    message=commit_data.get("message", ""),
                    author=commit_data.get("author", {}).get("name", ""),
                    html_url=commit_data.get("url", ""),
                    timestamp=self._parse_timestamp(commit_data.get("timestamp")),
                    modified_files=commit_data.get("modified", []) + commit_data.get("added", [])
                )
                
                await self._process_commit_for_docs(commit, repo_name, branch)
            
            # Update repository information in linked documents
            await self._update_repository_info(repo_name, branch, commits)
            
        except Exception as e:
            logger.error(f"Error processing GitHub push event: {e}")
            raise
    
    async def process_pull_request_event(self, payload: Dict[str, Any]) -> None:
        """
        Process GitHub pull request event for documentation reviews.
        
        Args:
            payload: GitHub pull request event payload
        """
        try:
            action = payload.get("action", "")
            pull_request = payload.get("pull_request", {})
            repository = payload.get("repository", {})
            
            pr_number = pull_request.get("number")
            pr_title = pull_request.get("title", "")
            pr_body = pull_request.get("body", "")
            pr_url = pull_request.get("html_url", "")
            repo_name = repository.get("full_name", "")
            
            logger.info(f"Processing GitHub PR {action}: {repo_name}#{pr_number}")
            
            if action in ["opened", "synchronize"]:
                # Check for documentation changes in PR
                await self._analyze_pr_for_docs(pr_number, repo_name, pr_title, pr_body, pr_url)
            
            elif action == "closed" and pull_request.get("merged"):
                # Update documentation when PR is merged
                await self._handle_merged_pr(pr_number, repo_name, pull_request)
            
        except Exception as e:
            logger.error(f"Error processing GitHub PR event: {e}")
            raise
    
    async def process_issues_event(self, payload: Dict[str, Any]) -> None:
        """
        Process GitHub issues event for issue linking and documentation tasks.
        
        Args:
            payload: GitHub issues event payload
        """
        try:
            action = payload.get("action", "")
            issue = payload.get("issue", {})
            repository = payload.get("repository", {})
            
            issue_number = issue.get("number")
            issue_title = issue.get("title", "")
            issue_body = issue.get("body", "")
            issue_url = issue.get("html_url", "")
            issue_state = issue.get("state", "open")
            repo_name = repository.get("full_name", "")
            
            labels = [label.get("name", "") for label in issue.get("labels", [])]
            assignees = [assignee.get("login", "") for assignee in issue.get("assignees", [])]
            
            github_issue = GitHubIssue(
                number=issue_number,
                title=issue_title,
                state=issue_state,
                html_url=issue_url,
                body=issue_body,
                labels=labels,
                assignees=assignees,
                created_at=self._parse_timestamp(issue.get("created_at")),
                updated_at=self._parse_timestamp(issue.get("updated_at"))
            )
            
            logger.info(f"Processing GitHub issue {action}: {repo_name}#{issue_number}")
            
            if action in ["opened", "edited"]:
                # Create or update documentation tasks from issues
                await self._create_docs_from_issue(github_issue, repo_name)
            
            elif action == "closed":
                # Update linked documentation when issue is closed
                await self._update_docs_for_closed_issue(github_issue, repo_name)
            
            # Update issue status in linked documents
            await self._update_issue_status_in_docs(github_issue, repo_name)
            
        except Exception as e:
            logger.error(f"Error processing GitHub issues event: {e}")
            raise
    
    async def link_issue_to_document(self, document_id: uuid.UUID, repo_name: str, 
                                   issue_number: int, user: User) -> None:
        """
        Link a GitHub issue to a documentation page.
        
        Args:
            document_id: Document ID to link to
            repo_name: GitHub repository name (owner/repo)
            issue_number: GitHub issue number
            user: User creating the link
        """
        try:
            # Get document
            document = await self.document_service.get_document(document_id, user)
            
            # Fetch issue information from GitHub API
            issue = await self._fetch_github_issue(repo_name, issue_number)
            
            # Add issue link to document metadata
            metadata = document.custom_metadata or {}
            linked_issues = metadata.get("github_issues", [])
            
            # Check if issue is already linked
            existing_link = next(
                (link for link in linked_issues if link.get("number") == issue_number),
                None
            )
            
            if existing_link:
                # Update existing link
                existing_link.update({
                    "title": issue.title,
                    "state": issue.state,
                    "url": issue.html_url,
                    "updated_at": datetime.utcnow().isoformat()
                })
            else:
                # Add new link
                linked_issues.append({
                    "number": issue_number,
                    "title": issue.title,
                    "state": issue.state,
                    "url": issue.html_url,
                    "repository": repo_name,
                    "linked_at": datetime.utcnow().isoformat(),
                    "linked_by": user.username
                })
            
            metadata["github_issues"] = linked_issues
            
            # Update document
            await self.document_service.update_document_metadata(document_id, metadata, user)
            
            logger.info(f"Linked GitHub issue {repo_name}#{issue_number} to document {document_id}")
            
        except Exception as e:
            logger.error(f"Error linking GitHub issue to document: {e}")
            raise
    
    async def get_issue_status(self, repo_name: str, issue_number: int) -> Dict[str, Any]:
        """
        Get current status of a GitHub issue.
        
        Args:
            repo_name: GitHub repository name (owner/repo)
            issue_number: GitHub issue number
            
        Returns:
            Issue status information
        """
        try:
            issue = await self._fetch_github_issue(repo_name, issue_number)
            
            return {
                "number": issue.number,
                "title": issue.title,
                "state": issue.state,
                "url": issue.html_url,
                "labels": issue.labels,
                "assignees": issue.assignees,
                "created_at": issue.created_at.isoformat() if issue.created_at else None,
                "updated_at": issue.updated_at.isoformat() if issue.updated_at else None
            }
            
        except Exception as e:
            logger.error(f"Error fetching GitHub issue status: {e}")
            raise
    
    async def process_mentions(self, content: str, repo_name: str) -> str:
        """
        Process @mentions in content and convert to GitHub user links.
        
        Args:
            content: Content with potential @mentions
            repo_name: GitHub repository name for context
            
        Returns:
            Content with processed mentions
        """
        try:
            # Find @mentions in content
            mention_pattern = r'@([a-zA-Z0-9_-]+)'
            mentions = re.findall(mention_pattern, content)
            
            if not mentions:
                return content
            
            # Get repository collaborators
            collaborators = await self._fetch_repository_collaborators(repo_name)
            collaborator_usernames = {collab.lower() for collab in collaborators}
            
            # Replace valid mentions with GitHub profile links
            processed_content = content
            for mention in set(mentions):
                if mention.lower() in collaborator_usernames:
                    github_link = f"[@{mention}](https://github.com/{mention})"
                    processed_content = processed_content.replace(f"@{mention}", github_link)
            
            return processed_content
            
        except Exception as e:
            logger.error(f"Error processing mentions: {e}")
            return content  # Return original content on error
    
    async def _process_commit_for_docs(self, commit: GitHubCommit, repo_name: str, branch: str) -> None:
        """Process a commit for potential documentation updates."""
        try:
            # Check if commit message indicates documentation changes
            doc_keywords = ["docs", "documentation", "readme", "wiki", "guide"]
            commit_message_lower = commit.message.lower()
            
            has_doc_changes = any(keyword in commit_message_lower for keyword in doc_keywords)
            has_doc_files = any(
                file.lower().endswith(('.md', '.rst', '.txt', '.adoc'))
                for file in commit.modified_files
            )
            
            if has_doc_changes or has_doc_files:
                # Find documents that reference this repository
                documents = await self._find_documents_by_repository(repo_name)
                
                for document in documents:
                    # Add commit information to document metadata
                    await self._add_commit_to_document(document, commit, branch)
            
        except Exception as e:
            logger.error(f"Error processing commit for docs: {e}")
    
    async def _analyze_pr_for_docs(self, pr_number: int, repo_name: str, 
                                 title: str, body: str, url: str) -> None:
        """Analyze PR for documentation-related changes."""
        try:
            # Check if PR affects documentation
            doc_keywords = ["docs", "documentation", "readme", "wiki"]
            affects_docs = any(keyword in title.lower() or keyword in body.lower() 
                             for keyword in doc_keywords)
            
            if affects_docs:
                # Find related documents and add PR reference
                documents = await self._find_documents_by_repository(repo_name)
                
                for document in documents:
                    await self._add_pr_reference_to_document(document, pr_number, title, url)
            
        except Exception as e:
            logger.error(f"Error analyzing PR for docs: {e}")
    
    async def _create_docs_from_issue(self, issue: GitHubIssue, repo_name: str) -> None:
        """Create documentation tasks from GitHub issues."""
        try:
            # Check if issue is documentation-related
            doc_labels = {"documentation", "docs", "wiki", "guide", "readme"}
            is_doc_issue = any(label.lower() in doc_labels for label in issue.labels)
            
            if is_doc_issue:
                # Create a documentation task or update existing documents
                logger.info(f"Creating documentation task from issue {repo_name}#{issue.number}")
                
                # This would integrate with a task management system
                # For now, we'll log the action
                
        except Exception as e:
            logger.error(f"Error creating docs from issue: {e}")
    
    async def _fetch_github_issue(self, repo_name: str, issue_number: int) -> GitHubIssue:
        """Fetch issue information from GitHub API."""
        if not self.github_token:
            raise ValidationError("GitHub token not configured")
        
        url = f"https://api.github.com/repos/{repo_name}/issues/{issue_number}"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 404:
                    raise NotFoundError(f"GitHub issue {repo_name}#{issue_number} not found")
                elif response.status != 200:
                    raise InternalError(f"GitHub API error: {response.status}")
                
                data = await response.json()
                
                return GitHubIssue(
                    number=data["number"],
                    title=data["title"],
                    state=data["state"],
                    html_url=data["html_url"],
                    body=data.get("body", ""),
                    labels=[label["name"] for label in data.get("labels", [])],
                    assignees=[assignee["login"] for assignee in data.get("assignees", [])],
                    created_at=self._parse_timestamp(data.get("created_at")),
                    updated_at=self._parse_timestamp(data.get("updated_at"))
                )
    
    async def _fetch_repository_collaborators(self, repo_name: str) -> List[str]:
        """Fetch repository collaborators from GitHub API."""
        if not self.github_token:
            return []
        
        url = f"https://api.github.com/repos/{repo_name}/collaborators"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return [collab["login"] for collab in data]
                    else:
                        logger.warning(f"Failed to fetch collaborators for {repo_name}: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error fetching repository collaborators: {e}")
            return []
    
    async def _find_documents_by_repository(self, repo_name: str) -> List[Document]:
        """Find documents that reference a specific repository."""
        try:
            # Search for documents that mention the repository in metadata or content
            stmt = select(Document).where(
                Document.custom_metadata.op('?')('github_repository')
            )
            result = await self.db.execute(stmt)
            documents = result.scalars().all()
            
            # Filter documents that reference this specific repository
            matching_docs = []
            for doc in documents:
                if doc.custom_metadata and doc.custom_metadata.get('github_repository') == repo_name:
                    matching_docs.append(doc)
            
            return matching_docs
            
        except Exception as e:
            logger.error(f"Error finding documents by repository: {e}")
            return []
    
    async def _add_commit_to_document(self, document: Document, commit: GitHubCommit, branch: str) -> None:
        """Add commit information to document metadata."""
        try:
            metadata = document.custom_metadata or {}
            commits = metadata.get("github_commits", [])
            
            # Add new commit (keep only last 10 commits)
            commits.insert(0, {
                "sha": commit.sha,
                "message": commit.message,
                "author": commit.author,
                "url": commit.html_url,
                "branch": branch,
                "timestamp": commit.timestamp.isoformat() if commit.timestamp else None,
                "modified_files": commit.modified_files
            })
            
            # Keep only the last 10 commits
            metadata["github_commits"] = commits[:10]
            
            # Update document metadata
            document.custom_metadata = metadata
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error adding commit to document: {e}")
    
    async def _add_pr_reference_to_document(self, document: Document, pr_number: int, 
                                          title: str, url: str) -> None:
        """Add PR reference to document metadata."""
        try:
            metadata = document.custom_metadata or {}
            prs = metadata.get("github_prs", [])
            
            # Check if PR is already referenced
            existing_pr = next((pr for pr in prs if pr.get("number") == pr_number), None)
            
            if not existing_pr:
                prs.append({
                    "number": pr_number,
                    "title": title,
                    "url": url,
                    "referenced_at": datetime.utcnow().isoformat()
                })
                
                metadata["github_prs"] = prs
                document.custom_metadata = metadata
                await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error adding PR reference to document: {e}")
    
    async def _update_repository_info(self, repo_name: str, branch: str, commits: List[Dict]) -> None:
        """Update repository information in linked documents."""
        try:
            documents = await self._find_documents_by_repository(repo_name)
            
            for document in documents:
                metadata = document.custom_metadata or {}
                repo_info = metadata.get("repository_info", {})
                
                repo_info.update({
                    "last_push_at": datetime.utcnow().isoformat(),
                    "last_push_branch": branch,
                    "last_commit_count": len(commits),
                    "last_commit_sha": commits[0].get("id") if commits else None
                })
                
                metadata["repository_info"] = repo_info
                document.custom_metadata = metadata
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error updating repository info: {e}")
    
    async def _update_docs_for_closed_issue(self, issue: GitHubIssue, repo_name: str) -> None:
        """Update documentation when an issue is closed."""
        try:
            documents = await self._find_documents_by_repository(repo_name)
            
            for document in documents:
                metadata = document.custom_metadata or {}
                linked_issues = metadata.get("github_issues", [])
                
                # Update issue status
                for linked_issue in linked_issues:
                    if linked_issue.get("number") == issue.number:
                        linked_issue["state"] = issue.state
                        linked_issue["updated_at"] = datetime.utcnow().isoformat()
                
                metadata["github_issues"] = linked_issues
                document.custom_metadata = metadata
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error updating docs for closed issue: {e}")
    
    async def _update_issue_status_in_docs(self, issue: GitHubIssue, repo_name: str) -> None:
        """Update issue status in all linked documents."""
        try:
            documents = await self._find_documents_by_repository(repo_name)
            
            for document in documents:
                metadata = document.custom_metadata or {}
                linked_issues = metadata.get("github_issues", [])
                
                # Find and update the issue
                for linked_issue in linked_issues:
                    if linked_issue.get("number") == issue.number:
                        linked_issue.update({
                            "title": issue.title,
                            "state": issue.state,
                            "labels": issue.labels,
                            "assignees": issue.assignees,
                            "updated_at": datetime.utcnow().isoformat()
                        })
                
                metadata["github_issues"] = linked_issues
                document.custom_metadata = metadata
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error updating issue status in docs: {e}")
    
    async def _handle_merged_pr(self, pr_number: int, repo_name: str, pull_request: Dict) -> None:
        """Handle merged pull request for documentation updates."""
        try:
            # Update documents with merged PR information
            documents = await self._find_documents_by_repository(repo_name)
            
            for document in documents:
                metadata = document.custom_metadata or {}
                merged_prs = metadata.get("github_merged_prs", [])
                
                merged_prs.append({
                    "number": pr_number,
                    "title": pull_request.get("title", ""),
                    "url": pull_request.get("html_url", ""),
                    "merged_at": datetime.utcnow().isoformat(),
                    "merge_commit_sha": pull_request.get("merge_commit_sha")
                })
                
                # Keep only last 20 merged PRs
                metadata["github_merged_prs"] = merged_prs[-20:]
                document.custom_metadata = metadata
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error handling merged PR: {e}")
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse GitHub timestamp string to datetime."""
        if not timestamp_str:
            return None
        
        try:
            # GitHub uses ISO 8601 format
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None