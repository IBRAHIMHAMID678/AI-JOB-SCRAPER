document.addEventListener("DOMContentLoaded", () => {
    const startBtn = document.getElementById("start-btn");
    const downloadBtn = document.getElementById("download-btn");
    const downloadDocxBtn = document.getElementById("download-docx-btn");
    const consoleOutput = document.getElementById("console-output");
    const clearConsoleBtn = document.getElementById("clear-console-btn");
    const jobsBody = document.getElementById("jobs-body");
    const pendingList = document.getElementById("pending-list");
    const pipelineBadge = document.getElementById("pipeline-status-badge");
    const mongoBadge = document.getElementById("mongo-status-badge");
    const sourcesGrid = document.getElementById("sources-grid");
    
    // Search and Filter controls
    const searchInput = document.getElementById("search-input");
    const filterBtns = document.querySelectorAll(".filter-btn");
    
    // Metrics elements
    const metricScraped = document.getElementById("metric-scraped");
    const metricMatched = document.getElementById("metric-matched");
    const metricPending = document.getElementById("metric-pending");
    const metricApplied = document.getElementById("metric-applied");
    
    // Clear and mark applied elements
    const clearAllBtn = document.getElementById("clear-all-btn");
    const inspectMarkAppliedBtn = document.getElementById("inspect-mark-applied-btn");
    
    let totalScrapedCount = 0;
    let matchedJobsList = [];
    let appliedJobsList = [];
    let pendingJobs = {};
    let activeFilter = "all";
    let searchTerm = "";
    
    // Verification Modal elements
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
    
    // Right Window Job Inspector Modal elements
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
    const inspectDesc = document.getElementById("inspect-desc");

    const candidateCV = `Computer Science graduate (2026), Junior Software Engineer / AI Engineer skilled in 
Python (FastAPI), React, Next.js, Node.js, NestJS, LangChain, RAG, vector databases (MongoDB Atlas), 
and LLM integration. Looking for Remote, USD pay ($15-$60/hr or equivalent USD salary), 0-2 years experience roles, 
specifically AI Engineer, AI Full Stack Developer, or Full Stack Developer. Candidate based in Pakistan requiring Worldwide Remote / Work from Anywhere.`;

    document.getElementById("modal-candidate-cv").textContent = candidateCV;

    function updateMongoBadge(isConnected) {
        if (isConnected) {
            mongoBadge.textContent = "🍃 MongoDB: Connected";
            mongoBadge.className = "status-indicator status-complete";
        } else {
            mongoBadge.textContent = "🍃 MongoDB: Off (In-Memory)";
            mongoBadge.className = "status-indicator";
        }
    }

    // Check DB status on page load
    fetch("/api/jobs/saved")
        .then(res => res.json())
        .then(data => {
            updateMongoBadge(data.mongo_connected);
            if (data.jobs && data.jobs.length > 0) {
                data.jobs.forEach(job => addJobRow(job));
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
            }
        })
        .catch(err => console.log("Applied check error:", err));

    function disableDownloads() {
        downloadBtn.style.pointerEvents = "none";
        downloadBtn.style.opacity = "0.5";
        downloadDocxBtn.style.pointerEvents = "none";
        downloadDocxBtn.style.opacity = "0.5";
    }
    
    function enableDownloads() {
        downloadBtn.style.pointerEvents = "auto";
        downloadBtn.style.opacity = "1";
        downloadDocxBtn.style.pointerEvents = "auto";
        downloadDocxBtn.style.opacity = "1";
    }
    
    disableDownloads();

    function setPipelineStatus(statusText, type = "idle") {
        pipelineBadge.textContent = statusText;
        pipelineBadge.className = `status-indicator status-${type}`;
    }

    function addLog(message) {
        const p = document.createElement("p");
        
        let cls = "log-line";
        if (message.includes("[SYSTEM]")) cls += " log-system";
        else if (message.includes("[SCRAPER]")) cls += " log-scraper";
        else if (message.includes("[EVALUATOR]")) cls += " log-evaluator";
        else if (message.includes("[MATCH]")) cls += " log-match";
        else if (message.includes("[DATABASE]")) cls += " log-summary";
        else if (message.includes("[ERROR]")) cls += " log-error";
        else if (message.includes("[SUMMARY]")) cls += " log-summary";
        
        p.className = cls;
        p.textContent = `> ${message}`;
        consoleOutput.appendChild(p);
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
        
        if (message.includes("Total raw jobs collected")) {
            const match = message.match(/\d+/);
            if (match) {
                totalScrapedCount = parseInt(match[0]);
                metricScraped.textContent = totalScrapedCount;
            }
        }
    }

    function updateSourceCards(sourceStats) {
        if (!sourceStats) return;
        for (const [name, count] of Object.entries(sourceStats)) {
            const cards = sourcesGrid.querySelectorAll(".source-card");
            cards.forEach(card => {
                const cardName = card.getAttribute("data-source");
                if (cardName && (cardName.includes(name) || name.includes(cardName.split(" ")[0]))) {
                    const countSpan = card.querySelector(".source-count");
                    if (countSpan) {
                        countSpan.textContent = `${count} Jobs`;
                        countSpan.className = "source-count active-count";
                    }
                }
            });
        }
    }

    clearConsoleBtn.addEventListener("click", () => {
        consoleOutput.innerHTML = "";
    });

    function extractSkills(fullText) {
        const targetSkills = ["Python", "FastAPI", "React", "Next.js", "Node.js", "LangChain", "RAG", "MongoDB", "LLM", "TypeScript"];
        return targetSkills.filter(skill => 
            new RegExp('\\b' + skill.replace('.', '\\.') + '\\b', 'i').test(fullText)
        );
    }

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
                
                // Move from active to applied list
                matchedJobsList = matchedJobsList.filter(j => j.url !== job.url);
                if (!appliedJobsList.some(j => j.url === job.url)) {
                    appliedJobsList.push(job);
                    appliedJobsList.sort((a, b) => b.match_score - a.match_score);
                }
                
                renderMatchedJobs();
                metricApplied.textContent = appliedJobsList.length;
                metricMatched.textContent = matchedJobsList.length;
                addLog(`[ACTION] Job marked as Applied: ${job.title}`);
                
                // Close modal if open
                if (activeVerificationJob && activeVerificationJob.url === job.url) {
                    closeVerificationModal();
                }
                closeJobInspector();
            }
        } catch (err) {
            console.error("Mark applied error:", err);
            alert("Failed to mark job as applied.");
        }
    }

    function renderMatchedJobs() {
        jobsBody.innerHTML = "";
        
        const listToRender = (activeFilter === "applied") ? appliedJobsList : matchedJobsList;
        
        const filtered = listToRender.filter(job => {
            const query = searchTerm.toLowerCase();
            const matchesSearch = !query || 
                job.title.toLowerCase().includes(query) || 
                job.company.toLowerCase().includes(query) || 
                (job.match_reason && job.match_reason.toLowerCase().includes(query)) ||
                (job.description && job.description.toLowerCase().includes(query));
                
            if (!matchesSearch) return false;
            
            if (activeFilter === "high") return job.match_score >= 80;
            if (activeFilter === "hourly") return (job.estimated_pay || "").toLowerCase().includes("hr") || (job.estimated_pay || "").toLowerCase().includes("hour");
            if (activeFilter === "worldwide") return (job.location || "").toLowerCase().includes("worldwide") || (job.location || "").toLowerCase().includes("anywhere");
            
            return true;
        });

        if (filtered.length === 0) {
            jobsBody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-secondary); padding: 2rem;">No jobs matching current filter.</td></tr>';
            return;
        }

        filtered.forEach(job => {
            const tr = document.createElement("tr");
            tr.className = "clickable-row";
            
            let scoreClass = 'score';
            if (job.match_score < 60) scoreClass += ' text-warning';
            if (job.match_score >= 80) scoreClass += ' text-success';
            
            const skills = extractSkills(`${job.title} ${job.description} ${job.match_reason}`);
            const skillChipsHtml = skills.map(s => `<span class="skill-chip">${s}</span>`).join("");
            
            const isAppliedJob = (activeFilter === "applied") || (job.status === "applied");

            tr.innerHTML = `
                <td>
                    <div class="score-circle ${scoreClass}">${job.match_score}%</div>
                </td>
                <td>
                    <strong class="job-title-text">${job.title}</strong>
                    <div class="skill-chips-row">${skillChipsHtml}</div>
                    <small class="match-reason-sub">${job.match_reason || "CV Fit Match"}</small>
                </td>
                <td>
                    <strong>${job.company}</strong><br>
                    <span class="source-tag">${job.source}</span>
                </td>
                <td><span class="pay-tag">${job.estimated_pay || "Not Disclosed"}</span></td>
                <td>
                    <div style="display: flex; gap: 0.5rem; align-items: center;">
                        <button class="inspect-btn primary-btn-sm">Inspect</button>
                        ${!isAppliedJob ? `<button class="row-apply-btn success-btn-sm" title="Mark as Applied">✓</button>` : `<span class="applied-badge-text">✓ Applied</span>`}
                    </div>
                </td>
            `;
            
            tr.addEventListener("click", () => {
                openJobInspector(job);
            });
            
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
        
        metricMatched.textContent = matchedJobsList.length;
    }

    function addJobRow(job) {
        if (!matchedJobsList.some(j => j.url === job.url)) {
            matchedJobsList.push(job);
            matchedJobsList.sort((a, b) => b.match_score - a.match_score);
            renderMatchedJobs();
        }
    }

    function addPendingJob(job) {
        const emptyState = pendingList.querySelector(".empty-state");
        if (emptyState) {
            pendingList.innerHTML = "";
        }
        
        pendingJobs[job.url] = job;
        metricPending.textContent = Object.keys(pendingJobs).length;
        
        const div = document.createElement("div");
        div.className = "pending-item";
        div.setAttribute("data-url", job.url);
        
        div.innerHTML = `
            <div class="pending-info">
                <strong>${job.title}</strong>
                <span>${job.company} &bull; ${job.source}</span>
            </div>
            <button class="verify-item-btn">Verify</button>
        `;
        
        div.querySelector(".verify-item-btn").addEventListener("click", (e) => {
            e.stopPropagation();
            openVerificationModal(job);
        });
        
        pendingList.appendChild(div);
    }

    function removePendingJob(url) {
        delete pendingJobs[url];
        metricPending.textContent = Object.keys(pendingJobs).length;
        
        const item = pendingList.querySelector(`.pending-item[data-url="${url}"]`);
        if (item) {
            item.remove();
        }
        
        if (pendingList.children.length === 0) {
            pendingList.innerHTML = '<p class="empty-state">No jobs pending verification.</p>';
        }
    }

    // Right Window Job Inspector Modal logic
    let activeInspectJob = null;
    function openJobInspector(job) {
        activeInspectJob = job;
        inspectTitle.textContent = job.title;
        inspectCompany.textContent = job.company;
        inspectPay.textContent = job.estimated_pay || "Not Disclosed";
        inspectScore.textContent = `${job.match_score}% Match Score`;
        inspectSource.textContent = job.source;
        inspectLocation.textContent = job.location || "Worldwide Remote";
        inspectReason.textContent = job.match_reason || "Matched tech criteria.";
        inspectApplyBtn.href = job.url;
        inspectDesc.innerHTML = job.description || "No job description content available.";
        
        const isApplied = (job.status === "applied") || appliedJobsList.some(j => j.url === job.url);
        if (isApplied) {
            inspectMarkAppliedBtn.style.display = "none";
        } else {
            inspectMarkAppliedBtn.style.display = "block";
            inspectMarkAppliedBtn.disabled = false;
        }
        
        inspectorModal.style.display = "flex";
        setTimeout(() => inspectorModal.classList.add("active"), 10);
    }

    function closeJobInspector() {
        inspectorModal.classList.remove("active");
        setTimeout(() => {
            inspectorModal.style.display = "none";
        }, 250);
    }

    inspectorClose.addEventListener("click", closeJobInspector);
    window.addEventListener("click", (e) => {
        if (e.target === inspectorModal) closeJobInspector();
        if (e.target === modal) closeVerificationModal();
    });

    // Verification Modal control
    function openVerificationModal(job) {
        activeVerificationJob = job;
        
        document.getElementById("modal-job-title").textContent = job.title;
        document.getElementById("modal-job-company").textContent = job.company;
        document.getElementById("modal-job-location").textContent = job.location;
        document.getElementById("modal-job-source").textContent = job.source;
        document.getElementById("modal-job-url").href = job.url;
        document.getElementById("modal-job-desc").innerHTML = job.description;
        
        verifyScoreInput.value = job.match_score || 50;
        verifyScoreVal.textContent = `${verifyScoreInput.value}%`;
        verifyPayInput.value = job.estimated_pay || "Not Disclosed";
        verifyLocationInput.value = job.location || "Remote";
        
        let cleanReason = job.match_reason || "";
        if (cleanReason.startsWith("[Smart Match] ")) {
            cleanReason = cleanReason.replace("[Smart Match] ", "");
        }
        verifyReasonInput.value = cleanReason;
        
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

    verifyScoreInput.addEventListener("input", (e) => {
        verifyScoreVal.textContent = `${e.target.value}%`;
    });

    modalClose.addEventListener("click", closeVerificationModal);

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
                addLog(`[ACTION] Manually verified & approved job: ${data.job.title}`);
                enableDownloads();
            }
        } catch (err) {
            console.error("Verification approve failed:", err);
            alert("Approval request failed.");
        }
    });

    btnReject.addEventListener("click", async () => {
        if (!activeVerificationJob) return;
        
        const payload = {
            url: activeVerificationJob.url,
            action: "reject",
            match_score: 0,
            match_reason: "",
            estimated_pay: "",
            location: ""
        };
        
        try {
            const res = await fetch("/api/verify-job", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            
            if (data.status === "rejected") {
                removePendingJob(activeVerificationJob.url);
                closeVerificationModal();
                addLog(`[ACTION] Rejected job: ${activeVerificationJob.title}`);
            }
        } catch (err) {
            console.error("Verification reject failed:", err);
            alert("Rejection request failed.");
        }
    });

    // Search and Filter tab listeners
    searchInput.addEventListener("input", (e) => {
        searchTerm = e.target.value;
        renderMatchedJobs();
    });

    const filterPills = document.querySelectorAll(".filter-pill");
    filterPills.forEach(btn => {
        btn.addEventListener("click", () => {
            filterPills.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            activeFilter = btn.getAttribute("data-filter");
            renderMatchedJobs();
        });
    });

    inspectMarkAppliedBtn.addEventListener("click", () => {
        if (activeInspectJob) {
            markJobAsApplied(activeInspectJob);
        }
    });

    clearAllBtn.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to purge all scraped jobs, pending review list, and the evaluation cache? This cannot be undone.")) {
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
                
                jobsBody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-secondary); padding: 3rem;">No matched jobs yet. Click <strong>Start Multi-Site Pipeline</strong> to scrape and evaluate live jobs.</td></tr>';
                pendingList.innerHTML = '<p class="empty-state">No jobs pending manual verification.</p>';
                
                const sourceCounts = sourcesGrid.querySelectorAll(".source-count");
                sourceCounts.forEach(sc => {
                     sc.textContent = "Ready";
                     sc.className = "source-count";
                });
                
                addLog("[SYSTEM] Cleared all scraped jobs, records, and AI cache.");
            }
        } catch (err) {
            console.error("Clear all failed:", err);
            alert("Failed to clear data.");
        }
    });

    // Pipeline Start button listener
    let eventSource = null;
    startBtn.addEventListener("click", async () => {
        startBtn.disabled = true;
        startBtn.textContent = "⏳ Scraping Multi-Site & Matching...";
        setPipelineStatus("● Pipeline Running...", "running");
        disableDownloads();
        
        consoleOutput.innerHTML = "";
        jobsBody.innerHTML = "";
        pendingList.innerHTML = '<p class="empty-state">No jobs pending verification.</p>';
        pendingJobs = {};
        matchedJobsList = [];
        totalScrapedCount = 0;
        metricScraped.textContent = "0";
        metricMatched.textContent = "0";
        metricPending.textContent = "0";
        metricApplied.textContent = appliedJobsList.length;
        
        const sourceCounts = sourcesGrid.querySelectorAll(".source-count");
        sourceCounts.forEach(sc => {
            sc.textContent = "Extracting...";
            sc.className = "source-count";
        });
        
        try {
            const response = await fetch("/api/start", { method: "POST" });
            const data = await response.json();
            
            if (data.status === "Already running") {
                addLog("[SYSTEM] Pipeline is already running in the background.");
            } else {
                addLog("[SYSTEM] Successfully started Multi-Site Scraping & AI Matching pipeline...");
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
                    console.error("Failed to parse job data:", err, e.data);
                }
            });
            
            eventSource.addEventListener("pending_job", (e) => {
                try {
                    const jobData = JSON.parse(e.data);
                    addPendingJob(jobData);
                } catch (err) {
                    console.error("Failed to parse pending job:", err, e.data);
                }
            });
            
            eventSource.addEventListener("done", (e) => {
                eventSource.close();
                startBtn.disabled = false;
                startBtn.textContent = "⚡ Start Multi-Site Pipeline";
                setPipelineStatus("● Pipeline Complete", "complete");
                enableDownloads();
                addLog("[SYSTEM] Pipeline execution completed! Explore matched jobs in the Right Window.");
            });
            
            eventSource.onerror = (err) => {
                console.error("EventSource failed:", err);
                addLog("[ERROR] Stream connection interrupted. Checking backend status...");
            };

        } catch (err) {
            addLog(`[ERROR] ${err.message}`);
            startBtn.disabled = false;
            startBtn.textContent = "⚡ Start Multi-Site Pipeline";
            setPipelineStatus("● Error Encountered", "error");
        }
    });
});
