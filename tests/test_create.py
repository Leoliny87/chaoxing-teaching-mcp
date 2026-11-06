"""Synthetic tests for assignment / exam / bank creation and exam publishing."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.ops_create import merge  # noqa: E402
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
    course = Course(id="1", name="合成课程", cpi="3", clazz_id="2", enc="E", t="9", classes=[{"clazz_id": "2", "name": "测试"}])
    monkeypatch.setattr(c, "ctx", lambda q, refresh=False: course)
    monkeypatch.setattr(c, "course", lambda q: course)
    return c


def test_merge_lets_type_fields_win_and_keeps_repeats():
    out = merge([("a", 1), ("answerForTF", "true"), ("b", 2)], [("answerForTF", "false"), ("d", "A"), ("d", "C")])
    assert out == [("a", 1), ("b", 2), ("answerForTF", "false"), ("d", "A"), ("d", "C")]


def test_create_work_chain_reuses_type_groups(client, monkeypatch):
    calls = []

    def call(host, path, method="GET", form=None):
        calls.append((path.split("?")[0], form))
        if path.endswith("questionInit"):
            n = sum(1 for p, _ in calls if p.endswith("questionInit"))
            assert form["workid"] == ("" if n == 1 else "w1")
            assert form["relationid"] == (0 if n in (1, 3) else "70")   # second 判断 reuses its group
            return {"http": 200, "json": {"status": True, "questionid": 100 + n, "relationid": 69 + n, "workid": "w1"}}
        if path.endswith("toEditWorkQuestion") or path.endswith("saveInnerQuestion"):
            return {"http": 200, "json": {"success": True, "status": True}}
        return {"http": 200, "json": {"status": True}}
    monkeypatch.setattr(client, "_call", call)
    monkeypatch.setattr(client, "assignment_library_first_page", lambda c: {"items": [{"id": "w1", "questions": "3"}]})
    r = client.create_work("1", "标题", [{"type": "判断", "stem": "甲", "answer": "对"},
                                         {"type": "判断", "stem": "乙<script>", "answer": "错", "score": 10},
                                         {"type": "阅读理解", "stem": "材料", "children": [{"type": "判断", "stem": "丙", "answer": "对"}]}])
    edits = [dict(f) for p, f in calls if p.endswith("toEditWorkQuestion")]
    assert [e["answerForTF"] for e in edits] == ["true", "false"] and edits[1]["score"] == "10.0"
    assert "&lt;script&gt;" in edits[1]["content"] and edits[0]["workid"] == "w1" and edits[0]["typeName"] == "判断题"
    inner = [f for p, f in calls if p.endswith("saveInnerQuestion")][0]
    assert inner["type"] == 15 and json.loads(inner["answer"])[0]["type"] == 3
    assert calls[-1][0] == "/mooc2-ans/work/save-work" and r["ok"] is True and r["questions"] == 3


def test_create_work_refuses_evaluation_in_percent_grading(client):
    with pytest.raises(XxtError):
        client.create_work("1", "t", [{"type": "测评", "stem": "x", "options": ["a", "b"], "option_scores": [1, 2]}])


def test_create_work_stops_on_failed_init(client, monkeypatch):
    monkeypatch.setattr(client, "_call", lambda *a, **k: {"http": 200, "json": {"status": False}})
    with pytest.raises(XxtError):
        client.create_work("1", "标题", [{"type": "判断", "stem": "甲", "answer": "对"}])


def test_create_paper_chain(client, monkeypatch):
    calls = []

    def call(host, path, method="GET", form=None):
        p = path.split("?")[0]
        calls.append((p, form))
        if p.endswith("createAnEmptyPaper"):
            return {"http": 200, "json": {"paperId": 55}}
        if p.endswith("add-empty-paperquestion"):
            n = sum(1 for x, _ in calls if x.endswith("add-empty-paperquestion"))
            if n == 2:
                assert form["relationid"] == "8"          # same type -> same group
            return {"http": 200, "json": {"status": True, "data": {"paperQuestionId": 8 + n, "paperLibraryRelationId": 8}}}
        if p.endswith("editPaperSingleChoiceV2"):
            d = dict(form)
            assert d["defAnswer"] == "B" and d["typeId"] == 8
            return {"http": 200, "json": {"status": True}}
        return {"http": 200, "json": {"status": True}}
    monkeypatch.setattr(client, "_call", call)
    monkeypatch.setattr(client, "papers", lambda c: [{"paper_id": "55", "title": "卷", "questions": "2"}])
    q = {"type": "单选", "stem": "甲", "options": ["a", "b"], "answer": "B"}
    r = client.create_paper("1", "卷", [q, q])
    assert [p for p, _ in calls][:2] == ["/mooc2-ans/exam/createAnEmptyPaper", "/mooc2-ans/exam/update-exampaper-title"]
    assert r["ok"] is True and r["paper_id"] == "55" and r["questions"] == 2


def test_create_paper_stops_on_rejected_save(client, monkeypatch):
    def call(host, path, method="GET", form=None):
        if "createAnEmptyPaper" in path:
            return {"http": 200, "json": {"paperId": 55}}
        if "add-empty" in path:
            return {"http": 200, "json": {"status": True, "data": {"paperQuestionId": 9, "paperLibraryRelationId": 8}}}
        if "editPaper" in path:
            return {"http": 200, "json": {"status": False, "msg": "x"}}
        return {"http": 200, "json": {"status": True}}
    monkeypatch.setattr(client, "_call", call)
    with pytest.raises(XxtError):
        client.create_paper("1", "卷", [{"type": "判断", "stem": "甲", "answer": "对"}])


def test_publish_exam_whitelist_and_form(client, monkeypatch):
    with pytest.raises(XxtError):
        client.publish_exam_v3("1", "55", ["2"], "", "", 60, {"evil": 1})
    with pytest.raises(XxtError):
        client.publish_exam_v3("1", "55", ["2"], "", "", 0)
    lists = [[], [{"id": "e1", "paper_id": "55"}]]
    monkeypatch.setattr(client, "exams", lambda c: lists.pop(0))
    sent = {}
    monkeypatch.setattr(client, "_call", lambda host, path, method="GET", form=None: sent.update(path=path, form=form) or {"http": 200, "json": {"status": True}})
    r = client.publish_exam_v3("1", "55", ["2"], "2099-01-01 08:00", "2099-01-01 10:00", 45, {"randomSort": True})
    f = sent["form"]
    assert sent["path"] == "/mooc2-ans/exam/test/publish" and f["limitTime"] == 45 and f["randomSort"] == 1
    assert json.loads(f["publishObj"]) == [{"classid": 2, "publishType": 0}] and f["forbidMultiterminal"] == 1
    assert r["ok"] is True


def test_creation_tools_are_executable_writes():
    from xuexitong_mcp import server as srv
    kinds = {n: k for n, k, _, _ in srv.TOOLS}
    for n in ("create_assignment", "create_exam", "publish_exam", "add_question_to_bank"):
        assert kinds[n] == "write" and n not in srv._PREVIEW_ONLY_TOOLS


def test_bank_listing_never_returns_answers(client, monkeypatch):
    row = {"dirName": "", "questionBank": {"id": "ab" * 16, "type": 0, "content": "<p>题干&amp;<b>x</b></p>", "answer": "[SECRET]",
                                           "janswer": [{"isanswer": True}], "analysis": "SECRET", "difficulty": 0.8, "useNum": 1,
                                           "createTime": 1794000000000}}
    monkeypatch.setattr(client, "_call", lambda *a, **k: {"http": 200, "json": {"status": True, "total": 1, "questionBankRelationList": [row]}})
    r = client.bank_questions("1", "x")
    assert r["items"][0]["stem"] == "题干& x" and r["items"][0]["type"] == "单选题" and "SECRET" not in json.dumps(r, ensure_ascii=False)
    monkeypatch.setattr(client, "_call", lambda *a, **k: {"http": 200, "json": {"status": True}})
    with pytest.raises(XxtError):
        client.bank_questions("1")
