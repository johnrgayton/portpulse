# PortPulse

PortPulse is a real-time supply chain monitoring project that combines:
- streaming AIS vessel telemetry
- maritime news scraping
- delay-signal enrichment

The current repository contains three active components:
- `components/landing/aisstream_producer`: AIS stream ingestion to Kafka/Redpanda
- `components/webscraper`: maritime news scraping and JSONL output generation
- `components/webscraper/analysis`: NLP-based delay scoring on scraped articles

## Current Features

### 1) AIS Landing Producer (`components/landing/aisstream_producer`)
- Connects to `wss://stream.aisstream.io/v0/stream`
- Subscribes to configured bounding boxes and message types
- Publishes raw AIS messages to Kafka/Redpanda with idempotent producer settings
- Retries on stream disconnects using exponential backoff
- Supports optional SASL auth via environment variables

Key failure-handling behavior:
- Fails fast if required Kafka settings are missing
- Handles producer backpressure (`BufferError`) by flushing and continuing
- Logs malformed/unexpected AIS payloads instead of crashing

### 2) News Scraper (`components/webscraper`)
- Scrapes configured maritime news sources from `sources.py`
- Uses per-source parser strategies (`gcaptain`, `marineinsight`, generic fallback)
- Normalizes article payloads and computes deterministic article IDs
- Applies request pacing + jitter + retries for resilience
- Supports fast mode (`--no-article-fetch`) to skip full article extraction
- Writes one timestamped JSONL file per run

Current output behavior:
- `--output output/news.jsonl` produces files like `output/news-YYYYMMDDTHHMMSSZ.jsonl`
- The base output name is used as a stem; each run creates a unique file

### 3) Delay Detector (`components/webscraper/analysis`)
- Reads input JSONL and enriches records with delay intelligence
- Uses spaCy + `EntityRuler` for delay terms and known ports
- Produces `delay_score`, `delay_terms`, `ports_mentioned`, and metadata fields
- Deduplicates by `article_id` against prior scored output
- Uses a watermark file to skip analysis when no new input lines are detected

## Repository Layout

- `components/landing/aisstream_producer`: AIS websocket -> Kafka producer
- `components/webscraper`: scraping logic, source config, parser tests
- `components/webscraper/analysis`: delay analysis pipeline + tests
- `output`: runtime JSONL artifacts
- `docker-compose.yml`: compose config (currently includes `webscraper` service)

## Prerequisites

- Python 3.11+
- Docker (for containerized runs)
- Optional: access to Kafka/Redpanda and AISStream API key for landing component

## Local Run: News Scraper

```bash
cd components/webscraper
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Example scrape run
python news_scraper.py \
  --output ../../output/news.jsonl \
  --limit-per-source 10 \
  --max-retries 3 \
  --sleep 1.0
```

Fast metadata-only mode:

```bash
python news_scraper.py \
  --output ../../output/news.jsonl \
  --no-article-fetch
```

## Local Run: Delay Detector

Install dependencies:

```bash
cd components/webscraper/analysis
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run analysis against the most recent scraper output:

```bash
LATEST_NEWS_FILE=$(ls -t ../../output/news-*.jsonl | head -n 1)
python delay_detector.py \
  --input "$LATEST_NEWS_FILE" \
  --output ../../output/news_scored.jsonl \
  --watermark ../../output/.analysis_watermark
```

## Local Run: AIS Landing Producer

```bash
cd components/landing/aisstream_producer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export AISSTREAM_API_KEY="your_api_key"
export KAFKA_BROKERS="localhost:9092"
export KAFKA_TOPIC="ais.raw"

# Optional SASL
# export KAFKA_USERNAME="..."
# export KAFKA_PASSWORD="..."
# export KAFKA_SECURITY_PROTOCOL="SASL_PLAINTEXT"
# export KAFKA_SASL_MECHANISM="SCRAM-SHA-256"

python producer.py
```

## Docker Usage

### Option A: Docker Compose (Repository Root)

Current `docker-compose.yml` includes `webscraper` service.

```bash
docker compose build webscraper
docker compose run --rm webscraper
```

Output files are written to local `./output` via bind mount.

### Option B: Docker Build/Run Per Component

News scraper:

```bash
docker build -t portpulse-webscraper ./components/webscraper
docker run --rm \
  -v "$(pwd)/output:/app/output" \
  portpulse-webscraper \
  python /app/news_scraper.py --output /app/output/news.jsonl
```

Delay detector:

```bash
docker build -t portpulse-delay-detector ./components/webscraper/analysis
LATEST_NEWS_FILE=$(basename "$(ls -t output/news-*.jsonl | head -n 1)")
docker run --rm \
  -v "$(pwd)/output:/app/output" \
  portpulse-delay-detector \
  python /app/delay_detector.py \
    --input "/app/output/$LATEST_NEWS_FILE" \
    --output /app/output/news_scored.jsonl \
    --watermark /app/output/.analysis_watermark
```

AIS landing producer:

```bash
docker build -t portpulse-ais-producer ./components/landing/aisstream_producer
docker run --rm \
  -e AISSTREAM_API_KEY="your_api_key" \
  -e KAFKA_BROKERS="host.docker.internal:9092" \
  -e KAFKA_TOPIC="ais.raw" \
  portpulse-ais-producer
```

## End-to-End Example (Scrape -> Analyze)

From repository root:

```bash
# 1) Scrape
python components/webscraper/news_scraper.py --output output/news.jsonl

# 2) Analyze the latest scrape artifact
LATEST_NEWS_FILE=$(ls -t output/news-*.jsonl | head -n 1)
python components/webscraper/analysis/delay_detector.py \
  --input "$LATEST_NEWS_FILE" \
  --output output/news_scored.jsonl \
  --watermark output/.analysis_watermark
```

## Testing

Web scraper tests:

```bash
cd components/webscraper
pip install -r requirements-dev.txt
pytest -q
```

Delay detector tests:

```bash
cd components/webscraper/analysis
pytest -q
```

## Notes and Tradeoffs (Current State)

- Compose currently wires only `webscraper`; analysis service is present but commented out.
- The scraper now emits timestamped files per run; downstream jobs should select the latest file or pass an explicit input path.
- `future_improvements.md` tracks next-step enhancements and operational hardening.
