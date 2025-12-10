"""
Test Risk Score Calculation - New Formula (Optimized)
"""
import math


def calculate_risk_score(total_alerts, error_count, warning_count, info_count, avg_confidence, escalation_level):
    """
    New risk score formula (OPTIMIZED v2):
    - Base: 0.5 (always starts here)
    - Volume: log10(total + 1) * 10 (reduced weight)
    - Severity: (ERROR% * 35) + (WARNING% * 15) + (INFO% * 3)
    - Confidence: avg_ML_probability * 30 (increased)
    - Escalation: level * 20 (increased)
    """
    base_score = 0.5
    volume_score = math.log10(total_alerts + 1) * 10
    
    error_pct = error_count / total_alerts if total_alerts > 0 else 0
    warning_pct = warning_count / total_alerts if total_alerts > 0 else 0
    info_pct = info_count / total_alerts if total_alerts > 0 else 0
    
    severity_score = (error_pct * 35) + (warning_pct * 15) + (info_pct * 3)
    confidence_score = avg_confidence * 30
    escalation_score = escalation_level * 20
    
    final_score = base_score + volume_score + severity_score + confidence_score + escalation_score
    
    return {
        'total': min(round(final_score, 1), 100.0),
        'breakdown': {
            'base': base_score,
            'volume': round(volume_score, 1),
            'severity': round(severity_score, 1),
            'confidence': round(confidence_score, 1),
            'escalation': escalation_score
        }
    }


if __name__ == "__main__":
    print('🧪 Risk Score Calculation Examples (New Formula)')
    print('=' * 80)
    print()
    
    test_cases = [
        {
            'name': '📊 100 INFO alerts (70% confidence, no escalation)',
            'total': 100, 'error': 0, 'warning': 0, 'info': 100,
            'confidence': 0.7, 'escalation': 0
        },
        {
            'name': '⚠️  100 WARNING alerts (90% confidence, no escalation)',
            'total': 100, 'error': 0, 'warning': 100, 'info': 0,
            'confidence': 0.9, 'escalation': 0
        },
        {
            'name': '🚨 50 ERROR alerts (95% confidence, + attack sequence)',
            'total': 50, 'error': 50, 'warning': 0, 'info': 0,
            'confidence': 0.95, 'escalation': 2
        },
        {
            'name': '🔀 Mixed: 20 ERROR + 100 WARNING + 200 INFO (80% conf, single pattern)',
            'total': 320, 'error': 20, 'warning': 100, 'info': 200,
            'confidence': 0.8, 'escalation': 1
        },
        {
            'name': '📈 1000 WARNING alerts (85% confidence)',
            'total': 1000, 'error': 0, 'warning': 1000, 'info': 0,
            'confidence': 0.85, 'escalation': 0
        },
        {
            'name': '💥 5 ERROR alerts (98% confidence, + attack sequence) - CRITICAL',
            'total': 5, 'error': 5, 'warning': 0, 'info': 0,
            'confidence': 0.98, 'escalation': 2
        },
        {
            'name': '🟢 10 INFO alerts (60% confidence) - Low noise',
            'total': 10, 'error': 0, 'warning': 0, 'info': 10,
            'confidence': 0.6, 'escalation': 0
        },
        {
            'name': '🔴 Mixed critical: 5 ERROR + 20 WARNING (95% conf, + escalation)',
            'total': 25, 'error': 5, 'warning': 20, 'info': 0,
            'confidence': 0.95, 'escalation': 2
        }
    ]
    
    for test in test_cases:
        result = calculate_risk_score(
            test['total'], test['error'], test['warning'], 
            test['info'], test['confidence'], test['escalation']
        )
        
        print(f"{test['name']}")
        print(f"  Total Score: {result['total']:.1f}/100")
        print(f"  Breakdown:")
        print(f"    - Base:       {result['breakdown']['base']:.1f}")
        print(f"    - Volume:     {result['breakdown']['volume']:.1f}  (log10({test['total']}+1) * 10)")
        print(f"    - Severity:   {result['breakdown']['severity']:.1f}  (E:{test['error']} W:{test['warning']} I:{test['info']})")
        print(f"    - Confidence: {result['breakdown']['confidence']:.1f}  ({test['confidence']*100:.0f}% * 30)")
        print(f"    - Escalation: {result['breakdown']['escalation']:.1f}  (level {test['escalation']})")
        print()
    
    print('=' * 80)
    print('✅ Test completed!')
    print()
    print('📊 Score Interpretation:')
    print('  0-30:   🟢 LOW RISK      - Routine monitoring')
    print('  30-50:  🟡 MEDIUM RISK   - Investigate patterns')
    print('  50-70:  🔴 HIGH RISK     - Immediate review required')
    print('  70-100: 🚨 CRITICAL RISK - Emergency response')
