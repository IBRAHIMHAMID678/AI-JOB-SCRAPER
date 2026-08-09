# AI Remote Job Generator & Orchestrator Pro

An automated multi-source job scraper and AI-powered evaluation engine tailored for finding remote, Pakistan-eligible, and junior-friendly software/AI engineering roles.

---

## 🚀 Key Features

- **Multi-Source Scraping**: Pulls job postings from LinkedIn, Indeed, Glassdoor, ZipRecruiter (via JobSpy), Himalayas API, Remotive API, Remote OK API, WeWorkRemotely RSS, and Python.org/NoDesk.
- **Smart Local Evaluator**: Automatically scores jobs based on tech stack relevance (Python, FastAPI, React, Next.js, LangChain, RAG, MongoDB) and flags location/visa restrictions (e.g., US-only).
- **Auto-Approval Pipeline**: Automatically accepts jobs scoring $\ge 40\%$ and places borderline jobs into a **Pending Manual Review** queue.
- **Dual Storage**: Stores matched opportunities in MongoDB (falls back to local memory mode if MongoDB is offline).
- **Real-Time Control Panel**: Live console logs, status trackers, and interactive inspection tools using FastAPI and EventSource (SSE).
- **Report Exports**: One-click download of matched jobs as CSV or formatted Word documents (DOCX).

---

## 🛠️ Project Structure

- `server.py`: FastAPI server serving endpoints, logs, and downloads.
- `main.py`: CLI pipeline runner.
- `evaluator.py`: High-speed local filtering, matching logic, and evaluation cache.
- `database.py`: MongoDB client setup and schema helper functions.
- `log_manager.py`: Centralized logging queues.
- `scrapers/`: Sub-modules containing site-specific scrapers.
- `static/`: Frontend dashboard assets (`index.html`, `script.js`, `style.css`).

---

## ⚙️ Setup Instructions

### 1. Prerequisites
Ensure you have Python 3.10+ installed.

### 2. Install Dependencies
Run the following command to install required Python libraries:
```bash
pip install -r requirements.txt
```
*(Optional)* Install MongoDB Community Server locally to enable persistent storage. If MongoDB is not running, the application will automatically fall back to in-memory storage.

### 3. Environment Variables
Create a `.env` file in the root directory based on `.env.example`:
```env
GROQ_API_KEY=your_groq_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=job_scraper_db
```

---

## 🏃 Running the Application

To run the full interactive dashboard:
```bash
python server.py
```
Then open your browser and navigate to **[http://localhost:8000](http://localhost:8000)**.

To run the pipeline via CLI:
```bash
python main.py
```

---

## 📈 Planned Capabilities
- **Automated Applications**: Automated form submissions for Greenhouse and Lever.
- **Guided Workday Assistant**: Headed browser automation helping with login and page-by-page profile filling.
- **Profile Customization**: Interactive resume uploading and profile details form directly in the dashboard.
