// Base JavaScript for Wiki Documentation App

class WikiApp {
    constructor() {
        this.theme = this.getStoredTheme() || 'light';
        this.sidebarOpen = false;
        this.contextMenu = null;
        
        this.init();
    }
    
    init() {
        this.applyTheme();
        this.setupEventListeners();
        this.setupFolderTree();
        this.setupContextMenus();
    }
    
    // Theme management
    getStoredTheme() {
        return localStorage.getItem('wiki-theme');
    }
    
    setStoredTheme(theme) {
        localStorage.setItem('wiki-theme', theme);
    }
    
    applyTheme() {
        document.documentElement.setAttribute('data-theme', this.theme);
        const themeToggle = document.querySelector('.theme-toggle');
        if (themeToggle) {
            themeToggle.textContent = this.theme === 'dark' ? '☀️' : '🌙';
            themeToggle.setAttribute('aria-label', `Switch to ${this.theme === 'dark' ? 'light' : 'dark'} theme`);
        }
    }
    
    toggleTheme() {
        this.theme = this.theme === 'light' ? 'dark' : 'light';
        this.setStoredTheme(this.theme);
        this.applyTheme();
        
        // Dispatch theme change event
        document.dispatchEvent(new CustomEvent('themeChanged', { 
            detail: { theme: this.theme } 
        }));
        
        // Send theme preference to server
        this.updateThemePreference();
    }
    
    async updateThemePreference() {
        try {
            await fetch('/api/v1/auth/theme', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getAuthToken()}`
                },
                body: JSON.stringify({ theme: this.theme })
            });
        } catch (error) {
            console.warn('Failed to update theme preference:', error);
        }
    }
    
    // Mobile sidebar management
    toggleSidebar() {
        this.sidebarOpen = !this.sidebarOpen;
        const sidebar = document.querySelector('.app-sidebar');
        if (sidebar) {
            sidebar.classList.toggle('mobile-open', this.sidebarOpen);
        }
    }
    
    // Folder tree management
    setupFolderTree() {
        const folderToggles = document.querySelectorAll('.nav-folder-toggle');
        folderToggles.forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.toggleFolder(toggle);
            });
        });
    }
    
    toggleFolder(toggle) {
        const folder = toggle.closest('.nav-folder');
        const children = folder.querySelector('.nav-folder-children');
        const isExpanded = toggle.classList.contains('expanded');
        
        if (isExpanded) {
            toggle.classList.remove('expanded');
            children.classList.add('collapsed');
            toggle.setAttribute('aria-expanded', 'false');
        } else {
            toggle.classList.add('expanded');
            children.classList.remove('collapsed');
            toggle.setAttribute('aria-expanded', 'true');
        }
        
        // Store folder state
        const folderPath = folder.dataset.path;
        if (folderPath) {
            this.setFolderState(folderPath, !isExpanded);
        }
    }
    
    setFolderState(path, expanded) {
        const states = JSON.parse(localStorage.getItem('wiki-folder-states') || '{}');
        states[path] = expanded;
        localStorage.setItem('wiki-folder-states', JSON.stringify(states));
    }
    
    getFolderState(path) {
        const states = JSON.parse(localStorage.getItem('wiki-folder-states') || '{}');
        return states[path] !== false; // Default to expanded
    }
    
    // Context menu management
    setupContextMenus() {
        document.addEventListener('contextmenu', (e) => {
            const navItem = e.target.closest('.nav-link, .nav-folder');
            if (navItem) {
                e.preventDefault();
                this.showContextMenu(e, navItem);
            }
        });
        
        document.addEventListener('click', () => {
            this.hideContextMenu();
        });
        
        // Three-dot menu buttons
        document.querySelectorAll('.nav-menu-button').forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const navItem = button.closest('.nav-link, .nav-folder');
                this.showContextMenu(e, navItem);
            });
        });
    }
    
    showContextMenu(event, navItem) {
        this.hideContextMenu();
        
        const menu = this.createContextMenu(navItem);
        document.body.appendChild(menu);
        
        // Position menu
        const rect = menu.getBoundingClientRect();
        const x = Math.min(event.clientX, window.innerWidth - rect.width - 10);
        const y = Math.min(event.clientY, window.innerHeight - rect.height - 10);
        
        menu.style.left = `${x}px`;
        menu.style.top = `${y}px`;
        
        this.contextMenu = menu;
    }
    
    hideContextMenu() {
        if (this.contextMenu) {
            this.contextMenu.remove();
            this.contextMenu = null;
        }
    }
    
    createContextMenu(navItem) {
        const menu = document.createElement('div');
        menu.className = 'context-menu';
        
        const isFolder = navItem.classList.contains('nav-folder');
        const path = navItem.dataset.path || '';
        const title = navItem.dataset.title || '';
        
        const menuItems = [];
        
        if (isFolder) {
            menuItems.push(
                { text: 'Add Sub-page', action: () => this.addSubPage(path) },
                { text: 'Add Sub-folder', action: () => this.addSubFolder(path) },
                { separator: true },
                { text: 'Rename Folder', action: () => this.renameFolder(path) },
                { text: 'Move Folder', action: () => this.moveFolder(path) },
                { separator: true },
                { text: 'Delete Folder', action: () => this.deleteFolder(path), danger: true }
            );
        } else {
            menuItems.push(
                { text: 'Open in New Tab', action: () => this.openInNewTab(path) },
                { text: 'Copy Page Path', action: () => this.copyPagePath(path) },
                { separator: true },
                { text: 'Edit Page', action: () => this.editPage(path) },
                { text: 'Move Page', action: () => this.movePage(path) },
                { separator: true },
                { text: 'Delete Page', action: () => this.deletePage(path), danger: true }
            );
        }
        
        menuItems.forEach(item => {
            if (item.separator) {
                const separator = document.createElement('div');
                separator.className = 'context-menu-separator';
                menu.appendChild(separator);
            } else {
                const button = document.createElement('button');
                button.className = 'context-menu-item';
                button.textContent = item.text;
                if (item.danger) {
                    button.style.color = 'var(--danger)';
                }
                button.addEventListener('click', (e) => {
                    e.stopPropagation();
                    item.action();
                    this.hideContextMenu();
                });
                menu.appendChild(button);
            }
        });
        
        return menu;
    }
    
    // Context menu actions
    addSubPage(folderPath) {
        window.location.href = `/editor?folder=${encodeURIComponent(folderPath)}`;
    }
    
    addSubFolder(parentPath) {
        const name = prompt('Enter folder name:');
        if (name) {
            this.createFolder(parentPath, name);
        }
    }
    
    openInNewTab(path) {
        window.open(path, '_blank');
    }
    
    copyPagePath(path) {
        navigator.clipboard.writeText(window.location.origin + path).then(() => {
            this.showNotification('Page path copied to clipboard');
        });
    }
    
    editPage(path) {
        window.location.href = `/editor${path}`;
    }
    
    movePage(path) {
        // This would open a move dialog
        console.log('Move page:', path);
    }
    
    deletePage(path) {
        if (confirm('Are you sure you want to delete this page?')) {
            this.deleteDocument(path);
        }
    }
    
    renameFolder(path) {
        const currentName = path.split('/').pop();
        const newName = prompt('Enter new folder name:', currentName);
        if (newName && newName !== currentName) {
            this.renameFolder(path, newName);
        }
    }
    
    moveFolder(path) {
        // This would open a move dialog
        console.log('Move folder:', path);
    }
    
    deleteFolder(path) {
        if (confirm('Are you sure you want to delete this folder and all its contents?')) {
            this.deleteFolderAndContents(path);
        }
    }
    
    // API helpers
    getAuthToken() {
        return localStorage.getItem('auth-token') || sessionStorage.getItem('auth-token');
    }
    
    async createFolder(parentPath, name) {
        try {
            const response = await fetch('/api/v1/folders', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getAuthToken()}`
                },
                body: JSON.stringify({
                    name: name,
                    parent_path: parentPath
                })
            });
            
            if (response.ok) {
                window.location.reload();
            } else {
                throw new Error('Failed to create folder');
            }
        } catch (error) {
            this.showNotification('Failed to create folder', 'error');
        }
    }
    
    async deleteDocument(path) {
        try {
            const response = await fetch(`/api/v1/documents${path}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`
                }
            });
            
            if (response.ok) {
                window.location.reload();
            } else {
                throw new Error('Failed to delete document');
            }
        } catch (error) {
            this.showNotification('Failed to delete document', 'error');
        }
    }
    
    // Notification system
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }
    
    // Event listeners setup
    setupEventListeners() {
        // Theme toggle
        const themeToggle = document.querySelector('.theme-toggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', () => this.toggleTheme());
        }
        
        // Mobile menu toggle
        const mobileToggle = document.querySelector('.mobile-menu-toggle');
        if (mobileToggle) {
            mobileToggle.addEventListener('click', () => this.toggleSidebar());
        }
        
        // Close sidebar when clicking outside on mobile
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 768 && this.sidebarOpen) {
                const sidebar = document.querySelector('.app-sidebar');
                const toggle = document.querySelector('.mobile-menu-toggle');
                
                if (!sidebar.contains(e.target) && !toggle.contains(e.target)) {
                    this.toggleSidebar();
                }
            }
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + K for search
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                const searchInput = document.querySelector('.search-input');
                if (searchInput) {
                    searchInput.focus();
                }
            }
            
            // Escape to close context menu
            if (e.key === 'Escape') {
                this.hideContextMenu();
            }
        });
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.wikiApp = new WikiApp();
});
// S
earch functionality
class SearchManager {
    constructor() {
        this.searchInput = document.querySelector('.search-input');
        this.searchResults = document.querySelector('.search-results');
        this.currentResults = [];
        this.selectedIndex = -1;
        this.searchTimeout = null;
        
        if (this.searchInput) {
            this.setupSearchListeners();
        }
    }
    
    setupSearchListeners() {
        this.searchInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            
            clearTimeout(this.searchTimeout);
            
            if (query.length < 2) {
                this.hideResults();
                return;
            }
            
            this.searchTimeout = setTimeout(() => {
                this.performSearch(query);
            }, 300);
        });
        
        this.searchInput.addEventListener('keydown', (e) => {
            if (!this.searchResults.classList.contains('show')) return;
            
            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    this.selectNext();
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    this.selectPrevious();
                    break;
                case 'Enter':
                    e.preventDefault();
                    this.selectCurrent();
                    break;
                case 'Escape':
                    this.hideResults();
                    break;
            }
        });
        
        this.searchInput.addEventListener('blur', () => {
            // Delay hiding to allow clicking on results
            setTimeout(() => this.hideResults(), 150);
        });
        
        document.addEventListener('click', (e) => {
            if (!this.searchInput.contains(e.target) && !this.searchResults.contains(e.target)) {
                this.hideResults();
            }
        });
    }
    
    async performSearch(query) {
        try {
            const response = await fetch(`/api/v1/search/autocomplete?q=${encodeURIComponent(query)}`, {
                headers: {
                    'Authorization': `Bearer ${window.wikiApp.getAuthToken()}`
                }
            });
            
            if (response.ok) {
                const results = await response.json();
                this.displayResults(results);
            }
        } catch (error) {
            console.warn('Search failed:', error);
        }
    }
    
    displayResults(results) {
        this.currentResults = results;
        this.selectedIndex = -1;
        
        if (results.length === 0) {
            this.hideResults();
            return;
        }
        
        this.searchResults.innerHTML = '';
        
        results.forEach((result, index) => {
            const item = document.createElement('div');
            item.className = 'search-result-item';
            item.innerHTML = `
                <div class="search-result-title">${this.escapeHtml(result.title)}</div>
                <div class="search-result-path">${this.escapeHtml(result.path)}</div>
            `;
            
            item.addEventListener('click', () => {
                window.location.href = result.path;
            });
            
            this.searchResults.appendChild(item);
        });
        
        this.showResults();
    }
    
    showResults() {
        this.searchResults.classList.add('show');
    }
    
    hideResults() {
        this.searchResults.classList.remove('show');
        this.selectedIndex = -1;
        this.updateSelection();
    }
    
    selectNext() {
        if (this.selectedIndex < this.currentResults.length - 1) {
            this.selectedIndex++;
            this.updateSelection();
        }
    }
    
    selectPrevious() {
        if (this.selectedIndex > 0) {
            this.selectedIndex--;
            this.updateSelection();
        }
    }
    
    selectCurrent() {
        if (this.selectedIndex >= 0 && this.selectedIndex < this.currentResults.length) {
            const result = this.currentResults[this.selectedIndex];
            window.location.href = result.path;
        }
    }
    
    updateSelection() {
        const items = this.searchResults.querySelectorAll('.search-result-item');
        items.forEach((item, index) => {
            item.classList.toggle('highlighted', index === this.selectedIndex);
        });
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Message management
class MessageManager {
    constructor() {
        this.setupMessageListeners();
    }
    
    setupMessageListeners() {
        document.querySelectorAll('.message-close').forEach(button => {
            button.addEventListener('click', () => {
                button.closest('.message').remove();
            });
        });
    }
}

// Enhanced WikiApp with search
class EnhancedWikiApp extends WikiApp {
    constructor() {
        super();
        this.searchManager = new SearchManager();
        this.messageManager = new MessageManager();
    }
}

// Replace the original WikiApp initialization
document.addEventListener('DOMContentLoaded', () => {
    window.wikiApp = new EnhancedWikiApp();
});