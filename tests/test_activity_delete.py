"""Regression tests: delete_activity works for any activity type, not just notices.

The setdel + recycle-bin verification is type-agnostic; only the notice-specific
prepare (active_type==45 + ownership ledger) was restricted. A general prepare
must accept e.g. a check-in (active_type 2), freeze the target, and the existing
delete must verify absence + a positive recycle-bin row.

All data is synthetic; browser helpers are replaced by fakes.
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
    monkeypatch.setattr(c, "course", lambda q: course)
    return c


def _checkin():
    return {"activity_id": "1000178248255", "title": "[MCP测试]二维码签到", "active_type": 2,
            "class_id": "2", "type": "签到", "status_name": "进行中", "start": "2026-11-08 22:18:50"}


def test_prepare_deletion_accepts_non_notice_activity(client, monkeypatch):
    act = _checkin()
    monkeypatch.setattr(client, "activities", lambda *a, **k: [act])
    p = client.prepare_activity_deletion("1", "1000178248255", "2")
    assert p["target"]["activity_id"] == "1000178248255"
    assert p["deletion_id"]
    assert p["deletion_id"] in client._linked_activity_deletions


def test_prepare_deletion_rejects_missing_activity(client, monkeypatch):
    monkeypatch.setattr(client, "activities", lambda *a, **k: [])
    with pytest.raises(XxtError):
        client.prepare_activity_deletion("1", "999", "2")


def test_prepare_deletion_accepts_activity_without_class_id_field(client, monkeypatch):
    act = _checkin()
    del act["class_id"]  # activities() omits class_id for non-notice types
    monkeypatch.setattr(client, "activities", lambda *a, **k: [act])
    p = client.prepare_activity_deletion("1", "1000178248255", "2")
    assert p["target"]["activity_id"] == "1000178248255"


def test_prepare_deletion_rejects_wrong_class(client, monkeypatch):
    monkeypatch.setattr(client, "activities", lambda *a, **k: [_checkin()])
    with pytest.raises(XxtError):
        client.prepare_activity_deletion("1", "1000178248255", "77")  # class not in course


def test_delete_general_activity_verifies_recycle(client, monkeypatch):
    act = _checkin()
    acts = [[act], [act], []]  # prepare snapshot, delete before, delete after (absent)
    monkeypatch.setattr(client, "activities", lambda *a, **k: acts.pop(0))
    calls = []
    monkeypatch.setattr(client, "on", lambda host, js, **k: calls.append(js) or {"status": 1})
    monkeypatch.setattr(client.b, "navigate", lambda *a, **k: "")
    monkeypatch.setattr(client, "here", lambda js, **k: {"valid": True, "matches": [{"id": "1000178248255", "text": "二维码签到 还原"}]})
    p = client.prepare_activity_deletion("1", "1000178248255", "2")
    r = client.delete_linked_activity("1", "1000178248255", "2", p["deletion_id"])
    assert r["ok"] is True
    assert r["absent_from_active_list"] is True
    assert r["recycle_row_verified"] is True
    assert any("setdel" in js and "status=1" in js for js in calls)