#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sys
import time
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


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def fetch_text(session: requests.Session, url: str, max_retries: int, sleep_s: float) -> Optional[str]:
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, timeout=DEFAULT_TIMEOUT)
            if resp.status_code in RETRY_STATUSES:
                logging.warning("retryable status %s for %s", resp.status_code, url)
                time.sleep(sleep_s * attempt)
                continue
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            logging.warning("request failed (%s/%s) for %s: %s", attempt, max_retries, url, exc)
            time.sleep(sleep_s * attempt)
    return None


def text_or_none(node) -> Optional[str]:
    if not node:
        return None
    text = node.get_text(" ", strip=True)
    return text or None


def normalize_url(base_url: str, href: str) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith("#"):
        return None
    return urljoin(base_url, href)


def domain_matches(base_url: str, candidate_url: str) -> bool:
    return urlparse(base_url).netloc == urlparse(candidate_url).netloc


def parse_gcaptain_list(html: str, base_url: str) -> List[Dict]:
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
    soup = BeautifulSoup(html, "lxml")
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

    return {
        "source": source,
        "url": url,
        "title": title,
        "published_raw": published,
        "content": "\n".join(paragraphs) if paragraphs else None,
        "scraped_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "domain": urlparse(base_url).netloc,
    }


def write_jsonl(path: str, rows: Iterable[Dict]) -> int:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    count = 0
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")
            count += 1
    return count


def limit_items(items: List[Dict], limit: int) -> List[Dict]:
    if limit <= 0:
        return items
    return items[:limit]


def main() -> int:
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

    sources = SOURCES

    session = build_session()
    output_rows = []
    seen_urls = set()

    for source in sources:
        list_url = source["url"]
        logging.info("fetch list: %s", list_url)
        html = fetch_text(session, list_url, args.max_retries, args.sleep)
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
                output_rows.append(
                    {
                        "source": item.get("source"),
                        "url": url,
                        "title": item.get("title"),
                        "summary": item.get("summary"),
                        "published_raw": item.get("published_raw"),
                        "scraped_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                        "domain": urlparse(list_url).netloc,
                        "list_url": list_url,
                    }
                )
                continue

            time.sleep(args.sleep)
            article_html = fetch_text(session, url, args.max_retries, args.sleep)
            if not article_html:
                logging.warning("failed to fetch article: %s", url)
                continue

            output_rows.append(
                extract_article_fields(
                    article_html,
                    list_url,
                    item.get("source") or source["name"],
                    url,
                    item.get("title"),
                )
            )

    count = write_jsonl(args.output, output_rows)
    logging.info("wrote %s records to %s", count, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
