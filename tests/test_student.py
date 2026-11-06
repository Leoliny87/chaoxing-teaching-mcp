"""Student tools: answer mapping, confirmation phrase, plan binding."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp.ops_student import StudentOps  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402

QS = [
    {"no": 1, "qid": "11", "type": 0, "type_name": "单选题", "options": [{"key": "A", "value": "A"}, {"key": "B", "value": "B"}]},
    {"no": 2, "qid": "12", "type": 1, "type_name": "多选题", "options": [{"key": k, "value": k} for k in "ABCD"]},
    {"no": 3, "qid": "13", "type": 3, "type_name": "判断题", "options": [{"key": "A", "value": "true"}, {"key": "B", "value": "false"}]},
    {"no": 4, "qid": "14", "type": 4, "type_name": "简答题", "options": []},
    {"no": 5, "qid": "15", "type": 11, "type_name": "连线题", "options": []},
]


def test_build_answers_maps_each_type():
    out = StudentOps.build_answers(QS, {"1": "b", "2": "C,A", "3": "错", "4": "第一行<b>\n第二行"})
    assert out == {"11": "B", "12": "AC", "13": "false", "14": "<p>第一行&lt;b&gt;</p><p>第二行</p>"}


@pytest.mark.parametrize("bad", [{"1": "C"}, {"2": "Z"}, {"3": "是"}, {"4": " "}, {"5": "x"}, {"9": "A"}, {}])
def test_build_answers_refuses(bad):
    with pytest.raises(XxtError):
        StudentOps.build_answers(QS, bad)


def test_submit_requires_phrase_and_plan_ignores_it(monkeypatch):
    from xuexitong_mcp import server as srv
    T = {n: srv._wrap(fn, k) for n, k, _, fn in srv.TOOLS}
    monkeypatch.setattr(srv, "_answer_preview", lambda *a, **k: {"assignment": "作业", "status": "未交", "answers": [], "unanswered": []})
    monkeypatch.setattr(srv, "_check_student_write", lambda c: None)
    calls = []

    class FakeClient:
        def answer_my_assignment(self, *a, **k):
            calls.append(k)
            return {"ok": True}
    monkeypatch.setattr(srv, "client", lambda: FakeClient())
    p = T["submit_my_assignment"](course="助手", assignment="1", answers={"1": "A"})
    assert p["dry_run"] and p["plan_id"] and "确认提交" in p["next"]
    bad = T["submit_my_assignment"](course="助手", assignment="1", answers={"1": "A"}, confirm=True, plan_id=p["plan_id"], confirm_text="好的")
    assert bad["ok"] is False and not calls
    p = T["submit_my_assignment"](course="助手", assignment="1", answers={"1": "A"})
    ok = T["submit_my_assignment"](course="助手", assignment="1", answers={"1": "A"}, confirm=True, plan_id=p["plan_id"], confirm_text="确认提交")
    assert ok["ok"] is True and calls == [{"submit": True}]
