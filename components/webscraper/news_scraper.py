#!/usr/bin/env python3
import argparse
import hashlib
import json
import logging
import os
import random
import sys
import time
import uuid
from datetime import datetime
from typing import Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from sources import SOURCES


USER_AGENT = (
    "Mozilla/5.0 (compatible; PortPulseScraper/0.1; "
    "+https://example.com/portpulse)"
)
DEFAULT_TIMEOUT = 20
RETRY_STATUSES = {429, 500, 502, 503, 504}
JITTER_RATIO = 0.35


def build_session() -> requests.Session:
    # Centralize browser-like defaults once so all requests share consistent headers.
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return session


def compute_jitter(base: float, ratio: float) -> float:
    # Add bounded randomness to reduce deterministic request patterns.
    if base <= 0 or ratio <= 0:
        return 0.0
    return random.uniform(0.0, base * ratio)


def pace_request(pacing_state: Optional[Dict[str, float]], domain: str, base_sleep: float, jitter_ratio: float) -> None:
    # Per-domain pacing limits burst traffic when multiple sources are scraped in one run.
    if pacing_state is None or base_sleep <= 0:
        return
    now = time.monotonic()
    next_allowed = pacing_state.get(domain, now)
    if now < next_allowed:
        time.sleep(next_allowed - now)
    delay = base_sleep + compute_jitter(base_sleep, jitter_ratio)
    pacing_state[domain] = time.monotonic() + delay


def fetch_text(
    session: requests.Session,
    url: str,
    max_retries: int,
    sleep_s: float,
    pacing_state: Optional[Dict[str, float]] = None,
    jitter_ratio: float = 0.0,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    # Fetch with retry/backoff+jitter so transient failures do not fail the entire run.
    for attempt in range(1, max_retries + 1):
        if pacing_state is not None:
            pace_request(pacing_state, urlparse(url).netloc, sleep_s, jitter_ratio)
        try:
            resp = session.get(url, timeout=DEFAULT_TIMEOUT, headers=headers)
            if resp.status_code in RETRY_STATUSES:
                logging.warning("retryable status %s for %s", resp.status_code, url)
                backoff = sleep_s * (2 ** (attempt - 1))
                time.sleep(backoff + compute_jitter(backoff, jitter_ratio))
                continue
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            logging.warning("request failed (%s/%s) for %s: %s", attempt, max_retries, url, exc)
            backoff = sleep_s * (2 ** (attempt - 1))
            time.sleep(backoff + compute_jitter(backoff, jitter_ratio))
    return None


def text_or_none(node) -> Optional[str]:
    if not node:
        return None
    text = node.get_text(" ", strip=True)
    return text or None


def normalize_url(base_url: str, href: str) -> Optional[str]:
    # Resolve relative links while ignoring fragment-only anchors.
    if not href:
        return None
    href = href.strip()
    if href.startswith("#"):
        return None
    return urljoin(base_url, href)


def domain_matches(base_url: str, candidate_url: str) -> bool:
    return urlparse(base_url).netloc == urlparse(candidate_url).netloc


def make_hash_id(txt: str) -> str:
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()


def canonicalize_url(url: str, html: Optional[str] = None) -> str:
    # Prefer canonical links so tracking/query variants map to the same logical article.
    if html:
        soup = BeautifulSoup(html, "lxml")
        canonical = soup.select_one("link[rel='canonical']")
        if canonical:
            href = canonical.get("href")
            if href:
                return href.strip()
    return url


def parse_gcaptain_list(html: str, base_url: str) -> List[Dict]:
    # Site-specific extractor for gCaptain listing pages.
    soup = BeautifulSoup(html, "lxml")
    items = []
    for article in soup.select("article"):
        link = article.select_one("h2 a, h3 a, a")
        url = normalize_url(base_url, link.get("href")) if link else None
        if not url:
            continue
        title = text_or_none(link) or text_or_none(article.select_one("h2, h3"))
        summary = text_or_none(article.select_one("p"))
        published = text_or_none(article.select_one("time"))
        items.append(
            {
                "source": "gcaptain",
                "list_url": base_url,
                "url": url,
                "title": title,
                "summary": summary,
                "published_raw": published,
            }
        )
    return items


def parse_marineinsight_list(html: str, base_url: str) -> List[Dict]:
    # Site-specific extractor for Marine Insight listing pages.
    soup = BeautifulSoup(html, "lxml")
    items = []
    for link in soup.select("h3 a, h2 a, article a"):
        url = normalize_url(base_url, link.get("href"))
        if not url or not domain_matches(base_url, url):
            continue
        title = text_or_none(link)
        if not title:
            continue
        items.append(
            {
                "source": "marineinsight",
                "list_url": base_url,
                "url": url,
                "title": title,
            }
        )
    return items


def parse_generic_port_list(html: str, base_url: str) -> List[Dict]:
    # Generic fallback for port/news pages with inconsistent markup.
    soup = BeautifulSoup(html, "lxml")
    items = []
    seen = set()
    for link in soup.select("a[href]"):
        url = normalize_url(base_url, link.get("href"))
        if not url or not domain_matches(base_url, url):
            continue
        title = text_or_none(link)
        if not title or len(title) < 15:
            continue
        if url in seen:
            continue
        seen.add(url)
        items.append(
            {
                "source": "port_notice",
                "list_url": base_url,
                "url": url,
                "title": title,
            }
        )
    return items


def extract_article_fields(
    html: str, base_url: str, source: str, url: str, title_hint: Optional[str]
) -> Dict:
    # Extract normalized article payload for downstream scoring and storage.
    soup = BeautifulSoup(html, from_encoding="utf-8", features="lxml")
    title = text_or_none(soup.select_one("h1")) or title_hint
    published = text_or_none(soup.select_one("time"))

    if source == "gcaptain":
        content = soup.select_one(".entry-content")
    elif source == "marineinsight":
        content = soup.select_one(".td-post-content, .post-content")
    else:
        content = soup.select_one("article") or soup.select_one("main") or soup.body

    paragraphs = []
    if content:
        for p in content.select("p"):
            text = p.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)

    canonical_url = canonicalize_url(url, html)
    return {
        "source": source,
        "url": url,
        "canonical_url": canonical_url,
        "article_id": make_hash_id(canonical_url),
        "title": title,
        "published_raw": published,
        "content": "\n".join(paragraphs) if paragraphs else None,
        "scraped_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "domain": urlparse(base_url).netloc,
    }


def write_jsonl(path: str, rows: Iterable[Dict]) -> int:
    # Write each run to a unique timestamped JSONL file derived from the target path.
    output_dir = os.path.dirname(path) or "."
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.basename(path)
    stem, ext = os.path.splitext(base_name)
    run_stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    output_path = os.path.join(output_dir, f"{stem}-{run_stamp}{ext or '.jsonl'}")

    row_list = list(rows)
    if not row_list:
        return 0

    # Pre-serialize once for efficient batched writes.
    lines = [json.dumps(row, ensure_ascii=True) + "\n" for row in row_list]
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.writelines(lines)
    return len(row_list)


def limit_items(items: List[Dict], limit: int) -> List[Dict]:
    # Guardrail to cap source volume during testing and incremental runs.
    if limit <= 0:
        return items
    return items[:limit]


def main() -> int:
    # Orchestrates source fetch -> parse -> optional article fetch -> JSONL append.
    parser = argparse.ArgumentParser(description="Scrape maritime news sources.")
    parser.add_argument("--output", default="output/news.jsonl", help="JSONL output path")
    parser.add_argument("--limit-per-source", type=int, default=15, help="Max items per source")
    parser.add_argument("--max-retries", type=int, default=3, help="HTTP retry attempts")
    parser.add_argument("--sleep", type=float, default=1.5, help="Seconds between requests")
    parser.add_argument("--no-article-fetch", action="store_true", help="Skip fetching article bodies")
    # TODO: add a --sources flag to filter SOURCES by name at runtime.
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    # Source config is isolated in sources.py for easy enable/disable updates.
    sources = SOURCES

    session = build_session()
    pacing_state = {}
    output_rows = []
    seen_urls = set()
    run_id = str(uuid.uuid4())

    for source in sources:
        list_url = source["url"]
        logging.info("fetch list: %s", list_url)
        list_headers = source.get("headers")
        html = fetch_text(
            session,
            list_url,
            args.max_retries,
            args.sleep,
            pacing_state=pacing_state,
            jitter_ratio=JITTER_RATIO,
            headers=list_headers,
        )
        if not html:
            logging.warning("failed to fetch list: %s", list_url)
            continue

        if source["kind"] == "gcaptain":
            items = parse_gcaptain_list(html, list_url)
        elif source["kind"] == "marineinsight":
            items = parse_marineinsight_list(html, list_url)
        else:
            items = parse_generic_port_list(html, list_url)

        for item in limit_items(items, args.limit_per_source):
            url = item.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            if args.no_article_fetch:
                # Fast mode writes list-page metadata without full article requests.
                output_rows.append(
                    {
                        "source": item.get("source"),
                        "url": url,
                        "canonical_url": url,
                        "article_id": make_hash_id(url),
                        "run_id": run_id,
                        "title": item.get("title"),
                        "summary": item.get("summary"),
                        "summary_hash": make_hash_id(item.get("summary") or ""),
                        "published_raw": item.get("published_raw"),
                        "scraped_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                        "domain": urlparse(list_url).netloc,
                        "list_url": list_url,
                    }
                )
                continue

            article_headers = dict(source.get("headers") or {})
            # Referer improves compatibility with sites that enforce basic request provenance.
            article_headers.setdefault("Referer", list_url)
            article_html = fetch_text(
                session,
                url,
                args.max_retries,
                args.sleep,
                pacing_state=pacing_state,
                jitter_ratio=JITTER_RATIO,
                headers=article_headers,
            )
            if not article_html:
                logging.warning("failed to fetch article: %s", url)
                continue

            article_row = extract_article_fields(
                article_html,
                list_url,
                item.get("source") or source["name"],
                url,
                item.get("title"),
            )
            article_row["run_id"] = run_id
            output_rows.append(article_row)

    count = write_jsonl(args.output, output_rows)
    logging.info("wrote %s records to %s", count, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
