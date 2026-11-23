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


@pytest.mark.parametrize(("qid", "score", "expected_score"), [("4321", None, 0), ("ab" * 16, 8, 8)])
def test_bank_edit_preserves_native_metadata_and_checks_the_result(client, monkeypatch, qid, score, expected_score):
    from xuexitong_mcp.ops_bank import _edit_metadata

    native = {"type": 1, "score": 0, "difficulty": 0.2, "isOpen": 1, "easy": 2, "chapterId": 92,
              "courseQuestionTypeId": 641, "courseTargetId": 41, "topicId": 17, "topicList": [{"id": 17}, {"id": 18}]}
    metadata = _edit_metadata(native)
    saved = {}

    def all_questions(course, detail_id=""):
        assert detail_id == qid
        row = {"type_id": 1, "folder_id": "55", "stem": "原题", "full_stem": "原题", "analysis": "", "edit_metadata": metadata}
        if saved:
            row.update(stem="新题", full_stem="新题", analysis="过程", edit_metadata={**metadata, "score": expected_score})
        return {qid: row}

    def submit(host, js, retry_safe=True):
        assert retry_safe is False and "edit-question?" in js and "create-question?" not in js
        assert "updateExamWord=false" in js and "dirId=55" in js and "saveAsNew=false" in js
        pairs, _ = json.JSONDecoder().raw_decode(js.split("const pairs=", 1)[1])
        saved.update(pairs)
        assert [value for name, value in pairs if name == "defAnswer"] == ["A", "C"]
        assert saved["score"] == expected_score and saved["difficulty"] == 0.2 and saved["chapterId"] == 92
        assert saved["isOpen"] == saved["isopen"] == 1 and saved["courseQuestionTypeId"] == 641
        assert saved["labelIdArr"] == "11,12" and saved["topicId"] == "17,18" and saved["courseTargetId"] == 41
        assert saved["qbankScoreEdit"] == ("true" if score is not None else "false")
        return {"qid": qid, "status": True}

    monkeypatch.setattr(client, "_all_questions", all_questions)
    monkeypatch.setattr(client, "_bank_label_data", lambda *args: {"checkedIds": [12, 11]})
    monkeypatch.setattr(client, "on", submit)
    question = {"type": "多选", "stem": "新题", "options": ["甲", "乙", "丙"], "answer": "AC", "analysis": "过程"}
    if score is not None:
        question["score"] = score
    assert client.add_bank_question("1", question, edit_id=qid)["ok"]
    saved.clear()
    monkeypatch.setattr(client, "_bank_label_data", lambda *args: {"checkedIds": [] if saved else [11, 12]})
    assert client.edit_bank_question("1", qid, question)["write_outcome"] == "unknown"


def test_bank_edit_missing_score_metadata_refuses_to_post(client, monkeypatch):
    row = {"type_id": 3, "folder_id": "0", "edit_metadata": {"isOpen": 1, "difficulty": 0.8}}
    monkeypatch.setattr(client, "_all_questions", lambda *args, **kwargs: {"274": row})
    monkeypatch.setattr(client, "on", lambda *a, **kw: pytest.fail("unexpected write"))
    with pytest.raises(XxtError, match="原题分值"):
        client.edit_bank_question("1", "274", {"type": "判断", "stem": "甲", "answer": True})


@pytest.mark.parametrize(("specified", "expected"), [({}, 5), ({"score": 7}, 7)])
def test_create_bank_question_posts_its_declared_score(client, monkeypatch, specified, expected):
    monkeypatch.setattr(client.b, "navigate", lambda *a, **kw: None)
    monkeypatch.setattr(client, "here", lambda *a, **kw: {"enc": "test", "ts": "123"})

    def submit(path, method, fields):
        data = dict(fields)
        assert data["score"] == expected and data["qbankScoreEdit"] == "true" and data["isEdit"] == "false"
        return {"http": 200, "json": {"qid": "52", "status": True}}

    monkeypatch.setattr(client, "_call_here", submit)
    assert client.add_bank_question("1", {"type": "判断", "stem": "甲", "answer": True, **specified})["ok"]


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
