#!/usr/bin/env python3
"""
Simple WordPress detection crawler using requests library.
Writes results immediately to CSV as they are found.
Can resume from interruptions.
"""

import csv
import os
import re
import requests
import time
import urllib.parse
from bs4 import BeautifulSoup

# Configuration
NAMES_CSV = "acuity_idns.csv"
OUTPUT_CSV = "wordpress_idns.csv"
SEARCH_DELAY = 12.0  # Very conservative delay between searches
FETCH_DELAY = 4.0    # Delay between website fetches
TIMEOUT = 30         # Request timeout
MAX_RESULTS = 3      # Number of search results to check per IDN

# WordPress detection patterns
WP_PATTERNS = [
    r'/wp-content/',
    r'/wp-includes/',
    r'/wp-admin/',
    r'wp-json',
    r'WordPress',
    r'wp-embed',
    r'wp_enqueue_script',
    r'generator.*wordpress',
    r'powered by wordpress'
]
WP_REGEX = re.compile('|'.join(WP_PATTERNS), re.IGNORECASE)

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

def get_processed_names():
    """Get list of already processed names from CSV"""
    processed = set()
    try:
        if os.path.exists(OUTPUT_CSV):
            with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if row:
                        processed.add(row[0])
    except Exception as e:
        log_message(f"Error reading existing results: {e}")
    return processed

def search_bing(query):
    """Search Bing and return domain list"""
    try:
        search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=TIMEOUT)
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        domains = []
        for link in soup.select("h2 a, .b_algo h2 a"):
            href = link.get("href")
            if href and isinstance(href, str) and href.startswith("http"):
                try:
                    parsed = urllib.parse.urlparse(href)
                    if parsed.netloc:
                        domains.append(parsed.netloc)
                        if len(domains) >= MAX_RESULTS:
                            break
                except:
                    continue
        
        return domains
        
    except Exception as e:
        log_message(f"Bing search error for '{query}': {e}")
        return []

def test_rest_api(domain):
    """Return True if the domain exposes an open WordPress REST API."""
    API_PATHS = [
        "/wp-json/wp/v2/types",
        "/wp-json/wp/v2/posts?per_page=1",
        "/wp-json/"
    ]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    for path in API_PATHS:
        for proto in ("https", "http"):
            url = f"{proto}://{domain}{path}"
            try:
                resp = requests.get(url, headers=headers, timeout=TIMEOUT, verify=False)
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
                    # quick sanity check – JSON starts with { or [ or contains namespaces
                    txt = resp.text.strip()
                    if txt.startswith("{") or txt.startswith("[") or "namespaces" in txt:
                        return True
            except Exception:
                continue
    return False

# alias the old name so the rest of the code stays unchanged
def test_wordpress(url):
    """Backward-compat wrapper: expects a full URL; extracts domain and runs test_rest_api."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc:
            return test_rest_api(parsed.netloc)
    except Exception:
        pass
    return False

def process_idn(name, processed_count, total_count):
    """Process a single IDN and return True if WordPress found"""
    try:
        log_message(f"Processing {processed_count}/{total_count}: {name}")
        
        # Search for the IDN
        domains = search_bing(name)
        time.sleep(SEARCH_DELAY)
        
        if not domains:
            log_message(f"No domains found for: {name}")
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
                    if test_wordpress(url):
                        # Found WordPress! Write immediately to CSV
                        write_wordpress_site(name, domain)
                        return True
                    
                    time.sleep(FETCH_DELAY)
                    
                except Exception as e:
                    continue
        
        return False
        
    except Exception as e:
        log_message(f"Error processing {name}: {e}")
        return False

def main():
    """Main crawler function"""
    log_message("Starting simple WordPress detection crawler...")
    
    # Disable SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
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
    
    # Get already processed names to avoid duplicates
    processed_names = get_processed_names()
    if processed_names:
        log_message(f"Found {len(processed_names)} already processed IDNs")
        names = [name for name in names if name not in processed_names]
        log_message(f"Remaining to process: {len(names)} IDNs")
    
    # Initialize CSV file if it doesn't exist
    if not os.path.exists(OUTPUT_CSV):
        try:
            with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['name', 'domain'])
            log_message(f"Initialized output file: {OUTPUT_CSV}")
        except Exception as e:
            log_message(f"Error initializing CSV: {e}")
            return
    
    wordpress_found = 0
    start_time = time.time()
    
    for i, name in enumerate(names, 1):
        try:
            found = process_idn(name, i, len(names))
            if found:
                wordpress_found += 1
            
            # Progress update every 25 IDNs
            if i % 25 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed * 60  # IDNs per minute
                log_message(f"Progress: {i}/{len(names)} processed, {wordpress_found} WordPress sites found, {elapsed:.1f}s elapsed, rate: {rate:.1f}/min")
            
        except KeyboardInterrupt:
            log_message("Crawler interrupted by user")
            break
        except Exception as e:
            log_message(f"Error with IDN {i} ({name}): {e}")
            continue
    
    elapsed = time.time() - start_time
    log_message(f"Crawler completed! Found {wordpress_found} WordPress sites in {elapsed:.1f}s")
    log_message(f"Results saved to: {OUTPUT_CSV}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_message("Crawler interrupted by user")
    except Exception as e:
        log_message(f"Crawler error: {e}") 