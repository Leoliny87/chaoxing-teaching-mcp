"""Regression tests: all five check-in types publish via the saveOrBegin API.

The UI publisher needs the no-app-popup guard extension and hits observation_changed
on the re-rendering sign form, so gesture/location must use the API like the other
types. The sign type is the query `otherId` (0 normal / 2 QR / 3 gesture / 4 location /
5 code). Gesture stores the 1-9 nine-grid digit sequence in signCode; location sets
ifopenAddress=1 + locationText (place name) + locationRange, coordinates may be empty.
Verified live: gesture signCode='12357' and location locationText='湖南中医药大学' both
created and read back correctly via getPPTActiveInfo.

The raw tool function is called directly (plan machinery lives in the wrapper).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import server as srv  # noqa: E402
from xuexitong_mcp.xxt import Course  # noqa: E402

RAW = dict((n, f) for n, _, _, f in srv.TOOLS)["start_checkin"]


class FakeClient:
    def __init__(self):
        self.calls = {}

    def start_checkin_v3(self, course, class_id, title, minutes, code="", late_minutes=10, qr_refresh=0,
                         other_id=0, location_text="", location_range=""):
        self.calls["api"] = dict(code=code, qr_refresh=qr_refresh, other_id=other_id,
                                 location_text=location_text, location_range=location_range)
        return {"ok": True, "activity": {"activity_id": "9"}}


@pytest.fixture()
def fake(monkeypatch):
    fc = FakeClient()
    monkeypatch.setattr(srv, "_check_write", lambda course: Course(id="1", name="助手", cpi="3"))
    monkeypatch.setattr(srv, "_preview_publish_class", lambda cid, cls: {"id": "2", "name": "测试"})
    monkeypatch.setattr(srv, "client", lambda: fc)
    return fc


def test_gesture_preview_executable_and_routes_to_api(fake):
    draft = RAW(course="1", sign_type="手势", gesture="12357", class_name="2", confirm=False)
    assert not draft.get("preview_only")
    r = RAW(course="1", sign_type="手势", gesture="12357", class_name="2", confirm=True)
    assert r["ok"] is True
    assert fake.calls["api"]["other_id"] == 3
    assert fake.calls["api"]["code"] == "12357"


def test_location_preview_executable_and_routes_to_api(fake):
    draft = RAW(course="1", sign_type="位置", address="湖南中医药大学", class_name="2", confirm=False)
    assert not draft.get("preview_only")
    r = RAW(course="1", sign_type="位置", address="湖南中医药大学", class_name="2", confirm=True)
    assert r["ok"] is True
    assert fake.calls["api"]["other_id"] == 4
    assert fake.calls["api"]["location_text"] == "湖南中医药大学"


def test_normal_routes_to_api_other_id_0(fake):
    r = RAW(course="1", sign_type="普通", class_name="2", confirm=True)
    assert r["ok"] is True
    assert fake.calls["api"]["other_id"] == 0


def test_qr_routes_to_api_other_id_2(fake):
    r = RAW(course="1", sign_type="二维码", class_name="2", confirm=True)
    assert r["ok"] is True
    assert fake.calls["api"]["other_id"] == 2
    assert fake.calls["api"]["qr_refresh"] == 10