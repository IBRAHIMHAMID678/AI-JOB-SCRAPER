import os
import pymongo
from dotenv import load_dotenv
from log_manager import log

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGO_DB_NAME", "job_scraper_db")

db_client = None
db_instance = None
jobs_collection = None
is_mongo_connected = False

def init_mongo():
    global db_client, db_instance, jobs_collection, is_mongo_connected
    try:
        db_client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        # Test connection
        db_client.admin.command('ping')
        db_instance = db_client[DB_NAME]
        jobs_collection = db_instance["matched_jobs"]
        # Ensure unique index on job URL
        jobs_collection.create_index("url", unique=True)
        is_mongo_connected = True
        log(f"[DATABASE] Connected to MongoDB successfully ({DB_NAME}.matched_jobs)")
    except Exception as e:
        is_mongo_connected = False
        log(f"[DATABASE] MongoDB connection unconfigured or unavailable: {e}. (Operating in memory mode)")

init_mongo()

def save_job_to_db(job):
    """
    Upserts a matched job into MongoDB.
    """
    if not is_mongo_connected or jobs_collection is None:
        return False
    try:
        job_data = dict(job)
        url = job_data.get("url")
        if not url:
            return False
            
        jobs_collection.update_one(
            {"url": url},
            {"$set": job_data},
            upsert=True
        )
        return True
    except Exception as e:
        log(f"[DATABASE] Error saving job to MongoDB: {e}")
        return False

def get_saved_jobs_from_db():
    """
    Retrieves all matched jobs stored in MongoDB.
    """
    if not is_mongo_connected or jobs_collection is None:
        return []
    try:
        cursor = jobs_collection.find({}, {"_id": 0}).sort("match_score", pymongo.DESCENDING)
        return list(cursor)
    except Exception as e:
        log(f"[DATABASE] Error retrieving jobs from MongoDB: {e}")
        return []
