#!/usr/bin/env python3
"""
Robust WordPress detection crawler for IDN networks.
This version writes results incrementally to CSV and has enhanced error handling.
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
SEARCH_DELAY = 8.0  # Even longer delay between searches
FETCH_DELAY = 2.0   # Delay between website fetches
MAX_CONCURRENT = 1  # Sequential processing only
MAX_BING_RESULTS = 2  # Even fewer results to reduce load
TIMEOUT = 45  # Longer timeout
MAX_RETRIES = 2

# Sub-domain prefixes to test
WP_PREFIXES = ["blog.", "news.", "www."]

# Paths to test on each domain
WP_PATHS = ["/", "/blog", "/wp-json", "/feed"]

# WordPress detection patterns
WP_PATTERNS = [
    r'wp-content/',
    r'wp-includes/',
    r'wordpress',
    r'<meta name="generator" content="WordPress',
    r'/wp-json/',
    r'wp_enqueue_script',
    r'wp-admin',
]
WP_REGEX = re.compile('|'.join(WP_PATTERNS), re.IGNORECASE)

def get_processed_names():
    """Get list of already processed names from CSV to avoid duplicates."""
    processed = set()
    try:
        if Path(OUTPUT_CSV).exists():
            with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if row and row[0].strip():
                        processed.add(row[0].strip())
    except Exception as e:
        print(f"Error reading existing results: {e}")
    return processed

def append_to_csv(name: str, domain: str):
    """Append a WordPress site to CSV immediately."""
    try:
        # Check if file exists
        file_exists = Path(OUTPUT_CSV).exists()
        
        with open(OUTPUT_CSV, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['name', 'domain'])
            writer.writerow([name, f"https://{domain}"])
        
        print(f"✓ WordPress found: {name} -> {domain}")
        return True
    except Exception as e:
        print(f"Error writing to CSV: {e}")
        return False

async def safe_bing_search(session: aiohttp.ClientSession, name: str) -> list[str]:
    """Search Bing with error handling and retries."""
    hosts = []
    query = f'"{name}" hospital health medical site:*.org OR site:*.com'
    url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}"
    
    for attempt in range(MAX_RETRIES):
        try:
            print(f"Searching Bing for: {name} (attempt {attempt + 1})")
            
            # Random delay
            await asyncio.sleep(SEARCH_DELAY + random.uniform(1, 3))
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # Parse Bing search results
                    for link in soup.select("h2 a, .b_algo h2 a"):
                        href = link.get("href")
                        if href and isinstance(href, str) and href.startswith("http"):
                            try:
                                parsed = urllib.parse.urlparse(href)
                                if parsed.netloc and parsed.netloc not in hosts:
                                    hosts.append(parsed.netloc)
                                    if len(hosts) >= MAX_BING_RESULTS:
                                        break
                            except:
                                continue
                    break
                else:
                    print(f"Bing returned HTTP {resp.status} for {name}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(10)
                        
        except asyncio.TimeoutError:
            print(f"Timeout searching for {name} (attempt {attempt + 1})")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(15)
        except Exception as e:
            print(f"Error searching for {name}: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(10)
    
    return hosts

async def safe_test_rest_api(session: aiohttp.ClientSession, domain: str) -> bool:
    """Return True if the domain exposes an open WordPress REST API."""
    api_paths = [
        "/wp-json/wp/v2/types",
        "/wp-json/wp/v2/posts?per_page=1",
        "/wp-json/"
    ]
    for path in api_paths:
        for proto in ["https", "http"]:
            url = f"{proto}://{domain}{path}"
            try:
                await asyncio.sleep(FETCH_DELAY + random.uniform(0, 0.5))
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
                    if resp.status == 200 and resp.headers.get("Content-Type", "").startswith("application/json"):
                        text = await resp.text()
                        if text.strip().startswith(('{', '[')) or "namespaces" in text:
                            return True
            except Exception:
                continue
    return False

async def process_single_idn(session_search: aiohttp.ClientSession, 
                            session_fetch: aiohttp.ClientSession, 
                            name: str) -> bool:
    """Process a single IDN and return True if WordPress found."""
    
    try:
        # Search for domains
        base_hosts = await safe_bing_search(session_search, name)
        if not base_hosts:
            return False
        
        # Expand with common prefixes
        all_hosts = []
        for host in base_hosts:
            all_hosts.append(host)
            for prefix in WP_PREFIXES:
                all_hosts.append(f"{prefix}{host}")
        
        # Test each host/path combination
        for host in all_hosts:
            for path in WP_PATHS:
                if await safe_test_rest_api(session_fetch, host):
                    append_to_csv(name, host)
                    return True
        
        return False
        
    except Exception as e:
        print(f"Error processing {name}: {e}")
        return False

async def main():
    """Main crawler function."""
    
    print("🚀 Starting robust WordPress IDN crawler...")
    
    # Load IDN names
    names = []
    try:
        with open(NAMES_CSV, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            for row in reader:
                if row and row[0].strip():
                    names.append(row[0].strip())
    except FileNotFoundError:
        print(f"❌ Error: {NAMES_CSV} not found!")
        return
    
    print(f"📋 Loaded {len(names)} IDN names")
    
    # Get already processed names to avoid duplicates
    processed_names = get_processed_names()
    if processed_names:
        print(f"📄 Found {len(processed_names)} already processed IDNs")
        names = [name for name in names if name not in processed_names]
        print(f"📋 Remaining to process: {len(names)} IDNs")
    
    if not names:
        print("✅ All IDNs have already been processed!")
        return
    
    # Initialize CSV
    if not Path(OUTPUT_CSV).exists():
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'domain'])
        print(f"📄 Created {OUTPUT_CSV}")
    else:
        print(f"📄 Appending to existing {OUTPUT_CSV}")
    
    # Setup sessions
    ssl_context = ssl.create_default_context()
    connector = aiohttp.TCPConnector(
        ssl=ssl_context, 
        limit=10,
        limit_per_host=2,
        ttl_dns_cache=300,
        use_dns_cache=True
    )
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    found_count = 0
    
    async with aiohttp.ClientSession(connector=connector, headers=headers) as search_session, \
               aiohttp.ClientSession(connector=connector, headers=headers) as fetch_session:
        
        print("🔍 Starting sequential processing...")
        
        for i, name in enumerate(names, 1):
            try:
                found = await process_single_idn(search_session, fetch_session, name)
                if found:
                    found_count += 1
                
                # Progress update
                if i % 25 == 0 or found:
                    print(f"📊 Progress: {i}/{len(names)} processed, {found_count} WordPress sites found")
                
                # Small delay between IDNs
                await asyncio.sleep(2)
                
            except KeyboardInterrupt:
                print(f"\n⏹️  Stopped by user at {i}/{len(names)}")
                break
            except Exception as e:
                print(f"❌ Unexpected error processing {name}: {e}")
                await asyncio.sleep(5)
    
    print(f"\n🎉 Completed! Found {found_count} WordPress sites")
    print(f"📁 Results saved in {OUTPUT_CSV}")

if __name__ == "__main__":
    start_time = time.time()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Crawler stopped by user")
    finally:
        elapsed = time.time() - start_time
        print(f"⏱️  Total runtime: {elapsed:.1f} seconds") 