"""
Severity Manager - Centralized risk level and severity calculations

This module provides a single source of truth for:
- Risk score thresholds
- Severity level labels  
- Color codes for UI
- Recommended actions based on risk level
"""
from enum import Enum
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


class RiskLevel(Enum):
    """Standard risk levels used across the application"""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass
class RiskThreshold:
    """Risk threshold configuration"""
    level: RiskLevel
    min_score: float
    color_hex: str
    color_name: str
    description: str


class SeverityManager:
    """
    Centralized manager for severity/risk calculations.
    
    Usage:
        from app.core.severity import severity_manager
        
        level = severity_manager.get_risk_level(75)  # "CRITICAL"
        color = severity_manager.get_risk_color(75)  # "#d32f2f"
        actions = severity_manager.get_recommendations(75)  # List of action strings
    """
    
    # Standard thresholds (score >= threshold = that level)
    # Order matters: check from highest to lowest
    THRESHOLDS: List[RiskThreshold] = [
        RiskThreshold(
            level=RiskLevel.CRITICAL,
            min_score=70.0,
            color_hex="#d32f2f",
            color_name="red",
            description="Immediate action required. Critical security incident."
        ),
        RiskThreshold(
            level=RiskLevel.HIGH,
            min_score=50.0,
            color_hex="#f57c00",
            color_name="orange",
            description="Significant security concern requiring prompt attention."
        ),
        RiskThreshold(
            level=RiskLevel.MEDIUM,
            min_score=30.0,
            color_hex="#fbc02d",
            color_name="yellow",
            description="Monitor closely. Take precautionary measures."
        ),
        RiskThreshold(
            level=RiskLevel.LOW,
            min_score=0.0,
            color_hex="#388e3c",
            color_name="green",
            description="Routine security activity. Continue standard monitoring."
        ),
    ]
    
    # Recommended actions by risk level
    RECOMMENDATIONS: Dict[RiskLevel, List[str]] = {
        RiskLevel.CRITICAL: [
            "IMMEDIATE: Block or isolate affected source IPs",
            "Investigate active sessions from affected IPs",
            "Review and reset credentials for compromised accounts",
            "Escalate to Security Operations Center (SOC)",
            "Document incident for forensic analysis",
        ],
        RiskLevel.HIGH: [
            "Conduct in-depth analysis of alert patterns",
            "Enable enhanced monitoring for affected assets",
            "Prepare incident response procedures",
            "Alert security team for investigation",
        ],
        RiskLevel.MEDIUM: [
            "Monitor trends and pattern changes",
            "Investigate high-confidence alerts",
            "Review firewall and access control rules",
            "Update threat intelligence",
        ],
        RiskLevel.LOW: [
            "Continue routine monitoring",
            "Archive alerts for audit trail",
            "Review and update detection rules",
        ],
    }
    
    # Attack pattern descriptions
    PATTERN_DESCRIPTIONS: Dict[str, str] = {
        "reconnaissance": "Information gathering to identify targets and vulnerabilities",
        "brute_force": "Credential attack attempts (login, password bruteforce)",
        "lateral_movement": "Movement within network to compromise additional systems",
        "exfiltration": "Data theft or unauthorized data transfer",
        "network_attack": "Network-level attacks (DDoS, flooding, amplification)",
        "malware": "Malware, trojan, virus, ransomware, or exploit detection",
        "web_attack": "Web application attacks (SQL injection, XSS, etc.)",
        "blocked_traffic": "Firewall blocked connections and denied traffic",
        "suspicious_traffic": "Suspicious or anomalous network activity",
        "unknown": "Unclassified security activity",
    }
    
    def get_threshold(self, score: float) -> RiskThreshold:
        """Get the threshold config for a given score"""
        for threshold in self.THRESHOLDS:
            if score >= threshold.min_score:
                return threshold
        # Fallback to lowest threshold
        return self.THRESHOLDS[-1]
    
    def get_risk_level(self, score: float) -> str:
        """
        Get risk level label from score.
        
        Args:
            score: Risk score (0-100)
            
        Returns:
            Risk level string: "CRITICAL", "HIGH", "MEDIUM", or "LOW"
        """
        return self.get_threshold(score).level.value
    
    def get_risk_level_enum(self, score: float) -> RiskLevel:
        """Get risk level as enum"""
        return self.get_threshold(score).level
    
    def get_risk_color(self, score: float) -> str:
        """
        Get color hex code for a risk score.
        
        Args:
            score: Risk score (0-100)
            
        Returns:
            Color hex string (e.g., "#d32f2f")
        """
        return self.get_threshold(score).color_hex
    
    def get_risk_color_name(self, score: float) -> str:
        """Get color name for a risk score"""
        return self.get_threshold(score).color_name
    
    def get_risk_description(self, score: float) -> str:
        """Get risk level description"""
        return self.get_threshold(score).description
    
    def get_recommendations(self, score: float) -> List[str]:
        """
        Get recommended actions for a risk score.
        
        Args:
            score: Risk score (0-100)
            
        Returns:
            List of recommended action strings
        """
        level = self.get_risk_level_enum(score)
        return self.RECOMMENDATIONS.get(level, self.RECOMMENDATIONS[RiskLevel.LOW])
    
    def get_pattern_description(self, pattern: str) -> str:
        """Get description for an attack pattern"""
        return self.PATTERN_DESCRIPTIONS.get(
            pattern.lower(), 
            "Security event"
        )
    
    def format_risk_assessment(self, score: float) -> str:
        """
        Format a complete risk assessment string.
        
        Args:
            score: Risk score (0-100)
            
        Returns:
            Formatted risk assessment string
        """
        level = self.get_risk_level(score)
        description = self.get_risk_description(score)
        return f"{level} RISK ({score:.1f}/100)\n{description}"
    
    def format_recommendations(self, score: float, numbered: bool = True) -> str:
        """
        Format recommendations as a string.
        
        Args:
            score: Risk score (0-100)
            numbered: Whether to number the recommendations
            
        Returns:
            Formatted recommendations string
        """
        recommendations = self.get_recommendations(score)
        if numbered:
            return "\n".join(f"  {i}. {rec}" for i, rec in enumerate(recommendations, 1))
        return "\n".join(f"  • {rec}" for rec in recommendations)


# Global singleton instance
severity_manager = SeverityManager()


# Convenience functions for direct import
def get_risk_level(score: float) -> str:
    """Get risk level label from score"""
    return severity_manager.get_risk_level(score)


def get_risk_color(score: float) -> str:
    """Get color hex for a risk score"""
    return severity_manager.get_risk_color(score)


def get_recommendations(score: float) -> List[str]:
    """Get recommended actions for a risk score"""
    return severity_manager.get_recommendations(score)


def get_pattern_description(pattern: str) -> str:
    """Get description for an attack pattern"""
    return severity_manager.get_pattern_description(pattern)
