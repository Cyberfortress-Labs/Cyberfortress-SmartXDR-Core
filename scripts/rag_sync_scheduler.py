#!/usr/bin/env python3
"""
RAG Sync Scheduler - Periodic sync of data/ directory to ChromaDB

Runs rag_sync.py at configurable intervals (default: 1 hour).
Configure via RAG_SYNC_INTERVAL environment variable (in minutes).

Usage:
    # Run as background process
    python scripts/rag_sync_scheduler.py &
    
Environment:
    RAG_SYNC_INTERVAL: Sync interval in minutes (default: 60)
    RAG_SYNC_ENABLED: Enable/disable scheduler (default: true)
"""
import os
import sys
import time
import signal
import subprocess
import logging
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [RAG-Scheduler] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('rag_sync_scheduler')

# Configuration
DEFAULT_INTERVAL = 60  # 60 minutes = 1 hour
DATA_DIR = Path("/app/data")
SYNC_SCRIPT = Path("/app/scripts/rag_sync.py")

# Graceful shutdown
shutdown_requested = False

def signal_handler(sig, frame):
    global shutdown_requested
    logger.info("Shutdown requested, stopping scheduler...")
    shutdown_requested = True

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def get_interval_minutes() -> int:
    """Get sync interval from environment (in minutes)"""
    interval_str = os.environ.get('RAG_SYNC_INTERVAL', str(DEFAULT_INTERVAL))
    try:
        interval = int(interval_str)
        if interval < 1:
            logger.warning(f"RAG_SYNC_INTERVAL too small ({interval}), using minimum of 1 minute")
            return 1
        return interval
    except ValueError:
        logger.warning(f"Invalid RAG_SYNC_INTERVAL '{interval_str}', using default {DEFAULT_INTERVAL}")
        return DEFAULT_INTERVAL


def is_enabled() -> bool:
    """Check if scheduler is enabled"""
    enabled = os.environ.get('RAG_SYNC_ENABLED', 'true').lower()
    return enabled in ('true', '1', 'yes', 'on')


def has_data_files() -> bool:
    """Check if data directory has files to sync"""
    if not DATA_DIR.exists():
        return False
    
    # Check for any file (excluding README.md)
    for f in DATA_DIR.rglob('*'):
        if f.is_file() and f.name != 'README.md':
            return True
    return False


def run_sync():
    """Run rag_sync.py"""
    logger.info("Starting RAG sync...")
    start_time = time.time()
    
    try:
        result = subprocess.run(
            [sys.executable, str(SYNC_SCRIPT), str(DATA_DIR)],
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            # Extract summary from output
            lines = result.stdout.strip().split('\n')
            summary_lines = [l for l in lines if any(x in l for x in ['Added:', 'Updated:', 'Deleted:', 'Total in DB:'])]
            summary = ' | '.join(summary_lines[-4:]) if summary_lines else 'Completed'
            logger.info(f"Sync completed in {elapsed:.1f}s: {summary}")
        else:
            logger.error(f"Sync failed (exit code {result.returncode})")
            if result.stderr:
                logger.error(f"Error: {result.stderr[:500]}")
                
    except subprocess.TimeoutExpired:
        logger.error("Sync timed out after 10 minutes")
    except Exception as e:
        logger.error(f"Sync error: {e}")


def main():
    """Main scheduler loop"""
    # Check if enabled
    if not is_enabled():
        logger.info("RAG sync scheduler is disabled (RAG_SYNC_ENABLED=false)")
        return
    
    interval = get_interval_minutes()
    logger.info(f"RAG Sync Scheduler started")
    logger.info(f"Interval: {interval} minutes")
    logger.info(f"Data directory: {DATA_DIR}")
    
    # Initial wait before first sync (let app fully start)
    logger.info("Waiting 10 seconds before first sync...")
    for _ in range(10):
        if shutdown_requested:
            return
        time.sleep(1)
    
    while not shutdown_requested:
        if has_data_files():
            run_sync()
        else:
            logger.info("No data files to sync, skipping")
        
        # Sleep for interval (check shutdown every minute)
        next_sync = datetime.now().strftime('%H:%M') + f" + {interval}min"
        logger.info(f"Next sync in {interval} minutes")
        
        for _ in range(interval * 60):
            if shutdown_requested:
                break
            time.sleep(1)
    
    logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
