"""
Job Application Orchestrator - Main orchestrator for automated job applications
Integrates scraper, application engine, and email service
"""

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional
from application_engine import JobApplicationEngine, ApplicationConfig
from email_service import EmailService

try:
    from jobpilot.services.auto_apply import apply_to_job as real_apply_to_job
except ImportError:  # pragma: no cover - only when jobpilot package is unavailable
    real_apply_to_job = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JobApplicationOrchestrator:
    """Main orchestrator for job application pipeline"""
    
    def __init__(self, config: Dict, resume_path: str):
        self.config = config
        self.resume_path = resume_path
        self.email_service = EmailService(config.get("email", {}))
        self.application_engine = JobApplicationEngine(config.get("application_engine", ApplicationConfig()))
        self.scraper_results = []
        self.application_results = []
        self.daily_summary_sent = False
    
    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing Job Application Orchestrator...")
        
        # Initialize application engine with resume
        self.application_engine.initialize(self.resume_path)
        
        # Configure email service if needed
        if "smtp_server" in self.config.get("email", {}):
            logger.info("Email service configured for notifications")
        
        logger.info("Job Application Orchestrator initialized successfully")
    
    async def run_application_pipeline(self, scraper_results: List[Dict]) -> Dict:
        """Run the complete application pipeline"""
        logger.info(f"Starting application pipeline for {len(scraper_results)} scraped jobs")
        
        self.scraper_results = scraper_results
        application_count = 0
        success_count = 0
        failed_count = 0
        
        # Sort jobs by match score and priority
        sorted_jobs = sorted(scraper_results, key=lambda x: x.get("match_score", 0), reverse=True)
        
        for job in sorted_jobs:
            try:
                # Skip jobs that don't meet application threshold
                if job.get("match_score", 0) < 60:
                    logger.info(f"Skipping job with low match score: {job.get('title', 'Unknown')} ({job.get('match_score', 0)}%)")
                    continue
                
                # Check if we have capacity for another application
                if application_count >= self.application_engine.config.max_daily_applications:
                    logger.warning("Daily application limit reached. Stopping application pipeline.")
                    break
                
                # Apply to job via the REAL evidence-based pipeline
                # (jobpilot.services.auto_apply). A job counts as "submitted"
                # ONLY when affirmative browser/SMTP evidence confirms it —
                # never simulated (audit item 41).
                logger.info(f"Applying to {job.get('title', 'Unknown')} at {job.get('company', 'Unknown')}...")
                if real_apply_to_job is None:
                    logger.error("Real auto-apply pipeline unavailable; marking failed (no fake success).")
                    application_result = {
                        "url": job.get("url"),
                        "title": job.get("title"),
                        "company": job.get("company"),
                        "source": job.get("source"),
                        "applied_at": datetime.now(),
                        "status": "failed",
                        "reason": "auto_apply pipeline unavailable",
                    }
                else:
                    job_url = job.get("url") or ""
                    legacy_job_id = "legacy_" + hashlib.sha256(job_url.encode()).hexdigest()[:16]
                    submitted = await asyncio.to_thread(
                        real_apply_to_job,
                        job_id=legacy_job_id,
                        job_title=job.get("title", "Unknown"),
                        company=job.get("company", "Unknown"),
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
                        # Honest: True only when the pipeline verified real submission evidence.
                        "status": "submitted" if submitted else "failed",
                    }
                
                self.application_results.append(application_result)
                application_count += 1
                
                if application_result.get("status") == "submitted":
                    success_count += 1
                    
                    # Send application confirmation email if email service is configured
                    if "smtp_server" in self.config.get("email", {}):
                        await self.email_service.send_application_confirmation(
                            application_result,
                            self.config.get("applicant_email", "applicant@example.com")
                        )
                else:
                    failed_count += 1
                
                # Rate limiting between applications
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error applying to job {job.get('title', 'Unknown')}: {e}")
                failed_count += 1
                continue
        
        # Generate daily summary if needed
        if not self.daily_summary_sent and application_count > 0:
            await self._send_daily_summary(application_count, success_count, failed_count)
            self.daily_summary_sent = True
        
        # Generate pipeline summary
        summary = {
            "total_jobs_analyzed": len(scraper_results),
            "applications_attempted": application_count,
            "applications_successful": success_count,
            "applications_failed": failed_count,
            "success_rate": (success_count / max(1, application_count)) * 100,
            "engine_stats": self.application_engine.get_application_stats(),
            "email_stats": self.email_service.get_notification_stats(),
            "completed_at": datetime.now().isoformat()
        }
        
        logger.info(f"Application pipeline completed. Success rate: {summary['success_rate']:.1f}%")
        return summary
    
    async def _send_daily_summary(self, attempted: int, successful: int, failed: int):
        """Send daily application summary"""
        try:
            summary_data = {
                "applications_count": attempted,
                "successful_count": successful,
                "pending_count": failed,
                "top_applied_positions": self._get_top_applied_positions(),
                "recent_activity": self._get_recent_activity()
            }
            
            await self.email_service.send_daily_summary(
                "Applicant",
                self.config.get("applicant_email", "applicant@example.com"),
                summary_data
            )
            
            logger.info("Daily summary email sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send daily summary: {e}")
    
    def _get_top_applied_positions(self) -> List[Dict]:
        """Get list of top applied positions"""
        position_counts = {}
        for app in self.application_results:
            if app.get("status") == "submitted":
                title = app.get("title", "Unknown")
                position_counts[title] = position_counts.get(title, 0) + 1
        
        # Sort by count and return top 5
        sorted_positions = sorted(position_counts.items(), key=lambda x: x[1], reverse=True)
        return [
            {"title": title, "applications": count}
            for title, count in sorted_positions[:5]
        ]
    
    def _get_recent_activity(self) -> List[Dict]:
        """Get recent application activity"""
        recent_apps = []
        for app in self.application_results[-5:]:
            if app.get("status") == "submitted":
                recent_apps.append({
                    "date": app.get("applied_at", datetime.now()).strftime("%Y-%m-%d %H:%M"),
                    "description": f"Applied to {app.get('title', 'Unknown')} at {app.get('company', 'Unknown')}"
                })
        return recent_apps
    
    def get_pipeline_status(self) -> Dict:
        """Get current pipeline status"""
        return {
            "scraper_results_count": len(self.scraper_results),
            "applications_submitted": len(self.application_results),
            "application_engine_stats": self.application_engine.get_application_stats(),
            "email_service_stats": self.email_service.get_notification_stats(),
            "daily_summary_sent": self.daily_summary_sent
        }

# Example usage and testing
if __name__ == "__main__":
    # Configuration
    config = {
        "application_engine": ApplicationConfig(
            max_daily_applications=10,
            applications_per_minute=1,
            retry_attempts=3
        ),
        "email": {
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "username": "your-email@gmail.com",
            "password": "your-app-password",
            "sender_email": "jobs@example.com",
            "use_smtp": False
        },
        "applicant_email": "applicant@example.com"
    }
    
    # Initialize orchestrator
    async def test_orchestrator():
        orchestrator = JobApplicationOrchestrator(config, "Ibrahim_Hamid_Resume.pdf")
        await orchestrator.initialize()
        
        # Simulate scraper results
        mock_scraper_results = [
            {
                "title": "AI Engineer",
                "company": "Tech Corp",
                "url": "https://example.com/job/1",
                "source": "LinkedIn",
                "match_score": 85,
                "description": "Looking for AI Engineer with Python and FastAPI experience"
            },
            {
                "title": "Full Stack Developer",
                "company": "StartupXYZ",
                "url": "https://example.com/job/2",
                "source": "Indeed",
                "match_score": 75,
                "description": "Full stack position with React and Node.js"
            },
            {
                "title": "Backend Engineer",
                "company": "DataSystems",
                "url": "https://example.com/job/3",
                "source": "Remote OK",
                "match_score": 55,
                "description": "Backend position with Python experience"
            }
        ]
        
        # Run application pipeline
        summary = await orchestrator.run_application_pipeline(mock_scraper_results)
        print("Application Pipeline Summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")
        
        # Get pipeline status
        status = orchestrator.get_pipeline_status()
        print("\nPipeline Status:")
        for key, value in status.items():
            print(f"  {key}: {value}")
    
    # Run test
    asyncio.run(test_orchestrator())