document.addEventListener("DOMContentLoaded", () => {
    const startBtn = document.getElementById("start-btn");
    const downloadBtn = document.getElementById("download-btn");
    const consoleOutput = document.getElementById("console-output");
    const jobsBody = document.getElementById("jobs-body");
    
    let eventSource = null;
    downloadBtn.style.pointerEvents = "none";
    downloadBtn.style.opacity = "0.5";

    function addLog(message) {
        const p = document.createElement("p");
        p.textContent = `> ${message}`;
        consoleOutput.appendChild(p);
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
    }

    function addJobRow(job) {
        const tr = document.createElement("tr");
        
        // Score formatting
        let scoreClass = 'score';
        if (job.match_score < 60) scoreClass += ' text-warning';
        if (job.match_score >= 80) scoreClass += ' text-success';
        
        tr.innerHTML = `
            <td class="${scoreClass}">${job.match_score}</td>
            <td><strong>${job.title}</strong></td>
            <td>${job.company}</td>
            <td>${job.estimated_pay}</td>
            <td><a href="${job.url}" target="_blank" class="job-link">Apply &nearr;</a></td>
        `;
        
        // Add animation class
        tr.style.opacity = '0';
        tr.style.transform = 'translateY(10px)';
        jobsBody.appendChild(tr);
        
        // Trigger reflow and animate
        setTimeout(() => {
            tr.style.transition = 'all 0.3s ease';
            tr.style.opacity = '1';
            tr.style.transform = 'translateY(0)';
        }, 10);
    }

    startBtn.addEventListener("click", async () => {
        startBtn.disabled = true;
        startBtn.textContent = "Scraping in Progress...";
        downloadBtn.style.pointerEvents = "none";
        downloadBtn.style.opacity = "0.5";
        
        // Clear previous runs
        consoleOutput.innerHTML = "";
        jobsBody.innerHTML = "";
        
        try {
            // Trigger the backend process
            const response = await fetch("/api/start", { method: "POST" });
            const data = await response.json();
            
            if (data.status === "Already running") {
                addLog("Pipeline is already running in the background.");
            } else {
                addLog("Successfully started pipeline...");
            }
            
            // Connect SSE for streaming updates
            if (eventSource) {
                eventSource.close();
            }
            
            eventSource = new EventSource("/api/stream");
            
            eventSource.addEventListener("log", (e) => {
                const logData = JSON.parse(e.data);
                addLog(logData.message);
                
                if (logData.message === "DONE") {
                    eventSource.close();
                    startBtn.disabled = false;
                    startBtn.textContent = "Start Scraping & Matching";
                    downloadBtn.style.pointerEvents = "auto";
                    downloadBtn.style.opacity = "1";
                    addLog("Connection closed. You can now download the CSV.");
                }
            });
            
            eventSource.addEventListener("job", (e) => {
                try {
                    const jobData = JSON.parse(e.data);
                    addJobRow(jobData);
                } catch (err) {
                    console.error("Failed to parse job data:", err, e.data);
                }
            });
            
            eventSource.onerror = (err) => {
                console.error("EventSource failed:", err);
                eventSource.close();
                startBtn.disabled = false;
                startBtn.textContent = "Start Scraping & Matching";
            };

        } catch (err) {
            addLog(`Error: ${err.message}`);
            startBtn.disabled = false;
            startBtn.textContent = "Start Scraping & Matching";
        }
    });
});
