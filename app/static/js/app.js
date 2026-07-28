/**
 * KCM AI Suite — Frontend Application Logic
 * Handles module switching, file uploads, translation pipeline,
 * order scrutiny pipeline, progress polling, and downloads.
 */

document.addEventListener('DOMContentLoaded', () => {
    if (typeof lucide !== 'undefined') lucide.createIcons();

    // Helper for robust pywebview downloads
    async function downloadFile(url) {
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error("Download failed");
            const disposition = response.headers.get('content-disposition');
            let filename = "download";
            if (disposition && disposition.indexOf('attachment') !== -1) {
                const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(disposition);
                if (matches != null && matches[1]) filename = matches[1].replace(/['"]/g, '');
            }
            const blob = await response.blob();
            const blobUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = blobUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
                window.URL.revokeObjectURL(blobUrl);
                a.remove();
            }, 100);
        } catch (e) {
            console.error("Download error:", e);
            alert("Failed to download file.");
        }
    }

    // ── State ───────────────────────────────────────────────
    let selectedFile = null;
    let currentJobId = null;
    let pollInterval = null;
    let activeModule = 'landing';

    // Scrutiny state
    let scrutinyFiles = { comp: null, intim: null, ao: null, cita: null, cita_comp: null };
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
        
        // Toggle landing layout
        document.body.classList.toggle('is-landing', mod === 'landing');
        
        // Only check API status for modules that need it (not landing)
        if (mod !== 'landing') {
            checkApiStatus();
        }
    }

    // Home / Logo click
    const navHome = document.getElementById('nav-home');
    if (navHome) {
        navHome.addEventListener('click', (e) => {
            e.preventDefault();
            switchModule('landing');
        });
    }

    // Landing grid cards click
    const landingCards = document.querySelectorAll('.landing-card');
    landingCards.forEach(card => {
        card.addEventListener('click', (e) => {
            e.preventDefault();
            const target = card.dataset.target;
            if (target) switchModule(target);
        });
    });

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

    const btnPrintTranslation = document.getElementById('btnPrintTranslation');
    const btnPreviewToggle = document.getElementById('btnPreviewToggle');
    const previewArea = document.getElementById('previewArea');
    const previewContent = document.getElementById('previewContent');
    const btnNewTranslation = document.getElementById('btnNewTranslation');
    const btnRetry = document.getElementById('btnRetry');
    const errorMessage = document.getElementById('errorMessage');

    const stages = {
        uploading: document.getElementById('stageUpload'),
        translating: document.getElementById('stageTranslate'),
        generating: document.getElementById('stageGenerate'),
    };
    const stageOrder = ['uploading', 'translating', 'generating'];

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
        const titles = { uploading: 'Uploading…', translating: 'Translating…', generating: 'Generating…' };
        progressTitle.textContent = titles[stage] || 'Processing…';
        const currentIdx = stageOrder.indexOf(stage);
        stageOrder.forEach((s, idx) => {
            const el = stages[s]; if (!el) return;
            el.classList.remove('active', 'completed');
            if (idx < currentIdx) el.classList.add('completed');
            else if (idx === currentIdx) el.classList.add('active');
        });
    }


    btnPrintTranslation.addEventListener('click', async () => {
        if (!currentJobId) return;
        
        // Ensure preview is loaded and visible
        if (previewArea.classList.contains('hidden')) {
            previewArea.classList.remove('hidden');
            btnPreviewToggle.querySelector('span').textContent = 'Hide Preview';
            try {
                const resp = await fetch(`/api/translate/preview/${currentJobId}`);
                const data = await resp.json();
                if (data.translated_text) {
                    previewContent.innerHTML = data.translated_text;
                }
            } catch (e) {
                console.error(e);
            }
        }
        
        // Handle Orientation dynamically
        const orientation = document.getElementById('printOrientation').value;
        let styleTag = document.getElementById('dynamic-print-style');
        if (!styleTag) {
            styleTag = document.createElement('style');
            styleTag.id = 'dynamic-print-style';
            document.head.appendChild(styleTag);
        }
        
        if (orientation === 'landscape') {
            styleTag.innerHTML = '@media print { @page { size: landscape; margin: 10mm; } }';
        } else {
            styleTag.innerHTML = '@media print { @page { size: portrait; margin: 10mm; } }';
        }
        
        // Slight delay to allow preview rendering before printing
        setTimeout(() => {
            window.print();
        }, 150);
    });

    btnPreviewToggle.addEventListener('click', async () => {
        if (previewArea.classList.contains('hidden')) {
            previewArea.classList.remove('hidden');
            btnPreviewToggle.querySelector('span').textContent = 'Hide Preview';
            try {
                const resp = await fetch(`/api/translate/preview/${currentJobId}`);
                const data = await resp.json();
                if (data.translated_text) {
                    // Inject HTML directly, bypassing marked.js
                    previewContent.innerHTML = data.translated_text;
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
    setupScrutinyCard('cita');
    setupScrutinyCard('citaComp');

    // Enable/disable generate button — comp, intim, ao, and password are all required
    intimPasswordInput.addEventListener('input', updateScrutinyButton);

    function updateScrutinyButton() {
        const ready = scrutinyFiles.comp && scrutinyFiles.intim && scrutinyFiles.ao;
        btnGenerateScrutiny.disabled = !ready;
    }

    // Generate
    btnGenerateScrutiny.addEventListener('click', startScrutiny);

    async function startScrutiny() {
        if (!scrutinyFiles.comp || !scrutinyFiles.intim || !scrutinyFiles.ao) return;

        const formData = new FormData();
        formData.append('computation_sheet', scrutinyFiles.comp);
        formData.append('intimation_order', scrutinyFiles.intim);
        formData.append('intimation_password', intimPasswordInput.value.trim());
        formData.append('assessment_order', scrutinyFiles.ao);
        if (scrutinyFiles.cita) formData.append('cita_order', scrutinyFiles.cita);
        if (scrutinyFiles.citaComp) formData.append('cita_comp_sheet', scrutinyFiles.citaComp);

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
        if (scrutinyJobId) downloadFile(`/api/scrutiny/download/${scrutinyJobId}`);
    });

    // New scrutiny / retry
    document.getElementById('btnNewScrutiny').addEventListener('click', resetScrutiny);
    document.getElementById('btnScrutinyRetry').addEventListener('click', resetScrutiny);

    function resetScrutiny() {
        if (scrutinyPollInterval) { clearInterval(scrutinyPollInterval); scrutinyPollInterval = null; }
        scrutinyFiles = { comp: null, intim: null, ao: null, cita: null, citaComp: null };
        scrutinyJobId = null;
        intimPasswordInput.value = '';
        ['comp', 'intim', 'ao', 'cita', 'citaComp'].forEach(prefix => {
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

    // ── Bulk Upload Mode ─────────────────────────────────────

    const modeIndividual = document.getElementById('modeIndividual');
    const modeBulk = document.getElementById('modeBulk');
    const individualUploadMode = document.getElementById('individualUploadMode');
    const bulkUploadMode = document.getElementById('bulkUploadMode');
    const bulkDropzone = document.getElementById('bulkDropzone');
    const bulkFileInput = document.getElementById('bulkFileInput');
    const bulkClassifying = document.getElementById('bulkClassifying');
    const bulkReview = document.getElementById('bulkReview');
    const bulkReviewBody = document.getElementById('bulkReviewBody');
    const bulkValidation = document.getElementById('bulkValidation');
    const btnBulkGenerate = document.getElementById('btnBulkGenerate');
    const btnBulkReset = document.getElementById('btnBulkReset');
    const bulkIntimPassword = document.getElementById('bulkIntimPassword');

    let bulkClassifiedFiles = []; // Array of {filename, saved_path, type, label, confidence, date}

    // Mode toggle
    [modeIndividual, modeBulk].forEach(btn => {
        btn.addEventListener('click', () => {
            const mode = btn.dataset.mode;
            modeIndividual.classList.toggle('active', mode === 'individual');
            modeBulk.classList.toggle('active', mode === 'bulk');
            individualUploadMode.classList.toggle('hidden', mode === 'bulk');
            bulkUploadMode.classList.toggle('hidden', mode === 'individual');
            if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 50);
        });
    });

    // Bulk drop zone events
    bulkDropzone.addEventListener('click', () => bulkFileInput.click());
    bulkFileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleBulkFiles(e.target.files);
    });
    bulkDropzone.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); bulkDropzone.classList.add('drag-over'); });
    bulkDropzone.addEventListener('dragleave', (e) => { e.preventDefault(); e.stopPropagation(); bulkDropzone.classList.remove('drag-over'); });
    bulkDropzone.addEventListener('drop', (e) => {
        e.preventDefault(); e.stopPropagation(); bulkDropzone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) handleBulkFiles(e.dataTransfer.files);
    });

    async function handleBulkFiles(fileList) {
        const pdfFiles = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith('.pdf'));
        if (pdfFiles.length === 0) { alert('No PDF files found. Please select PDF documents.'); return; }

        // Show classifying state
        bulkDropzone.classList.add('hidden');
        bulkClassifying.classList.remove('hidden');
        bulkReview.classList.add('hidden');

        // Upload files for classification
        const formData = new FormData();
        pdfFiles.forEach(f => formData.append('files', f));

        try {
            const resp = await fetch('/api/scrutiny/classify', { method: 'POST', body: formData });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'Classification failed.');

            bulkClassifiedFiles = data.files;
            renderBulkReview();
        } catch (err) {
            alert('Classification error: ' + err.message);
            resetBulkUpload();
        }
    }

    const DOC_TYPE_OPTIONS = [
        { value: '', label: '— Skip (not needed) —' },
        { value: 'computation_sheet', label: 'Computation Sheet' },
        { value: 'intimation_order', label: 'Intimation Order / ITR' },
        { value: 'assessment_order', label: 'Assessment Order' },
        { value: 'cita_order', label: 'CIT(A) Order u/s 250' },
        { value: 'cita_comp_sheet', label: 'CIT(A) Computation Sheet' },
    ];

    function renderBulkReview() {
        bulkClassifying.classList.add('hidden');
        bulkReview.classList.remove('hidden');
        bulkReviewBody.innerHTML = '';

        bulkClassifiedFiles.forEach((f, idx) => {
            const tr = document.createElement('tr');

            // Filename
            const tdName = document.createElement('td');
            tdName.classList.add('bulk-filename');
            tdName.textContent = f.filename;
            tdName.title = f.filename;
            tr.appendChild(tdName);

            // Type dropdown
            const tdType = document.createElement('td');
            const select = document.createElement('select');
            select.classList.add('bulk-type-select');
            select.dataset.idx = idx;
            DOC_TYPE_OPTIONS.forEach(opt => {
                const option = document.createElement('option');
                option.value = opt.value;
                option.textContent = opt.label;
                if (opt.value === (f.type || '')) option.selected = true;
                select.appendChild(option);
            });
            select.addEventListener('change', (e) => {
                bulkClassifiedFiles[idx].type = e.target.value || null;
                bulkClassifiedFiles[idx].label = e.target.value
                    ? DOC_TYPE_OPTIONS.find(o => o.value === e.target.value)?.label || ''
                    : 'Skipped';
                validateBulkAssignments();
            });
            tdType.appendChild(select);
            tr.appendChild(tdType);

            // Confidence badge
            const tdConf = document.createElement('td');
            const badge = document.createElement('span');
            badge.classList.add('confidence-badge', `confidence-${f.confidence}`);
            const confLabels = { high: '✓ Auto', medium: '~ AI', low: '? Guess', none: '✗ Unknown' };
            badge.textContent = confLabels[f.confidence] || f.confidence;
            tdConf.appendChild(badge);
            tr.appendChild(tdConf);

            // Date
            const tdDate = document.createElement('td');
            tdDate.classList.add('bulk-date');
            tdDate.textContent = f.date || '—';
            tr.appendChild(tdDate);

            // Remove button
            const tdRemove = document.createElement('td');
            const removeBtn = document.createElement('button');
            removeBtn.classList.add('suc-remove');
            removeBtn.title = 'Remove file';
            removeBtn.innerHTML = '<i data-lucide="x"></i>';
            removeBtn.addEventListener('click', () => {
                bulkClassifiedFiles.splice(idx, 1);
                if (bulkClassifiedFiles.length === 0) {
                    resetBulkUpload();
                } else {
                    renderBulkReview();
                }
            });
            tdRemove.appendChild(removeBtn);
            tr.appendChild(tdRemove);

            bulkReviewBody.appendChild(tr);
        });

        if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 50);
        validateBulkAssignments();
    }

    function validateBulkAssignments() {
        const types = bulkClassifiedFiles.map(f => f.type).filter(Boolean);
        const missing = [];
        if (!types.includes('computation_sheet')) missing.push('Computation Sheet');
        if (!types.includes('intimation_order')) missing.push('Intimation Order / ITR');
        if (!types.includes('assessment_order')) missing.push('Assessment Order');

        // Check for duplicates
        const dupes = [];
        const typeCounts = {};
        types.forEach(t => { typeCounts[t] = (typeCounts[t] || 0) + 1; });
        Object.entries(typeCounts).forEach(([t, count]) => {
            if (count > 1) {
                const label = DOC_TYPE_OPTIONS.find(o => o.value === t)?.label || t;
                dupes.push(label);
            }
        });

        let html = '';
        if (missing.length > 0) {
            html += `<div class="validation-warning"><i data-lucide="alert-circle"></i> Missing required: <strong>${missing.join(', ')}</strong></div>`;
        }
        if (dupes.length > 0) {
            html += `<div class="validation-warning"><i data-lucide="alert-triangle"></i> Duplicate type: <strong>${dupes.join(', ')}</strong> — please reassign one</div>`;
        }
        if (missing.length === 0 && dupes.length === 0) {
            html = `<div class="validation-ok"><i data-lucide="check-circle-2"></i> All required documents identified</div>`;
        }
        bulkValidation.innerHTML = html;
        if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 50);

        btnBulkGenerate.disabled = missing.length > 0 || dupes.length > 0;
    }

    function resetBulkUpload() {
        bulkClassifiedFiles = [];
        bulkFileInput.value = '';
        bulkDropzone.classList.remove('hidden');
        bulkClassifying.classList.add('hidden');
        bulkReview.classList.add('hidden');
        bulkReviewBody.innerHTML = '';
        bulkValidation.innerHTML = '';
        bulkIntimPassword.value = '';
        btnBulkGenerate.disabled = true;
        if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 50);
    }

    btnBulkReset.addEventListener('click', resetBulkUpload);

    // Bulk Generate
    btnBulkGenerate.addEventListener('click', async () => {
        const assignments = bulkClassifiedFiles
            .filter(f => f.type)
            .map(f => ({ saved_path: f.saved_path, type: f.type }));

        const formData = new FormData();
        formData.append('mode', 'bulk');
        formData.append('assignments', JSON.stringify(assignments));
        formData.append('intimation_password', bulkIntimPassword.value.trim());

        showScrutinySection('progress');
        updateScrutinyProgress('uploading', 'Starting Order Scrutiny…', 0);

        try {
            const resp = await fetch('/api/scrutiny', { method: 'POST', body: formData });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'Failed to start scrutiny.');
            scrutinyJobId = data.job_id;
            startScrutinyPolling();
        } catch (err) { showScrutinyError(err.message); }
    });

    // Override resetScrutiny to also reset bulk state
    const _origResetScrutiny = resetScrutiny;
    function resetScrutinyFull() {
        _origResetScrutiny();
        resetBulkUpload();
    }
    document.getElementById('btnNewScrutiny').removeEventListener('click', resetScrutiny);
    document.getElementById('btnScrutinyRetry').removeEventListener('click', resetScrutiny);
    document.getElementById('btnNewScrutiny').addEventListener('click', resetScrutinyFull);
    document.getElementById('btnScrutinyRetry').addEventListener('click', resetScrutinyFull);


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

    document.getElementById('btnDownloadReplyDocx').addEventListener('click', () => {
        if (noticeJobId) downloadFile(`/api/notice-reply/download/${noticeJobId}/docx`);
    });
    document.getElementById('btnDownloadDetailsXlsx').addEventListener('click', () => {
        if (noticeJobId) downloadFile(`/api/notice-reply/download/${noticeJobId}/xlsx`);
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

    // ═════════════════════════════════════════════════════════
    //  CASE LAW FINDER MODULE
    // ═════════════════════════════════════════════════════════

    const caselawScenario = document.getElementById('caselawScenario');
    const caselawCourtFilter = document.getElementById('caselawCourtFilter');
    const btnSearchCaselaw = document.getElementById('btnSearchCaselaw');
    const caselawSearchSection = document.getElementById('caselawSearchSection');
    const caselawLoadingSection = document.getElementById('caselawLoadingSection');
    const caselawResultsSection = document.getElementById('caselawResultsSection');
    const caselawNoResultsSection = document.getElementById('caselawNoResultsSection');
    const caselawErrorSection = document.getElementById('caselawErrorSection');
    const caselawResultsSummary = document.getElementById('caselawResultsSummary');
    const caselawResultsList = document.getElementById('caselawResultsList');
    const caselawNoResultsReason = document.getElementById('caselawNoResultsReason');
    const caselawErrorMessage = document.getElementById('caselawErrorMessage');
    const btnNewCaselawSearch = document.getElementById('btnNewCaselawSearch');
    const btnRetryCaselaw = document.getElementById('btnRetryCaselaw');
    const btnCaselawErrorRetry = document.getElementById('btnCaselawErrorRetry');
    const caselawLoadingTitle = document.getElementById('caselawLoadingTitle');
    const caselawLoadingDesc = document.getElementById('caselawLoadingDesc');

    // File attachment elements
    const caselawAttachZone = document.getElementById('caselawAttachZone');
    const caselawFileInput = document.getElementById('caselawFileInput');
    const caselawAttachedFiles = document.getElementById('caselawAttachedFiles');
    let caselawFiles = []; // Array of File objects

    // File attachment — click to browse
    if (caselawAttachZone && caselawFileInput) {
        caselawAttachZone.addEventListener('click', () => caselawFileInput.click());
        caselawFileInput.addEventListener('change', (e) => {
            addCaselawFiles(Array.from(e.target.files));
            caselawFileInput.value = '';
        });

        // Drag & drop
        caselawAttachZone.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); caselawAttachZone.classList.add('drag-over'); });
        caselawAttachZone.addEventListener('dragleave', (e) => { e.preventDefault(); e.stopPropagation(); caselawAttachZone.classList.remove('drag-over'); });
        caselawAttachZone.addEventListener('drop', (e) => {
            e.preventDefault(); e.stopPropagation();
            caselawAttachZone.classList.remove('drag-over');
            addCaselawFiles(Array.from(e.dataTransfer.files));
        });
    }

    function addCaselawFiles(newFiles) {
        const allowed = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.jpg', '.jpeg', '.png'];
        for (const f of newFiles) {
            const ext = '.' + f.name.split('.').pop().toLowerCase();
            if (allowed.includes(ext) && !caselawFiles.find(ef => ef.name === f.name && ef.size === f.size)) {
                caselawFiles.push(f);
            }
        }
        renderCaselawFileChips();
    }

    function removeCaselawFile(idx) {
        caselawFiles.splice(idx, 1);
        renderCaselawFileChips();
    }

    function renderCaselawFileChips() {
        if (!caselawAttachedFiles) return;
        caselawAttachedFiles.innerHTML = '';
        caselawFiles.forEach((f, idx) => {
            const chip = document.createElement('div');
            chip.className = 'attached-file-chip';
            chip.innerHTML = `
                <i data-lucide="file-text" style="width:14px;height:14px;"></i>
                <span>${escapeHtml(f.name)}</span>
                <button class="chip-remove" data-idx="${idx}" title="Remove">×</button>
            `;
            chip.querySelector('.chip-remove').addEventListener('click', (e) => {
                e.stopPropagation();
                removeCaselawFile(parseInt(e.target.dataset.idx));
            });
            caselawAttachedFiles.appendChild(chip);
        });
        if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 50);
    }

    function showCaselawSection(which) {
        [caselawSearchSection, caselawLoadingSection, caselawResultsSection,
         caselawNoResultsSection, caselawErrorSection].forEach(s => {
            if (s) s.classList.add('hidden');
        });
        const map = {
            search: caselawSearchSection,
            loading: caselawLoadingSection,
            results: caselawResultsSection,
            noResults: caselawNoResultsSection,
            error: caselawErrorSection,
        };
        if (map[which]) map[which].classList.remove('hidden');
    }

    function resetCaselawUI() {
        showCaselawSection('search');
        if (caselawResultsList) caselawResultsList.innerHTML = '';
    }

    if (btnNewCaselawSearch) btnNewCaselawSearch.addEventListener('click', resetCaselawUI);
    if (btnRetryCaselaw) btnRetryCaselaw.addEventListener('click', resetCaselawUI);
    if (btnCaselawErrorRetry) btnCaselawErrorRetry.addEventListener('click', resetCaselawUI);

    if (btnSearchCaselaw) {
        btnSearchCaselaw.addEventListener('click', async () => {
            const query = caselawScenario ? caselawScenario.value.trim() : '';
            if (!query) {
                alert('Please describe your tax scenario.');
                return;
            }
            if (query.length < 15) {
                alert('Please provide a more detailed scenario description (at least 15 characters).');
                return;
            }

            // Update loading message
            if (caselawLoadingTitle) caselawLoadingTitle.textContent = 'Searching case laws…';
            if (caselawLoadingDesc) caselawLoadingDesc.textContent = 'Searching Indian Kanoon, Taxmann and legal databases for matching precedents…';
            showCaselawSection('loading');

            try {
                // Build FormData for file uploads
                const formData = new FormData();
                formData.append('query', query);
                formData.append('court_filter', caselawCourtFilter ? caselawCourtFilter.value : 'all');
                caselawFiles.forEach(f => formData.append('files', f));

                const resp = await fetch('/api/caselaw/search', {
                    method: 'POST',
                    body: formData,
                });

                const data = await resp.json();

                if (!resp.ok) {
                    throw new Error(data.error || 'Search failed');
                }

                const results = data.results || [];

                if (results.length === 0) {
                    if (caselawNoResultsReason) {
                        caselawNoResultsReason.textContent = data.no_results_reason || 'No case laws with substantially identical facts were found. Try rephrasing your scenario or broadening the court filter.';
                    }
                    showCaselawSection('noResults');
                    return;
                }

                renderCaselawResults(results, data.search_summary);

            } catch (e) {
                if (caselawErrorMessage) caselawErrorMessage.textContent = e.message;
                showCaselawSection('error');
            }
        });
    }

    function renderCaselawResults(results, summary) {
        if (caselawResultsSummary) {
            caselawResultsSummary.textContent = summary || `Found ${results.length} matching precedent${results.length > 1 ? 's' : ''}`;
        }

        if (!caselawResultsList) return;
        caselawResultsList.innerHTML = '';

        results.forEach((r, idx) => {
            const courtClass = getCourtClass(r.court || '');
            const citations = (r.citations || []).filter(c => c && c.trim());
            const citationHtml = citations.map(c => `<span class="citation-tag">${escapeHtml(c)}</span>`).join('');

            // Generate deterministic search links to avoid AI hallucinations and 404s
            const hasTaxmann = citations.some(c => c.toLowerCase().includes('taxmann'));
            
            let sourceUrl = '';
            let sourceLinkLabel = '';
            let isTaxmannLink = false;
            
            if (hasTaxmann) {
                const taxmannCitation = citations.find(c => c.toLowerCase().includes('taxmann'));
                // Use a highly specific Google Search that guarantees a working link to Taxmann
                sourceUrl = `https://www.google.com/search?q=${encodeURIComponent('"' + taxmannCitation + '" site:taxmann.com')}`;
                sourceLinkLabel = 'Search on Taxmann';
                isTaxmannLink = true;
            } else if (r.case_name) {
                // Fallback to Indian Kanoon's robust internal search engine
                sourceUrl = `https://indiankanoon.org/search/?formInput=${encodeURIComponent(r.case_name)}`;
                sourceLinkLabel = 'Search on Indian Kanoon';
            }

            const card = document.createElement('div');
            card.className = 'caselaw-card';
            card.innerHTML = `
                <div class="caselaw-card-header">
                    <div class="caselaw-card-title">
                        <span class="caselaw-index">${idx + 1}</span>
                        <h4>${escapeHtml(r.case_name || 'Unknown Case')}</h4>
                    </div>
                    <div class="caselaw-card-meta">
                        <span class="court-badge ${courtClass}">${escapeHtml(r.court || 'Unknown')}</span>
                        ${r.date ? `<span class="caselaw-date">${escapeHtml(r.date)}</span>` : ''}
                        ${r.section ? `<span class="caselaw-section">§ ${escapeHtml(r.section)}</span>` : ''}
                    </div>
                </div>

                <div class="caselaw-citations">
                    <span class="citations-label">Citations:</span>
                    ${citationHtml || '<span class="citation-tag citation-na">Not available</span>'}
                </div>

                <div class="caselaw-card-body">
                    <div class="caselaw-para">
                        <strong>Facts:</strong>
                        <p>${escapeHtml(r.facts_summary || '—')}</p>
                    </div>
                    <div class="caselaw-para">
                        <strong>Holding:</strong>
                        <p>${escapeHtml(r.holding || '—')}</p>
                    </div>
                </div>

                <div class="caselaw-card-footer">
                    <button class="btn-copy-summary" data-idx="${idx}" title="Copy summary to clipboard">
                        <i data-lucide="copy"></i>
                        <span>Copy Summary</span>
                    </button>
                    ${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener" class="btn-source-link ${isTaxmannLink ? 'btn-taxmann' : ''}">
                        <i data-lucide="external-link"></i>
                        <span>${sourceLinkLabel}</span>
                    </a>` : ''}
                </div>
            `;

            // Copy button handler
            const copyBtn = card.querySelector('.btn-copy-summary');
            if (copyBtn) {
                copyBtn.addEventListener('click', () => {
                    const citationsText = citations.length > 0 ? citations.join('; ') : '';
                    const textToCopy = `${r.case_name || ''}\n${citationsText}\n${r.court || ''} | ${r.date || ''}\n\nFacts: ${r.facts_summary || ''}\n\nHolding: ${r.holding || ''}`;
                    navigator.clipboard.writeText(textToCopy).then(() => {
                        const span = copyBtn.querySelector('span');
                        if (span) {
                            span.textContent = 'Copied!';
                            setTimeout(() => { span.textContent = 'Copy Summary'; }, 2000);
                        }
                    });
                });
            }

            caselawResultsList.appendChild(card);
        });

        if (typeof lucide !== 'undefined') setTimeout(() => lucide.createIcons(), 50);
        showCaselawSection('results');
    }

    function getCourtClass(court) {
        const c = court.toLowerCase();
        if (c.includes('supreme')) return 'court-sc';
        if (c.includes('high')) return 'court-hc';
        if (c.includes('itat') || c.includes('tribunal')) return 'court-itat';
        return 'court-other';
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

});
