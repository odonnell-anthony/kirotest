// Document viewer JavaScript functionality

class DocumentViewer {
    constructor() {
        this.documentId = this.getDocumentId();
        this.currentUser = this.getCurrentUser();
        this.tocGenerated = false;
        
        this.init();
    }
    
    init() {
        this.setupMermaid();
        this.setupSyntaxHighlighting();
        this.generateTableOfContents();
        this.setupHeadingAnchors();
        this.setupScrollSpy();
        this.setupDocumentMenu();
        this.setupCommentSystem();
        this.setupCodeCopyButtons();
        this.handleUrlFragment();
    }
    
    // Initialize Mermaid diagrams
    setupMermaid() {
        if (typeof mermaid !== 'undefined') {
            mermaid.initialize({
                startOnLoad: true,
                theme: document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'default',
                securityLevel: 'loose',
                fontFamily: 'var(--font-family-sans)'
            });
            
            // Re-render on theme change
            document.addEventListener('themeChanged', () => {
                const theme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'default';
                mermaid.initialize({ theme });
                mermaid.init();
            });
        }
    }
    
    // Setup syntax highlighting
    setupSyntaxHighlighting() {
        if (typeof Prism !== 'undefined') {
            Prism.highlightAll();
        }
    }
    
    // Generate table of contents from headings
    generateTableOfContents() {
        const tocNav = document.getElementById('toc-nav');
        const headings = document.querySelectorAll('.markdown-content h1, .markdown-content h2, .markdown-content h3, .markdown-content h4');
        
        if (!tocNav || headings.length === 0) {
            document.querySelector('.document-toc').style.display = 'none';
            return;
        }
        
        const tocList = document.createElement('ul');
        
        headings.forEach((heading, index) => {
            const level = parseInt(heading.tagName.charAt(1));
            const id = heading.id || `heading-${index}`;
            const text = heading.textContent;
            
            // Ensure heading has an ID
            if (!heading.id) {
                heading.id = id;
            }
            
            const listItem = document.createElement('li');
            const link = document.createElement('a');
            link.href = `#${id}`;
            link.textContent = text;
            link.className = `toc-h${level}`;
            link.addEventListener('click', (e) => {
                e.preventDefault();
                this.scrollToHeading(id);
            });
            
            listItem.appendChild(link);
            tocList.appendChild(listItem);
        });
        
        tocNav.appendChild(tocList);
        this.tocGenerated = true;
    }
    
    // Setup heading anchors for direct linking
    setupHeadingAnchors() {
        const headings = document.querySelectorAll('.markdown-content h1, .markdown-content h2, .markdown-content h3, .markdown-content h4, .markdown-content h5, .markdown-content h6');
        
        headings.forEach((heading, index) => {
            const id = heading.id || `heading-${index}`;
            if (!heading.id) {
                heading.id = id;
            }
            
            const anchor = document.createElement('a');
            anchor.href = `#${id}`;
            anchor.className = 'heading-anchor';
            anchor.textContent = '#';
            anchor.setAttribute('aria-label', `Link to ${heading.textContent}`);
            
            anchor.addEventListener('click', (e) => {
                e.preventDefault();
                this.scrollToHeading(id);
                this.updateUrl(`#${id}`);
            });
            
            heading.appendChild(anchor);
        });
    }
    
    // Setup scroll spy for TOC
    setupScrollSpy() {
        if (!this.tocGenerated) return;
        
        const headings = document.querySelectorAll('.markdown-content h1, .markdown-content h2, .markdown-content h3, .markdown-content h4');
        const tocLinks = document.querySelectorAll('.toc-nav a');
        
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                const id = entry.target.id;
                const tocLink = document.querySelector(`.toc-nav a[href="#${id}"]`);
                
                if (entry.isIntersecting) {
                    tocLinks.forEach(link => link.classList.remove('active'));
                    if (tocLink) {
                        tocLink.classList.add('active');
                    }
                }
            });
        }, {
            rootMargin: '-20% 0px -70% 0px'
        });
        
        headings.forEach(heading => observer.observe(heading));
    }
    
    // Setup document menu
    setupDocumentMenu() {
        const menuToggle = document.querySelector('.document-menu-toggle');
        const menu = document.querySelector('.document-menu');
        
        if (menuToggle && menu) {
            menuToggle.addEventListener('click', (e) => {
                e.stopPropagation();
                menu.classList.toggle('active');
            });
            
            document.addEventListener('click', () => {
                menu.classList.remove('active');
            });
            
            menu.addEventListener('click', (e) => {
                e.stopPropagation();
            });
        }
    }
    
    // Setup comment system
    setupCommentSystem() {
        // Auto-expand comment form on focus
        const commentTextarea = document.getElementById('comment-content');
        if (commentTextarea) {
            commentTextarea.addEventListener('focus', () => {
                commentTextarea.rows = 5;
                document.querySelector('.comment-actions').style.display = 'flex';
            });
        }
    }
    
    // Setup copy buttons for code blocks
    setupCodeCopyButtons() {
        const codeBlocks = document.querySelectorAll('.markdown-content pre');
        
        codeBlocks.forEach(block => {
            const button = document.createElement('button');
            button.className = 'code-copy-btn';
            button.textContent = 'Copy';
            button.setAttribute('aria-label', 'Copy code to clipboard');
            
            button.addEventListener('click', async () => {
                const code = block.querySelector('code');
                if (code) {
                    try {
                        await navigator.clipboard.writeText(code.textContent);
                        button.textContent = 'Copied!';
                        setTimeout(() => {
                            button.textContent = 'Copy';
                        }, 2000);
                    } catch (err) {
                        console.error('Failed to copy code:', err);
                        button.textContent = 'Failed';
                        setTimeout(() => {
                            button.textContent = 'Copy';
                        }, 2000);
                    }
                }
            });
            
            block.appendChild(button);
        });
    }
    
    // Handle URL fragments for direct linking
    handleUrlFragment() {
        const hash = window.location.hash;
        if (hash) {
            const targetId = hash.substring(1);
            setTimeout(() => {
                this.scrollToHeading(targetId, true);
            }, 100);
        }
    }
    
    // Utility methods
    scrollToHeading(id, highlight = false) {
        const element = document.getElementById(id);
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'start' });
            
            if (highlight) {
                element.classList.add('content-highlight');
                setTimeout(() => {
                    element.classList.remove('content-highlight');
                }, 3000);
            }
        }
    }
    
    updateUrl(fragment) {
        const url = new URL(window.location);
        url.hash = fragment;
        window.history.replaceState({}, '', url);
    }
    
    getDocumentId() {
        const meta = document.querySelector('meta[name="document-id"]');
        return meta ? meta.content : null;
    }
    
    getCurrentUser() {
        const meta = document.querySelector('meta[name="current-user"]');
        return meta ? JSON.parse(meta.content) : null;
    }
    
    getAuthToken() {
        return localStorage.getItem('auth-token') || sessionStorage.getItem('auth-token');
    }
}

// Document menu actions
function copyPageLink() {
    const url = window.location.href;
    navigator.clipboard.writeText(url).then(() => {
        showNotification('Page link copied to clipboard');
    });
}

function openInNewTab() {
    window.open(window.location.href, '_blank');
}

function showMoveDialog() {
    document.getElementById('move-modal').classList.add('show');
}

function closeMoveModal() {
    document.getElementById('move-modal').classList.remove('show');
}

function showRevisionHistory() {
    loadRevisionHistory();
    document.getElementById('revision-modal').classList.add('show');
}

function closeRevisionModal() {
    document.getElementById('revision-modal').classList.remove('show');
}

function deletePage() {
    if (confirm('Are you sure you want to delete this page? This action cannot be undone.')) {
        // Implementation would call delete API
        console.log('Delete page');
    }
}

// TOC toggle
function toggleToc() {
    const tocNav = document.getElementById('toc-nav');
    const toggle = document.querySelector('.toc-toggle');
    
    if (tocNav.classList.contains('collapsed')) {
        tocNav.classList.remove('collapsed');
        toggle.textContent = '−';
    } else {
        tocNav.classList.add('collapsed');
        toggle.textContent = '+';
    }
}

// Comment system functions
async function addComment(event) {
    event.preventDefault();
    
    const form = event.target;
    const content = form.content.value.trim();
    
    if (!content) return;
    
    try {
        const response = await fetch(`/api/v1/documents/${window.documentViewer.documentId}/comments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${window.documentViewer.getAuthToken()}`
            },
            body: JSON.stringify({ content })
        });
        
        if (response.ok) {
            const comment = await response.json();
            addCommentToDOM(comment);
            form.reset();
            cancelComment();
            updateCommentCount(1);
        } else {
            throw new Error('Failed to add comment');
        }
    } catch (error) {
        showNotification('Failed to add comment', 'error');
    }
}

function cancelComment() {
    const textarea = document.getElementById('comment-content');
    const actions = document.querySelector('.comment-actions');
    
    textarea.rows = 3;
    actions.style.display = 'none';
    textarea.blur();
}

function replyToComment(commentId) {
    const replyForm = document.getElementById(`comment-reply-${commentId}`);
    replyForm.style.display = 'block';
    replyForm.querySelector('textarea').focus();
}

function cancelReply(commentId) {
    const replyForm = document.getElementById(`comment-reply-${commentId}`);
    replyForm.style.display = 'none';
    replyForm.querySelector('form').reset();
}

async function addReply(event, parentId) {
    event.preventDefault();
    
    const form = event.target;
    const content = form.content.value.trim();
    
    if (!content) return;
    
    try {
        const response = await fetch(`/api/v1/documents/${window.documentViewer.documentId}/comments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${window.documentViewer.getAuthToken()}`
            },
            body: JSON.stringify({ content, parent_id: parentId })
        });
        
        if (response.ok) {
            const comment = await response.json();
            addReplyToDOM(comment, parentId);
            form.reset();
            cancelReply(parentId);
            updateCommentCount(1);
        } else {
            throw new Error('Failed to add reply');
        }
    } catch (error) {
        showNotification('Failed to add reply', 'error');
    }
}

function editComment(commentId) {
    const textDiv = document.getElementById(`comment-text-${commentId}`);
    const editForm = document.getElementById(`comment-edit-${commentId}`);
    
    textDiv.style.display = 'none';
    editForm.style.display = 'block';
    editForm.querySelector('textarea').focus();
}

function cancelEditComment(commentId) {
    const textDiv = document.getElementById(`comment-text-${commentId}`);
    const editForm = document.getElementById(`comment-edit-${commentId}`);
    
    textDiv.style.display = 'block';
    editForm.style.display = 'none';
}

async function updateComment(event, commentId) {
    event.preventDefault();
    
    const form = event.target;
    const content = form.content.value.trim();
    
    if (!content) return;
    
    try {
        const response = await fetch(`/api/v1/comments/${commentId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${window.documentViewer.getAuthToken()}`
            },
            body: JSON.stringify({ content })
        });
        
        if (response.ok) {
            const comment = await response.json();
            updateCommentInDOM(comment);
            cancelEditComment(commentId);
        } else {
            throw new Error('Failed to update comment');
        }
    } catch (error) {
        showNotification('Failed to update comment', 'error');
    }
}

async function deleteComment(commentId) {
    if (!confirm('Are you sure you want to delete this comment?')) return;
    
    try {
        const response = await fetch(`/api/v1/comments/${commentId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${window.documentViewer.getAuthToken()}`
            }
        });
        
        if (response.ok) {
            removeCommentFromDOM(commentId);
            updateCommentCount(-1);
        } else {
            throw new Error('Failed to delete comment');
        }
    } catch (error) {
        showNotification('Failed to delete comment', 'error');
    }
}

// DOM manipulation helpers
function addCommentToDOM(comment) {
    // Implementation would add comment HTML to DOM
    console.log('Add comment to DOM:', comment);
}

function addReplyToDOM(comment, parentId) {
    // Implementation would add reply HTML to DOM
    console.log('Add reply to DOM:', comment, parentId);
}

function updateCommentInDOM(comment) {
    // Implementation would update comment HTML in DOM
    console.log('Update comment in DOM:', comment);
}

function removeCommentFromDOM(commentId) {
    const commentElement = document.querySelector(`[data-comment-id="${commentId}"]`);
    if (commentElement) {
        commentElement.remove();
    }
}

function updateCommentCount(delta) {
    const countElement = document.querySelector('.comment-count');
    if (countElement) {
        const current = parseInt(countElement.textContent) || 0;
        const newCount = Math.max(0, current + delta);
        countElement.textContent = `${newCount} comment${newCount !== 1 ? 's' : ''}`;
    }
}

// Move page functionality
async function movePage(event) {
    event.preventDefault();
    
    const form = event.target;
    const newFolderPath = form.folder_path.value.trim();
    
    try {
        const response = await fetch(`/api/v1/documents/${window.documentViewer.documentId}/move`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${window.documentViewer.getAuthToken()}`
            },
            body: JSON.stringify({ folder_path: newFolderPath })
        });
        
        if (response.ok) {
            const result = await response.json();
            window.location.href = result.new_path;
        } else {
            throw new Error('Failed to move page');
        }
    } catch (error) {
        showNotification('Failed to move page', 'error');
    }
}

// Load revision history
async function loadRevisionHistory() {
    try {
        const response = await fetch(`/api/v1/documents/${window.documentViewer.documentId}/revisions`, {
            headers: {
                'Authorization': `Bearer ${window.documentViewer.getAuthToken()}`
            }
        });
        
        if (response.ok) {
            const revisions = await response.json();
            displayRevisionHistory(revisions);
        } else {
            throw new Error('Failed to load revision history');
        }
    } catch (error) {
        showNotification('Failed to load revision history', 'error');
    }
}

function displayRevisionHistory(revisions) {
    const container = document.getElementById('revision-list');
    container.innerHTML = revisions.map(revision => `
        <div class="revision-item">
            <div class="revision-header">
                <strong>Revision ${revision.revision_number}</strong>
                <span class="revision-date">${new Date(revision.created_at).toLocaleDateString()}</span>
            </div>
            <div class="revision-author">By ${revision.author.username}</div>
            <div class="revision-summary">${revision.change_summary || 'No summary provided'}</div>
            <div class="revision-actions">
                <button onclick="viewRevision('${revision.id}')" class="btn btn-secondary">View</button>
                <button onclick="restoreRevision('${revision.id}')" class="btn btn-primary">Restore</button>
            </div>
        </div>
    `).join('');
}

function viewRevision(revisionId) {
    window.open(`/documents/${window.documentViewer.documentId}/revisions/${revisionId}`, '_blank');
}

async function restoreRevision(revisionId) {
    if (!confirm('Are you sure you want to restore this revision? This will create a new revision with the old content.')) return;
    
    try {
        const response = await fetch(`/api/v1/documents/${window.documentViewer.documentId}/revisions/${revisionId}/restore`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${window.documentViewer.getAuthToken()}`
            }
        });
        
        if (response.ok) {
            window.location.reload();
        } else {
            throw new Error('Failed to restore revision');
        }
    } catch (error) {
        showNotification('Failed to restore revision', 'error');
    }
}

// Notification helper
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Initialize document viewer when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.documentViewer = new DocumentViewer();
});

// Handle theme changes for Mermaid
document.addEventListener('themeChanged', () => {
    if (window.documentViewer) {
        window.documentViewer.setupMermaid();
    }
});