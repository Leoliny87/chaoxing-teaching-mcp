"""Classroom activities and task points: request builders (live chains verified on a test class, 2026-11-07)."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import bsk as bsk_mod  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.ops_active import (KINDS, build_request, group_task_form, questionnaire_form, quiz_form,  # noqa: E402
                                      quiz_questions, resource_entry)
from xuexitong_mcp.ops_task import POINT_KINDS, _flatten, task_point_item  # noqa: E402
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


# ---------------------------------------------------------------- simple activities
@pytest.mark.parametrize("kind", sorted(KINDS))
def test_every_kind_builds_save_and_start(kind):
    title = "" if kind in ("计时器", "白板", "学生反馈") else "测试"
    s = {"countdown": False} if kind == "计时器" else {}
    m0, p0, q0, f0 = build_request(kind, "1", "2", title, False, s)
    m1, p1, q1, f1 = build_request(kind, "1", "2", title, True, s)
    assert m0 == m1 and p0 != p1 or kind == "评分"          # 评分 posts one endpoint with type 0/1
    if kind == "评分":
        assert (f0["type"], f1["type"]) == (0, 1)
    flat = {**q0, **f0}
    assert str(flat.get("courseId", "1")) == "1" and str(flat.get("classId", "2")) == "2"


def test_build_request_rejects_bad_input():
    with pytest.raises(XxtError):
        build_request("直播", "1", "2", "x", True, {})
    with pytest.raises(XxtError):
        build_request("抢答", "1", "2", "", True, {})
    with pytest.raises(XxtError):
        build_request("抽签", "1", "2", "x", True, {"count": 0})
    with pytest.raises(XxtError):
        build_request("计时器", "1", "2", "", True, {"countdown": True})


def test_discussion_sends_empty_active_id():
    # activeId 0 makes startDiscuss look up activity 0 ("未查询到活动信息")
    assert build_request("主题讨论", "1", "2", "t", True, {})[3]["activeId"] == ""


def test_feedback_takes_user_from_cookie_and_draw_lots_is_type_80():
    f = build_request("学生反馈", "1", "2", "", True, {})[3]
    assert f["uid"].startswith("__COOKIE__:") and f["fid"].startswith("__COOKIE__:") and f["title"] == "学生反馈"
    m, path, q, f = build_request("抽签", "1", "2", "t", False, {"count": 3})
    assert path.endswith("saveDrawLots") and f["activeType"] == 80 and f["selectNumByOnce"] == 3 and q["DB_STRATEGY"] == "COURSEID"


def test_vote_options_go_into_repeated_query_pairs():
    m, path, q, f = build_request("投票", "1", "2", "t", True, {"options": "正确/错误"})
    assert m == "GET" and q["_opts"] == [("question_options_2", "A"), ("question_options_2", "B")]
    assert f["question_option_2_0"] == "正确" and f["question_option_2_1"] == "错误"


# ---------------------------------------------------------------- 随堂练习
QUIZ = [
    {"type": "单选", "stem": "a", "options": ["x", "y"], "answer": "B", "score": 2},
    {"type": "多选", "stem": "b", "options": ["x", "y", "z"], "answer": "AC", "score": 3},
    {"type": "填空", "stem": "c", "answer": ["p", "q"]},
    {"type": "判断", "stem": "d", "answer": False},
    {"type": "简答", "stem": "e", "answer": "f"},
]


def test_quiz_questions_match_editor_templates():
    q = quiz_questions(QUIZ)
    assert [x["type"] for x in q] == [0, 1, 2, 16, 4]
    assert q[0]["rightAnswer"] == "B" and [a["name"] for a in q[0]["answer"]] == ["A", "B"]
    assert q[1]["rightAnswer"] == "AC" and (q[1]["amin"], q[1]["amax"]) == (1, 3)
    assert [a["content"] for a in q[2]["answer"]] == ["<p>p</p>", "<p>q</p>"] and q[2]["jsonConfig"]["xposition"] == 0
    assert q[3]["rightAnswer"] == "错" and [a["content"] for a in q[3]["answer"]] == ["对", "错"]
    assert q[4]["answer"] == [{"answer": "<p>f</p>", "recs": []}] and q[4]["jsonConfig"]["integralType"] == 2


def test_quiz_rejects_types_the_editor_lacks():
    with pytest.raises(XxtError):
        quiz_questions([{"type": "论述", "stem": "x", "answer": "y"}])


def test_quiz_form_defaults_and_settings():
    f = quiz_form("1", "2", "练习", QUIZ, 10, {"show_answer": False})
    assert f["timelong"] == 600000 and f["isLookAnswer"] == 0 and f["isSaveToReservoir"] == 1 and f["aTitle"] == "练习"
    assert len(json.loads(f["questions"])) == 5
    assert quiz_form("1", "2", "练习", QUIZ, -1, {})["timelong"] == -1
    with pytest.raises(XxtError):
        quiz_form("1", "2", "", QUIZ, 10, {})


# ---------------------------------------------------------------- 问卷
def test_questionnaire_form_shape():
    qs = [{"type": "单选", "stem": "a", "options": ["x", "y"], "required": True}, {"type": "简答", "stem": "b"},
          {"type": "判断题", "stem": "c"}, {"type": "多选", "stem": "d", "options": ["1", "2", "3"]}]
    f = questionnaire_form("1", "2", "问卷", qs, 30, False, {"anonymous": True})
    d = {}
    for k, v in f:
        d.setdefault(k, []).append(v)
    assert d["questioncount"] == ["4"] and d["isSaveAct"] == ["1"] and d["isanony"] == ["1"] and d["timelong"] == ["1800000"]
    assert d["question_type_1"] == ["0"] and d["question_options_1"] == ["A", "B"] and d["question_ismust_1"] == ["1"]
    assert d["question_type_2"] == ["4"] and "question_options_2" not in d
    assert d["question_type_3"] == ["16"] and d["question_option_3_1"] == ["错"]
    assert d["question_options_4"] == ["A", "B", "C"] and d["answerLimit_4"] == [""]
    assert d["questionId"] == ["0"] * 4
    assert dict(questionnaire_form("1", "2", "问卷", qs, 30, True, {}))["isSaveAct"] == "0"


def test_questionnaire_rejects_bad_questions():
    with pytest.raises(XxtError):
        questionnaire_form("1", "2", "t", [{"type": "填空", "stem": "x"}], 10, False, {})
    with pytest.raises(XxtError):
        questionnaire_form("1", "2", "t", [{"type": "单选", "stem": "x", "options": ["only"]}], 10, False, {})


# ---------------------------------------------------------------- 分组任务 / 资料
def test_group_task_form_is_personal_mode():
    f = group_task_form("1", "2", "3", "任务", "第一段\n第二段", 30, True, {})
    assert f["groupType"] == 3 and f["isSpecialPersonalTask"] == 1 and f["beginOrSave"] == 1 and f["timeLong"] == 1800000
    assert f["content"] == "<p>第一段</p><p>第二段</p>" and json.loads(f["evaluationWeightCount"])["weightTeacher"] == 100
    assert group_task_form("1", "2", "3", "任务", "", 30, False, {})["beginOrSave"] == 0


def test_resource_entry_ports_page_conversion():
    item = {"dataId": 9, "dataName": "讲义.pdf", "cataid": 100000019, "content": json.dumps({"suffix": "pdf", "objectId": "o"})}
    e = resource_entry(item)
    assert e["resourceType"] == 1006 and e["title"] == "讲义.pdf" and e["resourceData"] is item
    img = resource_entry({"dataName": "p", "cataid": 100000019, "content": {"suffix": "png", "thumbnail": "t"}})
    assert img["resourceType"] == 1003 and img["logo"] == "t"
    assert resource_entry({"dataName": "x", "cataid": 100000019, "content": "{bad"})["resourceType"] == 1000
    assert resource_entry({"dataName": "folder", "cataid": 1}) is None


def test_quiz_needs_class_of_course(client, monkeypatch):
    monkeypatch.setattr(client, "on", lambda *a, **k: pytest.fail("no request expected"))
    with pytest.raises(XxtError):
        client.create_quiz("1", "99", "t", QUIZ, False, 10)


# ---------------------------------------------------------------- task points
def test_every_point_kind_builds_an_item():
    row = {"name": "n", "title": "n", "activeName": "n", "bookName": "n", "cover": "c", "describe": "d", "id": 7, "courseId": 1, "exist": True,
           **{k: "X" for k in ("workLibraryId", "paperId", "knowledgePointsId", "uuid", "activeId", "relationUuid", "taskId", "videoId",
                                "documentId", "audioId", "questionnaireId", "examineAndApproveId", "categoryId", "offlineClassroomId",
                                "onlineClassroomId", "simulationId", "dxid")}}
    for kind, spec in POINT_KINDS.items():
        it = task_point_item(kind, row)
        assert it["name"] == "n" and it["externalDataId"] == "X" or (kind in ("章节", "签到") and it["externalDataId"] == 7), kind
        assert row.get(spec["by"][1]) is not None


def test_point_items_follow_page_fields():
    w = task_point_item("作业", {"name": "w", "workLibraryId": "L", "workType": 1, "id": 5, "describe": "", "courseId": 1, "cover": "c"})
    assert (w["externalDataId"], w["localDataId"], w["workType"], w["exist"]) == ("L", 5, 1, False)
    d = task_point_item("主题讨论", {"title": "t", "uuid": "u", "exist": True})
    assert d["exist"] is False and d["localDataId"] == "" and d["externalDataId"] == "u"
    e = task_point_item("考试", {"name": "e", "paperId": "P", "paperType": 2})
    assert e["paperType"] == 2


def test_flatten_chapter_tree():
    tree = [{"id": 1, "name": "a", "children": [{"id": 2, "name": "b", "children": [{"id": 3, "name": "c"}]}]}, {"id": 4, "name": "d"}]
    assert [x["id"] for x in _flatten(tree)] == [1, 2, 3, 4]


def test_add_task_points_validates_before_any_request(client, monkeypatch):
    monkeypatch.setattr(client, "on", lambda *a, **k: pytest.fail("no request expected"))
    tid = "SyntheticTask@0123456789abcdef"
    with pytest.raises(XxtError):
        client.add_task_points("1", tid, "直播", ["x"])
    with pytest.raises(XxtError):
        client.add_task_points("1", "bad id", "作业", ["x"])
    with pytest.raises(XxtError):
        client.add_task_points("1", tid, "作业", [])
    with pytest.raises(XxtError):
        client.add_task_points("1", tid, "作业", materials=["a.txt"])
