Future Improvements

### De-duplication of already scraped data
- 2026-01-14
    - Deduping/stateful scraping: store recent article_ids in a local state file (JSON/SQLite) and skip known items; add TTL/size caps to avoid unbounded growth.
    - Time windowing: stop processing once list items are older than a configured cutoff (e.g., N days), with a fallback to recent IDs for edits.
    - Conditional requests: cache ETag/Last-Modified for list pages and send If-Modified-Since/If-None-Match to reduce bandwidth when nothing changes.
