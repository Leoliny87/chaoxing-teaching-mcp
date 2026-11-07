"""Course settings, self-test templates, recycle-bin checks: pure parts (live chains verified 2026-11-07)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import server as srv  # noqa: E402
from xuexitong_mcp.ops_manage import moved_check  # noqa: E402
from xuexitong_mcp.ops_settings import read_value, selftest_form, setting_request  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402

CUR = {"switches": {"允许学生自测": False}, "choices": {"章节试读": "试读全部"},
       "notices": {"开课时间通知": True, "作业收件箱通知": True, "作业群聊通知": True, "考试通知": True},
       "basic": {"课程名称": "课", "课程教师": "师", "英文名称": "", "课程说明": "旧", "_group1": "1", "_unit": "2", "_v": "0", "_subject": ""},
       "commitment": "<p>旧承诺</p>"}


def test_switch_choice_notice_text_requests():
    assert setting_request("允许学生自测", True, CUR) == ("GET", "/mooc2-ans/tcm/updatecourseselftest", {"selftest": 1})
    assert setting_request("AI工作台", False, CUR)[2] == {"aiAssistant": -1}
    assert setting_request("章节试读", "试读前三章", CUR)[2] == {"isprivately": 2}
    m, u, p = setting_request("作业群聊通知", False, CUR)
    assert u.endswith("updatesendnoticetype") and p == {"courseSendNotice": 1, "workSendNotice": 0, "workSendInboxNotice": 1,
                                                        "workSendChatNotice": 0, "examSendNotice": 1}
    m, u, p = setting_request("课程说明", "新说明", CUR)
    assert m == "POST" and p["infoContent"] == "新说明" and p["courseName"] == "课" and p["studyModule"] == ""
    m, u, p = setting_request("课程承诺书内容", "第一行\n<b>第二行</b>", CUR)
    assert p["content"] == "<p>第一行</p><p>&lt;b&gt;第二行&lt;/b&gt;</p>"
    assert read_value("课程承诺书内容", CUR) == "旧承诺" and read_value("章节试读", CUR) == "试读全部"


@pytest.mark.parametrize("name,value", [("允许学生自测", "是"), ("章节试读", "随便"), ("课程密码", "x"), ("课程说明", "x" * 501),
                                        ("课程承诺书内容", "  "), ("人脸识别", True)])
def test_setting_request_rejects(name, value):
    with pytest.raises(XxtError):
        setting_request(name, value, CUR)


TYPES = [{"data": "0", "typeId": "0", "total": "10", "name": "单选题"}, {"data": "3", "typeId": "0", "total": "18", "name": "判断题"}]


def test_selftest_form_random_and_by_type():
    f = selftest_form("1", "2", {"name": "自测", "mode": "模拟测验", "minutes": 20, "count": 5}, TYPES, 130)
    assert (f["type"], f["limitTime"], f["randomNum"], f["randomType"], f["questionFrom"], f["templateType"]) == ("0", "20", "5", "0", "0", "2")
    f = selftest_form("1", "2", {"name": "刷题", "mode": "刷题", "by_type": {"单选": 2, "判断题": 3}}, TYPES, 130)
    assert f["type"] == "1" and f["limitTime"] == "" and f["randomNum"] == "5" and f["randomType"] == "2"
    assert json.loads(f["randomTypeSet"]) == [{"selectNum": 2, "type": 0, "typeId": 0}, {"selectNum": 3, "type": 3, "typeId": 0}]


@pytest.mark.parametrize("item", [{"name": "x", "mode": "模拟测验", "count": 5}, {"name": "x", "mode": "刷题", "count": 131},
                                  {"name": "x", "mode": "刷题", "by_type": {"多选": 1}}, {"name": "x", "mode": "刷题", "by_type": {"单选": 11}},
                                  {"name": "", "mode": "刷题", "count": 1}, {"name": "x", "mode": "考试", "count": 1},
                                  {"name": "x", "mode": "刷题", "source": "错题集", "by_type": {"单选": 1}}])
def test_selftest_form_rejects(item):
    with pytest.raises(XxtError):
        selftest_form("1", "2", item, TYPES, 130)


def test_moved_check():
    assert moved_check(["1", "2", "3"], ["1", "3"], ["2", "9"], "2") == (True, "")
    assert moved_check(["1", "2"], ["1", "2"], ["2"], "2")[0] is False                 # still listed
    assert moved_check(["1", "2", "3"], ["3"], ["2"], "2")[0] is False                 # another item vanished
    assert moved_check(["1", "2"], ["1"], ["9"], "2")[0] is False                      # not in the bin
    assert moved_check(["2"], [], None, "2") == (True, "")


def test_weight_changes():
    from xuexitong_mcp.ops_classadmin import weight_changes
    cur = {"video": "40", "ceyan": "20", "work": "25", "test": "15", "aiEvaluate": "0", "visitTime": "0"}
    assert weight_changes(cur, {"作业": 30, "考试": 10}) == {"work": 30, "test": 10}
    for bad in ({"作业": 30}, {"作业": "30", "考试": 10}, {"成绩": 1}, {"章节学习次数": 5, "作业": 20}, {}):
        with pytest.raises(XxtError):
            weight_changes(cur, bad)


def test_no_preview_only_tools_left():
    assert not srv._PREVIEW_ONLY_TOOLS
    names = {n for n, *_ in srv.TOOLS}
    assert {"get_course_settings", "set_course_setting", "list_recycle_bin", "restore_deleted", "purge_deleted", "moderate_discussion",
            "reply_discussion", "create_material_folder", "set_material_download", "move_material", "list_folder_materials"} <= names
