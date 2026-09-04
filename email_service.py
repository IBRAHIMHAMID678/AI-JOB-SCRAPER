"""
Email Notification Service - Handles application confirmations and notifications
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List, Optional
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmailService:
    """Email service for job application notifications"""
    
    def __init__(self, smtp_config: Dict):
        self.smtp_config = smtp_config
        self.email_templates = self._load_email_templates()
        self.notification_history = []
    
    def _load_email_templates(self) -> Dict:
        """Load email templates for different notification types"""
        return {
            "application_confirmation": {
                "subject": "Application Submitted Successfully",
                "template": """
Dear Applicant,

Great news! Your application has been successfully submitted to {company} for the {title} position.

Application Details:
- Job: {title}
- Company: {company}
- Application Reference: {application_id}
- Submitted On: {submitted_date}
- Estimated Response Time: {response_time}

Next Steps:
1. You will receive updates about this application in your dashboard
2. Check your email for any additional requirements
3. Monitor your application status in real-time

Best regards,
AI Job Scraper Team
                """
            },
            "application_status_update": {
                "subject": "Application Status Update",
                "template": """
Application Status Update

Dear Applicant,

We have an update regarding your application to {title} at {company}:

Status: {status}
Updated On: {update_date}

Details:
{details}

You can view all your applications and their status in your dashboard.

Best regards,
AI Job Scraper Team
                """
            },
            "daily_summary": {
                "subject": "Daily Application Summary - {date}",
                "template": """
Daily Application Summary

Hi {applicant_name},

Here's a summary of your job applications today:

Applications Today: {applications_count}
Successful Applications: {successful_count}
Pending Applications: {pending_count}

Top Applied Positions:
{top_positions_list}

Recent Activity:
{recent_activity}

You can view detailed statistics and manage all applications in your dashboard.

Best regards,
AI Job Scraper Team
                """
            }
        }
    
    async def send_application_confirmation(self, application_data: Dict, recipient_email: str) -> bool:
        """Send application confirmation email"""
        try:
            template = self.email_templates["application_confirmation"]
            
            email_content = template["template"].format(
                company=application_data.get("company", "Unknown Company"),
                title=application_data.get("title", "Unknown Position"),
                application_id=application_data.get("confirmation", {}).get("reference_id", "N/A"),
                submitted_date=application_data.get("applied_at", datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
                response_time=application_data.get("confirmation", {}).get("estimated_response", "2-3 weeks")
            )
            
            email_message = self._create_email_message(
                recipient_email,
                template["subject"],
                email_content
            )
            
            await self._send_email(email_message)
            
            # Log notification
            self.notification_history.append({
                "type": "application_confirmation",
                "recipient": recipient_email,
                "application_id": application_data.get("confirmation", {}).get("reference_id"),
                "sent_at": datetime.now(),
                "status": "sent"
            })
            
            logger.info(f"Application confirmation sent to {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send application confirmation to {recipient_email}: {e}")
            return False
    
    async def send_status_update(self, application_data: Dict, new_status: str, recipient_email: str, details: str = "") -> bool:
        """Send application status update email"""
        try:
            template = self.email_templates["application_status_update"]
            
            email_content = template["template"].format(
                status=new_status,
                update_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                title=application_data.get("title", "Unknown Position"),
                company=application_data.get("company", "Unknown Company"),
                details=details
            )
            
            email_message = self._create_email_message(
                recipient_email,
                template["subject"],
                email_content
            )
            
            await self._send_email(email_message)
            
            # Log notification
            self.notification_history.append({
                "type": "status_update",
                "recipient": recipient_email,
                "application_id": application_data.get("confirmation", {}).get("reference_id"),
                "new_status": new_status,
                "sent_at": datetime.now(),
                "status": "sent"
            })
            
            logger.info(f"Status update sent to {recipient_email}: {new_status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send status update to {recipient_email}: {e}")
            return False
    
    async def send_daily_summary(self, applicant_name: str, recipient_email: str, summary_data: Dict) -> bool:
        """Send daily application summary"""
        try:
            template = self.email_templates["daily_summary"]
            
            # Generate top positions list
            top_positions = summary_data.get("top_applied_positions", [])
            top_positions_list = "\n".join([
                f"- {pos['title']} at {pos['company']} ({pos['applications']} applications)"
                for pos in top_positions[:5]
            ])
            
            # Generate recent activity
            recent_activity = summary_data.get("recent_activity", [])
            recent_activity_text = "\n".join([
                f"- {activity['date']}: {activity['description']}"
                for activity in recent_activity[-5:]
            ])
            
            email_content = template["template"].format(
                applicant_name=applicant_name,
                date=datetime.now().strftime("%Y-%m-%d"),
                applications_count=summary_data.get("applications_count", 0),
                successful_count=summary_data.get("successful_count", 0),
                pending_count=summary_data.get("pending_count", 0),
                top_positions_list=top_positions_list,
                recent_activity=recent_activity_text
            )
            
            email_message = self._create_email_message(
                recipient_email,
                template["subject"].format(date=datetime.now().strftime("%Y-%m-%d")),
                email_content
            )
            
            await self._send_email(email_message)
            
            # Log notification
            self.notification_history.append({
                "type": "daily_summary",
                "recipient": recipient_email,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "applications_count": summary_data.get("applications_count", 0),
                "sent_at": datetime.now(),
                "status": "sent"
            })
            
            logger.info(f"Daily summary sent to {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send daily summary to {recipient_email}: {e}")
            return False
    
    def _create_email_message(self, recipient: str, subject: str, body: str) -> MIMEMultipart:
        """Create email message"""
        message = MIMEMultipart()
        message["From"] = self.smtp_config.get("sender_email", "jobs@example.com")
        message["To"] = recipient
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))
        
        return message
    
    async def _send_email(self, message: MIMEMultipart) -> None:
        """Send email using SMTP"""
        try:
            if self.smtp_config.get("use_smtp", True):
                server = smtplib.SMTP(
                    self.smtp_config.get("smtp_server", "smtp.example.com"),
                    self.smtp_config.get("smtp_port", 587)
                )
                server.starttls()
                server.login(
                    self.smtp_config.get("username", ""),
                    self.smtp_config.get("password", "")
                )
                server.send_message(message)
                server.quit()
                logger.info(f"Email sent successfully to {message['To']}")
            else:
                # For demo purposes, just log the email
                logger.info(f"Email would be sent to {message['To']}: {message['Subject']}")
                
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise
    
    def get_notification_stats(self) -> Dict:
        """Get email notification statistics"""
        total_sent = len(self.notification_history)
        sent_today = len([
            n for n in self.notification_history 
            if n.get("sent_at", datetime.min).date() == datetime.now().date()
        ])
        
        return {
            "total_notifications_sent": total_sent,
            "notifications_sent_today": sent_today,
            "notification_types": self._get_notification_type_counts(),
            "last_notification": self._get_last_notification_time()
        }
    
    def _get_notification_type_counts(self) -> Dict:
        """Get count of notifications by type"""
        type_counts = {}
        for notification in self.notification_history:
            notif_type = notification.get("type", "unknown")
            type_counts[notif_type] = type_counts.get(notif_type, 0) + 1
        return type_counts
    
    def _get_last_notification_time(self) -> Optional[datetime]:
        """Get time of last notification"""
        if not self.notification_history:
            return None
        return max(n.get("sent_at", datetime.min) for n in self.notification_history)
    
    def get_delivery_report(self) -> Dict:
        """Get delivery report for applications"""
        # This would integrate with application tracking system
        # to provide comprehensive delivery statistics
        return {
            "delivered_applications": len([
                n for n in self.notification_history 
                if n.get("type") == "application_confirmation"
            ]),
            "delivered_status_updates": len([
                n for n in self.notification_history 
                if n.get("type") == "status_update"
            ]),
            "delivered_daily_summaries": len([
                n for n in self.notification_history 
                if n.get("type") == "daily_summary"
            ]),
            "overall_delivery_rate": self._calculate_delivery_rate()
        }
    
    def _calculate_delivery_rate(self) -> float:
        """Calculate overall delivery rate"""
        total_notifications = len(self.notification_history)
        if total_notifications == 0:
            return 0.0
        
        delivered = sum(1 for n in self.notification_history if n.get("status") == "sent")
        return (delivered / total_notifications) * 100

# Example usage and testing
if __name__ == "__main__":
    # Configure email service (using example config)
    email_config = {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "username": "your-email@gmail.com",
        "password": "your-app-password",
        "sender_email": "jobs@example.com",
        "use_smtp": False  # Set to True for real SMTP
    }
    
    # Initialize email service
    email_service = EmailService(email_config)
    
    # Test application confirmation
    test_application = {
        "title": "AI Engineer",
        "company": "Tech Corp",
        "applied_at": datetime.now(),
        "confirmation": {
            "reference_id": "TEST-123",
            "estimated_response": "2-3 weeks"
        }
    }
    
    # Run async tests
    import asyncio
    
    async def test_email_service():
        print("Testing email service...")
        
        # Test application confirmation
        confirmation_result = await email_service.send_application_confirmation(
            test_application, "test@example.com"
        )
        print(f"Application confirmation sent: {confirmation_result}")
        
        # Test status update
        status_result = await email_service.send_status_update(
            test_application, "Under Review", "test@example.com", "Your application is being reviewed"
        )
        print(f"Status update sent: {status_result}")
        
        # Get statistics
        stats = email_service.get_notification_stats()
        print(f"Email service stats: {stats}")
        
        # Get delivery report
        delivery_report = email_service.get_delivery_report()
        print(f"Delivery report: {delivery_report}")
    
    # Run tests
    asyncio.run(test_email_service())