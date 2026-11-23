"""Tests for the new-UI (fanyav3) read layer. Synthetic data only; `on()` is faked."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.xxt import Course, GROUP, M2, STAT, XxtError, make_client  # noqa: E402
from xuexitong_mcp.ops_v3 import TASK  # noqa: E402

SIGNED = "https://groupweb.chaoxing.com/course/topic/topicList?courseid=1&clazzid=2&cpi=3&bbsid=0123456789abcdef0123456789abcdef&enc=SECRETENC"

BASE_INFO = {
    "status": True,
    "courseNavigationListV3": [
        {"translateName": "首页", "linkUrl": "/", "isDefault": 1, "openType": 0,
         "children": [{"translateName": "近期待办事项", "isDefault": 0, "openType": 0}]},
        {"translateName": "教学任务", "linkUrl": "https://task.chaoxing.com/task/index?enc=SECRETENC", "openType": 0},
    ],
    "noticeUrl": "https://notice.chaoxing.com/pc/course/notice/myNoticeList?courseid=1&t=9&enc=SECRETENC",
    "discussUrl": SIGNED,
    "activityClazzId": 2,
    "courseInfo": {"belongSchoolId": "7"},
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    lg = logging.getLogger("xuexitong_mcp.bsk")
    for h in list(lg.handlers):
        lg.removeHandler(h)
    monkeypatch.setattr(bsk_mod, "STATE_FILE", tmp_path / "state.json")
    cfg = Config()
    cfg.log_dir = tmp_path / "logs"
    c = make_client(cfg)
    course = Course(id="1", name="合成课程", cpi="3", clazz_id="2", enc="E", t="9")
    monkeypatch.setattr(c, "ctx", lambda q, refresh=False: course)
    monkeypatch.setattr(c, "course", lambda q: course)
    c._calls = []
    c._course = course
    return c


def fake_on(client, monkeypatch, responder):
    def on(host, body, **kw):
        client._calls.append((host, body))
        return responder(host, body)
    monkeypatch.setattr(client, "on", on)


def test_course_modules_return_no_signed_values(client, monkeypatch):
    def resp(host, body):
        if "base-info" in body:
            return BASE_INFO
        if "resource-info" in body:
            return {"status": True, "data": [{"name": "课件库", "href": "https://mobilelearn.chaoxing.com/page/ppt/coursewareList?enc=SECRETENC"},
                                             {"name": "作业库", "href": "/mooc2-ans/work/library"}]}
        raise AssertionError(body)
    fake_on(client, monkeypatch, resp)
    r = client.course_modules("1")
    blob = json.dumps(r, ensure_ascii=False)
    assert "SECRETENC" not in blob and "bbsid" not in blob
    assert r["has_discussion"] is True
    assert r["modules"][1] == {"name": "教学任务", "host": "task.chaoxing.com", "path": "/task/index",
                               "open_type": 0, "default": False, "children": []}
    assert r["resource_libraries"][1]["host"] == STAT


def test_shell_info_rejects_invalid(client, monkeypatch):
    fake_on(client, monkeypatch, lambda h, b: {"status": False})
    with pytest.raises(XxtError):
        client.shell_info(client._course, refresh=True)


def test_bbsid_comes_from_base_info(client, monkeypatch):
    fake_on(client, monkeypatch, lambda h, b: BASE_INFO)
    assert client._bbsid(client._course) == "0123456789abcdef0123456789abcdef"


def test_bbsid_missing_is_error(client, monkeypatch):
    fake_on(client, monkeypatch, lambda h, b: {**BASE_INFO, "discussUrl": ""})
    with pytest.raises(XxtError):
        client._bbsid(client._course)


def test_empty_forum_shape_is_empty_list_but_other_shapes_fail(client, monkeypatch):
    client._course.bbsid = "0123456789abcdef0123456789abcdef"
    # Run the page JS against a synthetic response by interpreting its branches in Python
    # would be brittle; instead assert the JS contains the strict empty-forum guard.
    seen = {}

    def resp(host, body):
        seen["body"] = body
        return {"valid": True, "items": []}
    fake_on(client, monkeypatch, resp)
    assert client.topics("1") == []
    assert "j.datas===undefined && j.userAuth && Array.isArray(j.folder_list)" in seen["body"]
    fake_on(client, monkeypatch, lambda h, b: {"valid": False})
    with pytest.raises(XxtError):
        client.topics("1")


def test_dashboard_marks_partial_failure(client, monkeypatch):
    def resp(host, body):
        if host == M2:
            return {"todo": {"ok": True, "body": {"status": True, "data": [{"x": 1}], "lessonData": []}},
                    "work_alert": {"ok": True, "body": {"status": True}},
                    "exam_progress": {"ok": False, "http_status": 500},
                    "ai_evaluate_alert": {"ok": True, "body": {"status": True, "data": []}}}
        return {"study_board": {"ok": True, "body": {"status": True, "data": {"avgScore": 1}}},
                "high_risk": {"ok": True, "body": {"status": False}}}
    fake_on(client, monkeypatch, resp)
    r = client.dashboard("1")
    assert r["todo"] == {"ok": True, "todos": [{"x": 1}], "lessons": []}
    assert r["exam_progress"]["ok"] is False and r["high_risk"]["ok"] is False
    assert r["study_board"]["data"] == {"avgScore": 1}
    assert r["complete"] is False


def test_resource_overview_uses_empty_enc_and_reports_http_status(client, monkeypatch):
    def resp(host, body):
        assert host == STAT
        assert "enc=E" not in body and "enc=&" in body
        return {"courseware": {"ok": True, "body": {"status": True, "data": {"count": 3}}},
                "resources": {"ok": False, "http_status": 403}}
    fake_on(client, monkeypatch, resp)
    r = client.resource_overview("1")
    assert r["courseware"] == {"ok": True, "data": {"count": 3}}
    assert r["resources"]["http_status"] == 403
    assert r["exams"]["ok"] is False and r["complete"] is False


def test_portal_stats_native_zero_is_not_a_missing_metric_or_a_library_total(client, monkeypatch):
    def respond(host, script):
        assert "enc=E" not in script and "fetch(url,{credentials:'include',cache:'no-store'})" in script
        if host == STAT:
            assert "clazzid=0" in script and "courseid=1" in script and "semester=0" in script
            return {"/stat2/base-data/v3/taskEngineInfo": {"counts": {"task_engines": 9}},
                    "/stat2/base-data/v3/aiEvaluateInfo": {"counts": {"ai_practices": 7}},
                    "/stat2/base-data-new/getAiAssistantStatic": {"counts": {"knowledge_bases": 1, "knowledge_files": None,
                                                                           "knowledge_segments": 0}, "unused": "PRIVATE"}}
        if host == TASK:
            assert "courseId=1" in script and "isDel=0" in script and "pageSize=1" in script
            return {"/task/getTaskDataLists": {"counts": {"active_teaching_tasks": 10}}}
        assert host == M2 and "courseid=1" in script and "folderId=0" in script and "ps=1" in script
        return {"/mooc2-ans/ai-evaluate/v2/library/list": {"error": "http_403"}}

    fake_on(client, monkeypatch, respond)
    r = client.course_portal_statistics("1")
    assert r["complete"] is True and r["course_id"] == "1" and "PRIVATE" not in json.dumps(r)
    panel, libraries = r["portal_counts"], r["library_counts"]
    assert panel["knowledge_segments"] == {"available": True, "count": 0, "field": "data.totalFileSegmentCount",
                                           "source": "https://stat2-ans.chaoxing.com/stat2/base-data-new/getAiAssistantStatic"}
    assert panel["knowledge_files"]["count"] is None and not panel["knowledge_files"]["available"]
    assert panel["task_engines"]["count"] == 9 and libraries["active_teaching_tasks"]["count"] == 10
    assert libraries["practice_library_root_entries"]["error"] == "http_403"


def test_portal_stats_invalid_response_and_ambiguous_course(client, monkeypatch):
    fake_on(client, monkeypatch, lambda *a: {"/stat2/base-data-new/getAiAssistantStatic": {"counts": {"knowledge_segments": False}}})
    with pytest.raises(XxtError, match="完整课程名"):
        client.course_portal_statistics("合成")
    monkeypatch.setattr(client, "courses", lambda: [client._course, client._course])
    with pytest.raises(XxtError, match="同名课程"):
        client.course_portal_statistics("合成课程")
    assert not client._calls
    r = client.course_portal_statistics("1")
    assert r["complete"] is False and all(v["count"] is None for v in r["portal_counts"].values())


def test_teaching_tasks_validates_and_pages(client, monkeypatch):
    def resp(host, body):
        assert host == TASK and "isDel=1" in body and "page=2" in body
        return {"result": True, "data": [{"id": 1}], "total": 120}
    fake_on(client, monkeypatch, resp)
    r = client.teaching_tasks("1", page=2, page_size=50, deleted=True)
    assert r["items"] == [{"id": 1}] and r["has_more"] is True
    fake_on(client, monkeypatch, lambda h, b: {"result": False})
    with pytest.raises(XxtError):
        client.teaching_tasks("1")


def test_list_cap(client, monkeypatch):
    fake_on(client, monkeypatch, lambda h, b: {"result": True, "data": list(range(900)), "total": 900})
    assert len(client.teaching_tasks("1")["items"]) == 500


def test_new_tools_registered_as_read():
    from xuexitong_mcp import server as srv
    kinds = {n: k for n, k, _, _ in srv.TOOLS}
    for n in ("list_course_modules", "get_course_dashboard", "get_resource_overview", "get_course_portal_statistics",
              "list_teaching_tasks", "list_coursewares", "list_practices"):
        assert kinds[n] == "read"
