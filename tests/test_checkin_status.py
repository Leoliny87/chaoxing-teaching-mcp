"""Regression tests: checkin_status reads signed/unsigned lists via getAttendList.

Previously it scraped the re-rendering endSign page and returned null lists. The
platform's /widget/sign/pcTeaSignController/getAttendList returns yiqianList /
weiqianList plus counts directly; checkin_status must use it and cross-check the
list lengths against the reported counts.

All data is synthetic; the same-origin `on` helper is replaced by a fake.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.xxt import Course, XxtError, make_client  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    lg = logging.getLogger("xuexitong_mcp.bsk")
    for h in list(lg.handlers):
        lg.removeHandler(h)
    monkeypatch.setattr(bsk_mod, "STATE_FILE", tmp_path / "state.json")
    cfg = Config()
    cfg.log_dir = tmp_path / "logs"
    c = make_client(cfg)
    course = Course(id="1", name="合成课程", cpi="3", clazz_id="2", enc="E", t="9",
                    classes=[{"clazz_id": "2", "name": "测试"}])
    monkeypatch.setattr(c, "ctx", lambda q, refresh=False: course)
    monkeypatch.setattr(c, "_find_activity", lambda c, a: {"activity_id": "100", "title": "签到",
                                                          "active_type": 2, "status_name": "进行中"})
    monkeypatch.setattr(c.b, "navigate", lambda *a, **k: "")
    monkeypatch.setattr(c, "wait_for", lambda *a, **k: True)
    monkeypatch.setattr(c, "here", lambda *a, **k: {"signed": "1", "unsigned": "1", "rate": "50%", "list": []})
    return c


def _resp(signed=1, unsigned=1, rate=50, sl=None, ul=None):
    return {"valid": True, "signed": signed, "unsigned": unsigned, "rate": rate,
            "signed_list": sl if sl is not None else [{"name": "测试号", "username": "001", "uid": "11", "status": 1, "submittime": "2026-11-08 22:00"}],
            "unsigned_list": ul if ul is not None else [{"name": "林云", "username": "002", "uid": "22", "status": 0, "submittime": None}]}


def test_checkin_status_reads_lists_via_api(client, monkeypatch):
    seen = {}

    def fake_on(host, js, **kw):
        seen["js"] = js
        return _resp()
    monkeypatch.setattr(client, "on", fake_on)

    def no_nav(*a, **k):
        raise AssertionError("checkin_status must read lists via getAttendList, not navigate the live page")
    monkeypatch.setattr(client.b, "navigate", no_nav)

    r = client.checkin_status("1", "100")
    assert "getAttendList" in seen["js"]
    assert r["signed_list"][0]["name"] == "测试号"
    assert r["unsigned_list"][0]["name"] == "林云"
    assert r["signed"] == 1 and r["unsigned"] == 1
    assert r["lists_verified"] is True


def test_checkin_status_flags_count_mismatch(client, monkeypatch):
    monkeypatch.setattr(client, "on", lambda *a, **k: _resp(signed=5, unsigned=1))  # counts != list lengths
    r = client.checkin_status("1", "100")
    assert r["lists_verified"] is False


def test_checkin_status_invalid_response_raises(client, monkeypatch):
    monkeypatch.setattr(client, "on", lambda *a, **k: {"valid": False})
    with pytest.raises(XxtError):
        client.checkin_status("1", "100")