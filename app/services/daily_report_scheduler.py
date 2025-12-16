"""
Daily Report Scheduler - Automated email reports at scheduled time

Features:
- Schedule daily alert summary emails
- Configurable send time via environment variable
- Background thread execution
- Automatic AI analysis integration
"""
import os
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv

from app.services.alert_summarization_service import get_alert_summarization_service
from app.services.email_service import get_email_service
from app.services.llm_service import LLMService

load_dotenv()

logger = logging.getLogger(__name__)


class DailyReportScheduler:
    """Scheduler for automated daily security reports"""
    
    def __init__(self):
        """Initialize scheduler"""
        self.alert_service = get_alert_summarization_service()
        self.email_service = get_email_service()
        self.llm_service = LLMService()
        self.running = False
        self.thread = None
        
        # Get configuration from environment
        self.send_time = os.getenv('DAILY_REPORT_TIME', '07:00')  # Default 7:00 AM
        self.recipient_email = os.getenv('FROM_EMAIL', '')  # Send to same email by default
        self.enabled = self.email_service.enabled and self.recipient_email
        
        if self.enabled:
            logger.info(f"Daily report scheduler initialized: {self.send_time} → {self.recipient_email}")
        else:
            logger.warning("  Daily report scheduler disabled (missing email config)")
    
    def start(self):
        """Start scheduler in background thread"""
        if not self.enabled:
            logger.warning("  Daily report scheduler not enabled")
            return
        
        if self.running:
            logger.warning("  Daily report scheduler already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.thread.start()
        logger.info(f" Daily report scheduler started (send time: {self.send_time})")
    
    def stop(self):
        """Stop scheduler"""
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join(timeout=2)
            logger.info(" Daily report scheduler stopped")
    
    def _scheduler_loop(self):
        """Main scheduler loop - optimized to sleep until next scheduled time"""
        last_sent_date = None  # Track last sent date to avoid duplicates
        
        while self.running:
            try:
                now = datetime.now()
                current_date = now.date()
                
                # Check if already sent today
                if last_sent_date == current_date:
                    # Already sent today, sleep until tomorrow
                    next_send = self._calculate_next_send_time()
                    sleep_seconds = (next_send - now).total_seconds()
                    logger.info(f"📅 Report already sent today. Next send: {next_send.strftime('%Y-%m-%d %H:%M')}")
                    
                    # Sleep in 5-minute chunks to allow graceful shutdown
                    while sleep_seconds > 0 and self.running:
                        chunk = min(300, sleep_seconds)  # Sleep max 5 minutes at a time
                        time.sleep(chunk)
                        sleep_seconds -= chunk
                    continue
                
                # Check if it's time to send
                if self._should_send_report():
                    logger.info("⏰ Sending scheduled daily report...")
                    self._send_daily_report()
                    last_sent_date = current_date
                    
                    # Calculate next send time (tomorrow at scheduled time)
                    next_send = self._calculate_next_send_time()
                    sleep_seconds = (next_send - datetime.now()).total_seconds()
                    logger.info(f"✅ Report sent. Next send: {next_send.strftime('%Y-%m-%d %H:%M')} (in {sleep_seconds/3600:.1f}h)")
                else:
                    # Calculate seconds until next check
                    next_send = self._calculate_next_send_time()
                    sleep_seconds = (next_send - now).total_seconds()
                    
                    # If next send is today and soon, check more frequently
                    if next_send.date() == current_date and sleep_seconds < 600:  # Within 10 minutes
                        time.sleep(30)  # Check every 30 seconds
                    else:
                        # Sleep until 5 minutes before scheduled time
                        safe_sleep = max(60, sleep_seconds - 300)  # Wake up 5 min early, minimum 1 min
                        time.sleep(min(safe_sleep, 3600))  # Max 1 hour sleep chunks
            
            except Exception as e:
                logger.error(f"❌ Scheduler error: {str(e)}")
                time.sleep(60)
    
    def _calculate_next_send_time(self) -> datetime:
        """Calculate next scheduled send time"""
        try:
            now = datetime.now()
            target_hour, target_minute = map(int, self.send_time.split(':'))
            
            # Create datetime for today's scheduled time
            next_send = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            
            # If today's time has passed, schedule for tomorrow
            if next_send <= now:
                next_send += timedelta(days=1)
            
            return next_send
        
        except Exception as e:
            logger.error(f"❌ Error calculating next send time: {str(e)}")
            # Fallback: send in 24 hours
            return datetime.now() + timedelta(days=1)
    
    def _should_send_report(self) -> bool:
        """Check if current time matches scheduled send time"""
        try:
            now = datetime.now()
            target_hour, target_minute = map(int, self.send_time.split(':'))
            
            # Check if current time is within 1 minute of target time
            return (now.hour == target_hour and 
                    abs(now.minute - target_minute) < 1)
        
        except Exception as e:
            logger.error(f"❌ Error parsing send time '{self.send_time}': {str(e)}")
            return False
    
    def _send_daily_report(self):
        """Generate and send daily security report"""
        try:
            # Get alert summary for last 24 hours (daily report sent at 7am)
            logger.info("📊 Generating alert summary for last 24 hours...")
            summary_data = self.alert_service.summarize_alerts(time_window_minutes=1440)  # 24 hours
            
            if not summary_data.get('success'):
                logger.error(f"❌ Alert summary failed: {summary_data.get('error', 'Unknown error')}")
                return
            
            # Get AI analysis and recommendations
            logger.info("🤖 Generating AI analysis...")
            ai_analysis = self._get_ai_analysis(summary_data)
            
            # Add AI analysis to summary data
            summary_data['ai_analysis'] = ai_analysis
            
            # Send email
            logger.info(f" Sending email to {self.recipient_email}...")
            success = self.email_service.send_alert_summary_email(
                to_email=self.recipient_email,
                summary_data=summary_data
            )
            
            if success:
                logger.info(" Daily report sent successfully")
            else:
                logger.error(" Failed to send daily report email")
        
        except Exception as e:
            logger.error(f" Failed to send daily report: {str(e)}")
    
    def _get_ai_analysis(self, summary_data: dict) -> str:
        """
        Get AI analysis and recommendations using LLM + RAG
        
        Args:
            summary_data: Alert summary data
        
        Returns:
            str: AI-generated analysis and recommendations
        """
        try:
            # Build context from summary
            risk_score = summary_data.get('risk_score', 0)
            count = summary_data.get('count', 0)
            grouped_alerts = summary_data.get('grouped_alerts', [])
            
            # Extract top patterns
            patterns = {}
            for group in grouped_alerts[:5]:  # Top 5 groups
                pattern = group.get('pattern', 'unknown')
                if pattern not in patterns:
                    patterns[pattern] = {
                        'count': 0,
                        'severity': group.get('severity', 'INFO'),
                        'ips': set()
                    }
                patterns[pattern]['count'] += group.get('alert_count', 0)
                patterns[pattern]['ips'].add(group.get('source_ip', 'unknown'))
            
            # Build query for AI
            pattern_summary = []
            for pattern, data in patterns.items():
                pattern_summary.append(
                    f"- {pattern.upper()}: {data['count']} alerts, "
                    f"severity {data['severity']}, "
                    f"{len(data['ips'])} unique IPs"
                )
            
            query = f"""Analyze this security alert summary and provide brief recommendations:

Risk Score: {risk_score:.1f}/100
Total Alerts: {count}
Time Window: Last 7 days

Top Attack Patterns:
{chr(10).join(pattern_summary)}

Provide:
1. Brief threat assessment (2-3 sentences)
2. Top 3 recommended actions (concise, bullet points)
3. Any MITRE ATT&CK techniques to investigate

Keep response under 300 words, actionable and specific."""
            
            # Use LLM with RAG
            response = self.llm_service.ask_rag(query)
            
            if response.get('status') == 'success':
                return response.get('answer', 'AI analysis unavailable')
            else:
                logger.warning(f" AI analysis failed: {response.get('error', 'Unknown')}")
                return "AI analysis temporarily unavailable. Please review alert summary above."
        
        except Exception as e:
            logger.error(f" AI analysis error: {str(e)}")
            return "AI analysis temporarily unavailable due to error."
    
    def send_report_now(self, recipient_email: Optional[str] = None) -> bool:
        """
        Send report immediately (for testing or manual trigger)
        
        Args:
            recipient_email: Override default recipient email
        
        Returns:
            bool: True if sent successfully
        """
        try:
            target_email = recipient_email or self.recipient_email
            
            # Get alert summary
            summary_data = self.alert_service.summarize_alerts()
            
            if not summary_data.get('success'):
                return False
            
            # Get AI analysis
            ai_analysis = self._get_ai_analysis(summary_data)
            summary_data['ai_analysis'] = ai_analysis
            
            # Send email
            return self.email_service.send_alert_summary_email(
                to_email=target_email,
                summary_data=summary_data
            )
        
        except Exception as e:
            logger.error(f" Failed to send immediate report: {str(e)}")
            return False


# Singleton instance
_scheduler_instance = None


def get_daily_report_scheduler() -> DailyReportScheduler:
    """Get singleton instance of daily report scheduler"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = DailyReportScheduler()
    return _scheduler_instance
