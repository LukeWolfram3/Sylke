#!/usr/bin/env python3
"""
Background WordPress detection crawler for all 1,785 IDN networks.
Writes results incrementally and provides regular progress updates.
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
PROGRESS_LOG = "crawler_progress.log"
SEARCH_DELAY = 10.0  # Conservative delay between searches
FETCH_DELAY = 3.0   # Delay between website fetches
MAX_CONCURRENT = 1  # Sequential processing to avoid rate limiting
MAX_BING_RESULTS = 2  # Fewer results to reduce load
TIMEOUT = 60  # Longer timeout
MAX_RETRIES = 3

# Sub-domain prefixes to test for WordPress
WP_PREFIXES = ["", "www.", "blog.", "news.", "media.", "press."]

# Paths to test for WordPress
WP_PATHS = ["/", "/blog", "/news", "/wp-json/wp/v2", "/wp-login.php", "/wp-admin", "/xmlrpc.php"]

# Enhanced WordPress detection patterns
WP_PATTERNS = [
    r'wp-content[/\\]',
    r'wp-includes[/\\]',
    r'wp-admin[/\\]',
    r'/wp-json/',
    r'wordpress',
    r'wp_version',
    r'generator.*wordpress',
    r'wp-embed',
    r'wp_enqueue_script',
    r'wpdb',
    r'wp_head\(\)',
    r'wp_footer\(\)'
]

WP_REGEX = re.compile('|'.join(WP_PATTERNS), re.IGNORECASE)

def log_progress(message):
    """Log progress to both console and file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {message}"
    print(log_msg, flush=True)
    with open(PROGRESS_LOG, "a", encoding="utf-8") as f:
        f.write(log_msg + "\n")

def load_idn_names():
    """Load IDN names from CSV file."""
    names = []
    try:
        with open(NAMES_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get('Network Name', '').strip()
                if name:
                    names.append(name)
    except Exception as e:
        log_progress(f"Error loading IDN names: {e}")
        return []
    
    log_progress(f"Loaded {len(names)} IDN names")
    return names

def write_wordpress_result(name, domain):
    """Write a WordPress result immediately to CSV."""
    file_exists = os.path.exists(OUTPUT_CSV)
    
    with open(OUTPUT_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['name', 'domain'])
        writer.writerow([name, domain])
    
    log_progress(f"✓ WordPress found: {name} -> {domain}")

async def search_bing(session, query):
    """Search Bing for domains related to the query."""
    try:
        search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        
        async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as response:
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
                        if parsed.netloc and parsed.netloc not in domains:
                            domains.append(parsed.netloc)
                            if len(domains) >= MAX_BING_RESULTS:
                                break
                    except:
                        continue
            
            return domains
            
    except Exception as e:
        log_progress(f"Bing search error for '{query}': {e}")
        return []

async def test_wordpress(session, url):
    """Test if a URL runs WordPress."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as response:
            if response.status == 200:
                html = await response.text()
                return bool(WP_REGEX.search(html))
    except:
        pass
    return False

async def check_idn_for_wordpress(session, name):
    """Check if an IDN uses WordPress by searching and testing domains."""
    try:
        # Search for domains related to this IDN
        domains = await search_bing(session, name)
        await asyncio.sleep(SEARCH_DELAY + random.uniform(0, 2))
        
        if not domains:
            return None
        
        # Test each domain with various prefixes and paths
        for domain in domains:
            for prefix in WP_PREFIXES:
                for path in WP_PATHS:
                    test_url = f"https://{prefix}{domain}{path}"
                    
                    if await test_wordpress(session, test_url):
                        return domain
                    
                    await asyncio.sleep(FETCH_DELAY)
        
        return None
        
    except Exception as e:
        log_progress(f"Error checking {name}: {e}")
        return None

async def main():
    """Main crawler function."""
    # Initialize progress log
    with open(PROGRESS_LOG, "w", encoding="utf-8") as f:
        f.write("")
    
    log_progress("Starting WordPress detection crawler...")
    
    # Load IDN names
    names = load_idn_names()
    if not names:
        log_progress("No IDN names loaded. Exiting.")
        return
    
    # Initialize CSV with headers if it doesn't exist
    if not os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'domain'])
    
    log_progress(f"Processing {len(names)} IDNs...")
    
    # Create HTTP session with conservative settings
    connector = aiohttp.TCPConnector(
        ssl=ssl.create_default_context(),
        limit=MAX_CONCURRENT,
        limit_per_host=1,
        ttl_dns_cache=300,
        use_dns_cache=True
    )
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    wordpress_count = 0
    start_time = time.time()
    
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        for i, name in enumerate(names, 1):
            domain = await check_idn_for_wordpress(session, name)
            
            if domain:
                write_wordpress_result(name, domain)
                wordpress_count += 1
            
            # Progress updates every 50 IDNs
            if i % 50 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed * 60  # IDNs per minute
                eta_mins = (len(names) - i) / rate if rate > 0 else 0
                log_progress(f"Processed {i}/{len(names)} IDNs - WordPress found: {wordpress_count} - Rate: {rate:.1f}/min - ETA: {eta_mins:.0f}min")
    
    # Final summary
    elapsed = time.time() - start_time
    log_progress(f"COMPLETED: Found {wordpress_count} WordPress sites out of {len(names)} IDNs in {elapsed/3600:.1f} hours")
    log_progress(f"Results saved to {OUTPUT_CSV}")

if __name__ == "__main__":
    asyncio.run(main()) 