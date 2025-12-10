"""
Email Service - Send daily security reports via SMTP

Features:
- Send daily alert summary reports
- Schedule email sending
- HTML formatting support
- Embedded visualization charts
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP"""
    
    def __init__(self):
        """Initialize email service with SMTP configuration"""
        self.from_email = os.getenv('FROM_EMAIL', '')
        self.to_emails = os.getenv('TO_EMAILS', self.from_email)  # Default to FROM_EMAIL if not set
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.email_password = os.getenv('EMAIL_PASSWORD', '')
        
        if not self.from_email or not self.email_password:
            logger.warning("⚠️  Email credentials not configured in .env")
            self.enabled = False
        else:
            self.enabled = True
            logger.info(f"✓ Email service initialized: {self.from_email} → {self.to_emails}")
    
    def send_alert_summary_email(
        self,
        to_email: str,
        summary_data: Dict[str, Any],
        subject: Optional[str] = None
    ) -> bool:
        """
        Send alert summary email with visualization
        
        Args:
            to_email: Recipient email address
            summary_data: Alert summary data from AlertSummarizationService
            subject: Email subject (optional, auto-generated if None)
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.error("❌ Email service not configured")
            return False
        
        try:
            # Extract data
            risk_score = summary_data.get('risk_score', 0)
            summary_text = summary_data.get('summary', '')
            ai_analysis = summary_data.get('ai_analysis', '')
            grouped_alerts = summary_data.get('grouped_alerts', [])
            count = summary_data.get('count', 0)
            time_window = summary_data.get('time_window_minutes', 10080) // 1440  # Convert to days
            
            # Generate subject if not provided
            if subject is None:
                risk_level = self._get_risk_level(risk_score)
                subject = f"🚨 [{risk_level}] Security Alert Summary - {datetime.now().strftime('%Y-%m-%d')}"
            
            # Create HTML email
            html_content = self._build_html_email(
                summary_text=summary_text,
                ai_analysis=ai_analysis,
                risk_score=risk_score,
                grouped_alerts=grouped_alerts,
                count=count,
                time_window=time_window
            )
            
            # Create message
            msg = MIMEMultipart('related')
            msg['From'] = self.from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Attach HTML body
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Attach visualization if available
            visualization_b64 = summary_data.get('visualization')
            if visualization_b64:
                import base64
                img_data = base64.b64decode(visualization_b64)
                img = MIMEImage(img_data, name='chart.png')
                img.add_header('Content-ID', '<visualization_chart>')
                msg.attach(img)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.from_email, self.email_password)
                server.send_message(msg)
            
            logger.info(f"✅ Alert summary email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send email: {str(e)}")
            return False
    
    def _get_risk_level(self, risk_score: float) -> str:
        """Get risk level label from score"""
        if risk_score >= 70:
            return "CRITICAL"
        elif risk_score >= 50:
            return "HIGH"
        elif risk_score >= 30:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _build_html_email(
        self,
        summary_text: str,
        ai_analysis: str,
        risk_score: float,
        grouped_alerts: list,
        count: int,
        time_window: int
    ) -> str:
        """Build HTML email content"""
        risk_level = self._get_risk_level(risk_score)
        risk_color = self._get_risk_color(risk_score)
        
        # Convert markdown-like formatting to HTML
        summary_html = summary_text.replace('\n', '<br>')
        summary_html = summary_html.replace('<b>', '<strong>').replace('</b>', '</strong>')
        summary_html = summary_html.replace('<code>', '<code style="background: #f4f4f4; padding: 2px 4px; border-radius: 3px;">').replace('</code>', '</code>')
        
        ai_analysis_html = ai_analysis.replace('\n', '<br>') if ai_analysis else ''
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="color-scheme" content="light">
    <meta name="supported-color-schemes" content="light">
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333333 !important;
            background-color: #ffffff !important;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, {risk_color} 0%, {risk_color}dd 100%) !important;
            color: #ffffff !important;
            padding: 30px;
            border-radius: 10px;
            text-align: center;
            margin-bottom: 20px;
        }}
        .risk-score {{
            font-size: 48px;
            font-weight: bold;
            margin: 10px 0;
            color: #ffffff !important;
        }}
        .risk-label {{
            font-size: 24px;
            font-weight: bold;
            color: #ffffff !important;
        }}
        .section {{
            background: #f9f9f9 !important;
            color: #333333 !important;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            border-left: 4px solid {risk_color};
        }}
        .section h2 {{
            margin-top: 0;
            color: {risk_color} !important;
        }}
        .stats-banner {{
            background: linear-gradient(135deg, {risk_color}20 0%, {risk_color}10 100%) !important;
            border: 2px solid {risk_color};
            border-radius: 10px;
            padding: 30px 20px;
            margin: 20px auto;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 40px;
            max-width: 600px;
        }}
        .stat-item {{
            text-align: center;
            padding: 0 20px;
        }}
        .stat-item:not(:last-child) {{
            border-right: 2px solid {risk_color}40;
        }}
        .stat-value {{
            font-size: 42px;
            font-weight: bold;
            color: {risk_color} !important;
            margin-bottom: 5px;
        }}
        .stat-label {{
            font-size: 14px;
            font-weight: 600;
            color: #666666 !important;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .chart {{
            text-align: center;
            margin: 20px 0;
        }}
        .chart img {{
            max-width: 100%;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #dddddd;
            color: #666666 !important;
            font-size: 12px;
            background-color: #ffffff !important;
        }}
        .ai-section {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
            color: #ffffff !important;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .ai-section h2 {{
            margin-top: 0;
            color: #ffffff !important;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            background: #ffffff !important;
        }}
        th {{
            background: {risk_color} !important;
            color: #ffffff !important;
            padding: 10px;
            text-align: left;
            border: 1px solid #dddddd;
        }}
        td {{
            padding: 10px;
            border: 1px solid #dddddd;
            color: #333333 !important;
            background: #ffffff !important;
        }}
        p, div, span {{
            color: #333333 !important;
        }}
        strong, b {{
            color: #333333 !important;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="risk-label">{risk_level} RISK</div>
        <div class="risk-score">{risk_score:.1f}/100</div>
        <p style="color: #ffffff !important;">Security Alert Summary Report</p>
        <p style="color: #ffffff !important;">{datetime.now().strftime('%B %d, %Y at %H:%M %Z')}</p>
    </div>
    
    <div class="stats-banner">
        <div class="stat-item">
            <div class="stat-value">{count}</div>
            <div class="stat-label">Total Alerts</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">{len(grouped_alerts)}</div>
            <div class="stat-label">Alert Groups</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">{time_window}d</div>
            <div class="stat-label">Time Window</div>
        </div>
    </div>
    
    <div class="section">
        <h2>📊 Alert Summary</h2>
        <div style="color: #333333 !important;">{summary_html}</div>
    </div>
"""
        
        # Add AI analysis if available
        if ai_analysis:
            html += f"""
    <div class="ai-section">
        <h2>🤖 AI Analysis & Recommendations</h2>
        <div style="color: #ffffff !important;">{ai_analysis_html}</div>
    </div>
"""
        
        # Add visualization if available
        html += """
    <div class="chart">
        <h2 style="color: #333333 !important;">📈 Alert Visualization</h2>
        <img src="cid:visualization_chart" alt="Alert Visualization">
    </div>
    
    <div class="footer">
        <p style="color: #666666 !important;">This is an automated security report generated by <strong>Cyberfortress SmartXDR</strong></p>
        <p>Report Time: """ + datetime.now().isoformat() + """</p>
    </div>
</body>
</html>
"""
        return html
    
    def _get_risk_color(self, risk_score: float) -> str:
        """Get color based on risk score"""
        if risk_score >= 70:
            return "#d32f2f"  # Red
        elif risk_score >= 50:
            return "#f57c00"  # Orange
        elif risk_score >= 30:
            return "#fbc02d"  # Yellow
        else:
            return "#388e3c"  # Green


# Singleton instance
_email_service_instance = None


def get_email_service() -> EmailService:
    """Get singleton instance of email service"""
    global _email_service_instance
    if _email_service_instance is None:
        _email_service_instance = EmailService()
    return _email_service_instance
