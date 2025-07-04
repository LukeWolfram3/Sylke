#!/usr/bin/env python3
"""
Incremental WordPress detection crawler that writes results immediately.
This version ensures we don't lose data if the process crashes.
"""

import asyncio
import csv
import os
import random
import re
import ssl
import sys
import time
import urllib.parse
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

# Configuration
NAMES_CSV = "acuity_idns.csv"
OUTPUT_CSV = "wordpress_idns.csv"
SEARCH_DELAY = 15.0  # Very conservative delay
FETCH_DELAY = 3.0
MAX_CONCURRENT = 1  # Sequential processing
MAX_BING_RESULTS = 2
TIMEOUT = 45
MAX_RETRIES = 2

# WordPress detection patterns
WP_PATTERNS = [
    r'/wp-content/',
    r'/wp-includes/',
    r'/wp-admin/',
    r'wp-json',
    r'WordPress',
    r'wp_',
    r'wpdb',
    r'wp-login',
    r'wp-config'
]
WP_REGEX = re.compile('|'.join(WP_PATTERNS), re.IGNORECASE)

# Sub-domain prefixes to test
WP_PREFIXES = ['www', 'blog', 'news', 'stories', 'newsroom', 'media']

def log_message(msg):
    """Print timestamped log message"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def write_wordpress_site(name, domain):
    """Immediately write a WordPress site to CSV"""
    try:
        # Check if file exists to determine if we need headers
        file_exists = os.path.exists(OUTPUT_CSV)
        
        with open(OUTPUT_CSV, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write headers if file is new
            if not file_exists:
                writer.writerow(['name', 'domain'])
            
            # Write the WordPress site
            writer.writerow([name, domain])
            f.flush()  # Force write to disk
        
        log_message(f"✓ WordPress found: {name} -> {domain}")
        return True
    except Exception as e:
        log_message(f"Error writing to CSV: {e}")
        return False

async def search_bing(session, query):
    """Search Bing and return domain list"""
    try:
        search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        
        async with session.get(search_url, timeout=TIMEOUT) as response:
            if response.status != 200:
                return []
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            domains = []
            for link in soup.select("h2 a, .b_algo h2 a"):
                href = link.get("href")
                if href and isinstance(href, str) and href.startswith("http"):
                    try:
                        parsed = urllib.parse.urlparse(href)
                        if parsed.netloc:
                            domains.append(parsed.netloc)
                            if len(domains) >= MAX_BING_RESULTS:
                                break
                    except:
                        continue
            
            return domains
            
    except Exception as e:
        log_message(f"Bing search error for '{query}': {e}")
        return []

async def test_wordpress(session, url):
    """Test if a URL uses WordPress"""
    try:
        async with session.get(url, timeout=TIMEOUT) as response:
            if response.status != 200:
                return False
            
            html = await response.text()
            return bool(WP_REGEX.search(html))
            
    except Exception as e:
        return False

async def process_idn(session, search_session, name, processed_count, total_count):
    """Process a single IDN and return True if WordPress found"""
    try:
        log_message(f"Processing {processed_count}/{total_count}: {name}")
        
        # Search for the IDN
        domains = await search_bing(search_session, name)
        await asyncio.sleep(SEARCH_DELAY + random.uniform(0, 2))
        
        if not domains:
            return False
        
        # Test each domain for WordPress
        for domain in domains:
            # Test main domain and common WordPress paths
            test_urls = [
                f"https://{domain}",
                f"https://{domain}/wp-json/wp/v2/",
                f"https://{domain}/wp-admin/",
                f"https://{domain}/blog/",
                f"https://{domain}/news/"
            ]
            
            # Also test with www prefix if not already present
            if not domain.startswith('www.'):
                test_urls.extend([
                    f"https://www.{domain}",
                    f"https://www.{domain}/wp-json/wp/v2/"
                ])
            
            for url in test_urls:
                try:
                    if await test_wordpress(session, url):
                        # Found WordPress! Write immediately to CSV
                        write_wordpress_site(name, domain)
                        return True
                    
                    await asyncio.sleep(FETCH_DELAY)
                    
                except Exception as e:
                    continue
        
        return False
        
    except Exception as e:
        log_message(f"Error processing {name}: {e}")
        return False

async def main():
    """Main crawler function"""
    log_message("Starting incremental WordPress detection crawler...")
    
    # Load IDN names
    try:
        with open(NAMES_CSV, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            names = []
            for i, row in enumerate(reader):
                if row and row[0].strip():
                    # Skip header row
                    if i == 0 and row[0].strip().lower() == 'name':
                        continue
                    names.append(row[0].strip())
        
        log_message(f"Loaded {len(names)} IDN names")
        
        if not names:
            log_message("No IDN names loaded. Exiting.")
            return
            
    except Exception as e:
        log_message(f"Error loading IDN names: {e}")
        return
    
    # Initialize CSV file
    try:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'domain'])
        log_message(f"Initialized output file: {OUTPUT_CSV}")
    except Exception as e:
        log_message(f"Error initializing CSV: {e}")
        return
    
    # Setup sessions
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(
        ssl=ssl_context,
        limit=10,
        limit_per_host=5,
        keepalive_timeout=30
    )
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    wordpress_found = 0
    start_time = time.time()
    
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        async with aiohttp.ClientSession(connector=connector, headers=headers) as search_session:
            
            for i, name in enumerate(names, 1):
                try:
                    found = await process_idn(session, search_session, name, i, len(names))
                    if found:
                        wordpress_found += 1
                    
                    # Progress update every 50 IDNs
                    if i % 50 == 0:
                        elapsed = time.time() - start_time
                        log_message(f"Progress: {i}/{len(names)} processed, {wordpress_found} WordPress sites found, {elapsed:.1f}s elapsed")
                    
                except Exception as e:
                    log_message(f"Error with IDN {i} ({name}): {e}")
                    continue
    
    elapsed = time.time() - start_time
    log_message(f"Crawler completed! Found {wordpress_found} WordPress sites in {elapsed:.1f}s")
    log_message(f"Results saved to: {OUTPUT_CSV}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_message("Crawler interrupted by user")
    except Exception as e:
        log_message(f"Crawler error: {e}") 