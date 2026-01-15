#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set
from urllib.parse import parse_qsl, urlparse, urlunparse

import spacy
from spacy.pipeline import EntityRuler

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
}

DELAY_TERMS = [
    "congestion",
    "backlog",
    "delay",
    "delays",
    "queue",
    "waiting",
    "anchorage",
    "berth",
    "berthing",
    "terminal closure",
    "berth closure",
    "port closure",
    "shutdown",
    "labor strike",
    "work stoppage",
    "slowdown",
    "disruption",
    "bottleneck",
    "diversion",
    "diverted",
    "held up",
    "backed up",
]

SEVERE_TERMS = {"closure", "shutdown", "strike", "work stoppage"}

PORT_TERMS = [
    "Port of Houston",
    "Port Houston",
    "Port of New York and New Jersey",
    "Port of NY/NJ",
    "Port of Savannah",
    "Port of Charleston",
    "JAXPORT",
    "Port of Miami",
    "Port of New Orleans",
    "Port of Mobile",
    "Port Tampa Bay",
    "Port of Tampa",
]


def normalize_url_for_id(url: str) -> str:
    parsed = urlparse(url)
    query_pairs = [
        (k, v) for (k, v) in parse_qsl(parsed.query, keep_blank_values=True)
        if k not in TRACKING_PARAMS
    ]
    new_query = "&".join([f"{k}={v}" for k, v in query_pairs])
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
    )


def make_article_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def build_nlp() -> spacy.language.Language:
    nlp = spacy.blank("en")
    ruler = EntityRuler(nlp, validate=True)
    delay_patterns = [{"label": "DELAY_SIGNAL", "pattern": term} for term in DELAY_TERMS]
    port_patterns = [{"label": "PORT", "pattern": term} for term in PORT_TERMS]
    ruler.add_patterns(delay_patterns + port_patterns)
    nlp.add_pipe(ruler)
    return nlp


def load_processed_ids(path: str) -> Set[str]:
    if not os.path.exists(path):
        return set()
    processed = set()
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            article_id = row.get("article_id")
            if not article_id:
                url = row.get("canonical_url") or row.get("url")
                if url:
                    article_id = make_article_id(normalize_url_for_id(url))
            if article_id:
                processed.add(article_id)
    return processed


def iter_jsonl(path: str) -> Iterable[Dict]:
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def analyze_record(record: Dict, nlp: spacy.language.Language, analysis_run_id: str) -> Optional[Dict]:
    if "delay_score" in record:
        return None
    text_parts = [
        record.get("title"),
        record.get("summary"),
        record.get("content"),
    ]
    text = " ".join([part for part in text_parts if part])
    if not text:
        return None

    doc = nlp(text)
    delay_terms = sorted({ent.text for ent in doc.ents if ent.label_ == "DELAY_SIGNAL"})
    ports = sorted({ent.text for ent in doc.ents if ent.label_ == "PORT"})

    if not delay_terms:
        score = 0.0
    else:
        score = min(1.0, 0.15 * len(delay_terms))
        if ports:
            score += 0.2
        if any(term.lower() in SEVERE_TERMS for term in delay_terms):
            score += 0.2
        score = min(1.0, score)

    enriched = dict(record)
    enriched["delay_score"] = round(score, 3)
    enriched["delay_terms"] = delay_terms
    enriched["ports_mentioned"] = ports
    enriched["delay_signal"] = score > 0
    enriched["analysis_run_id"] = analysis_run_id
    enriched["analyzed_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return enriched


def write_jsonl(path: str, rows: Iterable[Dict]) -> int:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    count = 0
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze scraped news for delay signals.")
    parser.add_argument("--input", default="output/news.jsonl", help="Input JSONL path")
    parser.add_argument("--output", default="output/news_scored.jsonl", help="Output JSONL path")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        raise SystemExit(f"input not found: {args.input}")

    processed_ids = load_processed_ids(args.output)
    nlp = build_nlp()
    analysis_run_id = str(uuid.uuid4())

    new_rows = []
    for record in iter_jsonl(args.input):
        canonical = record.get("canonical_url") or record.get("url")
        if canonical:
            normalized = normalize_url_for_id(canonical)
            record.setdefault("canonical_url", canonical)
            record.setdefault("article_id", make_article_id(normalized))
        article_id = record.get("article_id")
        if article_id and article_id in processed_ids:
            continue

        enriched = analyze_record(record, nlp, analysis_run_id)
        if not enriched:
            continue
        new_rows.append(enriched)
        if article_id:
            processed_ids.add(article_id)

    count = write_jsonl(args.output, new_rows)
    print(f"wrote {count} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
