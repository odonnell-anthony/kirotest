// Editor JavaScript for Wiki Documentation App

class DocumentEditor {
    constructor() {
        this.documentData = this.loadDocumentData();
        this.currentMode = 'markdown';
        this.codeMirror = null;
        this.quillEditor = null;
        this.isDirty = false;
        this.autoSaveInterval = null;
        this.lastSaveTime = null;
        this.selectedTags = new Set(this.documentData.tags || []);
        this.allTags = this.documentData.all_tags || [];
        
        this.init();
    }
    
    init() {
        this.setupElements();
        this.setupEditors();
        this.setupEventListeners();
        this.setupAutoSave();
        this.setupDragAndDrop();
        this.updateUI();
        
        // Initialize mermaid
        if (typeof mermaid !== 'undefined') {
            mermaid.initialize({ 
                startOnLoad: false,
                theme: document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'default'
            });
        }
    }
    
    loadDocumentData() {
        const dataElement = document.getElementById('documentData');
        if (dataElement) {
            try {
                return JSON.parse(dataElement.textContent);
            } catch (e) {
                console.error('Failed to parse document data:', e);
            }
        }
        return {
            id: '',
            title: '',
            content: '',
            folder_path: '/',
            status: 'draft',
            tags: [],
            all_tags: [],
            is_editing: false
        };
    }
    
    setupElements() {
        this.elements = {
            titleInput: document.getElementById('documentTitle'),
            folderPathInput: document.getElementById('folderPath'),
            tagInput: document.getElementById('tagInput'),
            selectedTags: document.getElementById('selectedTags'),
            tagSuggestions: document.getElementById('tagSuggestions'),
            
            // Mode buttons
            modeButtons: document.querySelectorAll('.mode-btn'),
            
            // Editor panes
            markdownPane: document.getElementById('markdownEditor'),
            wysiwygPane: document.getElementById('wysiwygEditor'),
            previewPane: document.getElementById('previewPane'),
            
            // Action buttons
            previewBtn: document.getElementById('previewBtn'),
            saveAsDraftBtn: document.getElementById('saveAsDraftBtn'),
            publishBtn: document.getElementById('publishBtn'),
            
            // Status elements
            wordCount: document.getElementById('wordCount'),
            charCount: document.getElementById('charCount'),
            lineCount: document.getElementById('lineCount'),
            saveStatus: document.getElementById('saveStatus'),
            lastSaved: document.getElementById('lastSaved'),
            
            // Modals
            linkModal: document.getElementById('linkModal'),
            imageModal: document.getElementById('imageModal'),
            emojiModal: document.getElementById('emojiModal'),
            mermaidModal: document.getElementById('mermaidModal'),
            folderModal: document.getElementById('folderModal')
        };
    }
    
    setupEditors() {
        this.setupMarkdownEditor();
        this.setupWysiwygEditor();
    }
    
    setupMarkdownEditor() {
        const textarea = document.getElementById('markdownTextarea');
        if (textarea && typeof CodeMirror !== 'undefined') {
            this.codeMirror = CodeMirror.fromTextArea(textarea, {
                mode: 'markdown',
                theme: document.documentElement.getAttribute('data-theme') === 'dark' ? 'github-dark' : 'github',
                lineNumbers: true,
                lineWrapping: true,
                autoCloseBrackets: true,
                matchBrackets: true,
                extraKeys: {
                    'Ctrl-B': () => this.insertMarkdown('**', '**'),
                    'Ctrl-I': () => this.insertMarkdown('*', '*'),
                    'Ctrl-K': () => this.showLinkModal(),
                    'Ctrl-S': (cm) => { this.saveDocument(); return false; },
                    'Tab': (cm) => {
                        if (cm.somethingSelected()) {
                            cm.indentSelection('add');
                        } else {
                            cm.replaceSelection('    ');
                        }
                    }
                },
                placeholder: 'Start writing your document in Markdown...'
            });
            
            this.codeMirror.on('change', () => {
                this.markDirty();
                this.updateStats();
                this.updatePreview();
            });
            
            this.codeMirror.on('paste', (cm, event) => {
                this.handlePaste(event);
            });
        }
    }
    
    setupWysiwygEditor() {
        if (typeof Quill !== 'undefined') {
            this.quillEditor = new Quill('#quillEditor', {
                theme: 'snow',
                placeholder: 'Start writing your document...',
                modules: {
                    toolbar: [
                        [{ 'header': [1, 2, 3, false] }],
                        ['bold', 'italic', 'underline', 'strike'],
                        ['blockquote', 'code-block'],
                        [{ 'list': 'ordered'}, { 'list': 'bullet' }],
                        ['link', 'image'],
                        ['clean']
                    ]
                }
            });
            
            this.quillEditor.on('text-change', () => {
                this.markDirty();
                this.updateStats();
            });
            
            // Convert initial content if switching from markdown
            if (this.documentData.content) {
                this.quillEditor.root.innerHTML = this.markdownToHtml(this.documentData.content);
            }
        }
    }
    
    setupEventListeners() {
        // Title input
        if (this.elements.titleInput) {
            this.elements.titleInput.addEventListener('input', () => {
                this.markDirty();
                this.validateTitle();
            });
        }
        
        // Folder path input
        if (this.elements.folderPathInput) {
            this.elements.folderPathInput.addEventListener('input', () => {
                this.markDirty();
                this.validateFolderPath();
            });
        }
        
        // Mode switching
        this.elements.modeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const mode = btn.dataset.mode;
                this.switchMode(mode);
            });
        });
        
        // Action buttons
        if (this.elements.previewBtn) {
            this.elements.previewBtn.addEventListener('click', () => {
                this.togglePreview();
            });
        }
        
        if (this.elements.saveAsDraftBtn) {
            this.elements.saveAsDraftBtn.addEventListener('click', () => {
                this.saveDocument('draft');
            });
        }
        
        if (this.elements.publishBtn) {
            this.elements.publishBtn.addEventListener('click', () => {
                this.saveDocument('published');
            });
        }
        
        // Toolbar buttons
        document.querySelectorAll('.toolbar-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                this.handleToolbarAction(action);
            });
        });
        
        // Tag input
        this.setupTagInput();
        
        // Modal handlers
        this.setupModalHandlers();
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            this.handleKeyboardShortcuts(e);
        });
    }
    
    setupTagInput() {
        if (!this.elements.tagInput) return;
        
        this.elements.tagInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            this.showTagSuggestions(query);
        });
        
        this.elements.tagInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                this.addTag(e.target.value.trim());
                e.target.value = '';
                this.hideTagSuggestions();
            } else if (e.key === 'Escape') {
                this.hideTagSuggestions();
            }
        });
        
        this.elements.tagInput.addEventListener('blur', () => {
            setTimeout(() => this.hideTagSuggestions(), 150);
        });
    }
    
    setupModalHandlers() {
        // Close modals
        document.querySelectorAll('.modal-close, [data-dismiss="modal"]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const modal = btn.closest('.modal');
                if (modal) {
                    this.hideModal(modal);
                }
            });
        });
        
        // Modal backdrop click
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.hideModal(modal);
                }
            });
        });
        
        // Link modal
        const insertLinkBtn = document.getElementById('insertLinkBtn');
        if (insertLinkBtn) {
            insertLinkBtn.addEventListener('click', () => {
                this.insertLink();
            });
        }
        
        // Image modal
        const insertImageBtn = document.getElementById('insertImageBtn');
        if (insertImageBtn) {
            insertImageBtn.addEventListener('click', () => {
                this.insertImage();
            });
        }
        
        // Image upload
        this.setupImageUpload();
        
        // Mermaid modal
        const insertMermaidBtn = document.getElementById('insertMermaidBtn');
        if (insertMermaidBtn) {
            insertMermaidBtn.addEventListener('click', () => {
                this.insertMermaid();
            });
        }
        
        this.setupMermaidEditor();
    }
    
    setupImageUpload() {
        const dropZone = document.getElementById('imageDropZone');
        const fileInput = document.getElementById('imageFileInput');
        
        if (dropZone && fileInput) {
            dropZone.addEventListener('click', () => {
                fileInput.click();
            });
            
            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.uploadImage(e.target.files[0]);
                }
            });
            
            // Drag and drop
            dropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropZone.classList.add('dragover');
            });
            
            dropZone.addEventListener('dragleave', () => {
                dropZone.classList.remove('dragover');
            });
            
            dropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropZone.classList.remove('dragover');
                
                const files = Array.from(e.dataTransfer.files).filter(file => 
                    file.type.startsWith('image/')
                );
                
                if (files.length > 0) {
                    this.uploadImage(files[0]);
                }
            });
        }
        
        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                this.switchImageTab(tab);
            });
        });
    }
    
    setupMermaidEditor() {
        const codeTextarea = document.getElementById('mermaidCode');
        
        if (codeTextarea) {
            codeTextarea.addEventListener('input', () => {
                this.updateMermaidPreview();
            });
        }
        
        // Template buttons
        document.querySelectorAll('.template-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const template = btn.dataset.template;
                this.insertMermaidTemplate(template);
            });
        });
    }
    
    setupAutoSave() {
        this.autoSaveInterval = setInterval(() => {
            if (this.isDirty && this.isValidDocument()) {
                this.saveDocument('draft', true);
            }
        }, 30000); // Auto-save every 30 seconds
    }
    
    setupDragAndDrop() {
        const editorContent = document.querySelector('.editor-content');
        
        if (editorContent) {
            editorContent.addEventListener('dragover', (e) => {
                e.preventDefault();
                editorContent.classList.add('dragover');
            });
            
            editorContent.addEventListener('dragleave', (e) => {
                if (!editorContent.contains(e.relatedTarget)) {
                    editorContent.classList.remove('dragover');
                }
            });
            
            editorContent.addEventListener('drop', (e) => {
                e.preventDefault();
                editorContent.classList.remove('dragover');
                
                const files = Array.from(e.dataTransfer.files);
                const imageFiles = files.filter(file => file.type.startsWith('image/'));
                
                if (imageFiles.length > 0) {
                    imageFiles.forEach(file => this.uploadAndInsertImage(file));
                }
            });
        }
    }
    
    switchMode(mode) {
        if (mode === this.currentMode) return;
        
        // Save current content
        const currentContent = this.getCurrentContent();
        
        // Update UI
        this.elements.modeButtons.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.mode === mode);
        });
        
        // Hide all panes
        document.querySelectorAll('.editor-pane').forEach(pane => {
            pane.classList.remove('active');
        });
        
        // Show selected pane
        if (mode === 'markdown') {
            this.elements.markdownPane.classList.add('active');
            if (this.currentMode === 'wysiwyg' && this.quillEditor) {
                // Convert from HTML to Markdown
                const htmlContent = this.quillEditor.root.innerHTML;
                const markdownContent = this.htmlToMarkdown(htmlContent);
                this.codeMirror.setValue(markdownContent);
            }
        } else if (mode === 'wysiwyg') {
            this.elements.wysiwygPane.classList.add('active');
            if (this.currentMode === 'markdown' && this.codeMirror) {
                // Convert from Markdown to HTML
                const markdownContent = this.codeMirror.getValue();
                const htmlContent = this.markdownToHtml(markdownContent);
                this.quillEditor.root.innerHTML = htmlContent;
            }
        }
        
        this.currentMode = mode;
        this.updateStats();
    }
    
    togglePreview() {
        const isPreviewActive = this.elements.previewPane.classList.contains('active');
        
        if (isPreviewActive) {
            // Return to editor
            this.switchMode(this.currentMode === 'markdown' ? 'markdown' : 'wysiwyg');
            this.elements.previewBtn.textContent = '👁️ Preview';
        } else {
            // Show preview
            document.querySelectorAll('.editor-pane').forEach(pane => {
                pane.classList.remove('active');
            });
            this.elements.previewPane.classList.add('active');
            this.elements.previewBtn.textContent = '✏️ Edit';
            this.updatePreview();
        }
    }
    
    updatePreview() {
        const content = this.getCurrentContent();
        const previewContent = document.getElementById('previewContent');
        
        if (previewContent) {
            if (this.currentMode === 'markdown') {
                const html = this.markdownToHtml(content);
                previewContent.innerHTML = html;
            } else {
                previewContent.innerHTML = content;
            }
            
            // Render mermaid diagrams
            if (typeof mermaid !== 'undefined') {
                mermaid.init(undefined, previewContent.querySelectorAll('.mermaid'));
            }
        }
    }
    
    getCurrentContent() {
        if (this.currentMode === 'markdown' && this.codeMirror) {
            return this.codeMirror.getValue();
        } else if (this.currentMode === 'wysiwyg' && this.quillEditor) {
            return this.quillEditor.root.innerHTML;
        }
        return '';
    }
    
    setCurrentContent(content) {
        if (this.currentMode === 'markdown' && this.codeMirror) {
            this.codeMirror.setValue(content);
        } else if (this.currentMode === 'wysiwyg' && this.quillEditor) {
            this.quillEditor.root.innerHTML = content;
        }
    }
    
    markDirty() {
        if (!this.isDirty) {
            this.isDirty = true;
            this.updateSaveStatus('Unsaved changes');
        }
    }
    
    markClean() {
        this.isDirty = false;
        this.lastSaveTime = new Date();
        this.updateSaveStatus('All changes saved');
        this.updateLastSaved();
    }
    
    updateSaveStatus(status) {
        if (this.elements.saveStatus) {
            this.elements.saveStatus.textContent = status;
        }
    }
    
    updateLastSaved() {
        if (this.elements.lastSaved && this.lastSaveTime) {
            const timeStr = this.lastSaveTime.toLocaleTimeString();
            this.elements.lastSaved.textContent = `Last saved: ${timeStr}`;
        }
    }
    
    updateStats() {
        const content = this.getCurrentContent();
        const text = this.stripHtml(content);
        
        const words = text.trim() ? text.trim().split(/\s+/).length : 0;
        const chars = text.length;
        const lines = content.split('\n').length;
        
        if (this.elements.wordCount) {
            this.elements.wordCount.textContent = `Words: ${words}`;
        }
        if (this.elements.charCount) {
            this.elements.charCount.textContent = `Characters: ${chars}`;
        }
        if (this.elements.lineCount) {
            this.elements.lineCount.textContent = `Lines: ${lines}`;
        }
    }
    
    stripHtml(html) {
        const div = document.createElement('div');
        div.innerHTML = html;
        return div.textContent || div.innerText || '';
    }
    
    markdownToHtml(markdown) {
        if (typeof marked !== 'undefined') {
            return marked.parse(markdown);
        }
        // Fallback basic conversion
        return markdown
            .replace(/^# (.*$)/gim, '<h1>$1</h1>')
            .replace(/^## (.*$)/gim, '<h2>$1</h2>')
            .replace(/^### (.*$)/gim, '<h3>$1</h3>')
            .replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>')
            .replace(/\*(.*)\*/gim, '<em>$1</em>')
            .replace(/\n/gim, '<br>');
    }
    
    htmlToMarkdown(html) {
        // Basic HTML to Markdown conversion
        return html
            .replace(/<h1>(.*?)<\/h1>/gim, '# $1\n')
            .replace(/<h2>(.*?)<\/h2>/gim, '## $1\n')
            .replace(/<h3>(.*?)<\/h3>/gim, '### $1\n')
            .replace(/<strong>(.*?)<\/strong>/gim, '**$1**')
            .replace(/<em>(.*?)<\/em>/gim, '*$1*')
            .replace(/<br\s*\/?>/gim, '\n')
            .replace(/<p>(.*?)<\/p>/gim, '$1\n\n')
            .replace(/<[^>]*>/gim, ''); // Remove remaining HTML tags
    }
    
    handleToolbarAction(action) {
        switch (action) {
            case 'bold':
                this.insertMarkdown('**', '**');
                break;
            case 'italic':
                this.insertMarkdown('*', '*');
                break;
            case 'code':
                this.insertMarkdown('`', '`');
                break;
            case 'heading1':
                this.insertMarkdown('# ', '');
                break;
            case 'heading2':
                this.insertMarkdown('## ', '');
                break;
            case 'heading3':
                this.insertMarkdown('### ', '');
                break;
            case 'unordered-list':
                this.insertMarkdown('- ', '');
                break;
            case 'ordered-list':
                this.insertMarkdown('1. ', '');
                break;
            case 'blockquote':
                this.insertMarkdown('> ', '');
                break;
            case 'link':
                this.showLinkModal();
                break;
            case 'image':
                this.showImageModal();
                break;
            case 'table':
                this.insertTable();
                break;
            case 'emoji':
                this.showEmojiModal();
                break;
            case 'mermaid':
                this.showMermaidModal();
                break;
            case 'upload':
                this.showFileUpload();
                break;
        }
    }
    
    insertMarkdown(before, after) {
        if (this.codeMirror) {
            const doc = this.codeMirror.getDoc();
            const cursor = doc.getCursor();
            
            if (doc.somethingSelected()) {
                const selection = doc.getSelection();
                doc.replaceSelection(before + selection + after);
            } else {
                doc.replaceRange(before + after, cursor);
                doc.setCursor(cursor.line, cursor.ch + before.length);
            }
            
            this.codeMirror.focus();
        }
    }
    
    insertTable() {
        const tableMarkdown = `
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Row 1    | Data     | Data     |
| Row 2    | Data     | Data     |
`;
        this.insertMarkdown('\n' + tableMarkdown + '\n', '');
    }
    
    showModal(modal) {
        if (modal) {
            modal.classList.add('show');
            document.body.style.overflow = 'hidden';
        }
    }
    
    hideModal(modal) {
        if (modal) {
            modal.classList.remove('show');
            document.body.style.overflow = '';
        }
    }
    
    showLinkModal() {
        this.showModal(this.elements.linkModal);
        const linkText = document.getElementById('linkText');
        if (linkText) linkText.focus();
    }
    
    insertLink() {
        const linkText = document.getElementById('linkText');
        const linkUrl = document.getElementById('linkUrl');
        
        if (linkUrl && linkUrl.value) {
            const markdown = `[${linkText ? linkText.value : 'Link'}](${linkUrl.value})`;
            this.insertMarkdown(markdown, '');
            
            // Clear form
            if (linkText) linkText.value = '';
            if (linkUrl) linkUrl.value = '';
            
            this.hideModal(this.elements.linkModal);
        }
    }
    
    showImageModal() {
        this.showModal(this.elements.imageModal);
    }
    
    switchImageTab(tab) {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });
        
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === tab + 'Tab');
        });
    }
    
    async uploadImage(file) {
        const progressContainer = document.getElementById('uploadProgress');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        
        if (progressContainer) progressContainer.style.display = 'block';
        if (progressFill) progressFill.style.width = '0%';
        if (progressText) progressText.textContent = 'Uploading...';
        
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('folder_path', this.elements.folderPathInput.value);
            if (this.documentData.id) {
                formData.append('document_id', this.documentData.id);
            }
            
            const response = await fetch('/api/v1/files/upload', {
                method: 'POST',
                body: formData,
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`
                }
            });
            
            if (response.ok) {
                const result = await response.json();
                if (progressFill) progressFill.style.width = '100%';
                if (progressText) progressText.textContent = 'Upload complete!';
                
                // Insert image markdown
                const imageUrl = `/api/v1/files/${result.id}/download`;
                const altText = document.getElementById('imageAlt');
                const markdown = `![${altText ? altText.value : file.name}](${imageUrl})`;
                
                this.insertMarkdown(markdown, '');
                this.hideModal(this.elements.imageModal);
                
                // Clear form
                if (altText) altText.value = '';
                const fileInput = document.getElementById('imageFileInput');
                if (fileInput) fileInput.value = '';
                
                setTimeout(() => {
                    if (progressContainer) progressContainer.style.display = 'none';
                }, 1000);
                
            } else {
                throw new Error('Upload failed');
            }
            
        } catch (error) {
            console.error('Image upload failed:', error);
            if (progressText) progressText.textContent = 'Upload failed';
            if (progressFill) progressFill.style.backgroundColor = 'var(--danger)';
            
            if (window.wikiApp) {
                window.wikiApp.showNotification('Image upload failed', 'error');
            }
        }
    }
    
    insertImage() {
        const activeTab = document.querySelector('.tab-content.active');
        
        if (activeTab && activeTab.id === 'urlTab') {
            const imageUrl = document.getElementById('imageUrl');
            const altText = document.getElementById('imageAlt');
            
            if (imageUrl && imageUrl.value) {
                const markdown = `![${altText ? altText.value : 'Image'}](${imageUrl.value})`;
                this.insertMarkdown(markdown, '');
                
                // Clear form
                imageUrl.value = '';
                if (altText) altText.value = '';
                
                this.hideModal(this.elements.imageModal);
            }
        }
    }
    
    async uploadAndInsertImage(file) {
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('folder_path', this.elements.folderPathInput.value);
            if (this.documentData.id) {
                formData.append('document_id', this.documentData.id);
            }
            
            const response = await fetch('/api/v1/files/upload', {
                method: 'POST',
                body: formData,
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`
                }
            });
            
            if (response.ok) {
                const result = await response.json();
                const imageUrl = `/api/v1/files/${result.id}/download`;
                const markdown = `![${file.name}](${imageUrl})`;
                
                this.insertMarkdown('\n' + markdown + '\n', '');
                if (window.wikiApp) {
                    window.wikiApp.showNotification('Image uploaded successfully', 'success');
                }
            } else {
                throw new Error('Upload failed');
            }
            
        } catch (error) {
            console.error('Image upload failed:', error);
            if (window.wikiApp) {
                window.wikiApp.showNotification('Image upload failed', 'error');
            }
        }
    }
    
    showEmojiModal() {
        this.showModal(this.elements.emojiModal);
        
        // Initialize emoji picker if not already done
        const emojiPicker = document.getElementById('emojiPicker');
        if (emojiPicker && !emojiPicker.querySelector('emoji-picker')) {
            const picker = document.createElement('emoji-picker');
            emojiPicker.appendChild(picker);
            
            picker.addEventListener('emoji-click', (event) => {
                this.insertMarkdown(event.detail.unicode, '');
                this.hideModal(this.elements.emojiModal);
            });
        }
    }
    
    showMermaidModal() {
        this.showModal(this.elements.mermaidModal);
    }
    
    insertMermaidTemplate(template) {
        const templates = {
            flowchart: `graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Action 1]
    B -->|No| D[Action 2]
    C --> E[End]
    D --> E`,
            sequence: `sequenceDiagram
    participant A as Alice
    participant B as Bob
    A->>B: Hello Bob, how are you?
    B-->>A: Great!`,
            gantt: `gantt
    title Project Timeline
    dateFormat  YYYY-MM-DD
    section Planning
    Task 1           :a1, 2024-01-01, 30d
    Task 2           :after a1, 20d`,
            pie: `pie title Sample Pie Chart
    "Category A" : 42.96
    "Category B" : 50.05
    "Category C" : 10.01`
        };
        
        const code = templates[template] || '';
        const mermaidCode = document.getElementById('mermaidCode');
        if (mermaidCode) {
            mermaidCode.value = code;
            this.updateMermaidPreview();
        }
    }
    
    updateMermaidPreview() {
        const codeTextarea = document.getElementById('mermaidCode');
        const preview = document.getElementById('mermaidPreview');
        
        if (codeTextarea && preview) {
            const code = codeTextarea.value;
            
            if (code.trim() && typeof mermaid !== 'undefined') {
                try {
                    preview.innerHTML = `<div class="mermaid">${code}</div>`;
                    mermaid.init(undefined, preview.querySelector('.mermaid'));
                } catch (error) {
                    preview.innerHTML = '<p style="color: var(--danger);">Invalid Mermaid syntax</p>';
                }
            } else {
                preview.innerHTML = '<p class="preview-placeholder">Preview will appear here...</p>';
            }
        }
    }
    
    insertMermaid() {
        const codeTextarea = document.getElementById('mermaidCode');
        
        if (codeTextarea && codeTextarea.value.trim()) {
            const markdown = `\`\`\`mermaid\n${codeTextarea.value}\n\`\`\``;
            this.insertMarkdown('\n' + markdown + '\n', '');
            
            // Clear form
            codeTextarea.value = '';
            
            this.hideModal(this.elements.mermaidModal);
        }
    }
    
    showFileUpload() {
        const hiddenInput = document.getElementById('hiddenFileInput');
        if (hiddenInput) {
            hiddenInput.click();
        }
    }
    
    // Tag management
    showTagSuggestions(query) {
        if (!query || !this.elements.tagSuggestions) {
            this.hideTagSuggestions();
            return;
        }
        
        const suggestions = this.allTags.filter(tag => 
            tag.name.toLowerCase().includes(query.toLowerCase()) &&
            !this.selectedTags.has(tag.name)
        );
        
        if (suggestions.length === 0) {
            this.hideTagSuggestions();
            return;
        }
        
        const suggestionsHtml = suggestions.map(tag => 
            `<div class="tag-suggestion" data-tag="${tag.name}">${tag.name}</div>`
        ).join('');
        
        this.elements.tagSuggestions.innerHTML = suggestionsHtml;
        this.elements.tagSuggestions.classList.add('show');
        
        // Add click handlers
        this.elements.tagSuggestions.querySelectorAll('.tag-suggestion').forEach(item => {
            item.addEventListener('click', () => {
                this.addTag(item.dataset.tag);
                this.elements.tagInput.value = '';
                this.hideTagSuggestions();
            });
        });
    }
    
    hideTagSuggestions() {
        if (this.elements.tagSuggestions) {
            this.elements.tagSuggestions.classList.remove('show');
        }
    }
    
    addTag(tagName) {
        if (!tagName || this.selectedTags.has(tagName)) return;
        
        this.selectedTags.add(tagName);
        this.renderSelectedTags();
        this.markDirty();
    }
    
    removeTag(tagName) {
        this.selectedTags.delete(tagName);
        this.renderSelectedTags();
        this.markDirty();
    }
    
    renderSelectedTags() {
        if (!this.elements.selectedTags) return;
        
        const tagsHtml = Array.from(this.selectedTags).map(tag => 
            `<span class="tag-item" data-tag="${tag}">
                ${tag}
                <button type="button" class="tag-remove" aria-label="Remove tag">×</button>
            </span>`
        ).join('');
        
        this.elements.selectedTags.innerHTML = tagsHtml;
        
        // Add remove handlers
        this.elements.selectedTags.querySelectorAll('.tag-remove').forEach(btn => {
            btn.addEventListener('click', () => {
                const tagName = btn.closest('.tag-item').dataset.tag;
                this.removeTag(tagName);
            });
        });
    }
    
    // Validation
    validateTitle() {
        if (!this.elements.titleInput) return true;
        
        const title = this.elements.titleInput.value.trim();
        const errorElement = document.getElementById('titleError');
        
        if (!title) {
            if (errorElement) errorElement.textContent = 'Title is required';
            this.elements.titleInput.classList.add('error');
            return false;
        } else if (title.length > 255) {
            if (errorElement) errorElement.textContent = 'Title must be less than 255 characters';
            this.elements.titleInput.classList.add('error');
            return false;
        } else {
            if (errorElement) errorElement.textContent = '';
            this.elements.titleInput.classList.remove('error');
            return true;
        }
    }
    
    validateFolderPath() {
        if (!this.elements.folderPathInput) return true;
        
        const path = this.elements.folderPathInput.value.trim();
        const errorElement = document.getElementById('folderError');
        
        if (!path.startsWith('/')) {
            if (errorElement) errorElement.textContent = 'Folder path must start with /';
            this.elements.folderPathInput.classList.add('error');
            return false;
        } else if (!/^(\/[a-zA-Z0-9_-]+)*\/$/.test(path)) {
            if (errorElement) errorElement.textContent = 'Invalid folder path format';
            this.elements.folderPathInput.classList.add('error');
            return false;
        } else {
            if (errorElement) errorElement.textContent = '';
            this.elements.folderPathInput.classList.remove('error');
            return true;
        }
    }
    
    isValidDocument() {
        return this.validateTitle() && this.validateFolderPath();
    }
    
    // Save functionality
    async saveDocument(status = 'draft', isAutoSave = false) {
        if (!this.isValidDocument()) {
            if (!isAutoSave && window.wikiApp) {
                window.wikiApp.showNotification('Please fix validation errors', 'error');
            }
            return;
        }
        
        const saveData = {
            title: this.elements.titleInput.value.trim(),
            content: this.getCurrentContent(),
            folder_path: this.elements.folderPathInput.value.trim(),
            status: status,
            tags: Array.from(this.selectedTags),
            content_type: this.currentMode === 'markdown' ? 'markdown' : 'html'
        };
        
        try {
            this.updateSaveStatus(isAutoSave ? 'Auto-saving...' : 'Saving...');
            
            const url = this.documentData.is_editing 
                ? `/api/v1/documents/${this.documentData.id}`
                : '/api/v1/documents';
            
            const method = this.documentData.is_editing ? 'PUT' : 'POST';
            
            const response = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getAuthToken()}`
                },
                body: JSON.stringify(saveData)
            });
            
            if (response.ok) {
                const result = await response.json();
                
                // Update document data
                this.documentData.id = result.id;
                this.documentData.is_editing = true;
                
                this.markClean();
                
                if (!isAutoSave && window.wikiApp) {
                    const message = status === 'published' ? 'Document published!' : 'Document saved!';
                    window.wikiApp.showNotification(message, 'success');
                    
                    if (status === 'published') {
                        // Redirect to view page
                        setTimeout(() => {
                            window.location.href = `/${result.slug}`;
                        }, 1000);
                    }
                }
                
            } else {
                throw new Error('Save failed');
            }
            
        } catch (error) {
            console.error('Save failed:', error);
            this.updateSaveStatus('Save failed');
            
            if (!isAutoSave && window.wikiApp) {
                window.wikiApp.showNotification('Failed to save document', 'error');
            }
        }
    }
    
    // Paste handling
    handlePaste(event) {
        const items = Array.from(event.clipboardData.items);
        const imageItem = items.find(item => item.type.startsWith('image/'));
        
        if (imageItem) {
            event.preventDefault();
            const file = imageItem.getAsFile();
            this.processPastedImage(file);
        }
    }
    
    async processPastedImage(file) {
        try {
            // Convert file to base64
            const reader = new FileReader();
            reader.onload = async (e) => {
                const imageData = e.target.result;
                
                const response = await fetch('/api/v1/files/paste-image', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.getAuthToken()}`
                    },
                    body: JSON.stringify({
                        image_data: imageData,
                        folder_path: this.elements.folderPathInput.value,
                        document_id: this.documentData.id
                    })
                });
                
                if (response.ok) {
                    const result = await response.json();
                    const imageUrl = `/api/v1/files/${result.id}/download`;
                    const markdown = `![Pasted image](${imageUrl})`;
                    
                    this.insertMarkdown('\n' + markdown + '\n', '');
                    if (window.wikiApp) {
                        window.wikiApp.showNotification('Image pasted successfully', 'success');
                    }
                } else {
                    throw new Error('Paste failed');
                }
            };
            
            reader.readAsDataURL(file);
            
        } catch (error) {
            console.error('Image paste failed:', error);
            if (window.wikiApp) {
                window.wikiApp.showNotification('Failed to paste image', 'error');
            }
        }
    }
    
    // Keyboard shortcuts
    handleKeyboardShortcuts(e) {
        if (e.ctrlKey || e.metaKey) {
            switch (e.key) {
                case 's':
                    e.preventDefault();
                    this.saveDocument();
                    break;
                case 'p':
                    e.preventDefault();
                    this.togglePreview();
                    break;
            }
        }
    }
    
    // Utility methods
    getAuthToken() {
        return localStorage.getItem('auth-token') || sessionStorage.getItem('auth-token');
    }
    
    updateUI() {
        // Set initial values
        if (this.elements.titleInput) {
            this.elements.titleInput.value = this.documentData.title;
        }
        if (this.elements.folderPathInput) {
            this.elements.folderPathInput.value = this.documentData.folder_path;
        }
        
        // Render tags
        this.selectedTags = new Set(this.documentData.tags);
        this.renderSelectedTags();
        
        // Set content
        if (this.codeMirror && this.documentData.content) {
            this.codeMirror.setValue(this.documentData.content);
        }
        
        // Update stats
        this.updateStats();
        
        // Focus title if new document
        if (!this.documentData.is_editing && this.elements.titleInput) {
            this.elements.titleInput.focus();
        }
    }
    
    // Cleanup
    destroy() {
        if (this.autoSaveInterval) {
            clearInterval(this.autoSaveInterval);
        }
        
        if (this.codeMirror) {
            this.codeMirror.toTextArea();
        }
    }
}

// Initialize editor when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.documentEditor = new DocumentEditor();
});

// Cleanup on page unload
window.addEventListener('beforeunload', (e) => {
    if (window.documentEditor && window.documentEditor.isDirty) {
        e.preventDefault();
        e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
        return e.returnValue;
    }
});