#!/usr/bin/env python3
"""
Render-optimized WordPress detection crawler.
Designed to run as a web service with progress tracking.
"""

import csv
import os
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, send_file
import requests
from bs4 import BeautifulSoup
import urllib.parse

app = Flask(__name__)

# Configuration
NAMES_CSV = "acuity_idns.csv"
OUTPUT_CSV = "wordpress_idns.csv"
PROGRESS_FILE = "crawler_progress.json"
SEARCH_DELAY = 8.0  # Conservative delay
TIMEOUT = 30

# Global state
crawler_state = {
    "running": False,
    "progress": 0,
    "total": 0,
    "found": 0,
    "current_idn": "",
    "start_time": None,
    "last_update": None
}

# WordPress detection patterns
WP_PATTERNS = [
    r'/wp-content/',
    r'/wp-includes/',
    r'/wp-admin/',
    r'wp-json',
    r'WordPress',
    r'wp-login'
]

def log_message(msg):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")
    return f"[{timestamp}] {msg}"

def load_idns():
    """Load IDN names from CSV"""
    try:
        with open(NAMES_CSV, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            names = []
            for i, row in enumerate(reader):
                if row and row[0].strip():
                    # Skip header
                    if i == 0 and row[0].strip().lower() == 'name':
                        continue
                    names.append(row[0].strip())
        return names
    except Exception as e:
        log_message(f"Error loading IDNs: {e}")
        return []

def get_processed_idns():
    """Get list of already processed IDNs"""
    processed = set()
    try:
        if os.path.exists(OUTPUT_CSV):
            with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if row and len(row) >= 1:
                        processed.add(row[0].strip())
    except Exception as e:
        log_message(f"Error reading processed IDNs: {e}")
    return processed

def write_wordpress_site(name, domain):
    """Write WordPress site to CSV immediately"""
    try:
        # Check if file exists and has header
        file_exists = os.path.exists(OUTPUT_CSV)
        needs_header = True
        
        if file_exists:
            with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line == 'name,domain':
                    needs_header = False
        
        # Write to file
        with open(OUTPUT_CSV, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if needs_header:
                writer.writerow(['name', 'domain'])
            writer.writerow([name, domain])
        
        log_message(f"✓ WordPress found: {name} -> {domain}")
        return True
    except Exception as e:
        log_message(f"Error writing to CSV: {e}")
        return False

def bing_search(query):
    """Search Bing for domains related to query"""
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.bing.com/search?q={encoded_query}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        domains = []
        
        # Extract domains from search results
        for link in soup.select('h2 a, .b_algo h2 a'):
            href = link.get('href')
            if href and isinstance(href, str) and href.startswith('http'):
                try:
                    parsed = urllib.parse.urlparse(href)
                    if parsed.netloc and parsed.netloc not in domains:
                        domains.append(parsed.netloc)
                        if len(domains) >= 3:  # Limit results
                            break
                except:
                    continue
        
        return domains
    except Exception as e:
        log_message(f"Bing search error for '{query}': {e}")
        return []

def test_wordpress(url):
    """Test if a URL uses WordPress"""
    try:
        if not url.startswith('http'):
            url = f"https://{url}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        
        # Check for WordPress patterns
        content = response.text.lower()
        for pattern in WP_PATTERNS:
            if pattern.lower() in content:
                return True
        
        return False
    except Exception as e:
        return False

def process_idn(name):
    """Process a single IDN"""
    global crawler_state
    
    crawler_state["current_idn"] = name
    crawler_state["last_update"] = datetime.now().isoformat()
    
    # Search for domains
    domains = bing_search(name)
    if not domains:
        return False
    
    # Test each domain for WordPress
    for domain in domains:
        if test_wordpress(domain):
            write_wordpress_site(name, domain)
            crawler_state["found"] += 1
            return True
        time.sleep(2)  # Small delay between tests
    
    return False

def run_crawler():
    """Main crawler function"""
    global crawler_state
    
    try:
        crawler_state["running"] = True
        crawler_state["start_time"] = datetime.now().isoformat()
        
        # Load IDNs
        all_idns = load_idns()
        processed = get_processed_idns()
        remaining = [idn for idn in all_idns if idn not in processed]
        
        crawler_state["total"] = len(remaining)
        crawler_state["progress"] = 0
        
        log_message(f"Starting crawler: {len(remaining)} IDNs to process")
        
        for i, idn in enumerate(remaining):
            if not crawler_state["running"]:
                break
                
            process_idn(idn)
            crawler_state["progress"] = i + 1
            
            # Progress update every 25 IDNs
            if (i + 1) % 25 == 0:
                log_message(f"Progress: {i+1}/{len(remaining)} processed, {crawler_state['found']} WordPress sites found")
            
            time.sleep(SEARCH_DELAY)
        
        log_message(f"Crawler completed! Found {crawler_state['found']} WordPress sites")
        
    except Exception as e:
        log_message(f"Crawler error: {e}")
    finally:
        crawler_state["running"] = False

@app.route('/')
def home():
    """Home page with status"""
    return jsonify({
        "status": "WordPress IDN Crawler",
        "running": crawler_state["running"],
        "progress": f"{crawler_state['progress']}/{crawler_state['total']}",
        "found": crawler_state["found"],
        "current_idn": crawler_state["current_idn"],
        "start_time": crawler_state["start_time"],
        "last_update": crawler_state["last_update"]
    })

@app.route('/start')
def start_crawler():
    """Start the crawler"""
    if crawler_state["running"]:
        return jsonify({"error": "Crawler already running"})
    
    # Start crawler in background thread
    thread = threading.Thread(target=run_crawler, daemon=True)
    thread.start()
    
    return jsonify({"message": "Crawler started", "status": "running"})

@app.route('/stop')
def stop_crawler():
    """Stop the crawler"""
    crawler_state["running"] = False
    return jsonify({"message": "Crawler stop requested"})

@app.route('/status')
def get_status():
    """Get current status"""
    return jsonify(crawler_state)

@app.route('/download')
def download_results():
    """Download the results CSV"""
    if os.path.exists(OUTPUT_CSV):
        return send_file(OUTPUT_CSV, as_attachment=True)
    else:
        return jsonify({"error": "No results file found"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 