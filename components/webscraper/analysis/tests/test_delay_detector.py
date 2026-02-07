import json
from pathlib import Path

from delay_detector import (
    analyze_record,
    build_nlp,
    load_processed_ids,
    make_article_id,
    normalize_url_for_id,
    iter_jsonl,
    write_jsonl,
)


def test_normalize_url_for_id_removes_tracking():
    url = "https://example.com/story?utm_source=foo&x=1"
    normalized = normalize_url_for_id(url)
    assert "utm_source" not in normalized
    assert "x=1" in normalized


def test_analyze_record_scores_delay_terms():
    nlp = build_nlp()
    record = {
        "title": "Port of Houston faces congestion and delays",
        "summary": "Berth closure due to backlog.",
        "content": "Ships waiting at anchorage.",
    }
    enriched = analyze_record(record, nlp, analysis_run_id="test-run")
    assert enriched is not None
    assert enriched["delay_signal"] is True
    assert enriched["delay_score"] > 0
    assert "Port of Houston" in enriched["ports_mentioned"]
    assert "congestion" in [term.lower() for term in enriched["delay_terms"]]


def test_analyze_record_skips_when_no_text():
    nlp = build_nlp()
    record = {"title": None, "summary": None, "content": None}
    assert analyze_record(record, nlp, analysis_run_id="test-run") is None


def test_load_processed_ids_from_jsonl(tmp_path: Path):
    output = tmp_path / "scored.jsonl"
    payload = {"article_id": make_article_id("https://example.com/story")}
    output.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    processed = load_processed_ids(str(output))
    assert payload["article_id"] in processed


def test_jsonl_pipeline_end_to_end(tmp_path: Path):
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_rows = [
        {
            "title": "Port of Savannah sees congestion",
            "summary": "Backlog reported at terminal.",
            "content": "Vessels waiting at anchorage.",
            "url": "https://example.com/story?utm_source=foo",
        }
    ]
    input_path.write_text("\n".join(json.dumps(row) for row in input_rows) + "\n", encoding="utf-8")

    nlp = build_nlp()
    analysis_run_id = "test-run"
    enriched_rows = []
    for record in iter_jsonl(str(input_path)):
        enriched = analyze_record(record, nlp, analysis_run_id)
        assert enriched is not None
        enriched_rows.append(enriched)

    count = write_jsonl(str(output_path), enriched_rows)
    assert count == 1
    output_text = output_path.read_text(encoding="utf-8")
    assert "delay_score" in output_text
