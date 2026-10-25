import os
import json
import sqlite3
import pymongo
from dotenv import load_dotenv
from log_manager import log

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGO_DB_NAME", "job_scraper_db")
SQLITE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobpilot.db")

db_client = None
db_instance = None
jobs_collection = None
is_mongo_connected = False

def init_sqlite():
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS matched_jobs (
                url TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                location TEXT,
                description TEXT,
                source TEXT,
                match_score INTEGER,
                match_reason TEXT,
                estimated_pay TEXT,
                status TEXT DEFAULT 'matched',
                job_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Non-destructive migrations: Add Matcha parity columns if missing
        c.execute("PRAGMA table_info(matched_jobs)")
        existing_cols = {col[1] for col in c.fetchall()}
        
        new_columns = [
            ("direct_career_url", "TEXT"),
            ("salary_min", "INTEGER"),
            ("salary_max", "INTEGER"),
            ("salary_currency", "TEXT DEFAULT 'USD'"),
            ("remote_regions", "TEXT"),
            ("job_summary", "TEXT"),
            ("remote_summary", "TEXT"),
            ("date_posted", "TIMESTAMP"),
            ("is_24h_fresh", "INTEGER DEFAULT 1"),
            ("company_size", "INTEGER DEFAULT 0"),
            ("funding_total", "TEXT"),
            ("key_investors", "TEXT"),
            ("logo_url", "TEXT")
        ]

        for col_name, col_type in new_columns:
            if col_name not in existing_cols:
                try:
                    c.execute(f"ALTER TABLE matched_jobs ADD COLUMN {col_name} {col_type}")
                    log(f"[DATABASE] Migrated matched_jobs: Added column '{col_name}'")
                except Exception as col_err:
                    log(f"[DATABASE] Migration warning for {col_name}: {col_err}")

        conn.commit()
        conn.close()
    except Exception as e:
        log(f"[DATABASE] SQLite initialization error: {e}")

init_sqlite()

def init_mongo():
    global db_client, db_instance, jobs_collection, is_mongo_connected
    try:
        db_client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        # Test connection
        db_client.admin.command('ping')
        db_instance = db_client[DB_NAME]
        jobs_collection = db_instance["matched_jobs"]
        # Ensure unique index on job URL and index on job_hash
        jobs_collection.create_index("url", unique=True)
        jobs_collection.create_index("job_hash")
        is_mongo_connected = True
        log(f"[DATABASE] Connected to MongoDB successfully ({DB_NAME}.matched_jobs)")
    except Exception as e:
        is_mongo_connected = False
        log(f"[DATABASE] MongoDB unavailable ({e}). Using SQLite persistence at jobpilot.db")

init_mongo()

def save_job_to_db(job):
    """
    Upserts a matched job into MongoDB or SQLite.
    """
    job_data = dict(job)
    url = job_data.get("url")
    if not url:
        return False
        
    if "status" not in job_data:
        job_data["status"] = "matched"

    saved = False
    if is_mongo_connected and jobs_collection is not None:
        try:
            jobs_collection.update_one(
                {"url": url},
                {"$set": job_data},
                upsert=True
            )
            saved = True
        except Exception as e:
            log(f"[DATABASE] Error saving job to MongoDB: {e}")

    # Also persist to SQLite
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        c = conn.cursor()
        
        # Format list fields as JSON strings
        remote_regions_json = json.dumps(job_data.get("remote_regions", [])) if isinstance(job_data.get("remote_regions"), list) else str(job_data.get("remote_regions", ""))
        key_investors_json = json.dumps(job_data.get("key_investors", [])) if isinstance(job_data.get("key_investors"), list) else str(job_data.get("key_investors", ""))

        c.execute("""
            INSERT INTO matched_jobs (
                url, title, company, location, description, source, match_score, match_reason, estimated_pay, status, job_hash,
                direct_career_url, salary_min, salary_max, salary_currency, remote_regions, job_summary, remote_summary,
                date_posted, is_24h_fresh, company_size, funding_total, key_investors, logo_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title,
                company=excluded.company,
                location=excluded.location,
                description=excluded.description,
                source=excluded.source,
                match_score=excluded.match_score,
                match_reason=excluded.match_reason,
                estimated_pay=excluded.estimated_pay,
                status=excluded.status,
                job_hash=excluded.job_hash,
                direct_career_url=excluded.direct_career_url,
                salary_min=excluded.salary_min,
                salary_max=excluded.salary_max,
                salary_currency=excluded.salary_currency,
                remote_regions=excluded.remote_regions,
                job_summary=excluded.job_summary,
                remote_summary=excluded.remote_summary,
                date_posted=excluded.date_posted,
                is_24h_fresh=excluded.is_24h_fresh,
                company_size=excluded.company_size,
                funding_total=excluded.funding_total,
                key_investors=excluded.key_investors,
                logo_url=excluded.logo_url
        """, (
            url,
            str(job_data.get("title", "")),
            str(job_data.get("company", "")),
            str(job_data.get("location", "")),
            str(job_data.get("description", "")),
            str(job_data.get("source", "")),
            int(job_data.get("match_score", 0)),
            str(job_data.get("match_reason", "")),
            str(job_data.get("estimated_pay", "")),
            str(job_data.get("status", "matched")),
            str(job_data.get("job_hash", "")),
            str(job_data.get("direct_career_url") or url),
            job_data.get("salary_min"),
            job_data.get("salary_max"),
            str(job_data.get("salary_currency", "USD")),
            remote_regions_json,
            str(job_data.get("job_summary", "")),
            str(job_data.get("remote_summary", "")),
            str(job_data.get("date_posted", "")),
            1 if job_data.get("is_24h_fresh", True) else 0,
            int(job_data.get("company_size") or 0),
            str(job_data.get("funding_total", "")),
            key_investors_json,
            str(job_data.get("logo_url", ""))
        ))
        conn.commit()
        conn.close()
        saved = True
    except Exception as e:
        log(f"[DATABASE] Error saving to SQLite: {e}")
        
    return saved

def update_job_status(url, status):
    updated = False
    if is_mongo_connected and jobs_collection is not None:
        try:
            jobs_collection.update_one(
                {"url": url},
                {"$set": {"status": status}}
            )
            updated = True
        except Exception as e:
            log(f"[DATABASE] Error updating job status in MongoDB for {url}: {e}")
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE matched_jobs SET status = ? WHERE url = ?", (status, url))
        conn.commit()
        conn.close()
        updated = True
    except Exception as e:
        log(f"[DATABASE] Error updating job status in SQLite for {url}: {e}")
    return updated

def get_applied_jobs_from_db():
    if is_mongo_connected and jobs_collection is not None:
        try:
            cursor = jobs_collection.find({"status": "applied"}, {"_id": 0}).sort("match_score", pymongo.DESCENDING)
            return list(cursor)
        except Exception as e:
            log(f"[DATABASE] Error retrieving applied jobs from MongoDB: {e}")
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM matched_jobs WHERE status = 'applied' ORDER BY match_score DESC")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log(f"[DATABASE] Error retrieving applied jobs from SQLite: {e}")
        return []

def get_active_jobs_from_db():
    if is_mongo_connected and jobs_collection is not None:
        try:
            cursor = jobs_collection.find(
                {"$or": [{"status": "matched"}, {"status": {"$exists": False}}]},
                {"_id": 0}
            ).sort("match_score", pymongo.DESCENDING)
            return list(cursor)
        except Exception as e:
            log(f"[DATABASE] Error retrieving active jobs from MongoDB: {e}")
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM matched_jobs WHERE status = 'matched' OR status IS NULL ORDER BY match_score DESC")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log(f"[DATABASE] Error retrieving active jobs from SQLite: {e}")
        return []

def get_fresh_24h_jobs_from_db(max_hours=24.0):
    """
    Returns jobs posted within max_hours (default: 24.0h) with is_24h_fresh = 1.
    """
    if is_mongo_connected and jobs_collection is not None:
        try:
            cursor = jobs_collection.find(
                {"is_24h_fresh": True, "$or": [{"status": "matched"}, {"status": {"$exists": False}}]},
                {"_id": 0}
            ).sort("match_score", pymongo.DESCENDING)
            return list(cursor)
        except Exception as e:
            log(f"[DATABASE] Error retrieving fresh jobs from MongoDB: {e}")
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT * FROM matched_jobs 
            WHERE (status = 'matched' OR status IS NULL) AND is_24h_fresh = 1 
            ORDER BY match_score DESC
        """)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log(f"[DATABASE] Error retrieving fresh jobs from SQLite: {e}")
        return []

def delete_all_jobs_from_db():
    deleted = False
    if is_mongo_connected and jobs_collection is not None:
        try:
            jobs_collection.delete_many({})
            deleted = True
        except Exception as e:
            log(f"[DATABASE] Error clearing jobs from MongoDB: {e}")
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM matched_jobs")
        conn.commit()
        conn.close()
        deleted = True
    except Exception as e:
        log(f"[DATABASE] Error clearing jobs from SQLite: {e}")
    return deleted

def is_job_url_exists(url):
    if is_mongo_connected and jobs_collection is not None:
        try:
            count = jobs_collection.count_documents({"url": url})
            if count > 0:
                return True
        except Exception:
            pass
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT 1 FROM matched_jobs WHERE url = ? LIMIT 1", (url,))
        row = c.fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False

def get_saved_jobs_from_db():
    """
    Retrieves all matched jobs stored in MongoDB or SQLite.
    """
    if is_mongo_connected and jobs_collection is not None:
        try:
            cursor = jobs_collection.find({}, {"_id": 0}).sort("match_score", pymongo.DESCENDING)
            return list(cursor)
        except Exception as e:
            log(f"[DATABASE] Error retrieving jobs from MongoDB: {e}")
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM matched_jobs ORDER BY match_score DESC")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        log(f"[DATABASE] Error retrieving jobs from SQLite: {e}")
        return []

