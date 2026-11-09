"""Regression tests: student list_my_discussions / reply path against the real platform.

Verified live on a pure-student account: the teacher-permissioned groupweb
`getTopicList` API returns {"msg":"你没有权限操作"} for a real student (it only ever
worked for a course creator's own student identity). The student list is the
server-rendered `topicList` page, which needs a freshly-signed URL (rotating
stuenc/enc nonce) built from the course shell's hidden fields, navigated to as a
document, then parsed from the rendered `li[data-uuid]` rows. All data is synthetic.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.ops_student import StuCourse  # noqa: E402
from xuexitong_mcp.xxt import XxtError, make_client  # noqa: E402

BBS = "a1b2c3d4e5f60718293a4b5c6d7e8f90"


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
                    params={"courseid": "1", "clazzid": "2", "cpi": "3", "t": "9", "enc": "E", "bbsid": BBS}, t=0.0)
    monkeypatch.setattr(c, "_stu_ctx", lambda q: stu)
    return c


SHELL = {"courseid": "1", "clazzid": "2", "cpi": "3", "bbsid": BBS, "enc": "ENC123", "t": "999", "showAIEnc": "SAI"}
ROWS = {"total": "2", "topics": [
    {"topic_id": "u1", "title": "话题一", "content": "内容", "author": "林云", "role": "老师", "time": "11-07", "replies": "1", "type": "章节讨论", "classes": "测试"},
    {"topic_id": "u2", "title": "话题二", "content": "", "author": "测试号", "role": "学生", "time": "11-08", "replies": "", "type": "", "classes": ""},
]}


def _wire(client, monkeypatch, shell=SHELL, rows=ROWS):
    navs, js_seen = [], []

    def fake_nav(url, **k):
        navs.append(url)
        return ""
    monkeypatch.setattr(client.b, "navigate", fake_nav)

    def fake_wait_for(js, timeout=15, interval=1.0):
        js_seen.append(js)
        if "getElementById" in js:
            return shell
        if "data-uuid" in js:
            return rows
        return None
    monkeypatch.setattr(client, "wait_for", fake_wait_for)
    return navs, js_seen


def test_parses_rendered_rows_and_uses_signed_nonce_url(client, monkeypatch):
    navs, js_seen = _wire(client, monkeypatch)
    res = client.my_discussions("1")
    assert res["course"] == "合成课程"
    assert [t["topic_id"] for t in res["topics"]] == ["u1", "u2"]
    assert res["topics"][0]["title"] == "话题一"
    # navigates to the signed groupweb topicList page carrying the nonce stuenc/enc
    topic_urls = [u for u in navs if "groupweb.chaoxing.com/course/topic/topicList" in u]
    assert topic_urls and "stuenc=ENC123" in topic_urls[0] and "enc=ENC123" in topic_urls[0]
    # regression: the teacher-only getTopicList endpoint must never be used for a student
    assert all("getTopicList" not in js for js in js_seen)


def test_truncation_note_when_total_exceeds_rows(client, monkeypatch):
    _wire(client, monkeypatch, rows={"total": "30", "topics": ROWS["topics"]})
    res = client.my_discussions("1")
    assert res["total"] == 30
    assert "共 30 条" in res["note"]


def test_no_discussion_area(client, monkeypatch):
    stu = StuCourse(id="1", clazz_id="2", cpi="3", name="合成课程",
                    params={"courseid": "1", "clazzid": "2", "cpi": "3", "t": "9", "enc": "E", "bbsid": ""}, t=0.0)
    monkeypatch.setattr(client, "_stu_ctx", lambda q: stu)
    with pytest.raises(XxtError, match="没有讨论区"):
        client.my_discussions("1")


def test_missing_shell_signature_raises(client, monkeypatch):
    _wire(client, monkeypatch, shell={"courseid": "1", "clazzid": "2", "cpi": "3", "bbsid": BBS, "enc": "", "t": "", "showAIEnc": ""})
    with pytest.raises(XxtError, match="签名参数"):
        client.my_discussions("1")


def test_empty_discussion_returns_empty_list(client, monkeypatch):
    _wire(client, monkeypatch, rows={"total": "", "topics": []})
    res = client.my_discussions("1")
    assert res["topics"] == []
    assert "total" not in res
