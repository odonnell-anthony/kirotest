"""
Integration tests for complex workflows and end-to-end scenarios.
"""
import pytest
import uuid
from httpx import AsyncClient
from fastapi import status

from tests.conftest import UserFactory, DocumentFactory, TagFactory


@pytest.mark.integration
class TestDocumentWorkflows:
    """Test complex document management workflows."""
    
    @pytest.mark.asyncio
    async def test_complete_document_lifecycle(self, test_client: AsyncClient, test_db):
        """Test complete document lifecycle from creation to deletion."""
        # Create user
        user = await UserFactory.create_and_save_user(test_db, username="lifecycle_user")
        
        # Mock user authentication
        async def mock_user():
            return user
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_user
        
        # 1. Create document
        doc_data = {
            "title": "Lifecycle Test Document",
            "content": "# Initial Content\n\nThis document will go through its complete lifecycle.",
            "folder_path": "/lifecycle-test/",
            "tags": ["lifecycle", "test"],
            "status": "draft"
        }
        
        create_response = await test_client.post("/api/v1/documents", json=doc_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        document = create_response.json()
        doc_id = document["id"]
        
        # Verify document was created
        assert document["title"] == doc_data["title"]
        assert document["status"] == "draft"
        assert document["author_id"] == str(user.id)
        
        # 2. Update document multiple times (creating revisions)
        updates = [
            {
                "title": "Updated Lifecycle Document",
                "content": "# Updated Content\n\nFirst update to the document.",
            },
            {
                "content": "# Updated Content\n\nSecond update with more content.\n\n## New Section\n\nAdditional information.",
            },
            {
                "status": "published"
            }
        ]
        
        for i, update_data in enumerate(updates):
            update_response = await test_client.put(f"/api/v1/documents/{doc_id}", json=update_data)
            assert update_response.status_code == status.HTTP_200_OK
            
            updated_doc = update_response.json()
            if "title" in update_data:
                assert updated_doc["title"] == update_data["title"]
            if "content" in update_data:
                assert updated_doc["content"] == update_data["content"]
            if "status" in update_data:
                assert updated_doc["status"] == update_data["status"]
        
        # 3. Verify revisions were created
        revisions_response = await test_client.get(f"/api/v1/documents/{doc_id}/revisions")
        assert revisions_response.status_code == status.HTTP_200_OK
        revisions = revisions_response.json()
        
        # Should have multiple revisions (initial + updates)
        assert len(revisions) >= 3
        
        # 4. Add comments to document
        comments_data = [
            {"content": "Great document! Very informative."},
            {"content": "I have a question about the second section."},
            {"content": "Thanks for the feedback! I'll clarify that section."}
        ]
        
        comment_ids = []
        for comment_data in comments_data:
            comment_response = await test_client.post(f"/api/v1/documents/{doc_id}/comments", json=comment_data)
            assert comment_response.status_code == status.HTTP_201_CREATED
            comment = comment_response.json()
            comment_ids.append(comment["id"])
        
        # 5. Upload file attachment
        file_content = b"Attachment content for lifecycle test document"
        files = {"file": ("lifecycle_attachment.txt", file_content, "text/plain")}
        data = {"folder_path": "/attachments/", "document_id": doc_id}
        
        file_response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        assert file_response.status_code == status.HTTP_201_CREATED
        attachment = file_response.json()
        
        # 6. Move document to different folder
        move_data = {"folder_path": "/moved-documents/"}
        move_response = await test_client.put(f"/api/v1/documents/{doc_id}/move", json=move_data)
        assert move_response.status_code == status.HTTP_200_OK
        
        moved_doc = move_response.json()
        assert moved_doc["folder_path"] == "/moved-documents/"
        
        # 7. Search for document
        search_response = await test_client.get("/api/v1/search?q=lifecycle")
        assert search_response.status_code == status.HTTP_200_OK
        search_results = search_response.json()
        
        # Should find the document
        assert search_results["total"] >= 1
        found_doc = next((doc for doc in search_results["results"] if doc["id"] == doc_id), None)
        assert found_doc is not None
        
        # 8. Get document with all related data
        full_doc_response = await test_client.get(f"/api/v1/documents/{doc_id}?include=comments,revisions,attachments")
        assert full_doc_response.status_code == status.HTTP_200_OK
        full_doc = full_doc_response.json()
        
        # Verify all related data is included
        assert "comments" in full_doc or len(comment_ids) == 0
        assert "revisions" in full_doc or len(revisions) == 0
        assert "attachments" in full_doc or attachment is None
        
        # 9. Finally, delete document
        delete_response = await test_client.delete(f"/api/v1/documents/{doc_id}")
        assert delete_response.status_code == status.HTTP_200_OK
        
        # 10. Verify document is deleted
        get_response = await test_client.get(f"/api/v1/documents/{doc_id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND
        
        # Clean up
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_collaborative_document_editing(self, test_client: AsyncClient, test_db):
        """Test collaborative document editing workflow."""
        # Create multiple users
        author = await UserFactory.create_and_save_user(test_db, username="author")
        editor1 = await UserFactory.create_and_save_user(test_db, username="editor1")
        editor2 = await UserFactory.create_and_save_user(test_db, username="editor2")
        
        # Author creates document
        async def mock_author():
            return author
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_author
        
        doc_data = {
            "title": "Collaborative Document",
            "content": "# Collaborative Document\n\nThis document will be edited by multiple users.",
            "folder_path": "/collaborative/",
            "status": "published"
        }
        
        create_response = await test_client.post("/api/v1/documents", json=doc_data)
        assert create_response.status_code == status.HTTP_201_CREATED
        document = create_response.json()
        doc_id = document["id"]
        
        # Editor1 adds content
        async def mock_editor1():
            return editor1
        
        app.dependency_overrides[get_current_user] = mock_editor1
        
        editor1_update = {
            "content": document["content"] + "\n\n## Section by Editor 1\n\nContent added by the first editor."
        }
        
        update1_response = await test_client.put(f"/api/v1/documents/{doc_id}", json=editor1_update)
        assert update1_response.status_code == status.HTTP_200_OK
        updated_doc1 = update1_response.json()
        
        # Editor1 adds comment
        comment1_data = {"content": "I've added a new section to this document."}
        comment1_response = await test_client.post(f"/api/v1/documents/{doc_id}/comments", json=comment1_data)
        assert comment1_response.status_code == status.HTTP_201_CREATED
        
        # Editor2 adds more content
        async def mock_editor2():
            return editor2
        
        app.dependency_overrides[get_current_user] = mock_editor2
        
        editor2_update = {
            "content": updated_doc1["content"] + "\n\n## Section by Editor 2\n\nContent added by the second editor."
        }
        
        update2_response = await test_client.put(f"/api/v1/documents/{doc_id}", json=editor2_update)
        assert update2_response.status_code == status.HTTP_200_OK
        updated_doc2 = update2_response.json()
        
        # Editor2 replies to comment
        comment2_data = {"content": "Great addition! I've also added a section."}
        comment2_response = await test_client.post(f"/api/v1/documents/{doc_id}/comments", json=comment2_data)
        assert comment2_response.status_code == status.HTTP_201_CREATED
        
        # Author reviews changes
        app.dependency_overrides[get_current_user] = mock_author
        
        # Get revision history
        revisions_response = await test_client.get(f"/api/v1/documents/{doc_id}/revisions")
        assert revisions_response.status_code == status.HTTP_200_OK
        revisions = revisions_response.json()
        
        # Should have revisions from all three users
        assert len(revisions) >= 3
        
        # Verify different authors in revisions
        revision_authors = {rev["author_id"] for rev in revisions}
        assert str(author.id) in revision_authors
        assert str(editor1.id) in revision_authors
        assert str(editor2.id) in revision_authors
        
        # Get comments
        comments_response = await test_client.get(f"/api/v1/documents/{doc_id}/comments")
        assert comments_response.status_code == status.HTTP_200_OK
        comments = comments_response.json()
        
        # Should have comments from both editors
        assert len(comments) >= 2
        
        # Clean up
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_document_organization_workflow(self, test_client: AsyncClient, test_db):
        """Test document organization and folder management workflow."""
        user = await UserFactory.create_and_save_user(test_db, username="organizer")
        
        async def mock_user():
            return user
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_user
        
        # Create folder structure
        folders = [
            "/projects/",
            "/projects/project-a/",
            "/projects/project-a/docs/",
            "/projects/project-a/specs/",
            "/projects/project-b/",
            "/archive/"
        ]
        
        for folder_path in folders:
            folder_data = {"path": folder_path, "name": folder_path.strip("/").split("/")[-1] or "root"}
            folder_response = await test_client.post("/api/v1/folders", json=folder_data)
            # Folder creation might return 201 or 409 if already exists
            assert folder_response.status_code in [201, 409]
        
        # Create documents in different folders
        documents = [
            {
                "title": "Project A Overview",
                "content": "# Project A\n\nOverview of project A.",
                "folder_path": "/projects/project-a/",
                "tags": ["project-a", "overview"]
            },
            {
                "title": "Project A Technical Spec",
                "content": "# Technical Specification\n\nDetailed technical specs.",
                "folder_path": "/projects/project-a/specs/",
                "tags": ["project-a", "technical", "specification"]
            },
            {
                "title": "Project A User Guide",
                "content": "# User Guide\n\nHow to use project A.",
                "folder_path": "/projects/project-a/docs/",
                "tags": ["project-a", "documentation", "user-guide"]
            },
            {
                "title": "Project B Overview",
                "content": "# Project B\n\nOverview of project B.",
                "folder_path": "/projects/project-b/",
                "tags": ["project-b", "overview"]
            }
        ]
        
        created_docs = []
        for doc_data in documents:
            response = await test_client.post("/api/v1/documents", json=doc_data)
            assert response.status_code == status.HTTP_201_CREATED
            created_docs.append(response.json())
        
        # Test folder-based queries
        project_a_response = await test_client.get("/api/v1/documents?folder_path=/projects/project-a/")
        assert project_a_response.status_code == status.HTTP_200_OK
        project_a_docs = project_a_response.json()
        
        # Should find documents in project-a folder and subfolders
        assert project_a_docs["total"] >= 3
        
        # Test tag-based organization
        tag_response = await test_client.get("/api/v1/documents?tag=project-a")
        assert tag_response.status_code == status.HTTP_200_OK
        tagged_docs = tag_response.json()
        
        # Should find all project-a documents
        assert tagged_docs["total"] >= 3
        
        # Move document to archive
        doc_to_archive = created_docs[0]
        move_data = {"folder_path": "/archive/"}
        move_response = await test_client.put(f"/api/v1/documents/{doc_to_archive['id']}/move", json=move_data)
        assert move_response.status_code == status.HTTP_200_OK
        
        # Verify document was moved
        archived_response = await test_client.get("/api/v1/documents?folder_path=/archive/")
        assert archived_response.status_code == status.HTTP_200_OK
        archived_docs = archived_response.json()
        assert archived_docs["total"] >= 1
        
        # Clean up
        app.dependency_overrides.clear()


@pytest.mark.integration
class TestSearchWorkflows:
    """Test complex search and discovery workflows."""
    
    @pytest.mark.asyncio
    async def test_comprehensive_search_workflow(self, test_client: AsyncClient, test_db):
        """Test comprehensive search functionality."""
        user = await UserFactory.create_and_save_user(test_db, username="searcher")
        
        # Create searchable content
        documents = [
            {
                "title": "Python Programming Guide",
                "content": "# Python Programming\n\nLearn Python programming language with examples and best practices.",
                "tags": ["python", "programming", "tutorial"]
            },
            {
                "title": "JavaScript Fundamentals",
                "content": "# JavaScript Basics\n\nUnderstand JavaScript fundamentals including variables, functions, and objects.",
                "tags": ["javascript", "programming", "fundamentals"]
            },
            {
                "title": "Database Design Principles",
                "content": "# Database Design\n\nPrinciples of good database design including normalization and indexing.",
                "tags": ["database", "design", "sql"]
            },
            {
                "title": "API Development with Python",
                "content": "# API Development\n\nBuilding REST APIs using Python and FastAPI framework.",
                "tags": ["python", "api", "fastapi", "rest"]
            }
        ]
        
        created_docs = []
        for doc_data in documents:
            doc_data["folder_path"] = "/search-test/"
            doc_data["author_id"] = user.id
            doc = await DocumentFactory.create_and_save_document(test_db, **doc_data)
            created_docs.append(doc)
        
        # Create tags
        tags = ["python", "javascript", "programming", "database", "api", "tutorial", "fundamentals", "design"]
        for tag_name in tags:
            await TagFactory.create_and_save_tag(test_db, name=tag_name, usage_count=2)
        
        # Test basic text search
        search_response = await test_client.get("/api/v1/search?q=python")
        assert search_response.status_code == status.HTTP_200_OK
        search_results = search_response.json()
        
        # Should find Python-related documents
        assert search_results["total"] >= 2
        python_docs = [doc for doc in search_results["results"] if "python" in doc["title"].lower() or "python" in doc["content"].lower()]
        assert len(python_docs) >= 2
        
        # Test tag-based search
        tag_search_response = await test_client.get("/api/v1/search?q=programming&filter=tags")
        assert tag_search_response.status_code == status.HTTP_200_OK
        tag_results = tag_search_response.json()
        
        # Should find documents tagged with programming
        assert tag_results["total"] >= 2
        
        # Test autocomplete
        autocomplete_response = await test_client.get("/api/v1/search/autocomplete?q=prog")
        assert autocomplete_response.status_code == status.HTTP_200_OK
        autocomplete_data = autocomplete_response.json()
        
        # Should suggest programming-related terms
        suggestions = autocomplete_data["suggestions"]
        assert len(suggestions) > 0
        programming_suggestions = [s for s in suggestions if "prog" in s["name"].lower()]
        assert len(programming_suggestions) > 0
        
        # Test advanced search with filters
        advanced_search_response = await test_client.get("/api/v1/search?q=api&author_id=" + str(user.id))
        assert advanced_search_response.status_code == status.HTTP_200_OK
        advanced_results = advanced_search_response.json()
        
        # Should find API document by specific author
        assert advanced_results["total"] >= 1
        
        # Test search with date range
        from datetime import datetime, timedelta
        yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()
        tomorrow = (datetime.utcnow() + timedelta(days=1)).isoformat()
        
        date_search_response = await test_client.get(f"/api/v1/search?q=programming&created_after={yesterday}&created_before={tomorrow}")
        assert date_search_response.status_code == status.HTTP_200_OK
        date_results = date_search_response.json()
        
        # Should find recently created documents
        assert date_results["total"] >= 2
        
        # Test search pagination
        paginated_response = await test_client.get("/api/v1/search?q=programming&page=1&size=2")
        assert paginated_response.status_code == status.HTTP_200_OK
        paginated_results = paginated_response.json()
        
        # Should return paginated results
        assert len(paginated_results["results"]) <= 2
        assert paginated_results["page"] == 1
        assert paginated_results["size"] == 2
    
    @pytest.mark.asyncio
    async def test_tag_management_workflow(self, test_client: AsyncClient, test_db):
        """Test tag management and organization workflow."""
        user = await UserFactory.create_and_save_user(test_db, username="tag_manager")
        
        async def mock_user():
            return user
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_user
        
        # Create tags
        tag_data_list = [
            {"name": "python", "description": "Python programming language", "color": "#3776ab"},
            {"name": "javascript", "description": "JavaScript programming language", "color": "#f7df1e"},
            {"name": "web-development", "description": "Web development topics", "color": "#61dafb"},
            {"name": "backend", "description": "Backend development", "color": "#68217a"},
            {"name": "frontend", "description": "Frontend development", "color": "#ff6b6b"}
        ]
        
        created_tags = []
        for tag_data in tag_data_list:
            response = await test_client.post("/api/v1/tags", json=tag_data)
            assert response.status_code == status.HTTP_201_CREATED
            created_tags.append(response.json())
        
        # Create documents with tags
        doc_data = {
            "title": "Full Stack Web Development",
            "content": "# Full Stack Development\n\nBuilding web applications with Python backend and JavaScript frontend.",
            "folder_path": "/web-dev/",
            "tags": ["python", "javascript", "web-development", "backend", "frontend"]
        }
        
        doc_response = await test_client.post("/api/v1/documents", json=doc_data)
        assert doc_response.status_code == status.HTTP_201_CREATED
        document = doc_response.json()
        
        # Test tag autocomplete
        autocomplete_response = await test_client.get("/api/v1/search/autocomplete?q=web")
        assert autocomplete_response.status_code == status.HTTP_200_OK
        autocomplete_data = autocomplete_response.json()
        
        # Should suggest web-related tags
        suggestions = autocomplete_data["suggestions"]
        web_suggestions = [s for s in suggestions if "web" in s["name"].lower()]
        assert len(web_suggestions) >= 1
        
        # Test tag usage statistics
        tags_response = await test_client.get("/api/v1/tags")
        assert tags_response.status_code == status.HTTP_200_OK
        tags = tags_response.json()
        
        # Tags should have usage counts
        used_tags = [tag for tag in tags if tag["usage_count"] > 0]
        assert len(used_tags) >= 5  # All tags used in the document
        
        # Test tag renaming
        python_tag = next(tag for tag in created_tags if tag["name"] == "python")
        rename_data = {"old_name": "python", "new_name": "python-lang"}
        rename_response = await test_client.post("/api/v1/tags/rename", json=rename_data)
        assert rename_response.status_code == status.HTTP_200_OK
        
        # Verify tag was renamed
        renamed_tag_response = await test_client.get(f"/api/v1/tags/{python_tag['id']}")
        assert renamed_tag_response.status_code == status.HTTP_200_OK
        renamed_tag = renamed_tag_response.json()
        assert renamed_tag["name"] == "python-lang"
        
        # Test tag merging (if implemented)
        # This would involve merging two similar tags
        
        # Test tag deletion with usage check
        unused_tag_data = {"name": "unused-tag", "description": "This tag is not used"}
        unused_response = await test_client.post("/api/v1/tags", json=unused_tag_data)
        assert unused_response.status_code == status.HTTP_201_CREATED
        unused_tag = unused_response.json()
        
        # Delete unused tag
        delete_response = await test_client.delete(f"/api/v1/tags/{unused_tag['id']}")
        assert delete_response.status_code == status.HTTP_200_OK
        
        # Try to delete used tag (should require force)
        js_tag = next(tag for tag in created_tags if tag["name"] == "javascript")
        delete_used_response = await test_client.delete(f"/api/v1/tags/{js_tag['id']}")
        # Should either be rejected or require force parameter
        assert delete_used_response.status_code in [400, 409]
        
        # Clean up
        app.dependency_overrides.clear()


@pytest.mark.integration
class TestPermissionWorkflows:
    """Test permission and access control workflows."""
    
    @pytest.mark.asyncio
    async def test_permission_group_workflow(self, test_client: AsyncClient, test_db):
        """Test permission group management workflow."""
        from app.models.user import UserRole
        
        # Create admin and regular users
        admin = await UserFactory.create_and_save_user(test_db, username="admin", role=UserRole.ADMIN)
        editor = await UserFactory.create_and_save_user(test_db, username="editor")
        viewer = await UserFactory.create_and_save_user(test_db, username="viewer")
        
        # Mock admin user
        async def mock_admin():
            return admin
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_admin
        
        # Create permission groups
        groups_data = [
            {"name": "editors", "description": "Content editors group"},
            {"name": "viewers", "description": "Content viewers group"}
        ]
        
        created_groups = []
        for group_data in groups_data:
            response = await test_client.post("/api/v1/admin/permission-groups", json=group_data)
            assert response.status_code == status.HTTP_201_CREATED
            created_groups.append(response.json())
        
        editors_group = next(g for g in created_groups if g["name"] == "editors")
        viewers_group = next(g for g in created_groups if g["name"] == "viewers")
        
        # Add permissions to groups
        editor_permissions = [
            {
                "resource_pattern": "/docs/*",
                "action": "edit_pages",
                "effect": "allow"
            },
            {
                "resource_pattern": "/docs/*",
                "action": "read_pages",
                "effect": "allow"
            }
        ]
        
        for perm_data in editor_permissions:
            response = await test_client.post(f"/api/v1/admin/permission-groups/{editors_group['id']}/permissions", json=perm_data)
            assert response.status_code == status.HTTP_201_CREATED
        
        viewer_permissions = [
            {
                "resource_pattern": "/docs/*",
                "action": "read_pages",
                "effect": "allow"
            }
        ]
        
        for perm_data in viewer_permissions:
            response = await test_client.post(f"/api/v1/admin/permission-groups/{viewers_group['id']}/permissions", json=perm_data)
            assert response.status_code == status.HTTP_201_CREATED
        
        # Assign users to groups
        assign_editor_response = await test_client.post(f"/api/v1/admin/permission-groups/{editors_group['id']}/users/{editor.id}")
        assert assign_editor_response.status_code == status.HTTP_200_OK
        
        assign_viewer_response = await test_client.post(f"/api/v1/admin/permission-groups/{viewers_group['id']}/users/{viewer.id}")
        assert assign_viewer_response.status_code == status.HTTP_200_OK
        
        # Test editor permissions
        async def mock_editor():
            return editor
        
        app.dependency_overrides[get_current_user] = mock_editor
        
        # Editor should be able to create documents
        doc_data = {
            "title": "Editor Test Document",
            "content": "Content created by editor",
            "folder_path": "/docs/"
        }
        
        editor_create_response = await test_client.post("/api/v1/documents", json=doc_data)
        assert editor_create_response.status_code == status.HTTP_201_CREATED
        editor_doc = editor_create_response.json()
        
        # Test viewer permissions
        async def mock_viewer():
            return viewer
        
        app.dependency_overrides[get_current_user] = mock_viewer
        
        # Viewer should be able to read documents
        viewer_read_response = await test_client.get(f"/api/v1/documents/{editor_doc['id']}")
        assert viewer_read_response.status_code == status.HTTP_200_OK
        
        # Viewer should NOT be able to edit documents
        update_data = {"title": "Viewer trying to edit"}
        viewer_edit_response = await test_client.put(f"/api/v1/documents/{editor_doc['id']}", json=update_data)
        assert viewer_edit_response.status_code == status.HTTP_403_FORBIDDEN
        
        # Clean up
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_document_access_control_workflow(self, test_client: AsyncClient, test_db):
        """Test document-level access control workflow."""
        # Create users
        owner = await UserFactory.create_and_save_user(test_db, username="doc_owner")
        collaborator = await UserFactory.create_and_save_user(test_db, username="collaborator")
        outsider = await UserFactory.create_and_save_user(test_db, username="outsider")
        
        # Owner creates private document
        async def mock_owner():
            return owner
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_owner
        
        private_doc_data = {
            "title": "Private Document",
            "content": "This is a private document",
            "folder_path": "/private/",
            "status": "draft",  # Draft documents are typically private
            "is_public": False
        }
        
        private_response = await test_client.post("/api/v1/documents", json=private_doc_data)
        assert private_response.status_code == status.HTTP_201_CREATED
        private_doc = private_response.json()
        
        # Share document with collaborator
        share_data = {
            "user_id": str(collaborator.id),
            "permission": "edit"
        }
        
        share_response = await test_client.post(f"/api/v1/documents/{private_doc['id']}/share", json=share_data)
        # Response depends on implementation - might be 200 or 201
        assert share_response.status_code in [200, 201]
        
        # Test collaborator access
        async def mock_collaborator():
            return collaborator
        
        app.dependency_overrides[get_current_user] = mock_collaborator
        
        # Collaborator should be able to access shared document
        collab_read_response = await test_client.get(f"/api/v1/documents/{private_doc['id']}")
        assert collab_read_response.status_code == status.HTTP_200_OK
        
        # Collaborator should be able to edit shared document
        collab_edit_data = {"content": "Collaborator added this content"}
        collab_edit_response = await test_client.put(f"/api/v1/documents/{private_doc['id']}", json=collab_edit_data)
        assert collab_edit_response.status_code == status.HTTP_200_OK
        
        # Test outsider access
        async def mock_outsider():
            return outsider
        
        app.dependency_overrides[get_current_user] = mock_outsider
        
        # Outsider should NOT be able to access private document
        outsider_response = await test_client.get(f"/api/v1/documents/{private_doc['id']}")
        assert outsider_response.status_code in [403, 404]
        
        # Test public document access
        app.dependency_overrides[get_current_user] = mock_owner
        
        public_doc_data = {
            "title": "Public Document",
            "content": "This is a public document",
            "folder_path": "/public/",
            "status": "published",
            "is_public": True
        }
        
        public_response = await test_client.post("/api/v1/documents", json=public_doc_data)
        assert public_response.status_code == status.HTTP_201_CREATED
        public_doc = public_response.json()
        
        # Outsider should be able to read public document
        app.dependency_overrides[get_current_user] = mock_outsider
        
        public_read_response = await test_client.get(f"/api/v1/documents/{public_doc['id']}")
        assert public_read_response.status_code == status.HTTP_200_OK
        
        # But outsider should NOT be able to edit public document
        outsider_edit_data = {"content": "Outsider trying to edit"}
        outsider_edit_response = await test_client.put(f"/api/v1/documents/{public_doc['id']}", json=outsider_edit_data)
        assert outsider_edit_response.status_code == status.HTTP_403_FORBIDDEN
        
        # Clean up
        app.dependency_overrides.clear()