"""Student tools: answer mapping, confirmation phrase, plan binding."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp.ops_student import StudentOps  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402

CH = [{"key": "A", "value": "A"}, {"key": "B", "value": "B"}]
QS = [
    {"no": 1, "qid": "11", "type": 0, "type_name": "单选题", "options": CH},
    {"no": 2, "qid": "12", "type": 1, "type_name": "多选题", "options": [{"key": k, "value": k} for k in "ABCD"]},
    {"no": 3, "qid": "13", "type": 3, "type_name": "判断题", "options": [{"key": "A", "value": "true"}, {"key": "B", "value": "false"}]},
    {"no": 4, "qid": "14", "type": 4, "type_name": "简答题", "options": []},
    {"no": 5, "qid": "15", "type": 22, "type_name": "口语测评题", "options": []},
    {"no": 6, "qid": "16", "type": 2, "type_name": "填空题", "options": [], "detail": {"blanks": 2}},
    {"no": 7, "qid": "17", "type": 11, "type_name": "连线题", "options": [], "detail": {"lefts": ["1", "2"], "rights": ["A", "B"]}},
    {"no": 8, "qid": "18", "type": 13, "type_name": "排序题", "options": [], "detail": {"slots": 3, "letters": ["A", "B", "C"]}},
    {"no": 9, "qid": "19", "type": 20, "type_name": "共用选项题", "options": [], "detail": {"items": 2, "letters": ["A", "B", "C"]}},
    {"no": 10, "qid": "20", "type": 24, "type_name": "选词填空", "options": [], "detail": {"blanks": 2, "words": [{"key": "A"}, {"key": "B"}]}},
    {"no": 11, "qid": "21", "type": 23, "type_name": "钟表题", "options": [], "detail": {"clocks": 1}},
    {"no": 12, "qid": "22", "type": 14, "type_name": "完型填空", "options": [], "detail": {"children": [{"no": 1, "item": "u1", "options": ["A", "B"]}]}},
    {"no": 13, "qid": "23", "type": 15, "type_name": "阅读理解", "options": [], "detail": {"children": [
        {"no": 1, "qtid": "23u1", "item": "u1", "type": 0, "options": CH, "blanks": 0},
        {"no": 2, "qtid": "23u2", "item": "u2", "type": 3, "options": [], "blanks": 0},
        {"no": 3, "qtid": "23u3", "item": "u3", "type": 4, "options": [], "blanks": 0}]}},
    {"no": 14, "qid": "24", "type": 17, "type_name": "程序题", "options": [], "detail": {"language": "22", "languages": ["22:Python 3.12", "3:Java"]}},
    {"no": 15, "qid": "25", "type": 21, "type_name": "测评题", "options": CH, "detail": {"max_select": 1}},
]


def test_build_answers_maps_each_type():
    ops = {o["qid"]: o for o in StudentOps.build_answers(QS, {
        "1": "b", "2": "C,A", "3": "错", "4": "第一行<b>\n第二行", "6": ["x", "y"], "7": "BA", "8": "CAB", "9": ["B", "C"],
        "10": "BA", "11": ["9:05"], "12": "B", "13": ["A", "对", "因为"], "14": {"language": "java", "code": "class A{}"}, "15": "A"})}
    assert ops["11"]["v"] == "B" and ops["12"]["v"] == "AC" and ops["13"]["v"] == "false"
    assert ops["14"]["v"] == "<p>第一行&lt;b&gt;</p><p>第二行</p>" and ops["16"]["v"] == ["<p>x</p>", "<p>y</p>"]
    assert ops["17"]["v"] == '[{"name":"1","content":"B"},{"name":"2","content":"A"}]' and ops["18"]["v"] == "CAB"
    assert ops["19"]["v"] == '[{"name":1,"content":"B"},{"name":2,"content":"C"}]' and ops["21"]["v"] == '[{"hour":"9","minute":"5"}]'
    assert ops["22"]["v"] == [{"item": "u1", "v": "B"}]
    assert [c["v"] for c in ops["23"]["v"]] == ["A", True, "<p>因为</p>"] and ops["24"]["lang"] == 3 and ops["25"]["v"] == "A"


@pytest.mark.parametrize("bad", [{"1": "C"}, {"2": "Z"}, {"3": "是"}, {"4": " "}, {"5": "x"}, {"99": "A"}, {}, {"6": ["only one"]},
                                 {"7": "B"}, {"8": "AAB"}, {"11": ["25:00"]}, {"12": "C"}, {"13": ["A", "对"]}, {"14": {"language": "cobol", "code": "x"}},
                                 {"15": "AB"}])
def test_build_answers_refuses(bad):
    with pytest.raises(XxtError):
        StudentOps.build_answers(QS, bad)


def test_public_view_hides_internal_ids():
    v = StudentOps._public(QS[12])
    assert "qid" not in v and all("qtid" not in c and "item" not in c for c in v["detail"]["children"])
    assert v["detail"]["children"][0]["options"] == ["A", "B"]


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


def test_every_student_write_needs_the_students_phrase():
    import inspect
    from xuexitong_mcp import server as srv
    from xuexitong_mcp.policy import STUDENT_ONLY
    writes = [(n, fn) for n, k, _, fn in srv.TOOLS if n in STUDENT_ONLY and k in ("write", "destructive")]
    assert {n for n, _ in writes} >= {"save_my_answers", "submit_my_assignment", "submit_my_activity", "reply_my_discussion"}
    for n, fn in writes:
        assert "confirm_text" in inspect.signature(fn).parameters, n

    def no_phrase(confirm=False):
        return {"ok": True, "dry_run": True}
    no_phrase.__name__ = "reply_my_discussion"
    with pytest.raises(ValueError):
        srv._wrap(no_phrase, "write")


@pytest.mark.parametrize("tool,kw", [
    ("save_my_answers", dict(assignment="1", answers={"1": "A"})),
    ("reply_my_discussion", dict(topic_id="t1", content="我的回复")),
])
def test_save_and_reply_need_phrase(monkeypatch, tool, kw):
    from xuexitong_mcp import server as srv
    T = {n: srv._wrap(fn, k) for n, k, _, fn in srv.TOOLS}
    monkeypatch.setattr(srv, "_answer_preview", lambda *a, **k: {"assignment": "作业", "status": "未交", "answers": [], "unanswered": []})
    monkeypatch.setattr(srv, "_check_student_write", lambda c: None)
    calls = []

    class FakeClient:
        def answer_my_assignment(self, *a, **k):
            calls.append(k)
            return {"ok": True}

        def my_discussions(self, c):
            return {"topics": [{"topic_id": "t1", "title": "话题"}]}

        def reply_my_discussion(self, *a):
            calls.append(a)
            return {"ok": True}
    monkeypatch.setattr(srv, "client", lambda: FakeClient())
    p = T[tool](course="助手", **kw)
    assert p["dry_run"] and "确认提交" in p["next"]
    assert T[tool](course="助手", **kw, confirm_text="确认提交")["ok"] is False      # phrase during preview
    for bad in ("", "好的", "确认"):
        r = T[tool](course="助手", **kw, confirm=True, plan_id=p["plan_id"], confirm_text=bad)
        assert r["ok"] is False and not calls
        p = T[tool](course="助手", **kw)            # a wrong phrase spends the plan
    assert T[tool](course="助手", **kw, confirm=True, plan_id=p["plan_id"], confirm_text="确认提交")["ok"] is True and len(calls) == 1
