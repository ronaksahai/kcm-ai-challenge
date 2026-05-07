/**
 * KCM AI Suite — Frontend Application Logic
 * Handles module switching, file uploads, translation pipeline,
 * order scrutiny pipeline, progress polling, and downloads.
 */

document.addEventListener('DOMContentLoaded', () => {
    if (typeof lucide !== 'undefined') lucide.createIcons();

    // ── State ───────────────────────────────────────────────
    let selectedFile = null;
    let currentJobId = null;
    let pollInterval = null;
    let activeModule = 'translator';

    // Scrutiny state
    let scrutinyFiles = { comp: null, intim: null, ao: null };
    let scrutinyJobId = null;
    let scrutinyPollInterval = null;

    // ── DOM: Common ─────────────────────────────────────────
    const apiStatus = document.getElementById('apiStatus');

    // ── DOM: Module switching ────────────────────────────────
    const navItems = document.querySelectorAll('.nav-item[data-module]');
    const modules = document.querySelectorAll('.module-content');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const mod = item.dataset.module;
            if (mod) switchModule(mod);
        });
    });

    function switchModule(mod) {
        activeModule = mod;
        navItems.forEach(n => {
            n.classList.toggle('active', n.dataset.module === mod);
        });
        modules.forEach(m => {
            m.classList.toggle('active', m.id === mod + 'Module');
        });
        if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 50);
        checkApiStatus();
    }

    // ── API Status ──────────────────────────────────────────
    checkApiStatus();

    async function checkApiStatus() {
        try {
            const endpoint = (activeModule === 'scrutiny' || activeModule === 'noticeReply') ? '/api/notice-reply/config' : '/api/config/status';
            const resp = await fetch(endpoint);
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


    // ═════════════════════════════════════════════════════════
    //  TRANSLATOR MODULE (existing logic)
    // ═════════════════════════════════════════════════════════

    const uploadZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('fileInput');
    const uploadSection = document.getElementById('uploadSection');
    const fileInfoSection = document.getElementById('fileInfoSection');
    const progressSection = document.getElementById('progressSection');
    const completedSection = document.getElementById('completedSection');
    const errorSection = document.getElementById('errorSection');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const btnRemoveFile = document.getElementById('btnRemoveFile');
    const btnTranslate = document.getElementById('btnTranslate');
    const progressBar = document.getElementById('progressBar');
    const progressPct = document.getElementById('progressPct');
    const progressTitle = document.getElementById('progressTitle');
    const progressDetail = document.getElementById('progressDetail');
    const btnDownloadPdf = document.getElementById('btnDownloadPdf');
    const btnDownloadRtf = document.getElementById('btnDownloadRtf');
    const btnPreviewToggle = document.getElementById('btnPreviewToggle');
    const previewArea = document.getElementById('previewArea');
    const previewContent = document.getElementById('previewContent');
    const btnNewTranslation = document.getElementById('btnNewTranslation');
    const btnRetry = document.getElementById('btnRetry');
    const errorMessage = document.getElementById('errorMessage');

    const stages = {
        uploading: document.getElementById('stageUpload'),
        extracting: document.getElementById('stageExtract'),
        translating: document.getElementById('stageTranslate'),
        generating: document.getElementById('stageGenerate'),
    };
    const stageOrder = ['uploading', 'extracting', 'translating', 'generating'];

    // Upload zone events
    uploadZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleFileSelect(e.target.files[0]);
    });
    uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); uploadZone.classList.add('drag-over'); });
    uploadZone.addEventListener('dragleave', (e) => { e.preventDefault(); e.stopPropagation(); uploadZone.classList.remove('drag-over'); });
    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault(); e.stopPropagation(); uploadZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) handleFileSelect(e.dataTransfer.files[0]);
    });

    function handleFileSelect(file) {
        if (!file.name.toLowerCase().endsWith('.pdf')) { showTranslatorError('Please select a PDF file.'); return; }
        if (file.size > 200 * 1024 * 1024) { showTranslatorError('File too large. Max 200 MB.'); return; }
        selectedFile = file;
        fileName.textContent = file.name;
        fileSize.textContent = formatFileSize(file.size);
        showTranslatorSection('fileInfo');
    }

    btnRemoveFile.addEventListener('click', () => { selectedFile = null; fileInput.value = ''; showTranslatorSection('upload'); });
    btnTranslate.addEventListener('click', startTranslation);

    async function startTranslation() {
        if (!selectedFile) return;
        const formData = new FormData();
        formData.append('file', selectedFile);
        showTranslatorSection('progress');
        updateTranslatorProgress('uploading', 'Uploading document…', 0);
        try {
            const resp = await fetch('/api/translate', { method: 'POST', body: formData });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'Failed to start translation.');
            currentJobId = data.job_id;
            startTranslatorPolling();
        } catch (err) { showTranslatorError(err.message); }
    }

    function startTranslatorPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(async () => {
            try {
                const resp = await fetch(`/api/translate/status/${currentJobId}`);
                const data = await resp.json();
                if (data.status === 'processing') updateTranslatorProgress(data.stage, data.detail, data.progress);
                else if (data.status === 'completed') { clearInterval(pollInterval); pollInterval = null; showTranslatorSection('completed'); }
                else if (data.status === 'failed') { clearInterval(pollInterval); pollInterval = null; showTranslatorError(data.error || data.detail); }
            } catch (err) { console.error('Poll error:', err); }
        }, 1500);
    }

    function updateTranslatorProgress(stage, detail, progress) {
        progressBar.style.width = `${progress}%`;
        progressPct.textContent = `${Math.round(progress)}%`;
        progressDetail.textContent = detail;
        const titles = { uploading: 'Uploading…', extracting: 'Extracting Text…', translating: 'Translating…', generating: 'Generating…' };
        progressTitle.textContent = titles[stage] || 'Processing…';
        const currentIdx = stageOrder.indexOf(stage);
        stageOrder.forEach((s, idx) => {
            const el = stages[s]; if (!el) return;
            el.classList.remove('active', 'completed');
            if (idx < currentIdx) el.classList.add('completed');
            else if (idx === currentIdx) el.classList.add('active');
        });
    }

    btnDownloadPdf.addEventListener('click', () => { if (currentJobId) window.open(`/api/translate/download/${currentJobId}/pdf`, '_blank'); });
    btnDownloadRtf.addEventListener('click', () => { if (currentJobId) window.open(`/api/translate/download/${currentJobId}/rtf`, '_blank'); });

    btnPreviewToggle.addEventListener('click', async () => {
        if (previewArea.classList.contains('hidden')) {
            previewArea.classList.remove('hidden');
            btnPreviewToggle.querySelector('span').textContent = 'Hide Preview';
            try {
                const resp = await fetch(`/api/translate/preview/${currentJobId}`);
                const data = await resp.json();
                if (data.translated_text) {
                    previewContent.innerHTML = typeof marked !== 'undefined' ? marked.parse(data.translated_text) : data.translated_text;
                } else { previewContent.innerHTML = '<p>No content available.</p>'; }
            } catch { previewContent.innerHTML = '<p class="error-msg">Failed to load preview.</p>'; }
        } else {
            previewArea.classList.add('hidden');
            btnPreviewToggle.querySelector('span').textContent = 'Preview Translation';
        }
    });

    btnNewTranslation.addEventListener('click', resetTranslator);
    btnRetry.addEventListener('click', resetTranslator);

    function resetTranslator() {
        if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
        selectedFile = null; currentJobId = null; fileInput.value = '';
        previewArea.classList.add('hidden');
        btnPreviewToggle.querySelector('span').textContent = 'Preview Translation';
        showTranslatorSection('upload');
    }

    function showTranslatorSection(name) {
        const secs = { upload: uploadSection, fileInfo: fileInfoSection, progress: progressSection, completed: completedSection, error: errorSection };
        Object.values(secs).forEach(s => { if (s) s.classList.add('hidden'); });
        const target = secs[name];
        if (target) { target.classList.remove('hidden'); target.classList.remove('fade-in'); void target.offsetWidth; target.classList.add('fade-in'); }
        if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 50);
    }

    function showTranslatorError(msg) { errorMessage.textContent = msg; showTranslatorSection('error'); }


    // ═════════════════════════════════════════════════════════
    //  ORDER SCRUTINY MODULE
    // ═════════════════════════════════════════════════════════

    const btnGenerateScrutiny = document.getElementById('btnGenerateScrutiny');
    const scrutinyUploadSection = document.getElementById('scrutinyUploadSection');
    const scrutinyProgressSection = document.getElementById('scrutinyProgressSection');
    const scrutinyCompletedSection = document.getElementById('scrutinyCompletedSection');
    const scrutinyErrorSection = document.getElementById('scrutinyErrorSection');
    const scrutinyProgressBar = document.getElementById('scrutinyProgressBar');
    const scrutinyProgressPct = document.getElementById('scrutinyProgressPct');
    const scrutinyProgressTitle = document.getElementById('scrutinyProgressTitle');
    const scrutinyProgressDetail = document.getElementById('scrutinyProgressDetail');
    const scrutinyErrorMessage = document.getElementById('scrutinyErrorMessage');
    const intimPasswordInput = document.getElementById('intimPassword');

    // File upload handlers for each card
    function setupScrutinyCard(prefix) {
        const dropzone = document.getElementById(prefix + 'Dropzone');
        const input = document.getElementById(prefix + 'FileInput');
        const display = document.getElementById(prefix + 'FileDisplay');
        const nameEl = document.getElementById(prefix + 'FileName');
        const removeBtn = document.getElementById(prefix + 'Remove');

        dropzone.addEventListener('click', () => input.click());
        input.addEventListener('change', (e) => {
            if (e.target.files.length > 0) setScrutinyFile(prefix, e.target.files[0]);
        });
        dropzone.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); dropzone.classList.add('drag-over'); });
        dropzone.addEventListener('dragleave', (e) => { e.preventDefault(); e.stopPropagation(); dropzone.classList.remove('drag-over'); });
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault(); e.stopPropagation(); dropzone.classList.remove('drag-over');
            if (e.dataTransfer.files.length > 0) setScrutinyFile(prefix, e.dataTransfer.files[0]);
        });

        removeBtn.addEventListener('click', () => {
            scrutinyFiles[prefix] = null;
            input.value = '';
            dropzone.classList.remove('hidden');
            display.classList.add('hidden');
            updateScrutinyButton();
            if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 50);
        });
    }

    function setScrutinyFile(prefix, file) {
        if (!file.name.toLowerCase().endsWith('.pdf')) { alert('Please select a PDF file.'); return; }
        scrutinyFiles[prefix] = file;
        const dropzone = document.getElementById(prefix + 'Dropzone');
        const display = document.getElementById(prefix + 'FileDisplay');
        const nameEl = document.getElementById(prefix + 'FileName');
        dropzone.classList.add('hidden');
        display.classList.remove('hidden');
        nameEl.textContent = file.name;
        updateScrutinyButton();
        if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 50);
    }

    setupScrutinyCard('comp');
    setupScrutinyCard('intim');
    setupScrutinyCard('ao');

    // Enable/disable generate button
    intimPasswordInput.addEventListener('input', updateScrutinyButton);

    function updateScrutinyButton() {
        const ready = scrutinyFiles.comp && scrutinyFiles.intim && intimPasswordInput.value.trim();
        btnGenerateScrutiny.disabled = !ready;
    }

    // Generate
    btnGenerateScrutiny.addEventListener('click', startScrutiny);

    async function startScrutiny() {
        if (!scrutinyFiles.comp || !scrutinyFiles.intim || !intimPasswordInput.value.trim()) return;

        const formData = new FormData();
        formData.append('computation_sheet', scrutinyFiles.comp);
        formData.append('intimation_order', scrutinyFiles.intim);
        formData.append('intimation_password', intimPasswordInput.value.trim());
        if (scrutinyFiles.ao) formData.append('assessment_order', scrutinyFiles.ao);

        showScrutinySection('progress');
        updateScrutinyProgress('uploading', 'Uploading documents…', 0);

        try {
            const resp = await fetch('/api/scrutiny', { method: 'POST', body: formData });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'Failed to start scrutiny.');
            scrutinyJobId = data.job_id;
            startScrutinyPolling();
        } catch (err) { showScrutinyError(err.message); }
    }

    function startScrutinyPolling() {
        if (scrutinyPollInterval) clearInterval(scrutinyPollInterval);
        scrutinyPollInterval = setInterval(async () => {
            try {
                const resp = await fetch(`/api/scrutiny/status/${scrutinyJobId}`);
                const data = await resp.json();
                if (data.status === 'processing') {
                    updateScrutinyProgress(data.stage, data.detail, data.progress);
                } else if (data.status === 'completed') {
                    clearInterval(scrutinyPollInterval); scrutinyPollInterval = null;
                    showScrutinySection('completed');
                } else if (data.status === 'failed') {
                    clearInterval(scrutinyPollInterval); scrutinyPollInterval = null;
                    showScrutinyError(data.error || data.detail);
                }
            } catch (err) { console.error('Scrutiny poll error:', err); }
        }, 2000);
    }

    function updateScrutinyProgress(stage, detail, progress) {
        scrutinyProgressBar.style.width = `${progress}%`;
        scrutinyProgressPct.textContent = `${Math.round(progress)}%`;
        scrutinyProgressDetail.textContent = detail;
        const titles = { uploading: 'Uploading Documents…', extracting: 'Extracting Data from PDFs…', generating: 'Generating Excel…' };
        scrutinyProgressTitle.textContent = titles[stage] || 'Processing…';

        // Update stage indicators
        const stgs = scrutinyProgressSection.querySelectorAll('.stage');
        const sOrder = ['uploading', 'extracting', 'generating'];
        const idx = sOrder.indexOf(stage);
        stgs.forEach((s, i) => {
            s.classList.remove('active', 'completed');
            if (i < idx) s.classList.add('completed');
            else if (i === idx) s.classList.add('active');
        });
        const conns = scrutinyProgressSection.querySelectorAll('.stage-connector');
        conns.forEach((c, i) => c.classList.toggle('active', i < idx));
    }

    // Download Excel
    document.getElementById('btnDownloadExcel').addEventListener('click', () => {
        if (scrutinyJobId) window.open(`/api/scrutiny/download/${scrutinyJobId}`, '_blank');
    });

    // New scrutiny / retry
    document.getElementById('btnNewScrutiny').addEventListener('click', resetScrutiny);
    document.getElementById('btnScrutinyRetry').addEventListener('click', resetScrutiny);

    function resetScrutiny() {
        if (scrutinyPollInterval) { clearInterval(scrutinyPollInterval); scrutinyPollInterval = null; }
        scrutinyFiles = { comp: null, intim: null, ao: null };
        scrutinyJobId = null;
        intimPasswordInput.value = '';
        ['comp', 'intim', 'ao'].forEach(prefix => {
            document.getElementById(prefix + 'FileInput').value = '';
            document.getElementById(prefix + 'Dropzone').classList.remove('hidden');
            document.getElementById(prefix + 'FileDisplay').classList.add('hidden');
        });
        updateScrutinyButton();
        showScrutinySection('upload');
    }

    function showScrutinySection(name) {
        const secs = {
            upload: scrutinyUploadSection,
            progress: scrutinyProgressSection,
            completed: scrutinyCompletedSection,
            error: scrutinyErrorSection,
        };
        Object.values(secs).forEach(s => { if (s) s.classList.add('hidden'); });
        const target = secs[name];
        if (target) { target.classList.remove('hidden'); target.classList.remove('fade-in'); void target.offsetWidth; target.classList.add('fade-in'); }
        if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 50);
    }

    function showScrutinyError(msg) { scrutinyErrorMessage.textContent = msg; showScrutinySection('error'); }


    // ═════════════════════════════════════════════════════════
    //  NOTICE REPLY MODULE
    // ═════════════════════════════════════════════════════════

    let noticeFile = null;
    let noticeJobId = null;
    let noticePollInterval = null;

    const noticeUploadZone = document.getElementById('noticeUploadZone');
    const noticeFileInput = document.getElementById('noticeFileInput');
    const noticeUploadSection = document.getElementById('noticeUploadSection');
    const noticeFileInfoSection = document.getElementById('noticeFileInfoSection');
    const noticeProgressSection = document.getElementById('noticeProgressSection');
    const noticeCompletedSection = document.getElementById('noticeCompletedSection');
    const noticeErrorSection = document.getElementById('noticeErrorSection');
    const noticeFileName = document.getElementById('noticeFileName');
    const noticeFileSize = document.getElementById('noticeFileSize');
    const noticeProgressBar = document.getElementById('noticeProgressBar');
    const noticeProgressPct = document.getElementById('noticeProgressPct');
    const noticeProgressTitle = document.getElementById('noticeProgressTitle');
    const noticeProgressDetail = document.getElementById('noticeProgressDetail');
    const noticeErrorMessage = document.getElementById('noticeErrorMessage');
    const emailPreviewArea = document.getElementById('emailPreviewArea');
    const emailPreviewContent = document.getElementById('emailPreviewContent');

    // Upload handlers
    noticeUploadZone.addEventListener('click', () => noticeFileInput.click());
    noticeFileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleNoticeFileSelect(e.target.files[0]);
    });
    noticeUploadZone.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); noticeUploadZone.classList.add('drag-over'); });
    noticeUploadZone.addEventListener('dragleave', (e) => { e.preventDefault(); e.stopPropagation(); noticeUploadZone.classList.remove('drag-over'); });
    noticeUploadZone.addEventListener('drop', (e) => {
        e.preventDefault(); e.stopPropagation(); noticeUploadZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) handleNoticeFileSelect(e.dataTransfer.files[0]);
    });

    function handleNoticeFileSelect(file) {
        if (!file.name.toLowerCase().endsWith('.pdf')) { showNoticeError('Please select a PDF file.'); return; }
        if (file.size > 200 * 1024 * 1024) { showNoticeError('File too large. Max 200 MB.'); return; }
        noticeFile = file;
        noticeFileName.textContent = file.name;
        noticeFileSize.textContent = formatFileSize(file.size);
        showNoticeSection('fileInfo');
    }

    document.getElementById('btnRemoveNotice').addEventListener('click', () => {
        noticeFile = null; noticeFileInput.value = ''; showNoticeSection('upload');
    });

    document.getElementById('btnGenerateReply').addEventListener('click', startNoticeReply);

    async function startNoticeReply() {
        if (!noticeFile) return;
        const formData = new FormData();
        formData.append('notice_pdf', noticeFile);
        showNoticeSection('progress');
        updateNoticeProgress('uploading', 'Uploading notice…', 0);
        try {
            const resp = await fetch('/api/notice-reply', { method: 'POST', body: formData });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'Failed to start.');
            noticeJobId = data.job_id;
            startNoticePolling();
        } catch (err) { showNoticeError(err.message); }
    }

    function startNoticePolling() {
        if (noticePollInterval) clearInterval(noticePollInterval);
        noticePollInterval = setInterval(async () => {
            try {
                const resp = await fetch(`/api/notice-reply/status/${noticeJobId}`);
                const data = await resp.json();
                if (data.status === 'processing') {
                    updateNoticeProgress(data.stage, data.detail, data.progress);
                } else if (data.status === 'completed') {
                    clearInterval(noticePollInterval); noticePollInterval = null;
                    showNoticeSection('completed');
                    loadEmailMessage();
                } else if (data.status === 'failed') {
                    clearInterval(noticePollInterval); noticePollInterval = null;
                    showNoticeError(data.error || data.detail);
                }
            } catch (err) { console.error('Notice poll error:', err); }
        }, 2000);
    }

    function updateNoticeProgress(stage, detail, progress) {
        noticeProgressBar.style.width = `${progress}%`;
        noticeProgressPct.textContent = `${Math.round(progress)}%`;
        noticeProgressDetail.textContent = detail;
        const titles = { uploading: 'Uploading…', extracting: 'Reading Notice…', analyzing: 'Analyzing with AI…', generating: 'Generating Files…' };
        noticeProgressTitle.textContent = titles[stage] || 'Processing…';
        const stgs = noticeProgressSection.querySelectorAll('.stage');
        const sOrder = ['uploading', 'analyzing', 'generating'];
        const idx = sOrder.indexOf(stage);
        stgs.forEach((s, i) => {
            s.classList.remove('active', 'completed');
            if (i < idx) s.classList.add('completed');
            else if (i === idx) s.classList.add('active');
        });
    }

    async function loadEmailMessage() {
        try {
            const resp = await fetch(`/api/notice-reply/email/${noticeJobId}`);
            const data = await resp.json();
            emailPreviewContent.textContent = data.email_text || '';
        } catch { emailPreviewContent.textContent = 'Failed to load email message.'; }
    }

    // Downloads
    document.getElementById('btnDownloadReplyDocx').addEventListener('click', () => {
        if (noticeJobId) window.open(`/api/notice-reply/download/${noticeJobId}/docx`, '_blank');
    });
    document.getElementById('btnDownloadDetailsXlsx').addEventListener('click', () => {
        if (noticeJobId) window.open(`/api/notice-reply/download/${noticeJobId}/xlsx`, '_blank');
    });

    // Email toggle & copy
    document.getElementById('btnEmailToggle').addEventListener('click', () => {
        if (emailPreviewArea.classList.contains('hidden')) {
            emailPreviewArea.classList.remove('hidden');
            document.getElementById('btnEmailToggle').querySelector('span').textContent = 'Hide Client Email Message';
        } else {
            emailPreviewArea.classList.add('hidden');
            document.getElementById('btnEmailToggle').querySelector('span').textContent = 'Show Client Email Message';
        }
    });

    document.getElementById('btnCopyEmail').addEventListener('click', async () => {
        const text = emailPreviewContent.textContent;
        try {
            await navigator.clipboard.writeText(text);
            const btn = document.getElementById('btnCopyEmail');
            btn.querySelector('span').textContent = 'Copied!';
            setTimeout(() => { btn.querySelector('span').textContent = 'Copy'; }, 2000);
        } catch { /* fallback */ }
    });

    // Reset / retry
    document.getElementById('btnNewNoticeReply').addEventListener('click', resetNotice);
    document.getElementById('btnNoticeRetry').addEventListener('click', resetNotice);

    function resetNotice() {
        if (noticePollInterval) { clearInterval(noticePollInterval); noticePollInterval = null; }
        noticeFile = null; noticeJobId = null; noticeFileInput.value = '';
        emailPreviewArea.classList.add('hidden');
        document.getElementById('btnEmailToggle').querySelector('span').textContent = 'Show Client Email Message';
        showNoticeSection('upload');
    }

    function showNoticeSection(name) {
        const secs = { upload: noticeUploadSection, fileInfo: noticeFileInfoSection, progress: noticeProgressSection, completed: noticeCompletedSection, error: noticeErrorSection };
        Object.values(secs).forEach(s => { if (s) s.classList.add('hidden'); });
        const target = secs[name];
        if (target) { target.classList.remove('hidden'); target.classList.remove('fade-in'); void target.offsetWidth; target.classList.add('fade-in'); }
        if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 50);
    }

    function showNoticeError(msg) { noticeErrorMessage.textContent = msg; showNoticeSection('error'); }


    // ── Utilities ───────────────────────────────────────────
    function formatFileSize(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
});
