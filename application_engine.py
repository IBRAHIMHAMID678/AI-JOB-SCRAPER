"""
Job Application Engine - Core module for automated job applications
Integrates with resume optimizer and manages application pipeline
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class JobApplication:
    """Data class for job application tracking"""
    url: str
    title: str
    company: str
    source: str
    applied_at: datetime
    status: str = "applied"
    application_id: Optional[str] = None
    confirmation_data: Optional[Dict] = None

@dataclass
class ApplicationConfig:
    """Configuration for application engine"""
    max_daily_applications: int = 50
    applications_per_minute: int = 2
    retry_attempts: int = 3
    enable_captcha_handling: bool = True
    use_proxy_rotation: bool = False
    headless_browser: bool = True

class ResumeOptimizer:
    """Integration with existing resume optimizer system"""
    
    def __init__(self, resume_path: str):
        self.resume_path = resume_path
        self.optimized_cache = {}
    
    async def optimize_for_job(self, job_description: str, candidate_profile: str) -> Dict:
        """Optimize resume for specific job using existing resume optimizer system"""
        try:
            # This would integrate with the existing resume.txt system
            # For now, implement basic optimization
            keywords = self._extract_keywords(job_description)
            optimized_summary = self._create_optimized_summary(job_description, candidate_profile)
            
            return {
                "optimized_summary": optimized_summary,
                "keywords": keywords,
                "match_score": self._calculate_match_score(job_description, candidate_profile),
                "tailored_content": self._generate_tailored_content(job_description, candidate_profile)
            }
        except Exception as e:
            logger.error(f"Resume optimization failed: {e}")
            return {"error": str(e)}
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract relevant keywords from job description"""
        # Basic keyword extraction - would be enhanced with NLP
        tech_keywords = ["python", "fastapi", "react", "mongodb", "ai", "llm", "rag"]
        found_keywords = [kw for kw in tech_keywords if kw.lower() in text.lower()]
        return found_keywords
    
    def _create_optimized_summary(self, job_description: str, candidate_profile: str) -> str:
        """Create optimized professional summary"""
        return f"Experienced Software Engineer with {len(self._extract_keywords(job_description))} relevant skills applying for {job_description[:100]}..."
    
    def _calculate_match_score(self, job_description: str, candidate_profile: str) -> float:
        """Calculate match score between job and candidate"""
        return min(100.0, len(self._extract_keywords(job_description)) * 10)
    
    def _generate_tailored_content(self, job_description: str, candidate_profile: str) -> str:
        """Generate tailored content for application"""
        return f"Application tailored for {job_description[:200]}..."

class PortalSubmitter:
    """Base class for job portal submission handlers"""
    
    def __init__(self, config: ApplicationConfig):
        self.config = config
        self.session = None
        self.last_request_time = 0
    
    async def submit_application(self, job: Dict, optimized_resume: Dict) -> Dict:
        """Submit application to job portal"""
        raise NotImplementedError("Subclasses must implement submit_application")
    
    def _rate_limit(self):
        """Implement rate limiting for portal requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        min_interval = 60.0 / self.config.applications_per_minute
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            logger.info(f"Rate limiting: waiting {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()

class JobApplicationEngine:
    """Main application engine orchestrating job applications"""
    
    def __init__(self, config: ApplicationConfig):
        self.config = config
        self.applications_submitted = 0
        self.resume_optimizer = None
        self.resume_path: Optional[str] = None
        # NOTE: Portal submitters were removed (audit item 41). This legacy
        # engine now delegates to the real evidence-based pipeline in
        # jobpilot.services.auto_apply — it never fabricates "submitted" results.
        self.application_history = []
    
    def initialize(self, resume_path: str):
        """Initialize application engine with resume and portal handlers"""
        self.resume_optimizer = ResumeOptimizer(resume_path)
        self.resume_path = resume_path
        
        logger.info("Job Application Engine initialized successfully")
    
    async def apply_to_job(self, job: Dict) -> Dict:
        """
        Apply to a single job via the real evidence-based pipeline
        (jobpilot.services.auto_apply.apply_to_job). "submitted" is returned
        ONLY when real browser/SMTP evidence confirms the submission.
        """
        if self.applications_submitted >= self.config.max_daily_applications:
            logger.warning("Daily application limit reached")
            return {"status": "skipped", "reason": "daily_limit_reached"}

        import hashlib

        try:
            from jobpilot.services.auto_apply import apply_to_job as real_apply_to_job
        except ImportError as exc:
            logger.error("Real auto-apply pipeline unavailable: %s", exc)
            return {"status": "failed", "reason": f"auto_apply unavailable: {exc}"}

        job_url = job.get("url") or ""
        legacy_job_id = "legacy_" + hashlib.sha256(job_url.encode()).hexdigest()[:16]

        success = await asyncio.to_thread(
            real_apply_to_job,
            job_id=legacy_job_id,
            job_title=job.get("title", ""),
            company=job.get("company", ""),
            source=job.get("source", ""),
            apply_url=job_url or None,
            score=int(job.get("match_score", 0) or 0),
            description=job.get("description", ""),
            cv_path=self.resume_path,
            dry_run=False,
        )

        application_result = {
            "url": job_url,
            "title": job.get("title"),
            "company": job.get("company"),
            "source": job.get("source"),
            "applied_at": datetime.now(),
            # Honest mapping: the real pipeline returns True only when
            # affirmative submission evidence was detected.
            "status": "submitted" if success else "failed",
        }

        # Track application
        self.applications_submitted += 1
        self.application_history.append(application_result)

        return application_result
    
    def _get_candidate_profile(self) -> str:
        """Get candidate profile from resume"""
        return """Computer Science graduate (2026), Junior Software Engineer / AI Engineer skilled in 
Python (FastAPI, Django, Flask), React, Next.js, Node.js, NestJS, LangChain, RAG, vector databases (MongoDB Atlas), 
and LLM integration. Looking for Remote, USD/GBP pay, 0-2 years experience roles, 
specifically AI Engineer, AI Full Stack Developer, Full Stack Developer, or Backend Engineer.
Candidate is based in Pakistan and accepts Worldwide Remote / Work from Anywhere / Remote in Pakistan / UK Remote."""
    
    def get_application_stats(self) -> Dict:
        """Get application statistics"""
        return {
            "total_applications": self.applications_submitted,
            "max_daily_limit": self.config.max_daily_applications,
            "daily_remaining": self.config.max_daily_applications - self.applications_submitted,
            "success_rate": len([a for a in self.application_history if a.get("status") == "submitted"]) / max(1, len(self.application_history))
        }

# Example usage and testing
if __name__ == "__main__":
    # Test the application engine
    config = ApplicationConfig(
        max_daily_applications=10,
        applications_per_minute=1
    )
    
    engine = JobApplicationEngine(config)
    
    # Initialize with resume (would be actual path in production)
    engine.initialize("Ibrahim_Hamid_Resume.pdf")
    
    print(f"Application Engine initialized: {engine.get_application_stats()}")
    
    # Example job for testing
    test_job = {
        "title": "AI Engineer",
        "company": "Tech Corp",
        "url": "https://example.com/job/123",
        "source": "LinkedIn - TechCorp",
        "description": "Looking for AI Engineer with Python and FastAPI experience"
    }
    
    # Apply to test job
    result = asyncio.run(engine.apply_to_job(test_job))
    print(f"Application result: {result}")
    print(f"Engine stats: {engine.get_application_stats()}")