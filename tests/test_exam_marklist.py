"""Regression tests: exam_marklist reads submitted/unsubmitted rosters via API.

Previously it scraped the layui marklist DOM and returned null rosters. The
platform's POST /mooc2-ans/exam/test/markresult-new returns the student rows;
state:'1' is submitted (已交), state:'0' is unsubmitted (未交). exam_marklist must
fetch both, paginate, and cross-check roster lengths against the reported totals.

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
from xuexitong_mcp.xxt import Course, make_client  # noqa: E402


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
    monkeypatch.setattr(c, "exams", lambda cid: [{"id": "100", "paper_id": "P", "title": "考试", "class": "测试"}])
    monkeypatch.setattr(c.b, "navigate", lambda *a, **k: "")
    monkeypatch.setattr(c, "wait_for", lambda *a, **k: True)
    monkeypatch.setattr(c, "here", lambda *a, **k: {"total": "2", "submitted": "1", "unsubmitted": "1"})
    return c


def _row(name, uid, status, submit):
    return {"name": name, "uid": uid, "status": status, "submitTime": submit, "score": 0}


def test_exam_marklist_reads_both_rosters_via_api(client, monkeypatch):
    calls = []

    def fake_on(host, js, **kw):
        calls.append(js)
        if "state:'1'" in js:
            return {"valid": True, "total": 1, "classSize": 2, "rows": [_row("林云", "14", 3, "11-08 08:26")]}
        if "state:'0'" in js:
            return {"valid": True, "total": 1, "classSize": 2, "rows": [_row("测试号", "53", 0, "---")]}
        raise AssertionError(f"unexpected call: {js}")
    monkeypatch.setattr(client, "on", fake_on)

    def no_nav(*a, **k):
        raise AssertionError("exam_marklist must use markresult-new, not navigate the live page")
    monkeypatch.setattr(client.b, "navigate", no_nav)

    r = client.exam_marklist("1", "100")
    assert any("markresult-new" in js for js in calls)
    assert r["submitted_rows"][0]["name"] == "林云"
    assert r["unsubmitted_rows"][0]["name"] == "测试号"
    assert r["submitted"] == 1 and r["unsubmitted"] == 1
    assert r["lists_verified"] is True


def test_exam_marklist_flags_count_mismatch(client, monkeypatch):
    def fake_on(host, js, **kw):
        if "state:'1'" in js:
            return {"valid": True, "total": 9, "classSize": 2, "rows": [_row("林云", "14", 3, "11-08 08:26")]}
        return {"valid": True, "total": 1, "classSize": 2, "rows": [_row("测试号", "53", 0, "---")]}
    monkeypatch.setattr(client, "on", fake_on)
    r = client.exam_marklist("1", "100")
    assert r["lists_verified"] is False