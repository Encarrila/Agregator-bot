import datetime as dt
import json

from digest import state


def _use_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE_PATH", str(tmp_path / "seen.json"))


def test_record_and_load(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    assert state.load_seen() == set()
    state.record_seen(["https://a", "https://b"])
    assert state.load_seen() == {"https://a", "https://b"}


def test_record_is_idempotent(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    state.record_seen(["https://a"])
    state.record_seen(["https://a", "https://b"])
    assert state.load_seen() == {"https://a", "https://b"}


def test_prunes_entries_older_than_retention(tmp_path, monkeypatch):
    p = tmp_path / "seen.json"
    old = (dt.date.today() - dt.timedelta(days=state.RETENTION_DAYS + 5)).isoformat()
    p.write_text(json.dumps([{"url": "https://old", "date": old}]), encoding="utf-8")
    _use_tmp(tmp_path, monkeypatch)
    state.record_seen(["https://new"])
    seen = state.load_seen()
    assert "https://new" in seen and "https://old" not in seen


def test_ignores_empty_urls(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    state.record_seen([None, "", "https://x"])
    assert state.load_seen() == {"https://x"}
