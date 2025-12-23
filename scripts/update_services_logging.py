#!/usr/bin/env python3
"""Update remaining services to use centralized logger"""
import re
import os

UPDATES = {
    'app/services/alert_summarization_service.py': {
        'pattern': r"import logging",
        'remove_logger': r"^logger\s*=\s*logging\.getLogger\([^)]+\)\n?",
        'import': 'from app.utils.logger import alert_logger as logger'
    },
    'app/services/daily_report_scheduler.py': {
        'pattern': r"import logging",
        'remove_logger': r"^logger\s*=\s*logging\.getLogger\([^)]+\)\n?",
        'import': 'from app.utils.logger import scheduler_logger as logger'
    },
    'app/services/elasticsearch_service.py': {
        'pattern': r"import logging",
        'remove_logger': r"^logger\s*=\s*logging\.getLogger\([^)]+\)\n?",
        'import': 'from app.utils.logger import es_logger as logger'
    },
    'app/services/email_service.py': {
        'pattern': r"import logging",
        'remove_logger': r"^logger\s*=\s*logging\.getLogger\([^)]+\)\n?",
        'import': 'from app.utils.logger import email_logger as logger'
    },
    'app/services/prompt_builder_service.py': {
        'pattern': r"import logging",
        'remove_logger': r"^logger\s*=\s*logging\.getLogger\([^)]+\)\n?",
        'import': 'from app.utils.logger import prompt_logger as logger'
    },
    'app/services/telegram_middleware_service.py': {
        'pattern': r"import logging",
        'remove_logger': r"^logger\s*=\s*logging\.getLogger\([^)]+\)\n?",
        'import': 'from app.utils.logger import telegram_service_logger as logger'
    },
}

def update_file(filepath, config):
    if not os.path.exists(filepath):
        print(f"  SKIP: {filepath} not found")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Remove import logging
    content = re.sub(r'^import logging\n', '', content, flags=re.MULTILINE)
    
    # Remove old logger = logging.getLogger(...)
    content = re.sub(config['remove_logger'], '', content, flags=re.MULTILINE)
    
    # Find where to add new import (after other app imports)
    lines = content.split('\n')
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('from app.'):
            insert_idx = i + 1
    
    # Add new import if not already there
    if config['import'] not in content:
        lines.insert(insert_idx, config['import'])
        content = '\n'.join(lines)
    
    # Clean up multiple blank lines
    content = re.sub(r'\n\n\n+', '\n\n', content)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  UPDATED: {filepath}")
        return True
    else:
        print(f"  NO CHANGE: {filepath}")
        return False

def main():
    print("Updating service files...")
    updated = 0
    for filepath, config in UPDATES.items():
        if update_file(filepath, config):
            updated += 1
    print(f"\nDone! Updated {updated}/{len(UPDATES)} files")

if __name__ == '__main__':
    main()
