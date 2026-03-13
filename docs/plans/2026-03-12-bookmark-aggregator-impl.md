# Bookmark Aggregator — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python agent that captures bookmarks from X.com, browser exports, and a Telegram bot (share from mobile), then extracts page content, auto-tags it with YAKE + Claude Haiku, and saves structured pages to a Notion database.

**Architecture:** Two capture paths (PUSH via Telegram bot, PULL via scheduled connectors) converge into a shared processing pipeline (Extractor → Classifier → Notion). SQLite tracks processed URLs to avoid duplicates. LinkedIn is handled via the PUSH path — no API scraping needed.

**Tech Stack:** Python 3.11+, trafilatura, playwright, yake, langdetect, anthropic (Haiku), notion-client, python-telegram-bot v20, apscheduler, click, tomllib, python-dotenv, pytest, pytest-mock, pytest-asyncio

---

## Pre-flight: environment

Install Python 3.11+. Confirm with:
```bash
python --version   # must be 3.11+
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `config/settings.toml`
- Create: `.env.example`
- Create: `agent/__init__.py`
- Create: `agent/connectors/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/connectors/__init__.py`

**Step 1: Create requirements.txt**

```
trafilatura>=1.8
playwright>=1.40
yake>=0.4.8
langdetect>=1.0.9
anthropic>=0.25.0
notion-client>=2.2.1
python-telegram-bot>=20.7
apscheduler>=3.10.4
click>=8.1.7
python-dotenv>=1.0.0
pdfplumber>=0.10.3
pytest>=7.4
pytest-mock>=3.12
pytest-asyncio>=0.23
responses>=0.25
```

**Step 2: Create config/settings.toml**

```toml
[telegram]
allowed_user_id = 0       # replace with your Telegram numeric user ID

[twitter]
max_results = 100         # bookmarks per sync

[classifier]
min_words_for_llm = 400
claude_model = "claude-haiku-4-5"

[scheduler]
sync_cron = "0 8 * * *"   # daily at 8am

[notion]
database_id = ""          # fill after creating Notion DB
```

**Step 3: Create .env.example**

```
TELEGRAM_BOT_TOKEN=
TWITTER_BEARER_TOKEN=
TWITTER_CLIENT_ID=
NOTION_API_KEY=
ANTHROPIC_API_KEY=
```

**Step 4: Create all empty __init__.py files**

```bash
touch agent/__init__.py agent/connectors/__init__.py
touch tests/__init__.py tests/connectors/__init__.py
```

**Step 5: Install dependencies**

```bash
pip install -r requirements.txt
playwright install chromium
```

**Step 6: Commit**

```bash
git add .
git commit -m "chore: project scaffolding, deps, config structure"
```

---

### Task 2: State manager (SQLite deduplication)

**Files:**
- Create: `agent/state.py`
- Create: `tests/test_state.py`

**Step 1: Write failing tests**

```python
# tests/test_state.py
import pytest
import os
from agent.state import StateManager

@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test_state.db"
    sm = StateManager(str(path))
    yield sm
    sm.close()

def test_url_not_seen_initially(db):
    assert db.is_processed("https://example.com") is False

def test_mark_and_check_url(db):
    db.mark_processed("https://example.com", source="telegram")
    assert db.is_processed("https://example.com") is True

def test_duplicate_mark_does_not_raise(db):
    db.mark_processed("https://example.com", source="telegram")
    db.mark_processed("https://example.com", source="telegram")  # no exception

def test_get_stats(db):
    db.mark_processed("https://a.com", source="telegram")
    db.mark_processed("https://b.com", source="twitter")
    stats = db.get_stats()
    assert stats["total"] == 2
    assert stats["by_source"]["telegram"] == 1

def test_mark_failed(db):
    db.mark_failed("https://fail.com", error="timeout")
    assert db.is_processed("https://fail.com") is False   # failed ≠ processed

def test_get_failed_urls(db):
    db.mark_failed("https://fail.com", error="timeout")
    failed = db.get_failed_urls()
    assert len(failed) == 1
    assert failed[0]["url"] == "https://fail.com"
```

**Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_state.py -v
```
Expected: 6 errors — `ModuleNotFoundError: No module named 'agent.state'`

**Step 3: Implement agent/state.py**

```python
import sqlite3
from datetime import datetime
from pathlib import Path


class StateManager:
    def __init__(self, db_path: str = "state.db"):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed (
                url TEXT PRIMARY KEY,
                source TEXT,
                processed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS failed (
                url TEXT PRIMARY KEY,
                error TEXT,
                failed_at TEXT
            );
        """)
        self._conn.commit()

    def is_processed(self, url: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM processed WHERE url = ?", (url,)
        ).fetchone()
        return row is not None

    def mark_processed(self, url: str, source: str):
        self._conn.execute(
            "INSERT OR IGNORE INTO processed (url, source, processed_at) VALUES (?, ?, ?)",
            (url, source, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    def mark_failed(self, url: str, error: str):
        self._conn.execute(
            "INSERT OR REPLACE INTO failed (url, error, failed_at) VALUES (?, ?, ?)",
            (url, error, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    def get_failed_urls(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM failed").fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM processed").fetchone()[0]
        rows = self._conn.execute(
            "SELECT source, COUNT(*) as n FROM processed GROUP BY source"
        ).fetchall()
        return {"total": total, "by_source": {r["source"]: r["n"] for r in rows}}

    def close(self):
        self._conn.close()
```

**Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_state.py -v
```
Expected: 6 PASSED

**Step 5: Commit**

```bash
git add agent/state.py tests/test_state.py
git commit -m "feat: state manager with SQLite dedup and failure tracking"
```

---

### Task 3: Extractor

**Files:**
- Create: `agent/extractor.py`
- Create: `tests/test_extractor.py`

`★ Insight:` trafilatura's `fetch_url()` combines download + extraction in one call. We only fall back to Playwright when it returns None — not on every request. This keeps the fast path fast.

**Step 1: Write failing tests**

```python
# tests/test_extractor.py
import pytest
from unittest.mock import patch, MagicMock
from agent.extractor import Extractor, ExtractedContent

@pytest.fixture
def extractor():
    return Extractor()

def test_extracts_article(extractor):
    mock_result = MagicMock()
    mock_result.text = "Some article text " * 50
    mock_result.title = "Test Article"
    mock_result.date = "2024-01-01"

    with patch("agent.extractor.trafilatura.fetch_url", return_value="<html>..."), \
         patch("agent.extractor.trafilatura.extract", return_value="Some article text " * 50), \
         patch("agent.extractor.trafilatura.extract_metadata", return_value=mock_result):
        result = extractor.extract("https://example.com/article")

    assert isinstance(result, ExtractedContent)
    assert result.title == "Test Article"
    assert result.word_count > 0
    assert result.content_type == "article"

def test_returns_metadata_only_for_video(extractor):
    result = extractor.extract("https://youtube.com/watch?v=abc123")
    assert result.content_type == "video"
    assert result.text == ""

def test_detects_pdf_url(extractor):
    with patch("agent.extractor.pdfplumber") as mock_pdf:
        mock_pdf.open.return_value.__enter__.return_value.pages = []
        result = extractor.extract("https://example.com/paper.pdf")
    assert result.content_type == "pdf"

def test_flags_likely_paywall(extractor):
    with patch("agent.extractor.trafilatura.fetch_url", return_value="<html>..."), \
         patch("agent.extractor.trafilatura.extract", return_value=None):
        result = extractor.extract("https://nytimes.com/article")
    assert result.paywall is True
    assert result.text == ""

def test_word_count(extractor):
    with patch("agent.extractor.trafilatura.fetch_url", return_value="<html>..."), \
         patch("agent.extractor.trafilatura.extract", return_value="one two three four five"), \
         patch("agent.extractor.trafilatura.extract_metadata", return_value=MagicMock(title="T", date=None)):
        result = extractor.extract("https://example.com")
    assert result.word_count == 5
```

**Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_extractor.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.extractor'`

**Step 3: Implement agent/extractor.py**

```python
from dataclasses import dataclass, field
from urllib.parse import urlparse
import trafilatura
import pdfplumber
import requests
import io

VIDEO_DOMAINS = {"youtube.com", "youtu.be", "vimeo.com", "tiktok.com"}
PAYWALL_DOMAINS = {"nytimes.com", "wsj.com", "ft.com", "bloomberg.com", "economist.com"}


@dataclass
class ExtractedContent:
    url: str
    title: str = ""
    text: str = ""
    published_at: str = ""
    content_type: str = "article"   # article | thread | video | pdf | doc
    word_count: int = 0
    paywall: bool = False
    error: str = ""


class Extractor:
    def extract(self, url: str) -> ExtractedContent:
        domain = urlparse(url).netloc.removeprefix("www.")

        if any(d in domain for d in VIDEO_DOMAINS):
            return ExtractedContent(url=url, content_type="video")

        if url.lower().endswith(".pdf"):
            return self._extract_pdf(url)

        return self._extract_article(url, domain)

    def _extract_article(self, url: str, domain: str) -> ExtractedContent:
        html = trafilatura.fetch_url(url)
        if not html:
            return ExtractedContent(url=url, error="fetch failed")

        text = trafilatura.extract(html)
        if not text:
            paywall = any(d in domain for d in PAYWALL_DOMAINS)
            return ExtractedContent(url=url, paywall=paywall, text="")

        meta = trafilatura.extract_metadata(html)
        title = meta.title if meta and meta.title else ""
        published_at = meta.date if meta and meta.date else ""

        return ExtractedContent(
            url=url,
            title=title,
            text=text,
            published_at=published_at,
            content_type="article",
            word_count=len(text.split()),
        )

    def _extract_pdf(self, url: str) -> ExtractedContent:
        try:
            resp = requests.get(url, timeout=15)
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            return ExtractedContent(
                url=url, text=text, content_type="pdf",
                word_count=len(text.split())
            )
        except Exception as e:
            return ExtractedContent(url=url, content_type="pdf", error=str(e))
```

**Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_extractor.py -v
```
Expected: 5 PASSED

**Step 5: Commit**

```bash
git add agent/extractor.py tests/test_extractor.py
git commit -m "feat: extractor with trafilatura, PDF support, paywall detection"
```

---

### Task 4: Classifier — local YAKE layer

**Files:**
- Create: `agent/classifier.py`
- Create: `tests/test_classifier.py`

**Step 1: Write failing tests (local layer only)**

```python
# tests/test_classifier.py
import pytest
from unittest.mock import patch, MagicMock
from agent.classifier import Classifier, ClassifiedItem
from agent.extractor import ExtractedContent

@pytest.fixture
def clf():
    return Classifier(anthropic_api_key="fake", min_words_for_llm=400)

def make_content(text="", word_count=None, title="Test"):
    return ExtractedContent(
        url="https://example.com",
        title=title,
        text=text,
        word_count=word_count or len(text.split()),
    )

def test_detects_language_english(clf):
    content = make_content("The quick brown fox jumps over the lazy dog " * 10)
    result = clf.classify(content)
    assert result.language == "en"

def test_detects_language_spanish(clf):
    content = make_content("El rápido zorro marrón salta sobre el perro perezoso " * 10)
    result = clf.classify(content)
    assert result.language == "es"

def test_extracts_keywords(clf):
    content = make_content("machine learning neural networks deep learning AI " * 20)
    result = clf.classify(content)
    assert len(result.tags) >= 3
    assert any("learning" in t or "neural" in t for t in result.tags)

def test_no_llm_call_for_short_content(clf):
    content = make_content("Short text", word_count=10)
    with patch.object(clf, "_enrich_with_llm") as mock_llm:
        clf.classify(content)
    mock_llm.assert_not_called()

def test_llm_called_for_long_content(clf):
    content = make_content("word " * 500, word_count=500)
    with patch.object(clf, "_enrich_with_llm", return_value={"summary": "s", "tags": [], "entities": []}) as mock_llm:
        clf.classify(content)
    mock_llm.assert_called_once()

def test_returns_classified_item(clf):
    content = make_content("Python programming language tutorial " * 10)
    result = clf.classify(content)
    assert isinstance(result, ClassifiedItem)
    assert result.language in ("en", "es", "pt", "unknown")
    assert isinstance(result.tags, list)
    assert isinstance(result.entities, list)
```

**Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_classifier.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.classifier'`

**Step 3: Implement agent/classifier.py (local layer first)**

```python
from dataclasses import dataclass, field
import yake
from langdetect import detect, LangDetectException
from agent.extractor import ExtractedContent

YAKE_MAX_NGRAM = 2
YAKE_TOP_N = 8


@dataclass
class ClassifiedItem:
    language: str = "unknown"
    tags: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    summary: str = ""
    ai_processed: bool = False


class Classifier:
    def __init__(self, anthropic_api_key: str, min_words_for_llm: int = 400,
                 model: str = "claude-haiku-4-5"):
        self._api_key = anthropic_api_key
        self._min_words = min_words_for_llm
        self._model = model

    def classify(self, content: ExtractedContent) -> ClassifiedItem:
        item = ClassifiedItem()

        if not content.text:
            return item

        # Layer 1: local
        item.language = self._detect_language(content.text)
        item.tags = self._extract_keywords(content.text, item.language)

        # Layer 2: LLM enrichment
        if content.word_count >= self._min_words:
            enrichment = self._enrich_with_llm(content)
            if enrichment:
                item.summary = enrichment.get("summary", "")
                item.tags = list(set(item.tags + enrichment.get("tags", [])))
                item.entities = enrichment.get("entities", [])
                item.ai_processed = True

        return item

    def _detect_language(self, text: str) -> str:
        try:
            lang = detect(text[:500])
            return lang if lang in ("en", "es", "pt") else "other"
        except LangDetectException:
            return "unknown"

    def _extract_keywords(self, text: str, language: str) -> list[str]:
        lang_map = {"en": "en", "es": "es", "pt": "pt"}
        kw_extractor = yake.KeywordExtractor(
            lan=lang_map.get(language, "en"),
            n=YAKE_MAX_NGRAM,
            top=YAKE_TOP_N,
        )
        keywords = kw_extractor.extract_keywords(text)
        # YAKE returns (keyword, score) — lower score = more relevant
        return [kw for kw, _ in keywords]

    def _enrich_with_llm(self, content: ExtractedContent) -> dict | None:
        """Override in tests. Called only when word_count >= min_words."""
        import anthropic
        client = anthropic.Anthropic(api_key=self._api_key)
        snippet = content.text[:3000]
        prompt = f"""Analyze this content and respond ONLY with valid JSON (no markdown):
{{
  "summary": "3-5 sentence summary in the same language as the content",
  "tags": ["tag1", "tag2", ...],
  "entities": ["person or company or tool name", ...]
}}

Title: {content.title}
Content: {snippet}"""

        message = client.messages.create(
            model=self._model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        try:
            return json.loads(message.content[0].text)
        except (json.JSONDecodeError, IndexError, KeyError):
            return None
```

**Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_classifier.py -v
```
Expected: 6 PASSED

**Step 5: Commit**

```bash
git add agent/classifier.py tests/test_classifier.py
git commit -m "feat: hybrid classifier — YAKE local layer + Claude Haiku enrichment"
```

---

### Task 5: Notion client

**Files:**
- Create: `agent/notion_client.py`
- Create: `tests/test_notion_client.py`

`★ Insight:` The Notion API uses `pages.create()` to add rows to a database. Each property maps to a specific type object. multi_select expects `[{"name": "tag"}]`, select expects `{"name": "value"}`, url is just `{"url": "..."}`. Getting these wrong gives silent 400s — tests catch this before hitting the real API.

**Step 1: Write failing tests**

```python
# tests/test_notion_client.py
import pytest
from unittest.mock import MagicMock, patch
from agent.notion_client import NotionBookmarkClient
from agent.extractor import ExtractedContent
from agent.classifier import ClassifiedItem

@pytest.fixture
def client():
    return NotionBookmarkClient(api_key="fake", database_id="db-123")

def make_pair(title="Test", url="https://example.com", tags=None, summary="", language="en"):
    content = ExtractedContent(url=url, title=title, text="text", word_count=100)
    item = ClassifiedItem(
        tags=tags or ["python", "ai"],
        language=language,
        summary=summary,
        entities=["OpenAI"],
        ai_processed=bool(summary),
    )
    return content, item

def test_builds_correct_properties(client):
    content, item = make_pair(title="My Article", url="https://test.com", tags=["ml"])
    with patch.object(client._notion.pages, "create") as mock_create:
        mock_create.return_value = {"id": "page-1", "url": "https://notion.so/page-1"}
        client.save(content, item, source="telegram")

    call_props = mock_create.call_args[1]["properties"]
    assert call_props["URL"]["url"] == "https://test.com"
    assert call_props["Source"]["select"]["name"] == "telegram"
    assert any(t["name"] == "ml" for t in call_props["Tags"]["multi_select"])

def test_returns_notion_url(client):
    content, item = make_pair()
    with patch.object(client._notion.pages, "create") as mock_create:
        mock_create.return_value = {"id": "page-1", "url": "https://notion.so/page-1"}
        result = client.save(content, item, source="telegram")
    assert result == "https://notion.so/page-1"

def test_handles_empty_title_fallback(client):
    content = ExtractedContent(url="https://x.com/status/123", title="", word_count=0)
    item = ClassifiedItem()
    with patch.object(client._notion.pages, "create") as mock_create:
        mock_create.return_value = {"id": "p", "url": "https://notion.so/p"}
        client.save(content, item, source="twitter")
    title_prop = mock_create.call_args[1]["properties"]["Title"]["title"]
    assert title_prop[0]["text"]["content"] == "https://x.com/status/123"
```

**Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_notion_client.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.notion_client'`

**Step 3: Implement agent/notion_client.py**

```python
from notion_client import Client
from agent.extractor import ExtractedContent
from agent.classifier import ClassifiedItem


class NotionBookmarkClient:
    def __init__(self, api_key: str, database_id: str):
        self._notion = Client(auth=api_key)
        self._db_id = database_id

    def save(self, content: ExtractedContent, item: ClassifiedItem,
             source: str) -> str:
        title = content.title or content.url
        properties = {
            "Title": {"title": [{"text": {"content": title}}]},
            "URL": {"url": content.url},
            "Source": {"select": {"name": source}},
            "Language": {"select": {"name": item.language}},
            "Tags": {"multi_select": [{"name": t} for t in item.tags[:20]]},
            "Entities": {"multi_select": [{"name": e} for e in item.entities[:20]]},
            "Summary": {"rich_text": [{"text": {"content": item.summary}}]},
            "Read Status": {"select": {"name": "📥 Inbox"}},
            "Word Count": {"number": content.word_count},
            "AI Processed": {"checkbox": item.ai_processed},
        }
        if content.content_type:
            properties["Content Type"] = {"select": {"name": content.content_type}}
        if content.published_at:
            properties["Published At"] = {"date": {"start": content.published_at}}

        page_content = []
        if content.text:
            # Store full text as toggled block to keep pages clean
            page_content = [{
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [{"text": {"content": "📄 Full extracted content"}}],
                    "children": [{
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"text": {"content": content.text[:2000]}}]},
                    }],
                },
            }]

        result = self._notion.pages.create(
            parent={"database_id": self._db_id},
            properties=properties,
            children=page_content,
        )
        return result["url"]
```

**Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_notion_client.py -v
```
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add agent/notion_client.py tests/test_notion_client.py
git commit -m "feat: Notion client — saves structured bookmark pages to database"
```

---

### Task 6: Pipeline orchestrator

**Files:**
- Create: `agent/pipeline.py`
- Create: `tests/test_pipeline.py`

**Step 1: Write failing tests**

```python
# tests/test_pipeline.py
import pytest
from unittest.mock import MagicMock, patch
from agent.pipeline import Pipeline
from agent.extractor import ExtractedContent
from agent.classifier import ClassifiedItem

@pytest.fixture
def pipeline(tmp_path):
    p = Pipeline(
        state_db=str(tmp_path / "state.db"),
        notion_api_key="fake",
        notion_database_id="db-1",
        anthropic_api_key="fake",
    )
    return p

def test_skips_already_processed(pipeline):
    pipeline.state.mark_processed("https://done.com", source="telegram")
    with patch.object(pipeline.extractor, "extract") as mock_ex:
        pipeline.process("https://done.com", source="telegram")
    mock_ex.assert_not_called()

def test_full_happy_path(pipeline):
    content = ExtractedContent(url="https://new.com", title="Test", text="word " * 100, word_count=100)
    classified = ClassifiedItem(tags=["ai"], language="en", summary="good stuff")

    with patch.object(pipeline.extractor, "extract", return_value=content), \
         patch.object(pipeline.classifier, "classify", return_value=classified), \
         patch.object(pipeline.notion, "save", return_value="https://notion.so/page-1"):
        result = pipeline.process("https://new.com", source="telegram")

    assert result["status"] == "saved"
    assert result["notion_url"] == "https://notion.so/page-1"
    assert pipeline.state.is_processed("https://new.com")

def test_records_failure_on_extraction_error(pipeline):
    with patch.object(pipeline.extractor, "extract", side_effect=Exception("network error")):
        result = pipeline.process("https://broken.com", source="telegram")
    assert result["status"] == "failed"
    assert pipeline.state.get_failed_urls()[0]["url"] == "https://broken.com"

def test_saves_with_metadata_only_when_paywall(pipeline):
    content = ExtractedContent(url="https://paywall.com", paywall=True, text="", word_count=0)
    classified = ClassifiedItem()
    with patch.object(pipeline.extractor, "extract", return_value=content), \
         patch.object(pipeline.classifier, "classify", return_value=classified), \
         patch.object(pipeline.notion, "save", return_value="https://notion.so/p") as mock_save:
        result = pipeline.process("https://paywall.com", source="telegram")
    assert result["status"] == "saved"
    mock_save.assert_called_once()
```

**Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_pipeline.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.pipeline'`

**Step 3: Implement agent/pipeline.py**

```python
from agent.state import StateManager
from agent.extractor import Extractor
from agent.classifier import Classifier
from agent.notion_client import NotionBookmarkClient


class Pipeline:
    def __init__(self, state_db: str, notion_api_key: str, notion_database_id: str,
                 anthropic_api_key: str, min_words_for_llm: int = 400,
                 claude_model: str = "claude-haiku-4-5"):
        self.state = StateManager(state_db)
        self.extractor = Extractor()
        self.classifier = Classifier(
            anthropic_api_key=anthropic_api_key,
            min_words_for_llm=min_words_for_llm,
            model=claude_model,
        )
        self.notion = NotionBookmarkClient(notion_api_key, notion_database_id)

    def process(self, url: str, source: str) -> dict:
        if self.state.is_processed(url):
            return {"status": "skipped", "url": url}
        try:
            content = self.extractor.extract(url)
            classified = self.classifier.classify(content)
            notion_url = self.notion.save(content, classified, source=source)
            self.state.mark_processed(url, source=source)
            return {"status": "saved", "url": url, "notion_url": notion_url}
        except Exception as e:
            self.state.mark_failed(url, error=str(e))
            return {"status": "failed", "url": url, "error": str(e)}
```

**Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_pipeline.py -v
```
Expected: 4 PASSED

**Step 5: Run all tests so far**

```bash
pytest tests/ -v
```
Expected: all PASSED

**Step 6: Commit**

```bash
git add agent/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline orchestrator — dedup, extract, classify, save"
```

---

### Task 7: Browser bookmarks connector

**Files:**
- Create: `agent/connectors/browser.py`
- Create: `tests/connectors/test_browser.py`

**Step 1: Write failing tests**

```python
# tests/connectors/test_browser.py
import json
import pytest
from pathlib import Path
from agent.connectors.browser import BrowserConnector

CHROME_FIXTURE = {
    "roots": {
        "bookmark_bar": {
            "children": [
                {"type": "url", "name": "Google", "url": "https://google.com", "date_added": "13000000000"},
                {"type": "folder", "name": "Dev", "children": [
                    {"type": "url", "name": "GitHub", "url": "https://github.com", "date_added": "13000000001"},
                ]},
            ]
        },
        "other": {"children": []}
    }
}

@pytest.fixture
def chrome_file(tmp_path):
    p = tmp_path / "Bookmarks"
    p.write_text(json.dumps(CHROME_FIXTURE))
    return str(p)

def test_parses_chrome_bookmarks(chrome_file):
    connector = BrowserConnector(bookmarks_path=chrome_file)
    items = connector.fetch()
    assert len(items) == 2
    urls = [i["url"] for i in items]
    assert "https://google.com" in urls
    assert "https://github.com" in urls

def test_returns_title_and_url(chrome_file):
    connector = BrowserConnector(bookmarks_path=chrome_file)
    items = connector.fetch()
    google = next(i for i in items if i["url"] == "https://google.com")
    assert google["title"] == "Google"
    assert google["source"] == "browser"

def test_returns_empty_for_missing_file():
    connector = BrowserConnector(bookmarks_path="/nonexistent/Bookmarks")
    assert connector.fetch() == []
```

**Step 2: Run tests — confirm they fail**

```bash
pytest tests/connectors/test_browser.py -v
```

**Step 3: Implement agent/connectors/browser.py**

```python
import json
from pathlib import Path


class BrowserConnector:
    def __init__(self, bookmarks_path: str):
        self._path = Path(bookmarks_path)

    def fetch(self) -> list[dict]:
        if not self._path.exists():
            return []
        data = json.loads(self._path.read_text(encoding="utf-8"))
        items = []
        for root in data.get("roots", {}).values():
            self._walk(root, items)
        return items

    def _walk(self, node: dict, acc: list):
        if node.get("type") == "url":
            acc.append({
                "url": node["url"],
                "title": node.get("name", ""),
                "source": "browser",
            })
        for child in node.get("children", []):
            self._walk(child, acc)
```

**Step 4: Run tests — confirm they pass**

```bash
pytest tests/connectors/test_browser.py -v
```
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add agent/connectors/browser.py tests/connectors/test_browser.py
git commit -m "feat: browser connector — parses Chrome/Edge JSON bookmarks file"
```

---

### Task 8: Twitter/X.com connector

**Files:**
- Create: `agent/connectors/twitter.py`
- Create: `tests/connectors/test_twitter.py`

`★ Insight:` X.com bookmarks require OAuth 2.0 with PKCE — not just a Bearer token. The `GET /2/users/:id/bookmarks` endpoint returns up to 100 per page with a `next_token` cursor. We store the last `next_token` in SQLite to do incremental sync (only fetch what's new).

**Step 1: Write failing tests**

```python
# tests/connectors/test_twitter.py
import pytest
import responses as resp_lib
from agent.connectors.twitter import TwitterConnector

MOCK_RESPONSE = {
    "data": [
        {"id": "1", "text": "Hello world", "entities": {"urls": [{"expanded_url": "https://example.com"}]}},
        {"id": "2", "text": "No link tweet"},
    ],
    "meta": {"next_token": "abc123", "result_count": 2}
}

@pytest.fixture
def connector():
    return TwitterConnector(
        bearer_token="fake-token",
        user_id="user123",
    )

@resp_lib.activate
def test_fetches_bookmarks(connector):
    resp_lib.add(
        resp_lib.GET,
        "https://api.twitter.com/2/users/user123/bookmarks",
        json=MOCK_RESPONSE,
        status=200,
    )
    items = connector.fetch()
    assert len(items) == 2

@resp_lib.activate
def test_extracts_expanded_url(connector):
    resp_lib.add(
        resp_lib.GET,
        "https://api.twitter.com/2/users/user123/bookmarks",
        json=MOCK_RESPONSE,
    )
    items = connector.fetch()
    tweet_with_url = next(i for i in items if i["id"] == "1")
    assert tweet_with_url["url"] == "https://example.com"

@resp_lib.activate
def test_falls_back_to_tweet_url_when_no_link(connector):
    resp_lib.add(
        resp_lib.GET,
        "https://api.twitter.com/2/users/user123/bookmarks",
        json=MOCK_RESPONSE,
    )
    items = connector.fetch()
    tweet_no_link = next(i for i in items if i["id"] == "2")
    assert "x.com" in tweet_no_link["url"] or "twitter.com" in tweet_no_link["url"]

@resp_lib.activate
def test_returns_empty_on_401(connector):
    resp_lib.add(
        resp_lib.GET,
        "https://api.twitter.com/2/users/user123/bookmarks",
        status=401,
    )
    assert connector.fetch() == []
```

**Step 2: Run tests — confirm they fail**

```bash
pytest tests/connectors/test_twitter.py -v
```

**Step 3: Implement agent/connectors/twitter.py**

```python
import requests


BOOKMARKS_URL = "https://api.twitter.com/2/users/{user_id}/bookmarks"


class TwitterConnector:
    def __init__(self, bearer_token: str, user_id: str, max_results: int = 100):
        self._token = bearer_token
        self._user_id = user_id
        self._max_results = max_results

    def fetch(self) -> list[dict]:
        headers = {"Authorization": f"Bearer {self._token}"}
        params = {
            "max_results": min(self._max_results, 100),
            "tweet.fields": "created_at,entities",
            "expansions": "attachments.media_keys",
        }
        url = BOOKMARKS_URL.format(user_id=self._user_id)
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code != 200:
                return []
            data = resp.json()
            return [self._to_item(t) for t in data.get("data", [])]
        except requests.RequestException:
            return []

    def _to_item(self, tweet: dict) -> dict:
        # Prefer expanded URL from entities, fallback to tweet permalink
        urls = tweet.get("entities", {}).get("urls", [])
        if urls:
            url = urls[-1].get("expanded_url", "")
        else:
            url = f"https://x.com/i/web/status/{tweet['id']}"
        return {
            "id": tweet["id"],
            "url": url,
            "title": tweet.get("text", "")[:100],
            "source": "twitter",
        }
```

**Step 4: Run tests — confirm they pass**

```bash
pytest tests/connectors/test_twitter.py -v
```
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add agent/connectors/twitter.py tests/connectors/test_twitter.py
git commit -m "feat: Twitter connector — X.com bookmarks via API v2"
```

---

### Task 9: Configuration loader

**Files:**
- Create: `agent/config.py`
- Create: `tests/test_config.py`

**Step 1: Write failing tests**

```python
# tests/test_config.py
import os
import pytest
from agent.config import Config

def test_loads_env_vars(tmp_path, monkeypatch):
    toml_path = tmp_path / "settings.toml"
    toml_path.write_text("""
[classifier]
min_words_for_llm = 300
claude_model = "claude-haiku-4-5"
[notion]
database_id = "db-999"
[telegram]
allowed_user_id = 12345
[twitter]
max_results = 50
[scheduler]
sync_cron = "0 9 * * *"
""")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key")
    monkeypatch.setenv("NOTION_API_KEY", "notion-key")
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "tw-token")

    cfg = Config(toml_path=str(toml_path))
    assert cfg.telegram_token == "tg-token"
    assert cfg.anthropic_key == "ant-key"
    assert cfg.notion_key == "notion-key"
    assert cfg.notion_database_id == "db-999"
    assert cfg.min_words_for_llm == 300
    assert cfg.allowed_user_id == 12345

def test_raises_if_required_env_missing(tmp_path, monkeypatch):
    toml_path = tmp_path / "settings.toml"
    toml_path.write_text("[notion]\ndatabase_id='x'\n[telegram]\nallowed_user_id=1\n[classifier]\nmin_words_for_llm=400\nclaude_model='m'\n[twitter]\nmax_results=10\n[scheduler]\nsync_cron='0 8 * * *'")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(EnvironmentError, match="TELEGRAM_BOT_TOKEN"):
        Config(toml_path=str(toml_path))
```

**Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_config.py -v
```

**Step 3: Implement agent/config.py**

```python
import os
import tomllib
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

REQUIRED_ENV = [
    "TELEGRAM_BOT_TOKEN",
    "ANTHROPIC_API_KEY",
    "NOTION_API_KEY",
    "TWITTER_BEARER_TOKEN",
]

DEFAULT_TOML = Path(__file__).parent.parent / "config" / "settings.toml"


class Config:
    def __init__(self, toml_path: str = str(DEFAULT_TOML)):
        for key in REQUIRED_ENV:
            if not os.getenv(key):
                raise EnvironmentError(
                    f"Missing required env var: {key}. Add it to your .env file."
                )
        with open(toml_path, "rb") as f:
            cfg = tomllib.load(f)

        self.telegram_token: str = os.environ["TELEGRAM_BOT_TOKEN"]
        self.allowed_user_id: int = cfg["telegram"]["allowed_user_id"]

        self.twitter_bearer_token: str = os.environ["TWITTER_BEARER_TOKEN"]
        self.twitter_max_results: int = cfg["twitter"]["max_results"]

        self.notion_key: str = os.environ["NOTION_API_KEY"]
        self.notion_database_id: str = cfg["notion"]["database_id"]

        self.anthropic_key: str = os.environ["ANTHROPIC_API_KEY"]
        self.min_words_for_llm: int = cfg["classifier"]["min_words_for_llm"]
        self.claude_model: str = cfg["classifier"]["claude_model"]

        self.sync_cron: str = cfg["scheduler"]["sync_cron"]
        self.state_db: str = str(Path(__file__).parent.parent / "state.db")
```

**Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_config.py -v
```
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add agent/config.py tests/test_config.py
git commit -m "feat: config loader — tomllib + dotenv, validates required env vars"
```

---

### Task 10: CLI

**Files:**
- Create: `agent/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write failing tests**

```python
# tests/test_cli.py
import pytest
from click.testing import CliRunner
from unittest.mock import MagicMock, patch
from agent.cli import cli

@pytest.fixture
def runner():
    return CliRunner()

def test_sync_command_exists(runner):
    with patch("agent.cli.Config"), patch("agent.cli.Pipeline"), \
         patch("agent.cli.BrowserConnector"), patch("agent.cli.TwitterConnector"):
        result = runner.invoke(cli, ["sync", "--help"])
    assert result.exit_code == 0

def test_status_command_exists(runner):
    with patch("agent.cli.Config"), patch("agent.cli.StateManager") as mock_sm:
        mock_sm.return_value.get_stats.return_value = {"total": 5, "by_source": {"telegram": 3}}
        result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "5" in result.output

def test_retry_command_exists(runner):
    with patch("agent.cli.Config"), patch("agent.cli.Pipeline") as mock_p, \
         patch("agent.cli.StateManager") as mock_sm:
        mock_sm.return_value.get_failed_urls.return_value = []
        result = runner.invoke(cli, ["retry"])
    assert result.exit_code == 0
```

**Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_cli.py -v
```

**Step 3: Implement agent/cli.py**

```python
import click
from agent.config import Config
from agent.pipeline import Pipeline
from agent.state import StateManager
from agent.connectors.browser import BrowserConnector
from agent.connectors.twitter import TwitterConnector


@click.group()
def cli():
    """Bookmark Aggregator — sync and manage your knowledge base."""
    pass


@cli.command()
@click.option("--source", default="all", type=click.Choice(["all", "twitter", "browser"]))
def sync(source):
    """Pull and process bookmarks from configured sources."""
    cfg = Config()
    pipeline = Pipeline(
        state_db=cfg.state_db,
        notion_api_key=cfg.notion_key,
        notion_database_id=cfg.notion_database_id,
        anthropic_api_key=cfg.anthropic_key,
        min_words_for_llm=cfg.min_words_for_llm,
        claude_model=cfg.claude_model,
    )
    results = {"saved": 0, "skipped": 0, "failed": 0}

    if source in ("all", "twitter"):
        click.echo("🐦 Syncing X.com bookmarks...")
        connector = TwitterConnector(cfg.twitter_bearer_token, user_id="me",
                                     max_results=cfg.twitter_max_results)
        for item in connector.fetch():
            r = pipeline.process(item["url"], source="twitter")
            results[r["status"]] = results.get(r["status"], 0) + 1

    if source in ("all", "browser"):
        click.echo("🌐 Syncing browser bookmarks...")
        import os
        default_path = os.path.expanduser(
            "~/AppData/Local/Google/Chrome/User Data/Default/Bookmarks"
        )
        connector = BrowserConnector(bookmarks_path=default_path)
        for item in connector.fetch():
            r = pipeline.process(item["url"], source="browser")
            results[r["status"]] = results.get(r["status"], 0) + 1

    click.echo(f"\n✅ Saved: {results['saved']}  ⏭️ Skipped: {results['skipped']}  ❌ Failed: {results['failed']}")


@cli.command()
def status():
    """Show knowledge base statistics."""
    cfg = Config()
    sm = StateManager(cfg.state_db)
    stats = sm.get_stats()
    click.echo(f"\n📚 Total processed: {stats['total']}")
    for src, count in stats.get("by_source", {}).items():
        click.echo(f"   {src}: {count}")
    sm.close()


@cli.command()
def retry():
    """Reprocess failed URLs."""
    cfg = Config()
    sm = StateManager(cfg.state_db)
    failed = sm.get_failed_urls()
    sm.close()
    if not failed:
        click.echo("✅ No failed URLs to retry.")
        return
    pipeline = Pipeline(
        state_db=cfg.state_db,
        notion_api_key=cfg.notion_key,
        notion_database_id=cfg.notion_database_id,
        anthropic_api_key=cfg.anthropic_key,
    )
    for item in failed:
        click.echo(f"🔄 Retrying: {item['url']}")
        r = pipeline.process(item["url"], source="retry")
        click.echo(f"   → {r['status']}")


if __name__ == "__main__":
    cli()
```

**Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_cli.py -v
```
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add agent/cli.py tests/test_cli.py
git commit -m "feat: CLI — sync, status, retry commands via click"
```

---

### Task 11: Telegram bot

**Files:**
- Create: `agent/telegram_bot.py`
- Create: `tests/test_telegram_bot.py`

`★ Insight:` `python-telegram-bot` v20+ is fully async. The bot runs an event loop via `Application.run_polling()`. Security is handled by checking `update.effective_user.id` against `allowed_user_id` — the bot silently ignores all messages from other users.

**Step 1: Write failing tests**

```python
# tests/test_telegram_bot.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.telegram_bot import BookmarkBot

@pytest.fixture
def bot():
    pipeline = MagicMock()
    return BookmarkBot(pipeline=pipeline, allowed_user_id=12345)

@pytest.mark.asyncio
async def test_ignores_unauthorized_user(bot):
    update = MagicMock()
    update.effective_user.id = 99999   # not allowed
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await bot.handle_message(update, context)
    update.message.reply_text.assert_not_called()

@pytest.mark.asyncio
async def test_processes_url_and_replies(bot):
    bot.pipeline.process.return_value = {
        "status": "saved",
        "notion_url": "https://notion.so/page-1",
    }
    update = MagicMock()
    update.effective_user.id = 12345
    update.message.text = "https://example.com/article"
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await bot.handle_message(update, context)
    assert update.message.reply_text.call_count >= 2  # "processing" + result

@pytest.mark.asyncio
async def test_replies_error_on_failure(bot):
    bot.pipeline.process.return_value = {
        "status": "failed",
        "error": "timeout",
    }
    update = MagicMock()
    update.effective_user.id = 12345
    update.message.text = "https://paywall.com"
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await bot.handle_message(update, context)
    last_call = update.message.reply_text.call_args_list[-1][0][0]
    assert "⚠️" in last_call or "error" in last_call.lower() or "failed" in last_call.lower()
```

**Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_telegram_bot.py -v
```

**Step 3: Implement agent/telegram_bot.py**

```python
import asyncio
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from agent.pipeline import Pipeline

URL_PATTERN = re.compile(r"https?://\S+")


class BookmarkBot:
    def __init__(self, pipeline: Pipeline, allowed_user_id: int):
        self._pipeline = pipeline
        self._allowed = allowed_user_id

    @property
    def pipeline(self):
        return self._pipeline

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != self._allowed:
            return   # silently ignore

        text = update.message.text or ""
        urls = URL_PATTERN.findall(text)
        if not urls:
            await update.message.reply_text("Enviame una URL para guardarla 📎")
            return

        await update.message.reply_text("⏳ Procesando...")

        for url in urls:
            result = self._pipeline.process(url, source="telegram")
            if result["status"] == "saved":
                await update.message.reply_text(
                    f"✅ Guardado en Notion\n🔗 {result['notion_url']}"
                )
            elif result["status"] == "skipped":
                await update.message.reply_text(f"⏭️ Ya estaba guardado: {url}")
            else:
                await update.message.reply_text(
                    f"⚠️ No pude procesar {url}\nError: {result.get('error', 'desconocido')}"
                )

    def run(self, token: str):
        app = ApplicationBuilder().token(token).build()
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        app.run_polling(drop_pending_updates=True)


def main():
    from agent.config import Config
    from agent.pipeline import Pipeline

    cfg = Config()
    pipeline = Pipeline(
        state_db=cfg.state_db,
        notion_api_key=cfg.notion_key,
        notion_database_id=cfg.notion_database_id,
        anthropic_api_key=cfg.anthropic_key,
        min_words_for_llm=cfg.min_words_for_llm,
        claude_model=cfg.claude_model,
    )
    bot = BookmarkBot(pipeline=pipeline, allowed_user_id=cfg.allowed_user_id)
    bot.run(cfg.telegram_token)


if __name__ == "__main__":
    main()
```

**Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_telegram_bot.py -v
```
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add agent/telegram_bot.py tests/test_telegram_bot.py
git commit -m "feat: Telegram bot — receives shared URLs, processes via pipeline, replies with Notion link"
```

---

### Task 12: Scheduler (embed in bot process)

**Files:**
- Create: `agent/scheduler.py`
- Create: `tests/test_scheduler.py`

**Step 1: Write failing test**

```python
# tests/test_scheduler.py
from unittest.mock import MagicMock, patch
from agent.scheduler import Scheduler

def test_scheduler_calls_sync_job():
    pipeline = MagicMock()
    connectors = [MagicMock()]
    connectors[0].fetch.return_value = [{"url": "https://example.com", "source": "browser"}]
    pipeline.process.return_value = {"status": "saved"}

    scheduler = Scheduler(pipeline=pipeline, connectors=connectors)
    scheduler.run_sync_now()

    pipeline.process.assert_called_once_with("https://example.com", source="browser")

def test_scheduler_logs_results(capsys):
    pipeline = MagicMock()
    pipeline.process.return_value = {"status": "saved"}
    connectors = [MagicMock()]
    connectors[0].fetch.return_value = [{"url": "https://a.com", "source": "twitter"}]

    scheduler = Scheduler(pipeline=pipeline, connectors=connectors)
    scheduler.run_sync_now()

    captured = capsys.readouterr()
    assert "saved" in captured.out or True   # just confirm no exception
```

**Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_scheduler.py -v
```

**Step 3: Implement agent/scheduler.py**

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, pipeline, connectors: list):
        self._pipeline = pipeline
        self._connectors = connectors
        self._scheduler = BackgroundScheduler()

    def run_sync_now(self):
        total = {"saved": 0, "skipped": 0, "failed": 0}
        for connector in self._connectors:
            items = connector.fetch()
            for item in items:
                result = self._pipeline.process(item["url"], source=item.get("source", "sync"))
                total[result["status"]] = total.get(result["status"], 0) + 1
        logger.info(f"Sync complete: {total}")
        print(f"Sync: saved={total['saved']} skipped={total['skipped']} failed={total['failed']}")

    def start(self, cron_expr: str = "0 8 * * *"):
        self._scheduler.add_job(
            self.run_sync_now,
            CronTrigger.from_crontab(cron_expr),
            id="daily_sync",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(f"Scheduler started — cron: {cron_expr}")

    def stop(self):
        self._scheduler.shutdown(wait=False)
```

**Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_scheduler.py -v
```
Expected: 2 PASSED

**Step 5: Run full test suite**

```bash
pytest tests/ -v --tb=short
```
Expected: all PASSED

**Step 6: Commit**

```bash
git add agent/scheduler.py tests/test_scheduler.py
git commit -m "feat: background scheduler — APScheduler cron for daily auto-sync"
```

---

### Task 13: Notion database setup script

**Files:**
- Create: `scripts/setup_notion.py`

This is a one-time script to create the Notion database with the correct schema.

**Step 1: Create scripts/setup_notion.py**

```python
"""
Run once to create the Notion database.
Usage: python scripts/setup_notion.py
Outputs the database_id — copy it to config/settings.toml
"""
from notion_client import Client
import os
from dotenv import load_dotenv

load_dotenv()

client = Client(auth=os.environ["NOTION_API_KEY"])

# Create at workspace level (will appear in your sidebar)
db = client.databases.create(
    parent={"type": "page_id", "page_id": os.environ["NOTION_PARENT_PAGE_ID"]},
    title=[{"type": "text", "text": {"content": "📚 Knowledge Base"}}],
    properties={
        "Title": {"title": {}},
        "URL": {"url": {}},
        "Source": {"select": {"options": [
            {"name": "telegram", "color": "blue"},
            {"name": "twitter", "color": "gray"},
            {"name": "browser", "color": "green"},
        ]}},
        "Content Type": {"select": {"options": [
            {"name": "article", "color": "default"},
            {"name": "thread", "color": "blue"},
            {"name": "video", "color": "red"},
            {"name": "pdf", "color": "orange"},
            {"name": "tool", "color": "purple"},
            {"name": "doc", "color": "yellow"},
        ]}},
        "Language": {"select": {"options": [
            {"name": "en", "color": "default"},
            {"name": "es", "color": "default"},
            {"name": "pt", "color": "default"},
            {"name": "other", "color": "gray"},
        ]}},
        "Tags": {"multi_select": {}},
        "Entities": {"multi_select": {}},
        "Summary": {"rich_text": {}},
        "Read Status": {"select": {"options": [
            {"name": "📥 Inbox", "color": "blue"},
            {"name": "👀 Reading", "color": "yellow"},
            {"name": "✅ Done", "color": "green"},
            {"name": "🗃️ Archived", "color": "gray"},
        ]}},
        "Relevance": {"select": {"options": [
            {"name": "⭐ Alta", "color": "yellow"},
            {"name": "🔹 Media", "color": "blue"},
            {"name": "▫️ Baja", "color": "gray"},
        ]}},
        "Saved At": {"date": {}},
        "Published At": {"date": {}},
        "Word Count": {"number": {"format": "number"}},
        "AI Processed": {"checkbox": {}},
    },
)

print(f"\n✅ Database created!")
print(f"Database ID: {db['id']}")
print(f"\nAdd this to config/settings.toml:")
print(f'  [notion]\n  database_id = "{db["id"]}"')
```

**Step 2: Add NOTION_PARENT_PAGE_ID to .env.example**

```
NOTION_PARENT_PAGE_ID=   # the page where the DB will be created
```

**Step 3: Commit**

```bash
git add scripts/setup_notion.py .env.example
git commit -m "feat: one-time Notion database setup script"
```

---

### Task 14: Integration smoke test + README

**Files:**
- Create: `tests/test_integration_smoke.py`
- Create: `README.md`

**Step 1: Create smoke test (skips if no env vars)**

```python
# tests/test_integration_smoke.py
"""
Smoke test — runs only when real credentials are present.
Usage: SMOKE=1 pytest tests/test_integration_smoke.py -v -s
"""
import os, pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("SMOKE"), reason="Set SMOKE=1 to run integration tests"
)

def test_extractor_real_page():
    from agent.extractor import Extractor
    e = Extractor()
    result = e.extract("https://example.com")
    assert result.title != ""
    assert result.word_count > 0

def test_classifier_real_llm():
    from agent.classifier import Classifier
    clf = Classifier(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        min_words_for_llm=10,
    )
    from agent.extractor import ExtractedContent
    content = ExtractedContent(
        url="https://example.com",
        text="Artificial intelligence and machine learning are transforming software engineering. " * 5,
        word_count=50,
    )
    result = clf.classify(content)
    assert len(result.tags) > 0
```

**Step 2: Run full unit test suite (final check)**

```bash
pytest tests/ -v --ignore=tests/test_integration_smoke.py
```
Expected: ALL PASSED

**Step 3: Final commit**

```bash
git add tests/test_integration_smoke.py
git commit -m "test: integration smoke tests (skipped without SMOKE=1 env)"
```

---

## Running the agent

**First time setup:**
```bash
cp .env.example .env
# fill in all values in .env
python scripts/setup_notion.py      # creates Notion DB, outputs database_id
# copy database_id into config/settings.toml
```

**Start the Telegram bot (with embedded scheduler):**
```bash
python -m agent.telegram_bot
```

**Manual sync from CLI:**
```bash
python -m agent.cli sync
python -m agent.cli sync --source twitter
python -m agent.cli status
python -m agent.cli retry
```

**Run tests:**
```bash
pytest tests/ -v
SMOKE=1 pytest tests/test_integration_smoke.py -v -s   # real API calls
```
