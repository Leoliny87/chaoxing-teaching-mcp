"""Synthetic tests for assignment / exam creation and exam publishing."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.ops_create import tf_questions  # noqa: E402
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


@pytest.mark.parametrize("bad", [[], [{"type": "单选", "stem": "x", "answer": "A"}], [{"stem": "", "answer": "对"}],
                                 [{"stem": "x", "answer": "是"}], [{"stem": "x", "answer": "对", "score": 0}]])
def test_tf_questions_rejects(bad):
    with pytest.raises(XxtError):
        tf_questions(bad)


def test_create_work_chain(client, monkeypatch):
    calls = []

    def call(host, path, method="GET", form=None):
        calls.append((path.split("?")[0], form))
        if path.endswith("questionInit"):
            n = sum(1 for p, _ in calls if p.endswith("questionInit"))
            assert form["workid"] == ("" if n == 1 else "w1")
            return {"http": 200, "json": {"status": True, "questionid": 100 + n, "relationid": 7, "workid": "w1"}}
        if path.endswith("toEditWorkQuestion"):
            return {"http": 200, "json": {"success": True}}
        return {"http": 200, "json": {"status": True}}
    monkeypatch.setattr(client, "_call", call)
    monkeypatch.setattr(client, "assignment_library_first_page", lambda c: {"items": [{"id": "w1", "questions": "2"}]})
    r = client.create_work_tf("1", "标题", [{"stem": "甲", "answer": "对"}, {"stem": "乙<script>", "answer": "错", "score": 10}])
    edits = [f for p, f in calls if p.endswith("toEditWorkQuestion")]
    assert [e["answerForTF"] for e in edits] == ["true", "false"] and edits[1]["score"] == "10.0"
    assert "&lt;script&gt;" in edits[1]["content"] and edits[0]["workid"] == "w1"
    assert calls[-1][0] == "/mooc2-ans/work/save-work" and r == {"ok": True, "library_id": "w1", "title": "标题", "questions": 2}


def test_create_work_stops_on_failed_init(client, monkeypatch):
    monkeypatch.setattr(client, "_call", lambda *a, **k: {"http": 200, "json": {"status": False}})
    with pytest.raises(XxtError):
        client.create_work_tf("1", "标题", [{"stem": "甲", "answer": "对"}])


def test_create_paper_chain(client, monkeypatch):
    calls = []

    def call(host, path, method="GET", form=None):
        p = path.split("?")[0]
        calls.append((p, form))
        if p.endswith("createAnEmptyPaper"):
            return {"http": 200, "json": {"paperId": 55}}
        if p.endswith("add-empty-paperquestion"):
            return {"http": 200, "json": {"status": True, "data": {"paperQuestionId": 9, "paperLibraryRelationId": 8}}}
        if p.endswith("editPaperTrueFalseV2"):
            assert form["typeId"] == 8 and form["questionId"] == 9 and form["answer"] == "true"
            return {"http": 200, "json": {"paperQuestionId": 9}}
        return {"http": 200, "json": {"status": True}}
    monkeypatch.setattr(client, "_call", call)
    monkeypatch.setattr(client, "papers", lambda c: [{"paper_id": "55", "title": "卷"}])
    r = client.create_paper_tf("1", "卷", [{"stem": "甲", "answer": "对"}])
    assert [p for p, _ in calls][:2] == ["/mooc2-ans/exam/createAnEmptyPaper", "/mooc2-ans/exam/update-exampaper-title"]
    assert r["ok"] is True and r["paper_id"] == "55"


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
    for n in ("create_assignment", "create_exam", "publish_exam"):
        assert kinds[n] == "write" and n not in srv._PREVIEW_ONLY_TOOLS
