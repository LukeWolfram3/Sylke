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

# -----------------------------
# Configuration constants
# -----------------------------
NAMES_CSV = "acuity_idns.csv"  # input file (single column header: name)
OUTPUT_CSV = "wordpress_idns.csv"  # output file (name, domain)

SEARCH_DELAY = 0.35  # seconds between Bing requests (jitter will be added)
CONCURRENCY = 4  # concurrent IDN workers
MAX_BING_RESULTS = 10  # how many search results to evaluate per IDN

# prefixes that often host WordPress instances for health systems
WP_PREFIXES = [
    "blog.",
    "news.",
    "today.",
    "stories.",
    "newsroom.",
]

# extra paths to probe on each host (in addition to "/")
WP_PATHS = [
    "/wp-json",  # WordPress REST API root
    "/wp-login.php",  # login page
    "/blog",  # common blog dir
    "/news",  # news dir
    "/feed",  # atom feed
    "/rss",  # alt feed
]

# regex for WordPress fingerprints
WP_RE = re.compile(
    r"wp-content|wp-includes|wordpress|wp-json", re.I
)

# -----------------------------
# Helpers
# -----------------------------


def load_names(path: str) -> list[str]:
    """Read first column from CSV (skipping header)."""
    names: list[str] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if row:
                names.append(row[0].strip())
    return names


async def bing_search(session: aiohttp.ClientSession, name: str) -> list[str]:
    """Return up to MAX_BING_RESULTS unique hostnames from Bing HTML results."""
    q = urllib.parse.quote_plus(f"{name} official website")
    url = f"https://www.bing.com/search?q={q}&count={MAX_BING_RESULTS}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            html = await resp.text()
    except Exception as e:
        print(f"Bing error for {name}: {e}", file=sys.stderr)
        return []

    hosts: list[str] = []
    soup = BeautifulSoup(html, "html.parser")
    # Bing results are inside li.b_algo > h2 > a
    for a in soup.select("li.b_algo h2 a"):
        href = str(a.get("href") or "")
        if not href or not href.startswith("http"):
            continue
        host = urllib.parse.urlsplit(href).hostname or ""
        if host and host not in hosts:
            hosts.append(host)
        if len(hosts) >= MAX_BING_RESULTS:
            break
    return hosts


def expand_hosts(hosts: list[str]) -> list[str]:
    """Add common WP subdomain prefixes for each base domain."""
    out: list[str] = []
    for host in hosts:
        out.append(host)
        # if host already has subdomain, use base domain as well
        parts = host.split(".")
        if len(parts) > 2:
            base = ".".join(parts[-2:])
        else:
            base = host
        for prefix in WP_PREFIXES:
            candidate = prefix + base
            out.append(candidate)
    return list(dict.fromkeys(out))  # dedupe preserving order


async def fetch_text(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=True) as resp:
            if resp.status < 400 and resp.content_type.startswith("text"):
                return await resp.text(errors="ignore")
            return ""
    except Exception:
        return ""


async def head_ok(session: aiohttp.ClientSession, url: str) -> bool:
    try:
        async with session.head(url, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True) as resp:
            return resp.status < 400
    except Exception:
        return False


async def test_host(session: aiohttp.ClientSession, host: str) -> bool:
    """Check host for WP signs across several paths."""
    schemes = ["https://", "http://"]
    for scheme in schemes:
        base_url = scheme + host
        # first: fetch root
        html = await fetch_text(session, base_url)
        if WP_RE.search(html):
            return True
        # other paths
        for p in WP_PATHS:
            url = base_url.rstrip("/") + p
            if p == "/wp-login.php":
                if await head_ok(session, url):
                    return True
            else:
                html_path = await fetch_text(session, url)
                if WP_RE.search(html_path):
                    return True
    return False


async def process_name(name: str, search_sess: aiohttp.ClientSession, fetch_sess: aiohttp.ClientSession) -> tuple[str, str] | None:
    await asyncio.sleep(SEARCH_DELAY + random.random() * 0.2)
    hosts = await bing_search(search_sess, name)
    if not hosts:
        return None
    hosts = expand_hosts(hosts)
    for host in hosts:
        is_wp = await test_host(fetch_sess, host)
        if is_wp:
            return name, host
    return None


async def run():
    names = load_names(NAMES_CSV)
    print(f"Total IDNs: {len(names)}")

    sslctx = ssl.create_default_context()
    headers = {"User-Agent": "Mozilla/5.0"}

    sem = asyncio.Semaphore(CONCURRENCY)

    results: list[tuple[str, str]] = []

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=sslctx, limit_per_host=CONCURRENCY), headers=headers) as search_sess, \
            aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=sslctx, limit_per_host=CONCURRENCY), headers=headers) as fetch_sess:

        async def worker(name: str):
            async with sem:
                res = await process_name(name, search_sess, fetch_sess)
                return res

        tasks = [asyncio.create_task(worker(n)) for n in names]
        for idx, task in enumerate(asyncio.as_completed(tasks), 1):
            res = await task
            if res:
                results.append(res)
            if idx % 50 == 0:
                print(
                    f"Processed {idx}/{len(names)} – WP hits: {len(results)}",
                    file=sys.stdout,
                    flush=True,
                )

    results_sorted = sorted(results, key=lambda x: x[0].lower())
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "domain"])
        w.writerows(results_sorted)
    print(f"Finished. WordPress sites detected: {len(results_sorted)}  -> {OUTPUT_CSV}")


if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(run())
    print(f"Elapsed {time.time() - start_time:.1f}s") 