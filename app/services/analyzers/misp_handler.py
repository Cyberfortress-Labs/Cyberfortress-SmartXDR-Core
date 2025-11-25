"""
MISP Analyzer Handler
"""
from . import BaseAnalyzerHandler, register_analyzer


@register_analyzer('misp')
class MISPHandler(BaseAnalyzerHandler):
    """
    Handler cho MISP analyzer.
    MISP trả về events/attributes liên quan đến IOC.
    """
    
    display_name = "MISP"
    priority = 90  # High priority - threat intel source
    
    def extract_stats(self, report: dict) -> dict:
        """
        Extract key stats từ MISP report.
        """
        if not report:
            return {"found": False}
        
        events = []
        tags = set()
        
        # Handle different MISP response formats
        if isinstance(report, list):
            items = report
        elif isinstance(report, dict):
            items = report.get('response', report.get('Attribute', report.get('Event', [])))
            if isinstance(items, dict):
                items = [items]
        else:
            return {"found": False}
        
        for item in items[:10]:  # Max 10 events
            if isinstance(item, dict):
                event_info = item.get('Event', item)
                if isinstance(event_info, dict):
                    events.append({
                        "id": event_info.get('id', ''),
                        "info": event_info.get('info', '')[:100],  # Truncate
                        "threat_level": event_info.get('threat_level_id', ''),
                        "date": event_info.get('date', '')
                    })
                    
                    # Extract tags
                    event_tags = event_info.get('Tag', [])
                    for tag in event_tags[:5]:
                        if isinstance(tag, dict):
                            tags.add(tag.get('name', ''))
        
        return {
            "found": len(events) > 0,
            "event_count": len(events),
            "events": events[:5],  # Top 5 events
            "tags": list(tags)[:10]
        }
    
    def summarize(self, analyzer: dict) -> dict:
        """
        Tóm tắt MISP report (~50-100 tokens).
        """
        name = analyzer.get('name', 'MISP')
        report = analyzer.get('report', {})
        
        summary = {
            "analyzer": name,
            "type": "misp"
        }
        
        if not report:
            summary["found"] = False
            summary["verdict"] = "clean"
            return summary
        
        # Parse MISP response
        events = []
        tags = set()
        
        # Handle different MISP response formats
        if isinstance(report, list):
            items = report
        elif isinstance(report, dict):
            items = report.get('response', report.get('Attribute', report.get('Event', [])))
            if isinstance(items, dict):
                items = [items]
        else:
            items = []
        
        for item in items[:5]:
            if isinstance(item, dict):
                event_info = item.get('Event', item)
                if isinstance(event_info, dict):
                    events.append({
                        "info": event_info.get('info', '')[:80],
                        "threat_level": event_info.get('threat_level_id', ''),
                        "date": event_info.get('date', '')
                    })
                    
                    for tag in event_info.get('Tag', [])[:3]:
                        if isinstance(tag, dict):
                            tags.add(tag.get('name', ''))
        
        summary["found"] = len(events) > 0
        summary["verdict"] = "malicious" if events else "clean"
        summary["event_count"] = len(events)
        summary["events"] = events
        summary["tags"] = list(tags)[:5]
        
        return summary
    
    def get_risk_score(self, report: dict) -> int:
        """
        Tính risk score từ MISP (0-100).
        
        Logic:
        - Found in MISP = tối thiểu 70 (known threat)
        - threat_level_id: 1 (high) = 100, 2 (medium) = 85, 3 (low) = 70
        - Multiple events = add bonus
        """
        stats = self.extract_stats(report)
        
        if not stats.get('found'):
            return 0
        
        # Base score for being in MISP
        base_score = 70
        
        # Check threat levels
        events = stats.get('events', [])
        max_threat = 4  # lowest
        
        for event in events:
            try:
                threat_level = int(event.get('threat_level', 4))
                max_threat = min(max_threat, threat_level)
            except (ValueError, TypeError):
                continue
        
        # Adjust based on threat level
        if max_threat == 1:  # High
            base_score = 100
        elif max_threat == 2:  # Medium
            base_score = 85
        elif max_threat == 3:  # Low
            base_score = 70
        
        # Bonus for multiple events
        event_count = stats.get('event_count', 0)
        if event_count > 1:
            base_score = min(100, base_score + (event_count - 1) * 5)
        
        return base_score
