#!/usr/bin/env python3
"""
Unified crawler startup script for Render deployment.
Runs both crawlers with proper coordination and logging.
"""

import asyncio
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler_deployment.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def setup_environment():
    """Set up the environment for optimal crawling"""
    logger.info("Setting up crawler environment...")
    
    # Ensure output directory exists
    os.makedirs('logs', exist_ok=True)
    
    # Set environment variables for better performance
    os.environ['PYTHONUNBUFFERED'] = '1'
    os.environ['REQUESTS_CA_BUNDLE'] = ''
    
    logger.info("Environment setup complete")

def run_simple_crawler():
    """Run the simple crawler with proper logging"""
    logger.info("Starting simple crawler...")
    try:
        result = subprocess.run([
            sys.executable, 'simple_wp_crawler.py'
        ], capture_output=False, text=True, timeout=None)
        
        if result.returncode == 0:
            logger.info("Simple crawler completed successfully")
        else:
            logger.error(f"Simple crawler failed with return code: {result.returncode}")
            
    except Exception as e:
        logger.error(f"Error running simple crawler: {e}")

def run_robust_crawler():
    """Run the robust crawler with proper logging"""
    logger.info("Starting robust crawler...")
    try:
        result = subprocess.run([
            sys.executable, 'robust_wp_crawler.py'
        ], capture_output=False, text=True, timeout=None)
        
        if result.returncode == 0:
            logger.info("Robust crawler completed successfully")
        else:
            logger.error(f"Robust crawler failed with return code: {result.returncode}")
            
    except Exception as e:
        logger.error(f"Error running robust crawler: {e}")

def run_sequential():
    """Run crawlers one after another"""
    logger.info("Running crawlers sequentially...")
    
    # Run simple crawler first (it has resume logic)
    run_simple_crawler()
    
    # Small delay between crawlers
    time.sleep(10)
    
    # Run robust crawler
    run_robust_crawler()
    
    logger.info("Sequential crawling completed")

def run_parallel():
    """Run both crawlers in parallel"""
    logger.info("Running crawlers in parallel...")
    
    import concurrent.futures
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        # Submit both crawlers
        simple_future = executor.submit(run_simple_crawler)
        robust_future = executor.submit(run_robust_crawler)
        
        # Wait for both to complete
        concurrent.futures.wait([simple_future, robust_future])
    
    logger.info("Parallel crawling completed")

def main():
    """Main function"""
    logger.info("=== Crawler Deployment Started ===")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    
    setup_environment()
    
    # Check which mode to run
    mode = os.environ.get('CRAWLER_MODE', 'simple')
    
    if mode == 'simple':
        logger.info("Running in SIMPLE mode (recommended for Render)")
        run_simple_crawler()
    elif mode == 'robust':
        logger.info("Running in ROBUST mode (requires aiohttp)")
        logger.warning("Note: Robust mode requires aiohttp which may have compatibility issues")
        run_robust_crawler()
    elif mode == 'sequential':
        logger.info("Running in SEQUENTIAL mode")
        run_sequential()
    elif mode == 'parallel':
        logger.info("Running in PARALLEL mode (not recommended for Render)")
        run_parallel()
    else:
        logger.info("Running in DEFAULT mode (simple)")
        run_simple_crawler()
    
    logger.info("=== Crawler Deployment Completed ===")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Crawler deployment interrupted by user")
    except Exception as e:
        logger.error(f"Crawler deployment error: {e}")
        sys.exit(1) 