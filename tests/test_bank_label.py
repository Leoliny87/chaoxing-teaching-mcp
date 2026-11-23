"""Bank label delete: resolve unique label, delete via question-label/delete?labelid, read back.

Live-verified 2026-11-23: the platform exposes label delete at
/mooc2-ans/question-label/delete with param `labelid` (GET); the qbank UI exposes
NO folder-delete endpoint (only insertdir / update-dirname), so folders cannot be
deleted via MCP.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp.ops_bank import BankOps  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402


class FakeBank(BankOps):
    def __init__(self, labels):
        self._labels = labels
        self.calls = []

    def course(self, name):
        return type("C", (), {"id": "1", "cpi": "9"})()

    def bank_labels(self, course, qid=""):
        return list(self._labels)

    def on(self, host, js, retry_safe=True, timeout=None):
        self.calls.append(js)
        # simulate the platform removing the label
        if "question-label/delete" in js and "labelid" in js:
            self._labels = [x for x in self._labels if x["id"] != "77"]
            return {"msg": "删除成功", "status": True}
        return {}


def test_delete_bank_label_resolves_and_verifies():
    b = FakeBank([{"id": "77", "name": "临时标签", "parent_id": "0", "checked": False}])
    out = b.delete_bank_label("课", "临时标签")
    assert out["ok"] is True and out["label_id"] == "77"
    assert b.calls and "question-label/delete" in b.calls[0] and "labelid" in b.calls[0]


def test_delete_bank_label_by_id():
    b = FakeBank([{"id": "77", "name": "临时标签", "parent_id": "0", "checked": False}])
    assert b.delete_bank_label("课", "77")["ok"] is True


def test_delete_bank_label_non_unique_raises():
    b = FakeBank([{"id": "77", "name": "重名", "parent_id": "0", "checked": False},
                  {"id": "78", "name": "重名", "parent_id": "0", "checked": False}])
    with pytest.raises(XxtError):
        b.delete_bank_label("课", "重名")


def test_delete_bank_label_missing_raises():
    b = FakeBank([])
    with pytest.raises(XxtError):
        b.delete_bank_label("课", "不存在")