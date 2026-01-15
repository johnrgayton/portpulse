import os

import pytest

from news_scraper import (
    extract_article_fields,
    parse_gcaptain_list,
    parse_generic_port_list,
    parse_marineinsight_list,
    make_article_id,
    canonicalize_url,
    fetch_text,
    build_session,
)


def test_parse_gcaptain_list_minimal():
    html = """
    <article>
      <h2><a href="/sample-story">Port delays expected</a></h2>
      <p>Backups at terminal gates</p>
      <time>2024-01-01</time>
    </article>
    """
    items = parse_gcaptain_list(html, "https://gcaptain.com/")
    assert len(items) == 1
    item = items[0]
    assert item["url"] == "https://gcaptain.com/sample-story"
    assert item["title"] == "Port delays expected"
    assert item["summary"] == "Backups at terminal gates"
    assert item["published_raw"] == "2024-01-01"


def test_parse_marineinsight_list_minimal():
    html = """
    <article>
      <h3><a href="https://www.marineinsight.com/ports/article">Port congestion</a></h3>
    </article>
    """
    items = parse_marineinsight_list(html, "https://www.marineinsight.com/")
    assert len(items) == 1
    assert items[0]["url"] == "https://www.marineinsight.com/ports/article"
    assert items[0]["title"] == "Port congestion"


def test_parse_generic_port_list_filters_short_titles():
    html = """
    <a href="/news/1">Short</a>
    <a href="/news/2">Extended notice about berth closures</a>
    """
    items = parse_generic_port_list(html, "https://example.com/news/")
    assert len(items) == 1
    assert items[0]["url"] == "https://example.com/news/2"
    assert "Extended notice" in items[0]["title"]


def test_extract_article_fields_pulls_content():
    html = """
    <html>
      <body>
        <article>
          <h1>Port backlog update</h1>
          <time>2024-02-10</time>
          <link rel="canonical" href="https://gcaptain.com/story-canonical" />
          <div class="entry-content">
            <p>First paragraph.</p>
            <p>Second paragraph.</p>
          </div>
        </article>
      </body>
    </html>
    """
    data = extract_article_fields(
        html,
        base_url="https://gcaptain.com/",
        source="gcaptain",
        url="https://gcaptain.com/story",
        title_hint=None,
    )
    assert data["title"] == "Port backlog update"
    assert "First paragraph." in data["content"]
    assert "Second paragraph." in data["content"]
    assert data["canonical_url"] == "https://gcaptain.com/story-canonical"
    assert data["article_id"] == make_article_id("https://gcaptain.com/story-canonical")


def test_canonicalize_url_fallback():
    url = "https://example.com/story?utm_source=foo"
    assert canonicalize_url(url, html=None) == url


@pytest.mark.integration
def test_fetch_text_integration():
    if os.getenv("RUN_INTEGRATION_TESTS") != "1":
        pytest.skip("set RUN_INTEGRATION_TESTS=1 to run live fetch tests")
    session = build_session()
    text = fetch_text(session, "https://gcaptain.com/", max_retries=1, sleep_s=0)
    assert text is not None
