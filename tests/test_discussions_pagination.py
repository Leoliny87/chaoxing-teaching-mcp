"""Regression tests: list_discussions/topics paginates through the whole forum.

The platform ignores the `page` number on its own: getTopicList is cursor-based.
The first request omits last_reply_time; each later request must carry
last_reply_time=<previous poff.lastValue> (and lastAuxValue=<poff.lastAuxValue>),
and the last page is flagged by poff.lastPage==1. topics() must follow that
cursor, accumulate up to `limit`, de-duplicate by topic uuid, and stop on
lastPage==1 or an empty page. Verified against the real 助手 forum (8 topics).

All data is synthetic; the same-origin `on` helper is replaced by a fake.
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp import ops_content  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.xxt import Course, make_client  # noqa: E402


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    lg = logging.getLogger("xuexitong_mcp.bsk")
    for h in list(lg.handlers):
        lg.removeHandler(h)
        h.close()
    monkeypatch.setattr(bsk_mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(bsk_mod, "FIXED_BROWSER_INSTANCE", "inst0001")
    c = Config()
    c.log_dir = tmp_path / "logs"
    c.log_level = "WARNING"
    c.settle = 0
    yield c
    for h in list(lg.handlers):
        lg.removeHandler(h)
        h.close()


def _items(start, n):
    return [{"topic_id": f"u{i}", "id": str(i), "title": f"话题{i}", "content": "", "author": "林云",
             "replies": 0, "reads": 0, "time": "2026-11-08"} for i in range(start, start + n)]


def _page(items, last_value, last_page=0, last_aux=""):
    return {"items": items, "lastValue": last_value, "lastAuxValue": last_aux, "lastPage": last_page}


def _client_with_pages(cfg, monkeypatch, pages):
    c = make_client(cfg)
    course = Course(id="100", name="合成课程", cpi="9", bbsid="ABCDEF0123456789")
    monkeypatch.setattr(c, "ctx", lambda q: course)
    monkeypatch.setattr(ops_content, "TOPIC_PAGE_SIZE", 3, raising=False)
    calls = []

    def fake_on(host, body, **kw):
        p = int(re.search(r"[?&]page=(\d+)", body).group(1))
        calls.append((p, body))
        return {"valid": True, **pages.get(p, _page([], "", last_page=1))}

    monkeypatch.setattr(c, "on", fake_on)
    return c, calls


def test_topics_follows_cursor_until_last_page_flag(cfg, monkeypatch):
    pages = {1: _page(_items(0, 3), "t1"), 2: _page(_items(3, 3), "t2"), 3: _page(_items(6, 1), "t3", last_page=1)}
    c, calls = _client_with_pages(cfg, monkeypatch, pages)
    out = c.topics("100", limit=100)
    assert [p for p, _ in calls] == [1, 2, 3]
    assert [x["topic_id"] for x in out] == [f"u{i}" for i in range(7)]
    # the cursor — not the page number — is what advances the query
    assert "last_reply_time=" not in calls[0][1]
    assert "last_reply_time=t1" in calls[1][1]
    assert "last_reply_time=t2" in calls[2][1]


def test_topics_limit_caps_total(cfg, monkeypatch):
    pages = {1: _page(_items(0, 3), "t1"), 2: _page(_items(3, 3), "t2"), 3: _page(_items(6, 3), "t3")}
    c, calls = _client_with_pages(cfg, monkeypatch, pages)
    out = c.topics("100", limit=4)
    assert len(out) == 4
    assert [p for p, _ in calls] == [1, 2]


def test_topics_dedups_by_uuid(cfg, monkeypatch):
    pages = {1: _page(_items(0, 3), "t1"), 2: _page(_items(2, 3), "t2"), 3: _page(_items(5, 1), "t3", last_page=1)}
    c, calls = _client_with_pages(cfg, monkeypatch, pages)
    out = c.topics("100", limit=100)
    ids = [x["topic_id"] for x in out]
    assert ids == ["u0", "u1", "u2", "u3", "u4", "u5"]
    assert len(ids) == len(set(ids))


def test_topics_empty_forum_returns_empty(cfg, monkeypatch):
    c, calls = _client_with_pages(cfg, monkeypatch, {1: _page([], "", last_page=1)})
    assert c.topics("100", limit=100) == []
    assert [p for p, _ in calls] == [1]