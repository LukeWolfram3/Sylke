#!/usr/bin/env python3
"""
Bing-based WordPress detection crawler for IDN networks.
This version uses Bing search instead of DuckDuckGo to find WordPress installations.
Now writes results incrementally to CSV as they are discovered.
"""

import asyncio
import csv
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
SEARCH_DELAY = 5.0  # Much longer delay between Bing requests
CONCURRENCY = 1  # Single worker only
MAX_BING_RESULTS = 3  # Fewer results per IDN to reduce load
TIMEOUT = 30  # Longer timeout for requests
RETRY_DELAY = 10  # Wait longer between retries

# Sub-domain prefixes to test
WP_PREFIXES = ["blog.", "news.", "today.", "stories.", "newsroom."]

# Paths to test on each domain
WP_PATHS = ["/", "/blog", "/news", "/wp-json", "/feed", "/rss", "/wp-login.php"]

# WordPress detection patterns
WP_PATTERNS = [
    r'wp-content/',
    r'wp-includes/',
    r'wordpress',
    r'<meta name="generator" content="WordPress',
    r'/wp-json/',
    r'wp_enqueue_script',
]
WP_REGEX = re.compile('|'.join(WP_PATTERNS), re.IGNORECASE)

def write_wordpress_site_to_csv(name: str, domain: str):
    """Write a WordPress site to CSV immediately when found."""
    # Check if file exists to determine if we need to write header
    file_exists = Path(OUTPUT_CSV).exists()
    
    with open(OUTPUT_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['name', 'domain'])
        writer.writerow([name, f"https://{domain}"])
    
    print(f"✓ WordPress found: {name} -> {domain}")

async def bing_search(session: aiohttp.ClientSession, name: str) -> list[str]:
    """Search Bing for IDN websites, return hostnames."""
    hosts: list[str] = []
    query = f"{name} official website"
    url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}"
    
    try:
        await asyncio.sleep(SEARCH_DELAY + random.random() * 2.0)  # More jitter
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
            if resp.status != 200:
                print(f"Bing search failed for {name}: HTTP {resp.status}")
                return []
            html = await resp.text()
    except Exception as e:
        print(f"Bing error for {name}: {e}")
        await asyncio.sleep(RETRY_DELAY)  # Wait before continuing
        return []

    # Parse search results
    soup = BeautifulSoup(html, "html.parser")
    # Look for result links in Bing's HTML structure
    for link in soup.select("h2 a, .b_algo h2 a, .algo h3 a"):
        href = str(link.get("href", ""))  # Cast to string with default empty string
        if href and href.startswith("http"):
            try:
                parsed = urllib.parse.urlparse(href)
                if parsed.netloc and parsed.netloc not in hosts:
                    hosts.append(parsed.netloc)
                    if len(hosts) >= MAX_BING_RESULTS:
                        break
            except:
                continue
    
    return hosts

async def test_wordpress(session: aiohttp.ClientSession, domain: str, path: str = "/") -> bool:
    """Test if a domain+path shows WordPress indicators."""
    url = f"https://{domain}{path}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
            if resp.status != 200:
                return False
            html = await resp.text()
            return bool(WP_REGEX.search(html))
    except Exception:
        # Try HTTP fallback
        try:
            url_http = f"http://{domain}{path}"
            async with session.get(url_http, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
                if resp.status != 200:
                    return False
                html = await resp.text()
                return bool(WP_REGEX.search(html))
        except Exception:
            return False

async def check_idn_wordpress(session_search: aiohttp.ClientSession, 
                             session_fetch: aiohttp.ClientSession, 
                             name: str) -> bool:
    """Check if an IDN uses WordPress. Writes to CSV immediately if found. Returns True if found."""
    
    # Get search results from Bing
    base_hosts = await bing_search(session_search, name)
    if not base_hosts:
        return False
    
    # Add delay between search requests
    await asyncio.sleep(SEARCH_DELAY + random.random() * 0.1)
    
    # Expand hosts with common WordPress sub-domains
    all_hosts = []
    for host in base_hosts:
        all_hosts.append(host)
        for prefix in WP_PREFIXES:
            all_hosts.append(f"{prefix}{host}")
    
    # Test each host/path combination
    for host in all_hosts:
        for path in WP_PATHS:
            if await test_wordpress(session_fetch, host, path):
                # Write immediately to CSV
                write_wordpress_site_to_csv(name, host)
                return True
    
    return False

async def main():
    """Main crawler function."""
    # Load IDN names
    print("Loading IDN names...")
    names = []
    try:
        with open(NAMES_CSV, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            for row in reader:
                if row:
                    names.append(row[0].strip())
    except FileNotFoundError:
        print(f"Error: {NAMES_CSV} not found!")
        return
    
    print(f"Total IDNs: {len(names)}")
    
    # Initialize CSV file (create with header if doesn't exist)
    if not Path(OUTPUT_CSV).exists():
        write_wordpress_site_to_csv("", "")  # Creates header only
        # Remove the empty row we just added
        with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        with open(OUTPUT_CSV, 'w', encoding='utf-8') as f:
            f.write(lines[0])  # Keep only header
    
    # Setup SSL and sessions
    ssl_context = ssl.create_default_context()
    connector = aiohttp.TCPConnector(ssl=ssl_context, limit=50)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    wordpress_count = 0
    
    async with aiohttp.ClientSession(connector=connector, headers=headers) as search_session, \
               aiohttp.ClientSession(connector=connector, headers=headers) as fetch_session:
        
        # Process IDNs with semaphore for concurrency control
        semaphore = asyncio.Semaphore(CONCURRENCY)
        
        async def process_idn(name: str) -> None:
            nonlocal wordpress_count
            async with semaphore:
                found = await check_idn_wordpress(search_session, fetch_session, name)
                if found:
                    wordpress_count += 1
        
        # Create tasks and process with progress updates
        tasks = [process_idn(name) for name in names]
        
        for i, task in enumerate(asyncio.as_completed(tasks), 1):
            await task
            if i % 50 == 0:
                print(f"Processed {i}/{len(names)} – WP hits: {wordpress_count}")
    
    print(f"Finished. WordPress sites detected: {wordpress_count} -> {OUTPUT_CSV}")
    print(f"Elapsed {time.time() - start_time:.1f}s")

if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(main()) 