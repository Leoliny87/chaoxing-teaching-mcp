"""Regression tests: question-map explore supports link/topic/answer task types.

The explore update-record endpoint takes type 0=link(关联), 1=topic(知识点),
2=answer(简答). The data shape is identical ({qid:[{id,questionLevel,stuAnswer}]});
only stuAnswer semantics differ: answer is HTML text (para-wrapped), link/topic are
raw ID strings (related question id / knowledge-point id). Verified live against the
助手 problem map: type1 stored stuAnswer='281207139', type0 stored '11413389'.

Browser helpers are replaced by fakes; no network is used.
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
from xuexitong_mcp.ops_graph2 import plain  # noqa: E402
from xuexitong_mcp.xxt import make_client  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    lg = logging.getLogger("xuexitong_mcp.bsk")
    for h in list(lg.handlers):
        lg.removeHandler(h)
    monkeypatch.setattr(bsk_mod, "STATE_FILE", tmp_path / "state.json")
    cfg = Config()
    cfg.log_dir = tmp_path / "logs"
    c = make_client(cfg)
    monkeypatch.setattr(c, "_stu_qm", lambda course: (None, {"courseid": "1", "clazzid": "2", "cpi": "3", "ut": "s", "modelId": 0}))
    return c


def _wire(client, monkeypatch):
    saved = {}
    posts = []

    def fake_explore(course, q, task_type="answer"):
        return {"exploring": {"question_id": "100", "question": "Q1",
                              "sub_questions": [{"sub_id": "200", "level": 2, "title": "Q2", "my_answer": saved.get("200", "")}]}}

    def fake_post(url, params):
        posts.append((url, params))
        for item in json.loads(params["data"])["100"]:
            saved[str(item["id"])] = plain(item["stuAnswer"])
        return {"status": True}

    monkeypatch.setattr(client, "my_qm_explore", fake_explore)
    monkeypatch.setattr(client, "_get", lambda url, params: {"data": {}})
    monkeypatch.setattr(client, "_post", fake_post)
    return posts


def test_topic_task_uses_type1_and_raw_id(client, monkeypatch):
    posts = _wire(client, monkeypatch)
    r = client.save_my_qm_explore("1", "100", {"200": "281207139"}, task_type="topic")
    assert r["ok"] is True
    params = posts[0][1]
    assert params["type"] == 1
    assert json.loads(params["data"])["100"][0]["stuAnswer"] == "281207139"


def test_link_task_uses_type0_and_raw_id(client, monkeypatch):
    posts = _wire(client, monkeypatch)
    r = client.save_my_qm_explore("1", "100", {"200": "11413389"}, task_type="link")
    assert r["ok"] is True
    params = posts[0][1]
    assert params["type"] == 0
    assert json.loads(params["data"])["100"][0]["stuAnswer"] == "11413389"


def test_answer_task_default_uses_type2_and_html(client, monkeypatch):
    posts = _wire(client, monkeypatch)
    r = client.save_my_qm_explore("1", "100", {"200": "我的回答"})
    assert r["ok"] is True
    params = posts[0][1]
    assert params["type"] == 2
    assert json.loads(params["data"])["100"][0]["stuAnswer"] == "<p>我的回答</p>"