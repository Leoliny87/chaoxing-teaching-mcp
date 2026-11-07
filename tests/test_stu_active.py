"""Student activities and new teacher builders: pure parts (live chains verified 2026-11-07)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import policy  # noqa: E402
from xuexitong_mcp.ops_active import group_task_form  # noqa: E402
from xuexitong_mcp.ops_stu_active import (SUBMITTABLE, fill_person_answers, question_view,  # noqa: E402
                                          questionnaire_answer_form, score_payload)
from xuexitong_mcp.ops_task import POINT_KINDS, library_create_payload  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402

QL = [
    {"id": 11, "type": 0, "content": "<p>先做什么？</p>", "answer": [{"name": "A", "content": "<p>直接</p>"}, {"name": "B", "content": "<p>预演</p>"}],
     "rightAnswer": "B", "answerAnalysis": "因为……", "ismust": 1},
    {"id": 12, "type": 1, "content": "哪些安全？", "answer": [{"name": x, "content": x} for x in "ABCD"], "answerLimitMap": {"min": "1", "max": "3"}},
    {"id": 13, "type": 2, "content": "先__再__", "answer": [{"name": "1", "content": ""}, {"name": "2", "content": ""}]},
    {"id": 14, "type": 16, "content": "不用核实。", "answer": [{"name": "1", "content": "对"}, {"name": "2", "content": "错"}]},
    {"id": 15, "type": 4, "content": "为什么？", "answer": [{"recs": []}]},
]


def test_question_view_never_shows_answers():
    v = question_view(QL)
    blob = json.dumps(v, ensure_ascii=False)
    assert "rightAnswer" not in blob and "因为" not in blob
    assert v[0]["options"] == ["A. 直接", "B. 预演"] and v[0]["required"] is True
    assert v[1]["choose"] == "1–3 项" and v[2]["blanks"] == 2 and v[3]["options"] == ["对", "错"]


def test_fill_person_answers_shapes():
    out, prev = fill_person_answers(QL, {"1": "b", "2": "AC", "3": ["预演", "确认"], "4": "错", "5": "避免误操作\n第二行"})
    assert out[0]["personAnswer"] == {"myoption": "B"} and out[1]["personAnswer"] == {"myoption": "AC"}
    assert out[2]["personAnswer"]["blankAnswer"] == [{"name": "1", "content": "预演"}, {"name": "2", "content": "确认"}]
    assert out[3]["personAnswer"] == {"myoption": "2"}
    assert out[4]["personAnswer"]["content"] == "<p>避免误操作</p><p>第二行</p>"
    assert [p["answer"] for p in prev][:4] == ["B", "AC", ["预演", "确认"], "错"]


@pytest.mark.parametrize("answers", [{"2": "A"}, {"1": "AB"}, {"1": "B", "2": "ABCD"}, {"1": "B", "3": ["只有一空"]}, {"1": "B", "4": "也许"}, {"9": "A"}])
def test_fill_person_answers_rejects(answers):
    with pytest.raises(XxtError):
        fill_person_answers(QL, answers)


def test_questionnaire_form_matches_page_form():
    f, prev = questionnaire_answer_form(QL[:2] + QL[3:], {"1": "B", "2": ["A", "C"], "3": "对", "4": "建议"}, "1", "2", "3")
    assert f[:3] == [("courseId", "1"), ("classId", "2"), ("activeId", "3")]
    assert ("answer11", "B") in f and ("answer12", "A") in f and ("answer12", "C") in f and ("answer14", "1") in f and ("answer15", "建议") in f
    assert [k for k, _ in f].count("questionId") == 4


def test_score_payload_total_and_criteria():
    body, prev = score_payload({"score": "10.0"}, {"score": 8, "comment": "好"})
    assert body == {"score": 8.0, "scoreList": "[]", "content": "好"}
    info = {"isnorm": 1, "normList": [{"content": "内容", "score": 6}, {"content": "表达", "score": 4}]}
    body, prev = score_payload(info, {"scores": [5, 3]})
    assert body["score"] == 8.0 and json.loads(body["scoreList"]) == [5.0, 3.0]
    with pytest.raises(XxtError):
        score_payload(info, {"scores": [7, 3]})
    with pytest.raises(XxtError):
        score_payload({"score": "10"}, {"score": 11})


def test_point_to_only_types_cannot_be_submitted():
    assert not ({2, 4, 11, 46, 49, 80} & SUBMITTABLE)


def test_student_profile_tools():
    allow = policy.allowed_tools("student", [(n, "read") for n in ("open_my_activity", "list_my_tasks", "list_my_task_points", "create_activity")]
                                 + [("submit_my_activity", "write")], [], [])
    assert {"open_my_activity", "submit_my_activity", "list_my_tasks", "list_my_task_points"} <= allow and "create_activity" not in allow


# ---------------------------------------------------------------- teacher builders added with this change
def test_grouped_task_form():
    f = group_task_form("1", "2", "3", "t", "", 30, True, {"weights": {"teacher": 60, "within": 20, "between": 20}, "leader_submits": True},
                        {"plan_id": "0", "groups": 2, "max": 3})
    assert (f["groupType"], f["groupNum"], f["maxStuNumOneGroup"], f["isSpecialPersonalTask"], f["onlyLeaderSubmit"]) == (1, 2, 3, 0, 1)
    assert json.loads(f["evaluationWeightCount"]) == {"weightTeacher": 60, "weightWithInGroup": 20, "weightBetween": 20, "weightSelf": 0}
    with pytest.raises(XxtError):
        group_task_form("1", "2", "3", "t", "", 30, True, {"weights": {"teacher": 50}}, None)
    with pytest.raises(XxtError):
        group_task_form("1", "2", "3", "t", "", 30, True, {"weights": {"teacher": 80, "within": 20}}, None)


def test_library_create_payloads():
    b = library_create_payload("线下课堂", {"name": "课", "start": "2026-11-20 08:00", "end": "2026-11-20 09:30"}, "9")
    assert b["courseId"] == "9" and b["endDate"] - b["startDate"] == 90 * 60_000 and b["cover"].startswith("https://")
    s = library_create_payload("签到", {"name": "签"}, "9", None, "T@1")
    assert s["taskId"] == "T@1" and s["cover"].startswith("https://p.cldisk.com/")
    c = library_create_payload("自定义", {"name": "x", "url": "https://mooc1.chaoxing.com/a"}, "9", {"id": 5, "cover": "cv"})
    assert c["customTypeId"] == 5 and c["cover"] == "cv"
    with pytest.raises(XxtError):
        library_create_payload("自定义", {"name": "x", "url": "https://evil.example/a"}, "9", {"id": 5})
    with pytest.raises(XxtError):
        library_create_payload("AI实践", {"name": "x"}, "9")
    with pytest.raises(XxtError):
        library_create_payload("作业", {"name": "x"}, "9")
    assert "AI课堂" not in POINT_KINDS and POINT_KINDS["AI实践"]["type"] == 15 and POINT_KINDS["签到"]["list"] is None
