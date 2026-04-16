/**
 * KCM AI Suite — Frontend Application Logic
 * Handles file upload, translation pipeline orchestration,
 * progress polling, and file downloads.
 */

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Lucide icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // ── State ───────────────────────────────────────────────
    let selectedFile = null;
    let currentJobId = null;
    let pollInterval = null;

    // ── DOM References ──────────────────────────────────────
    const uploadZone     = document.getElementById('uploadZone');
    const fileInput      = document.getElementById('fileInput');
    const uploadSection  = document.getElementById('uploadSection');
    const fileInfoSection = document.getElementById('fileInfoSection');
    const progressSection = document.getElementById('progressSection');
    const completedSection = document.getElementById('completedSection');
    const errorSection   = document.getElementById('errorSection');
    const fileName       = document.getElementById('fileName');
    const fileSize       = document.getElementById('fileSize');
    const btnRemoveFile  = document.getElementById('btnRemoveFile');
    const btnTranslate   = document.getElementById('btnTranslate');
    const progressBar    = document.getElementById('progressBar');
    const progressPct    = document.getElementById('progressPct');
    const progressTitle  = document.getElementById('progressTitle');
    const progressDetail = document.getElementById('progressDetail');
    const btnDownloadPdf = document.getElementById('btnDownloadPdf');
    const btnDownloadRtf = document.getElementById('btnDownloadRtf');
    const btnPreviewToggle = document.getElementById('btnPreviewToggle');
    const previewArea    = document.getElementById('previewArea');
    const previewContent = document.getElementById('previewContent');
    const btnNewTranslation = document.getElementById('btnNewTranslation');
    const btnRetry       = document.getElementById('btnRetry');
    const errorMessage   = document.getElementById('errorMessage');
    const apiStatus      = document.getElementById('apiStatus');

    // Stage elements
    const stages = {
        uploading:  document.getElementById('stageUpload'),
        extracting: document.getElementById('stageExtract'),
        translating: document.getElementById('stageTranslate'),
        generating: document.getElementById('stageGenerate'),
    };
    const stageOrder = ['uploading', 'extracting', 'translating', 'generating'];

    // ── Check API Status ────────────────────────────────────
    checkApiStatus();

    async function checkApiStatus() {
        try {
            const resp = await fetch('/api/config/status');
            const data = await resp.json();
            if (data.configured) {
                apiStatus.classList.add('connected');
                apiStatus.classList.remove('disconnected');
                apiStatus.querySelector('span').textContent = 'API Connected';
            } else {
                apiStatus.classList.add('disconnected');
                apiStatus.classList.remove('connected');
                apiStatus.querySelector('span').textContent = 'API Key Missing';
            }
        } catch {
            apiStatus.classList.add('disconnected');
            apiStatus.querySelector('span').textContent = 'Server Error';
        }
    }

    // ── Upload Zone Events ──────────────────────────────────

    // Click to upload
    uploadZone.addEventListener('click', () => {
        fileInput.click();
    });

    // File input change
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    // Drag and drop
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        uploadZone.classList.add('drag-over');
    });

    uploadZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        uploadZone.classList.remove('drag-over');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        uploadZone.classList.remove('drag-over');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileSelect(files[0]);
        }
    });

    // ── File Selection ──────────────────────────────────────
    function handleFileSelect(file) {
        // Validate file type
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            showError('Please select a PDF file.');
            return;
        }

        // Validate file size (200 MB)
        if (file.size > 200 * 1024 * 1024) {
            showError('File is too large. Maximum size is 200 MB.');
            return;
        }

        selectedFile = file;
        fileName.textContent = file.name;
        fileSize.textContent = formatFileSize(file.size);

        showSection('fileInfo');
    }

    // Remove file
    btnRemoveFile.addEventListener('click', () => {
        selectedFile = null;
        fileInput.value = '';
        showSection('upload');
    });

    // ── Translate Button ────────────────────────────────────
    btnTranslate.addEventListener('click', startTranslation);

    async function startTranslation() {
        if (!selectedFile) return;

        const formData = new FormData();
        formData.append('file', selectedFile);

        showSection('progress');
        updateProgress('uploading', 'Uploading document…', 0);

        try {
            const resp = await fetch('/api/translate', {
                method: 'POST',
                body: formData,
            });

            const data = await resp.json();

            if (!resp.ok) {
                throw new Error(data.error || 'Failed to start translation.');
            }

            currentJobId = data.job_id;
            startPolling();
        } catch (err) {
            showError(err.message);
        }
    }

    // ── Progress Polling ────────────────────────────────────
    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);

        pollInterval = setInterval(async () => {
            try {
                const resp = await fetch(`/api/translate/status/${currentJobId}`);
                const data = await resp.json();

                if (data.status === 'processing') {
                    updateProgress(data.stage, data.detail, data.progress);
                } else if (data.status === 'completed') {
                    stopPolling();
                    showSection('completed');
                } else if (data.status === 'failed') {
                    stopPolling();
                    showError(data.error || data.detail || 'Translation failed.');
                }
            } catch (err) {
                // Network error — keep polling, might be temporary
                console.error('Polling error:', err);
            }
        }, 1500);
    }

    function stopPolling() {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
    }

    function updateProgress(stage, detail, progress) {
        // Update progress bar
        progressBar.style.width = `${progress}%`;
        progressPct.textContent = `${Math.round(progress)}%`;
        progressDetail.textContent = detail;

        // Map stage to title
        const stageTitles = {
            uploading: 'Uploading Document…',
            extracting: 'Extracting Text (OCR)…',
            translating: 'Translating to English…',
            generating: 'Generating Documents…',
        };
        progressTitle.textContent = stageTitles[stage] || 'Processing…';

        // Update stage indicators
        const currentIdx = stageOrder.indexOf(stage);
        stageOrder.forEach((s, idx) => {
            const el = stages[s];
            if (!el) return;

            el.classList.remove('active', 'completed');

            if (idx < currentIdx) {
                el.classList.add('completed');
            } else if (idx === currentIdx) {
                el.classList.add('active');
            }
        });

        // Update connectors
        const connectors = document.querySelectorAll('.stage-connector');
        connectors.forEach((conn, idx) => {
            conn.classList.toggle('active', idx < currentIdx);
        });
    }

    // ── Download Handlers ───────────────────────────────────
    btnDownloadPdf.addEventListener('click', () => downloadFile('pdf'));
    btnDownloadRtf.addEventListener('click', () => downloadFile('rtf'));

    function downloadFile(format) {
        if (!currentJobId) return;
        // Open in system default browser for reliable download
        const url = `/api/translate/download/${currentJobId}/${format}`;
        window.open(url, '_blank');
    }

    // ── Preview ─────────────────────────────────────────────
    btnPreviewToggle.addEventListener('click', async () => {
        if (previewArea.classList.contains('hidden')) {
            previewArea.classList.remove('hidden');
            btnPreviewToggle.querySelector('span').textContent = 'Hide Preview';

            // Fetch preview content
            try {
                const resp = await fetch(`/api/translate/preview/${currentJobId}`);
                const data = await resp.json();
                previewContent.textContent = data.translated_text || 'No content available.';
            } catch {
                previewContent.textContent = 'Failed to load preview.';
            }
        } else {
            previewArea.classList.add('hidden');
            btnPreviewToggle.querySelector('span').textContent = 'Preview Translation';
        }
    });

    // ── New Translation / Retry ───────────────────────────────
    btnNewTranslation.addEventListener('click', resetToUpload);
    btnRetry.addEventListener('click', resetToUpload);

    function resetToUpload() {
        stopPolling();
        selectedFile = null;
        currentJobId = null;
        fileInput.value = '';
        previewArea.classList.add('hidden');
        btnPreviewToggle.querySelector('span').textContent = 'Preview Translation';
        showSection('upload');
    }

    // ── Section Management ──────────────────────────────────
    function showSection(name) {
        const sections = {
            upload: uploadSection,
            fileInfo: fileInfoSection,
            progress: progressSection,
            completed: completedSection,
            error: errorSection,
        };

        // Hide all
        Object.values(sections).forEach(s => {
            if (s) s.classList.add('hidden');
        });

        // Show target
        const target = sections[name];
        if (target) {
            target.classList.remove('hidden');
            target.classList.remove('fade-in');
            // Trigger reflow for animation restart
            void target.offsetWidth;
            target.classList.add('fade-in');
        }

        // Re-render icons for newly visible elements
        if (typeof lucide !== 'undefined') {
            setTimeout(() => lucide.createIcons(), 50);
        }
    }

    function showError(message) {
        errorMessage.textContent = message;
        showSection('error');
    }

    // ── Utilities ───────────────────────────────────────────
    function formatFileSize(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
});
