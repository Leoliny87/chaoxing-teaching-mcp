"""Regression tests: teacher course list reads via static-base same-origin fetch.

The new Vue portal keeps re-rendering, so navigating to the live course page and
scraping its DOM gets rejected by BrowserSkill (observation_changed). courses()
must instead fetch the course-list HTML from the host's static base page (the
`on` helper) and parse it, preserving id/cpi/role/name/info.

All data is synthetic; no browser or network is used.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.xxt import M2, XxtError, make_client  # noqa: E402


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


def _client(cfg):
    return make_client(cfg)


def test_courses_reads_via_static_fetch_and_preserves_role(cfg, monkeypatch):
    c = _client(cfg)
    seen = {}

    def fake_on(host, body, **kw):
        seen["host"] = host
        seen["body"] = body
        return [
            {"id": "100", "cpi": "9", "role": "1", "name": "合成课程", "info": "合成课程 置顶 已结课 林云"},
            {"id": "200", "cpi": "9", "role": "2", "name": "团队课", "info": "团队课 代洪波"},
        ]

    monkeypatch.setattr(c, "on", fake_on)

    def no_nav(*a, **k):
        raise AssertionError("courses() must not navigate to a live (re-rendering) page")

    monkeypatch.setattr(c.b, "navigate", no_nav)

    out = c.courses(refresh=True)

    assert seen["host"] == M2
    assert "courselistdata?courseType=0" in seen["body"]
    assert [x.id for x in out] == ["100", "200"]
    assert out[0].role == "1" and out[1].role == "2"
    assert out[0].name == "合成课程"
    assert out[0].cpi == "9"
    assert out[0].brief()["role"] == "主讲"
    assert out[1].brief()["role"] == "团队教师"


def test_courses_empty_result_raises(cfg, monkeypatch):
    c = _client(cfg)
    monkeypatch.setattr(c, "on", lambda *a, **k: [])
    monkeypatch.setattr(c.b, "navigate", lambda *a, **k: "")
    monkeypatch.setattr(c, "wait_for", lambda *a, **k: [])
    monkeypatch.setattr(c.b, "href", lambda *a, **k: "")
    with pytest.raises(XxtError):
        c.courses(refresh=True)


def test_health_detects_language_via_static_portal_fetch(cfg, monkeypatch):
    from xuexitong_mcp.xxt import NOTICE
    c = _client(cfg)
    monkeypatch.setattr(c.b, "doctor", lambda: [{"name": "x", "ok": True}])

    def ensure(**kw):
        c.b.session, c.b.tab = "s", 1
    monkeypatch.setattr(c.b, "ensure_session", ensure)

    on_calls = []

    def fake_on(host, body, **kw):
        on_calls.append((host, body))
        if host == NOTICE:
            return {"ok": True}
        if "courselistdata" in body:
            return [{"id": str(i), "cpi": "9", "role": "1", "name": f"课{i}", "info": ""} for i in range(60)]
        if "interaction" in body:
            return {"zh": True, "en": False}
        return {}
    monkeypatch.setattr(c, "on", fake_on)
    monkeypatch.setattr(c.b, "navigate", lambda *a, **k: "")

    def fake_here(body, **kw):
        if "__xxtNoAppGuard" in body:
            return {"guard": False, "lang": "zh-CN"}
        return ""
    monkeypatch.setattr(c, "here", fake_here)

    r = c.health()

    assert r["courses"] == 60
    assert r["ui_language"] == "中文"
    assert any(h == M2 and "interaction" in b for h, b in on_calls)