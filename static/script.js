document.addEventListener("DOMContentLoaded", () => {
    // Top Controls
    const startBtn = document.getElementById("start-btn");
    const startBtnLabel = document.getElementById("start-btn-label");
    const startBtnIcon = document.getElementById("start-btn-icon");
    const downloadBtn = document.getElementById("download-btn");
    const downloadDocxBtn = document.getElementById("download-docx-btn");
    const clearAllBtn = document.getElementById("clear-all-btn");

    // Stepper & Progress
    const progressTrack = document.getElementById("progress-track");
    const progressBar = document.getElementById("progress-bar");
    const step1 = document.getElementById("step-1");
    const step2 = document.getElementById("step-2");
    const step3 = document.getElementById("step-3");
    const step4 = document.getElementById("step-4");

    // Terminal
    const consoleOutput = document.getElementById("console-output");
    const clearConsoleBtn = document.getElementById("clear-console-btn");
    const autoscrollBtn = document.getElementById("autoscroll-btn");
    let autoScrollEnabled = true;

    // Opportunities & Review
    const jobsBody = document.getElementById("jobs-body");
    const pendingList = document.getElementById("pending-list");
    const pendingCountBadge = document.getElementById("pending-count-badge");
    const pipelineBadge = document.getElementById("pipeline-status-badge");
    const pipelineDot = document.getElementById("pipeline-status-dot");
    const mongoBadge = document.getElementById("mongo-status-badge");
    const mongoDot = document.getElementById("mongo-status-dot");
    const sourcesGrid = document.getElementById("sources-grid");

    // Search and Filter controls
    const searchInput = document.getElementById("search-input");
    const filterPills = document.querySelectorAll(".filter-pill");

    // Counts on Filter Pills
    const countFreshEl = document.getElementById("count-fresh");
    const countWorldwideEl = document.getElementById("count-worldwide");
    const countPakistanEl = document.getElementById("count-pakistan");
    const countUSEl = document.getElementById("count-us");
    const countAtsEl = document.getElementById("count-ats");
    const countHighEl = document.getElementById("count-high");
    const countAllEl = document.getElementById("count-all");
    const countAppliedEl = document.getElementById("count-applied");

    // Presets
    const presetAll = document.getElementById("preset-all");
    const presetFast = document.getElementById("preset-fast");
    const presetJobspy = document.getElementById("preset-jobspy");
    const presetRss = document.getElementById("preset-rss");
    const btnSelectAll = document.getElementById("btn-select-all");
    const btnDeselectAll = document.getElementById("btn-deselect-all");

    // Metrics elements
    const metricScraped = document.getElementById("metric-scraped");
    const metricMatched = document.getElementById("metric-matched");
    const metricPending = document.getElementById("metric-pending");
    const metricApplied = document.getElementById("metric-applied");

    let totalScrapedCount = 0;
    let matchedJobsList = [];
    let appliedJobsList = [];
    let pendingJobs = {};
    let activeFilter = "fresh";
    let searchTerm = "";

    // Candidate CV Reference for Inspector / Verification
    const candidateCV = `Candidate: Ibrahim Hamid
Profile: Junior AI Engineer & Full-Stack Developer (2026 CS Graduate)
Core Skills: Python (FastAPI), React, Next.js, Node.js, LangChain, RAG, MongoDB Atlas, LLM Integration
Eligibility: Worldwide Remote / Work from Anywhere / Pakistan Eligible
Target Pay: $15 - $60/hr or equivalent USD annual ($35k - $90k)
Target Experience: 0 - 2 years (Entry / Junior / Associate)`;

    document.getElementById("modal-candidate-cv").textContent = candidateCV;

    // =========================================================================
    // MongoDB & Initial State Handlers
    // =========================================================================
    function updateMongoBadge(isConnected) {
        if (isConnected) {
            mongoBadge.textContent = "MongoDB: Connected";
            mongoDot.className = "pill-dot dot-green";
        } else {
            mongoBadge.textContent = "MongoDB: Offline (In-Memory)";
            mongoDot.className = "pill-dot dot-amber";
        }
    }

    function setPipelineStatus(statusText, type = "idle") {
        pipelineBadge.textContent = statusText;
        if (type === "running") {
            pipelineDot.className = "pill-dot dot-blue";
        } else if (type === "complete") {
            pipelineDot.className = "pill-dot dot-green";
        } else if (type === "error") {
            pipelineDot.className = "pill-dot dot-amber";
        } else {
            pipelineDot.className = "pill-dot dot-cyan";
        }
    }

    function disableDownloads() {
        if (downloadBtn) {
            downloadBtn.classList.add("disabled");
        }
        if (downloadDocxBtn) {
            downloadDocxBtn.classList.add("disabled");
        }
    }

    function enableDownloads() {
        if (downloadBtn) {
            downloadBtn.classList.remove("disabled");
        }
        if (downloadDocxBtn) {
            downloadDocxBtn.classList.remove("disabled");
        }
    }

    disableDownloads();

    // Check DB status and load existing saved jobs on page load
    fetch("/api/jobs/saved")
        .then(res => res.json())
        .then(data => {
            updateMongoBadge(data.mongo_connected);
            if (data.jobs && data.jobs.length > 0) {
                data.jobs.forEach(job => {
                    if (!matchedJobsList.some(j => j.url === job.url)) {
                        matchedJobsList.push(job);
                    }
                });
                matchedJobsList.sort((a, b) => b.match_score - a.match_score);
                renderMatchedJobs();
                enableDownloads();
            }
        })
        .catch(err => console.log("DB check error:", err));

    // Check applied jobs on page load
    fetch("/api/jobs/applied")
        .then(res => res.json())
        .then(data => {
            if (data.jobs && data.jobs.length > 0) {
                data.jobs.forEach(job => {
                    if (!appliedJobsList.some(j => j.url === job.url)) {
                        appliedJobsList.push(job);
                    }
                });
                appliedJobsList.sort((a, b) => b.match_score - a.match_score);
                metricApplied.textContent = appliedJobsList.length;
                updateFilterCounts();
            }
        })
        .catch(err => console.log("Applied check error:", err));

    // =========================================================================
    // Preset & Scraper Lane Selectors
    // =========================================================================
    const sourceCards = document.querySelectorAll(".source-card");

    function syncCardActiveState(card) {
        const cb = card.querySelector(".source-checkbox");
        if (cb.checked) {
            card.classList.add("active");
        } else {
            card.classList.remove("active");
        }
    }

    sourceCards.forEach(card => {
        const cb = card.querySelector(".source-checkbox");
        card.addEventListener("click", (e) => {
            if (e.target !== cb) {
                cb.checked = !cb.checked;
            }
            syncCardActiveState(card);
            clearPresetActive();
        });
        cb.addEventListener("change", () => {
            syncCardActiveState(card);
            clearPresetActive();
        });
    });

    function clearPresetActive() {
        document.querySelectorAll(".preset-pill").forEach(p => p.classList.remove("active"));
    }

    function selectSourcesByCategory(predicate) {
        sourceCards.forEach(card => {
            const cb = card.querySelector(".source-checkbox");
            const shouldCheck = predicate(card);
            cb.checked = shouldCheck;
            syncCardActiveState(card);
        });
    }

    if (presetAll) {
        presetAll.addEventListener("click", () => {
            clearPresetActive();
            presetAll.classList.add("active");
            selectSourcesByCategory(() => true);
        });
    }

    if (presetFast) {
        presetFast.addEventListener("click", () => {
            clearPresetActive();
            presetFast.classList.add("active");
            selectSourcesByCategory(card => card.getAttribute("data-category") === "fast");
        });
    }

    if (presetJobspy) {
        presetJobspy.addEventListener("click", () => {
            clearPresetActive();
            presetJobspy.classList.add("active");
            selectSourcesByCategory(card => card.getAttribute("data-category") === "deep");
        });
    }

    if (presetRss) {
        presetRss.addEventListener("click", () => {
            clearPresetActive();
            presetRss.classList.add("active");
            selectSourcesByCategory(card => card.getAttribute("data-category") === "rss");
        });
    }

    if (btnSelectAll) {
        btnSelectAll.addEventListener("click", () => {
            clearPresetActive();
            if (presetAll) presetAll.classList.add("active");
            selectSourcesByCategory(() => true);
        });
    }

    if (btnDeselectAll) {
        btnDeselectAll.addEventListener("click", () => {
            clearPresetActive();
            selectSourcesByCategory(() => false);
        });
    }

    function getSelectedSources() {
        const selected = [];
        sourceCards.forEach(card => {
            const cb = card.querySelector(".source-checkbox");
            if (cb.checked) {
                selected.push(cb.value);
            }
        });
        return selected;
    }

    // =========================================================================
    // Pipeline Stepper & Progress Handlers
    // =========================================================================
    function setStep(stepNum) {
        [step1, step2, step3, step4].forEach((s, idx) => {
            if (!s) return;
            const num = idx + 1;
            if (num < stepNum) {
                s.className = "step-item done";
            } else if (num === stepNum) {
                s.className = "step-item active";
            } else {
                s.className = "step-item";
            }
        });

        const connectors = document.querySelectorAll(".step-connector");
        connectors.forEach((c, idx) => {
            if (idx + 1 < stepNum) {
                c.classList.add("active");
            } else {
                c.classList.remove("active");
            }
        });
    }

    function resetStepper() {
        setStep(1);
        if (progressTrack) progressTrack.style.display = "none";
        if (progressBar) {
            progressBar.className = "progress-bar-glow";
            progressBar.style.width = "0%";
        }
    }

    function startProgress() {
        if (progressTrack) progressTrack.style.display = "block";
        if (progressBar) {
            progressBar.className = "progress-bar-glow indeterminate";
        }
    }

    function completeProgress() {
        setStep(4);
        if (progressBar) {
            progressBar.className = "progress-bar-glow";
            progressBar.style.width = "100%";
        }
        setTimeout(() => {
            if (progressTrack) progressTrack.style.display = "none";
        }, 1200);
    }

    // =========================================================================
    // Terminal Log & Console Output
    // =========================================================================
    if (autoscrollBtn) {
        autoscrollBtn.addEventListener("click", () => {
            autoScrollEnabled = !autoScrollEnabled;
            autoscrollBtn.textContent = `Auto-Scroll: ${autoScrollEnabled ? "ON" : "OFF"}`;
        });
    }

    if (clearConsoleBtn) {
        clearConsoleBtn.addEventListener("click", () => {
            consoleOutput.innerHTML = '<p class="log-system">> Console cleared.</p>';
        });
    }

    function addLog(message) {
        const p = document.createElement("p");
        
        let cls = "log-line";
        if (message.includes("[SYSTEM]")) cls += " log-system";
        else if (message.includes("[SCRAPER]")) cls += " log-scraper";
        else if (message.includes("[EVALUATOR]")) cls += " log-evaluator";
        else if (message.includes("[MATCH]")) cls += " log-summary";
        else if (message.includes("[DATABASE]")) cls += " log-summary";
        else if (message.includes("[ACTION]")) cls += " log-action";
        else if (message.includes("[ERROR]")) cls += " log-error";
        else if (message.includes("[SUMMARY]") || message.includes("DONE")) cls += " log-summary";
        
        p.className = cls;
        p.textContent = `> ${message}`;
        consoleOutput.appendChild(p);

        if (autoScrollEnabled) {
            consoleOutput.scrollTop = consoleOutput.scrollHeight;
        }
        
        // Progress step detection from logs
        if (message.includes("Phase 1: Multi-Site Data Extraction")) {
            setStep(1);
        } else if (message.includes("deduplication") || message.includes("Total raw jobs collected")) {
            setStep(2);
            const match = message.match(/\d+/);
            if (match) {
                totalScrapedCount = parseInt(match[0]);
                metricScraped.textContent = totalScrapedCount;
            }
        } else if (message.includes("Phase 2: AI Evaluation")) {
            setStep(3);
        } else if (message.includes("Phase 3:") || message.includes("Pipeline finished") || message === "DONE") {
            completeProgress();
        }
    }

    function updateSourceCards(sourceStats) {
        if (!sourceStats) return;
        for (const [name, count] of Object.entries(sourceStats)) {
            sourceCards.forEach(card => {
                const cardSource = card.getAttribute("data-source") || "";
                if (cardSource.toLowerCase().includes(name.toLowerCase()) || name.toLowerCase().includes(cardSource.split(" ")[0].toLowerCase())) {
                    const countSpan = card.querySelector(".source-count");
                    const beacon = card.querySelector(".source-live-beacon");
                    if (countSpan) {
                        countSpan.textContent = `+${count} jobs`;
                        if (count > 0) {
                            countSpan.classList.add("has-jobs");
                        }
                    }
                    if (beacon) {
                        beacon.className = "source-live-beacon beacon-active";
                    }
                    card.classList.remove("is-running");
                }
            });
        }
    }

    // =========================================================================
    // Skills & Stack Extraction
    // =========================================================================
    function extractSkills(fullText) {
        const targetSkills = ["Python", "FastAPI", "React", "Next.js", "Node.js", "LangChain", "RAG", "MongoDB", "LLM", "TypeScript", "PyTorch", "Docker", "PostgreSQL"];
        return targetSkills.filter(skill => 
            new RegExp('\\b' + skill.replace('.', '\\.') + '\\b', 'i').test(fullText)
        );
    }

    // =========================================================================
    // Filter Counts & Rendering
    // =========================================================================
    function isJobUS(j) {
        let r = [];
        try {
            if (typeof j.remote_regions === 'string' && j.remote_regions.startsWith('[')) r = JSON.parse(j.remote_regions);
            else if (Array.isArray(j.remote_regions)) r = j.remote_regions;
        } catch(e) {}
        const loc = (j.location || '').toLowerCase();
        const rem = (j.remote_summary || '').toLowerCase();
        return r.includes("US") || 
            /(\bus\b|\busa\b|united states|san francisco|california|new york|austin|seattle|remote\s*[\(\-]\s*us)/i.test(loc) ||
            /united states/i.test(rem);
    }

    function isJobPak(j) {
        let r = [];
        try {
            if (typeof j.remote_regions === 'string' && j.remote_regions.startsWith('[')) r = JSON.parse(j.remote_regions);
            else if (Array.isArray(j.remote_regions)) r = j.remote_regions;
        } catch(e) {}
        const loc = (j.location || '').toLowerCase();
        return r.includes("Pakistan") || r.includes("Twin Cities") ||
            /(pakistan|islamabad|rawalpindi|lahore|karachi)/i.test(loc);
    }

    function updateFilterCounts() {
        const totalMatched = matchedJobsList.length;
        const totalFresh = matchedJobsList.filter(j => j.is_24h_fresh === true || j.is_24h_fresh === 1).length;
        const totalAts = matchedJobsList.filter(j => (j.source && j.source.startsWith("ats_")) || (j.direct_career_url && j.direct_career_url !== j.url)).length;
        const totalHigh = matchedJobsList.filter(j => j.match_score >= 80).length;
        const totalUS = matchedJobsList.filter(isJobUS).length;
        const totalPak = matchedJobsList.filter(isJobPak).length;
        const totalWorldwide = matchedJobsList.filter(j => !isJobUS(j) && !isJobPak(j)).length;
        const totalApplied = appliedJobsList.length;

        if (countFreshEl) countFreshEl.textContent = totalFresh;
        if (countAtsEl) countAtsEl.textContent = totalAts;
        if (countAllEl) countAllEl.textContent = totalMatched;
        if (countHighEl) countHighEl.textContent = totalHigh;
        if (countWorldwideEl) countWorldwideEl.textContent = totalWorldwide;
        if (countPakistanEl) countPakistanEl.textContent = totalPak;
        if (countUSEl) countUSEl.textContent = totalUS;
        if (countAppliedEl) countAppliedEl.textContent = totalApplied;

        metricMatched.textContent = totalMatched;
        metricApplied.textContent = totalApplied;
    }

    function renderMatchedJobs() {
        jobsBody.innerHTML = "";
        updateFilterCounts();
        
        const listToRender = (activeFilter === "applied") ? appliedJobsList : matchedJobsList;
        
        const filtered = listToRender.filter(job => {
            const query = searchTerm.toLowerCase();
            const matchesSearch = !query || 
                (job.title && job.title.toLowerCase().includes(query)) || 
                (job.company && job.company.toLowerCase().includes(query)) || 
                (job.location && job.location.toLowerCase().includes(query)) || 
                (job.match_reason && job.match_reason.toLowerCase().includes(query)) || 
                (job.description && job.description.toLowerCase().includes(query));
                
            if (!matchesSearch) return false;
            
            if (activeFilter === "fresh") return job.is_24h_fresh === true || job.is_24h_fresh === 1;
            if (activeFilter === "worldwide") return !isJobUS(job) && !isJobPak(job);
            if (activeFilter === "pakistan") return isJobPak(job);
            if (activeFilter === "us") return isJobUS(job);
            if (activeFilter === "ats") return (job.source && job.source.startsWith("ats_")) || (job.direct_career_url && job.direct_career_url !== job.url);
            if (activeFilter === "high") return job.match_score >= 80;
            
            return true;
        });

        if (filtered.length === 0) {
            jobsBody.innerHTML = `
                <tr>
                    <td colspan="5" class="empty-table-state">
                        <div class="empty-table-content">
                            <span class="empty-table-icon">🔍</span>
                            <h3>No opportunities found under "${activeFilter}"</h3>
                            <p>Try switching filter tabs or clearing your search term.</p>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        filtered.forEach(job => {
            const tr = document.createElement("tr");
            
            let scoreClass = 'score-med';
            if (job.match_score >= 80) scoreClass = 'score-high';
            else if (job.match_score < 60) scoreClass = 'score-low';
            
            const skills = extractSkills(`${job.title} ${job.description} ${job.match_reason}`);
            const skillChipsHtml = skills.map(s => {
                const isHighlight = ["Python", "FastAPI", "React", "Next.js", "LangChain", "RAG"].includes(s);
                return `<span class="skill-tag ${isHighlight ? 'highlight' : ''}">${s}</span>`;
            }).join("");
            
            const isAppliedJob = (activeFilter === "applied") || (job.status === "applied") || appliedJobsList.some(j => j.url === job.url);
            const payText = job.estimated_pay && job.estimated_pay !== "Not Disclosed" ? job.estimated_pay : "Not Disclosed";
            const payClass = payText === "Not Disclosed" ? "pay-badge pay-empty" : "pay-badge";

            // Regional Badge Computation
            let regionBadgeHtml = '';
            if (isJobPak(job)) {
                regionBadgeHtml = `<span class="region-badge-pakistan">🇵🇰 Pak & Twin Cities</span>`;
            } else if (isJobUS(job)) {
                regionBadgeHtml = `<span class="region-badge-us">🇺🇸 Remote US Only</span>`;
            } else {
                regionBadgeHtml = `<span class="region-badge-worldwide">🌍 Worldwide Remote</span>`;
            }

            // Matcha Metadata
            const logoDomain = (job.company || 'tech').toLowerCase().replace(/[^a-z0-9]/g, '');
            const logoUrl = job.logo_url || `https://www.google.com/s2/favicons?domain=${logoDomain}.com&sz=64`;
            const isDirectCareer = job.direct_career_url && (job.direct_career_url.includes('?gh_jid') || job.direct_career_url !== job.url);
            const targetApplyUrl = job.direct_career_url || job.url;
            const isFresh = job.is_24h_fresh === true || job.is_24h_fresh === 1;
            const freshBadgeHtml = isFresh ? `<span class="freshness-badge">🔥 <24h Fresh</span>` : '';
            const fundingHtml = job.funding_total ? `<span class="badge-funding">💰 ${job.funding_total}</span>` : '';
            
            let investorsList = [];
            try {
                if (typeof job.key_investors === 'string' && job.key_investors.startsWith('[')) investorsList = JSON.parse(job.key_investors);
                else if (Array.isArray(job.key_investors)) investorsList = job.key_investors;
            } catch(e) {}
            const investorsHtml = investorsList.length > 0 ? `<div class="investors-wrap">${investorsList.slice(0, 3).map(inv => `<span class="investor-pill">${inv}</span>`).join('')}</div>` : '';
            const summaryHtml = job.job_summary ? `<div class="job-summary-preview">${job.job_summary}</div>` : '';

            tr.innerHTML = `
                <td>
                    <div class="score-radial ${scoreClass}">${job.match_score}%</div>
                </td>
                <td>
                    <div class="job-title-cell">
                        <div class="job-title-text">${job.title} ${freshBadgeHtml} ${regionBadgeHtml}</div>
                        ${summaryHtml}
                        <div class="job-tags-row">${skillChipsHtml}</div>
                    </div>
                </td>
                <td>
                    <div class="company-cell-flex">
                        <img src="${logoUrl}" class="company-logo-img" alt="${job.company}" onerror="this.src='https://www.google.com/s2/favicons?domain=google.com&sz=64'">
                        <div class="company-cell">
                            <span class="company-name">${job.company}</span>
                            <span class="source-tag">Board: ${job.source}</span>
                            <span class="location-tag">📍 ${job.remote_summary || job.location || "Remote"}</span>
                            ${fundingHtml}
                            ${investorsHtml}
                        </div>
                    </div>
                </td>
                <td>
                    <span class="${payClass}">${payText}</span>
                </td>
                <td>
                    <div class="actions-cell">
                        <a href="/job/apply-redirect?url=${encodeURIComponent(targetApplyUrl)}" target="_blank" class="btn-action-apply ${isDirectCareer ? 'direct-apply-btn' : ''}" title="${isDirectCareer ? 'Direct Company Career Page' : 'Open employer listing'}">
                            ${isDirectCareer ? 'Direct Apply ↗' : 'Apply ↗'}
                        </a>
                        <button type="button" class="btn-action-inspect inspect-btn" title="Inspect full match breakdown">
                            Inspect
                        </button>
                        <button type="button" class="btn-action-applied row-apply-btn ${isAppliedJob ? 'is-applied' : ''}" title="${isAppliedJob ? 'Already Applied' : 'Mark as Applied'}">
                            ${isAppliedJob ? '✓' : '+'}
                        </button>
                    </div>
                </td>
            `;
            
            const rowApplyBtn = tr.querySelector(".row-apply-btn");
            if (rowApplyBtn) {
                rowApplyBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    markJobAsApplied(job);
                });
            }
            
            const inspectBtn = tr.querySelector(".inspect-btn");
            if (inspectBtn) {
                inspectBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    openJobInspector(job);
                });
            }
            
            jobsBody.appendChild(tr);
        });
    }

    function addJobRow(job) {
        if (!matchedJobsList.some(j => j.url === job.url)) {
            matchedJobsList.push(job);
            matchedJobsList.sort((a, b) => b.match_score - a.match_score);
            renderMatchedJobs();
        }
    }

    // =========================================================================
    // Mark as Applied
    // =========================================================================
    async function markJobAsApplied(job) {
        try {
            const res = await fetch("/api/jobs/apply", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: job.url })
            });
            const data = await res.json();
            if (data.status === "success") {
                job.status = "applied";
                
                matchedJobsList = matchedJobsList.filter(j => j.url !== job.url);
                if (!appliedJobsList.some(j => j.url === job.url)) {
                    appliedJobsList.push(job);
                    appliedJobsList.sort((a, b) => b.match_score - a.match_score);
                }
                
                renderMatchedJobs();
                addLog(`[ACTION] Job marked as Applied: ${job.title} (${job.company})`);
                
                closeJobInspector();
                if (activeVerificationJob && activeVerificationJob.url === job.url) {
                    closeVerificationModal();
                }
            }
        } catch (err) {
            console.error("Mark applied error:", err);
            alert("Failed to mark job as applied.");
        }
    }

    // =========================================================================
    // Pending Borderline Review
    // =========================================================================
    function addPendingJob(job) {
        const emptyState = pendingList.querySelector(".empty-state");
        if (emptyState) {
            pendingList.innerHTML = "";
        }
        
        pendingJobs[job.url] = job;
        const pendingCount = Object.keys(pendingJobs).length;
        metricPending.textContent = pendingCount;
        if (pendingCountBadge) pendingCountBadge.textContent = pendingCount;
        
        const div = document.createElement("div");
        div.className = "pending-item";
        div.setAttribute("data-url", job.url);
        
        div.innerHTML = `
            <div class="pending-title">${job.title}</div>
            <div class="pending-company">${job.company} &bull; ${job.source}</div>
            <div class="pending-reason">${job.match_reason || "Requires review"}</div>
            <div class="pending-actions">
                <button type="button" class="btn-pending-verify">Review & Approve</button>
                <button type="button" class="btn-pending-reject">Reject</button>
            </div>
        `;
        
        div.querySelector(".btn-pending-verify").addEventListener("click", () => {
            openVerificationModal(job);
        });

        div.querySelector(".btn-pending-reject").addEventListener("click", () => {
            rejectPendingJob(job);
        });
        
        pendingList.appendChild(div);
    }

    function removePendingJob(url) {
        delete pendingJobs[url];
        const pendingCount = Object.keys(pendingJobs).length;
        metricPending.textContent = pendingCount;
        if (pendingCountBadge) pendingCountBadge.textContent = pendingCount;
        
        const item = pendingList.querySelector(`.pending-item[data-url="${url}"]`);
        if (item) {
            item.remove();
        }
        
        if (pendingList.children.length === 0) {
            pendingList.innerHTML = `
                <div class="empty-state">
                    <span class="empty-icon">✓</span>
                    <p>No jobs pending manual review.</p>
                    <span class="empty-sub">Borderline roles will queue here for fast approval.</span>
                </div>
            `;
        }
    }

    async function rejectPendingJob(job) {
        try {
            const res = await fetch("/api/verify-job", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    url: job.url,
                    action: "reject",
                    match_score: 0,
                    match_reason: "",
                    estimated_pay: "",
                    location: ""
                })
            });
            const data = await res.json();
            if (data.status === "rejected") {
                removePendingJob(job.url);
                addLog(`[ACTION] Rejected borderline job: ${job.title}`);
            }
        } catch (err) {
            console.error("Reject pending error:", err);
        }
    }

    // =========================================================================
    // Modals: Inspector & Verification
    // =========================================================================
    const inspectorModal = document.getElementById("inspector-modal");
    const inspectorClose = document.getElementById("inspector-close");
    const inspectTitle = document.getElementById("inspect-title");
    const inspectCompany = document.getElementById("inspect-company");
    const inspectPay = document.getElementById("inspect-pay");
    const inspectScore = document.getElementById("inspect-score");
    const inspectSource = document.getElementById("inspect-source");
    const inspectLocation = document.getElementById("inspect-location");
    const inspectReason = document.getElementById("inspect-reason");
    const inspectApplyBtn = document.getElementById("inspect-apply-btn");
    const inspectMarkAppliedBtn = document.getElementById("inspect-mark-applied-btn");
    const inspectDesc = document.getElementById("inspect-desc");

    let activeInspectJob = null;

    function openJobInspector(job) {
        activeInspectJob = job;
        inspectTitle.textContent = job.title;
        inspectCompany.textContent = job.company;
        inspectPay.textContent = job.estimated_pay || "Not Disclosed";
        inspectScore.textContent = `${job.match_score}% Fit`;
        inspectSource.textContent = job.source;
        inspectLocation.textContent = job.location || "Worldwide Remote";
        inspectReason.textContent = job.match_reason || "Candidate technical skill alignment passed gate.";
        inspectApplyBtn.href = job.url;
        inspectDesc.innerHTML = job.description || "No full description text returned from board.";

        const isApplied = (job.status === "applied") || appliedJobsList.some(j => j.url === job.url);
        if (isApplied) {
            inspectMarkAppliedBtn.textContent = "✓ Already Applied";
            inspectMarkAppliedBtn.disabled = true;
        } else {
            inspectMarkAppliedBtn.textContent = "✓ Mark as Applied";
            inspectMarkAppliedBtn.disabled = false;
        }

        inspectorModal.style.display = "flex";
        setTimeout(() => inspectorModal.classList.add("active"), 10);
    }

    function closeJobInspector() {
        inspectorModal.classList.remove("active");
        setTimeout(() => {
            inspectorModal.style.display = "none";
            activeInspectJob = null;
        }, 250);
    }

    if (inspectorClose) inspectorClose.addEventListener("click", closeJobInspector);
    if (inspectMarkAppliedBtn) {
        inspectMarkAppliedBtn.addEventListener("click", () => {
            if (activeInspectJob) {
                markJobAsApplied(activeInspectJob);
            }
        });
    }

    // Verification Modal
    const modal = document.getElementById("verification-modal");
    const modalClose = document.getElementById("modal-close");
    const verifyScoreInput = document.getElementById("verify-score");
    const verifyScoreVal = document.getElementById("verify-score-val");
    const verifyPayInput = document.getElementById("verify-pay");
    const verifyLocationInput = document.getElementById("verify-location");
    const verifyReasonInput = document.getElementById("verify-reason");
    const btnApprove = document.getElementById("btn-approve");
    const btnReject = document.getElementById("btn-reject");
    let activeVerificationJob = null;

    function openVerificationModal(job) {
        activeVerificationJob = job;
        
        document.getElementById("modal-job-title").textContent = job.title;
        document.getElementById("modal-job-company").textContent = job.company;
        document.getElementById("modal-job-location").textContent = job.location;
        document.getElementById("modal-job-source").textContent = job.source;
        document.getElementById("modal-job-url").href = job.url;
        document.getElementById("modal-job-desc").innerHTML = job.description || "No description preview available.";
        
        verifyScoreInput.value = job.match_score || 60;
        verifyScoreVal.textContent = `${verifyScoreInput.value}%`;
        verifyPayInput.value = job.estimated_pay || "Not Disclosed";
        verifyLocationInput.value = job.location || "Remote";
        verifyReasonInput.value = (job.match_reason || "").replace("[Smart Match] ", "");
        
        modal.style.display = "flex";
        setTimeout(() => modal.classList.add("active"), 10);
    }

    function closeVerificationModal() {
        modal.classList.remove("active");
        setTimeout(() => {
            modal.style.display = "none";
            activeVerificationJob = null;
        }, 250);
    }

    if (modalClose) modalClose.addEventListener("click", closeVerificationModal);

    if (verifyScoreInput) {
        verifyScoreInput.addEventListener("input", (e) => {
            verifyScoreVal.textContent = `${e.target.value}%`;
        });
    }

    if (btnApprove) {
        btnApprove.addEventListener("click", async () => {
            if (!activeVerificationJob) return;
            
            const payload = {
                url: activeVerificationJob.url,
                action: "approve",
                match_score: parseInt(verifyScoreInput.value),
                match_reason: verifyReasonInput.value,
                estimated_pay: verifyPayInput.value,
                location: verifyLocationInput.value
            };
            
            try {
                const res = await fetch("/api/verify-job", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                
                if (data.status === "approved") {
                    addJobRow(data.job);
                    removePendingJob(activeVerificationJob.url);
                    closeVerificationModal();
                    addLog(`[ACTION] Approved & persisted job: ${data.job.title}`);
                    enableDownloads();
                }
            } catch (err) {
                console.error("Verification approve failed:", err);
                alert("Approval failed.");
            }
        });
    }

    if (btnReject) {
        btnReject.addEventListener("click", async () => {
            if (!activeVerificationJob) return;
            await rejectPendingJob(activeVerificationJob);
            closeVerificationModal();
        });
    }

    window.addEventListener("click", (e) => {
        if (e.target === inspectorModal) closeJobInspector();
        if (e.target === modal) closeVerificationModal();
    });

    // =========================================================================
    // Search and Filter Listeners
    // =========================================================================
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            searchTerm = e.target.value;
            renderMatchedJobs();
        });
    }

    filterPills.forEach(btn => {
        btn.addEventListener("click", () => {
            filterPills.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            activeFilter = btn.getAttribute("data-filter");
            renderMatchedJobs();
        });
    });

    // =========================================================================
    // Purge Cache
    // =========================================================================
    if (clearAllBtn) {
        clearAllBtn.addEventListener("click", async () => {
            if (!confirm("Are you sure you want to purge all scraped jobs, the pending review list, and the evaluation cache?")) {
                return;
            }
            try {
                const res = await fetch("/api/purge", { method: "POST" });
                const data = await res.json();
                if (data.status === "success") {
                    matchedJobsList = [];
                    appliedJobsList = [];
                    pendingJobs = {};
                    totalScrapedCount = 0;
                    
                    metricScraped.textContent = "0";
                    metricMatched.textContent = "0";
                    metricPending.textContent = "0";
                    metricApplied.textContent = "0";
                    if (pendingCountBadge) pendingCountBadge.textContent = "0";
                    
                    renderMatchedJobs();
                    pendingList.innerHTML = `
                        <div class="empty-state">
                            <span class="empty-icon">✓</span>
                            <p>No jobs pending manual review.</p>
                            <span class="empty-sub">Borderline roles will queue here for fast approval.</span>
                        </div>
                    `;
                    
                    sourceCards.forEach(card => {
                        const countSpan = card.querySelector(".source-count");
                        const beacon = card.querySelector(".source-live-beacon");
                        if (countSpan) {
                            countSpan.textContent = "Ready";
                            countSpan.className = "source-count";
                        }
                        if (beacon) {
                            beacon.className = "source-live-beacon";
                        }
                    });
                    
                    resetStepper();
                    addLog("[SYSTEM] Data, MongoDB records, and AI evaluation cache purged.");
                }
            } catch (err) {
                console.error("Clear all failed:", err);
                alert("Failed to clear data.");
            }
        });
    }

    // =========================================================================
    // Launch Scraper Pipeline Trigger
    // =========================================================================
    let eventSource = null;

    if (startBtn) {
        startBtn.addEventListener("click", async () => {
            const selected = getSelectedSources();
            if (selected.length === 0) {
                alert("Please select at least one scraper source from the grid.");
                return;
            }

            startBtn.disabled = true;
            startBtn.classList.add("is-running");
            if (startBtnLabel) startBtnLabel.textContent = "HARVESTING IN PROGRESS...";
            if (startBtnIcon) startBtnIcon.textContent = "⏳";
            setPipelineStatus("● Scraping Active...", "running");
            disableDownloads();
            startProgress();
            setStep(1);

            consoleOutput.innerHTML = '<p class="log-system">> Dispatching scraping agents...</p>';
            jobsBody.innerHTML = "";
            pendingList.innerHTML = `
                <div class="empty-state">
                    <span class="empty-icon">✓</span>
                    <p>No jobs pending manual review.</p>
                </div>
            `;
            pendingJobs = {};
            matchedJobsList = [];
            totalScrapedCount = 0;
            metricScraped.textContent = "0";
            metricMatched.textContent = "0";
            metricPending.textContent = "0";
            if (pendingCountBadge) pendingCountBadge.textContent = "0";

            // Mark selected cards as running
            sourceCards.forEach(card => {
                const cb = card.querySelector(".source-checkbox");
                const countSpan = card.querySelector(".source-count");
                const beacon = card.querySelector(".source-live-beacon");
                if (cb.checked) {
                    card.classList.add("is-running");
                    if (countSpan) countSpan.textContent = "Extracting...";
                    if (beacon) beacon.className = "source-live-beacon beacon-running";
                } else {
                    card.classList.remove("is-running");
                    if (countSpan) countSpan.textContent = "Skipped";
                    if (beacon) beacon.className = "source-live-beacon";
                }
            });

            try {
                const response = await fetch("/api/start", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ sources: selected })
                });
                const data = await response.json();

                if (data.status === "Already running") {
                    addLog("[SYSTEM] Pipeline is already running in background.");
                } else {
                    addLog(`[SYSTEM] Launched pipeline with ${selected.length} active scraping lanes...`);
                }

                if (eventSource) {
                    eventSource.close();
                }

                eventSource = new EventSource("/api/stream");

                eventSource.addEventListener("log", (e) => {
                    const logData = JSON.parse(e.data);
                    addLog(logData.message);
                    if (logData.sources) {
                        updateSourceCards(logData.sources);
                    }
                    if (typeof logData.mongo_connected !== "undefined") {
                        updateMongoBadge(logData.mongo_connected);
                    }
                });

                eventSource.addEventListener("job", (e) => {
                    try {
                        const jobData = JSON.parse(e.data);
                        addJobRow(jobData);
                        enableDownloads();
                    } catch (err) {
                        console.error("Failed to parse job data:", err);
                    }
                });

                eventSource.addEventListener("pending_job", (e) => {
                    try {
                        const jobData = JSON.parse(e.data);
                        addPendingJob(jobData);
                    } catch (err) {
                        console.error("Failed to parse pending job:", err);
                    }
                });

                eventSource.addEventListener("done", (e) => {
                    eventSource.close();
                    startBtn.disabled = false;
                    startBtn.classList.remove("is-running");
                    if (startBtnLabel) startBtnLabel.textContent = "LAUNCH SCRAPER PIPELINE";
                    if (startBtnIcon) startBtnIcon.textContent = "⚡";
                    setPipelineStatus("● Pipeline Completed", "complete");
                    completeProgress();
                    enableDownloads();
                    addLog("[SUMMARY] Multi-site harvesting & AI fit evaluation complete! Matched roles are ready in the matrix.");
                });

                eventSource.onerror = (err) => {
                    console.error("EventSource connection issue:", err);
                };

            } catch (err) {
                addLog(`[ERROR] ${err.message}`);
                startBtn.disabled = false;
                startBtn.classList.remove("is-running");
                if (startBtnLabel) startBtnLabel.textContent = "LAUNCH SCRAPER PIPELINE";
                if (startBtnIcon) startBtnIcon.textContent = "⚡";
                setPipelineStatus("● Pipeline Error", "error");
                resetStepper();
            }
        });
    }
});
