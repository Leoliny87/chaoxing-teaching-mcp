"""Regression tests: 错题集 (list_my_wrong_questions) against the real platform DOM.

Verified live on a pure-student account: POST /mooc2-ans/wrongque/data returns one
`.topic-list` per wrong question. The correct answer lives in `.answer-default`
("正确答案：…"), the per-option `.option-correct`/`.option-wrong` markers, and the
`.topic-analysis` explanation ("答案解析：…"). The old guessed selectors
(`.wrong-topic-item`, `.rightAnswer`, …) matched none of these, so the tool reported
an empty list even when wrong questions existed — and would have leaked the answer
the moment the item selector was fixed. These tests guard the verified selectors in
the browser JS and the Python defense-in-depth backstop. All data is synthetic.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.ops_student import StuCourse  # noqa: E402
from xuexitong_mcp.xxt import make_client  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    lg = logging.getLogger("xuexitong_mcp.bsk")
    for h in list(lg.handlers):
        lg.removeHandler(h)
    monkeypatch.setattr(bsk_mod, "STATE_FILE", tmp_path / "state.json")
    cfg = Config(profile="student")
    cfg.log_dir = tmp_path / "logs"
    c = make_client(cfg)
    stu = StuCourse(id="1", clazz_id="2", cpi="3", name="合成课程",
                    params={"courseid": "1", "clazzid": "2", "cpi": "3", "t": "9", "enc": "E"}, t=0.0)
    monkeypatch.setattr(c, "_stu_ctx", lambda q: stu)
    return c


def _capture_js(client, monkeypatch, result):
    seen = {}

    def fake_on(host, js, **kw):
        seen["js"] = js
        return result
    monkeypatch.setattr(client, "on", fake_on)
    return seen


def test_js_uses_verified_selectors_and_strips_answers(client, monkeypatch):
    seen = _capture_js(client, monkeypatch, {"stage": "ok", "empty": True, "items": []})
    client.my_wrong_questions("1")
    js = seen["js"]
    # item selector matches the real DOM
    assert "'.topic-list'" in js or ".topic-list" in js
    # every answer-bearing node is removed before text is read
    assert ".answer-default" in js
    assert ".topic-analysis:not(.topic-zhoshi-main)" in js
    assert ".option-correct" in js and ".option-wrong" in js
    # the student's own answer and the harmless knowledge point are kept
    assert ".answer-my" in js
    assert ".topic-zhoshi-main .topic-analysis-txt" in js
    # the broken guessed selectors are gone
    assert ".wrong-topic-item" not in js
    assert ".rightAnswer" not in js


def test_python_backstop_redacts_a_leaked_answer(client, monkeypatch):
    # Simulate a future DOM change where the JS stripping missed an answer: the
    # Python layer must still cut anything from an answer marker onward.
    leaked = {"stage": "ok", "empty": False, "items": [
        {"type": "[单选题]", "question": "题干 正确答案：B 选项", "options": ["A. 甲", "B. 乙"],
         "my_answer": "A", "knowledge_point": "答案解析：因为乙对", "record_id": "7"},
    ]}
    _capture_js(client, monkeypatch, leaked)
    res = client.my_wrong_questions("1")
    blob = json.dumps(res["items"], ensure_ascii=False)
    assert "正确答案" not in blob
    assert "答案解析" not in blob
    assert "因为乙对" not in blob
    it = res["items"][0]
    assert it["question"] == "题干"          # truncated at the marker
    assert it["knowledge_point"] == ""       # explanation dropped
    assert it["my_answer"] == "A"            # the student's own answer survives


def test_clean_items_pass_through_with_shape(client, monkeypatch):
    clean = {"stage": "ok", "empty": False, "items": [
        {"type": "[多选题]", "question": "下列哪些正确", "options": ["A. 一", "B. 二", "C. 三"],
         "my_answer": "C", "knowledge_point": "植物器官", "record_id": "922833"},
        {"type": "[判断题]", "question": "真果假果都是果实", "options": [],
         "my_answer": "错", "knowledge_point": "", "record_id": "922835"},
    ]}
    _capture_js(client, monkeypatch, clean)
    res = client.my_wrong_questions("1")
    assert res["course"] == "合成课程"
    assert res["count"] == 2
    assert res["items"][0]["options"] == ["A. 一", "B. 二", "C. 三"]
    assert res["items"][1]["my_answer"] == "错"
    assert "正确答案" in res["note"] and "解析" in res["note"]   # the note may name what it withholds


def test_items_without_question_or_options_are_dropped(client, monkeypatch):
    payload = {"stage": "ok", "empty": False, "items": [
        {"type": "", "question": "", "options": [], "my_answer": "", "knowledge_point": "", "record_id": "1"},
        {"type": "[填空题]", "question": "天麻入药部位", "options": [], "my_answer": "", "knowledge_point": "", "record_id": "2"},
    ]}
    _capture_js(client, monkeypatch, payload)
    res = client.my_wrong_questions("1")
    assert res["count"] == 1
    assert res["items"][0]["record_id"] == "2"


def test_empty_wrong_question_set(client, monkeypatch):
    _capture_js(client, monkeypatch, {"stage": "ok", "empty": True, "items": []})
    res = client.my_wrong_questions("1")
    assert res["count"] == 0
    assert res["items"] == []


def test_read_failure_raises(client, monkeypatch):
    from xuexitong_mcp.xxt import XxtError
    _capture_js(client, monkeypatch, {"stage": "page"})
    with pytest.raises(XxtError):
        client.my_wrong_questions("1")
