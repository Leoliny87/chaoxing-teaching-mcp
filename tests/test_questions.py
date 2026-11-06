"""Question builders vs. the request shapes captured from the real editors (2026-11-07)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import questions as Q  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402

ALL = {
    "单选": {"type": "单选", "stem": "第一步？", "options": ["提交", "预演"], "answer": "B"},
    "多选": {"type": "多选题", "stem": "写操作？", "options": ["发布", "查看", "发通知"], "answer": "AC"},
    "填空": {"type": "填空", "stem": "先 __ 再 __", "answer": ["预演", "确认"]},
    "判断": {"type": "判断", "stem": "可跳过回读", "answer": "错"},
    "简答": {"type": "简答", "stem": "为什么回读", "answer": "确认写入"},
    "名词解释": {"type": "名词解释", "stem": "MCP", "answer": "协议"},
    "论述": {"type": "论述", "stem": "论边界", "answer": ""},
    "计算": {"type": "计算", "stem": "1+1", "answer": "2"},
    "其它": {"type": "其他", "stem": "其它题", "answer": "x"},
    "分录": {"type": "分录", "stem": "办公用品", "answer": "借：管理费用 贷：银行存款"},
    "连线": {"type": "连线", "stem": "连线", "left": ["建作业", "发考试"], "right": ["publish", "init"], "answer": ["B", "A"]},
    "排序": {"type": "排序", "stem": "排序", "options": ["确认", "预演", "回读", "选课"], "answer": "DBAC"},
    "完型填空": {"type": "完形填空", "stem": "先 ##1## 再确认", "children": [{"type": "单选", "options": ["提交", "预演"], "answer": "B"}]},
    "阅读理解": {"type": "阅读理解", "stem": "材料", "children": [{"type": "单选", "stem": "一", "options": ["a", "b"], "answer": "B"},
                                                          {"type": "判断", "stem": "二", "answer": "错"}]},
    "程序": {"type": "程序", "stem": "输出 2", "language": "python", "answer": "print(1+1)", "cases": [{"input": "", "output": "2"}],
           "template": "# 作答"},
    "口语": {"type": "口语", "stem": "介绍学习通", "answer": "平台"},
    "听力": {"type": "听力", "stem": "听力", "children": [{"type": "简答", "stem": "为什么", "answer": "确认"}]},
    "共用选项": {"type": "共用选项", "stem": "选工具", "options": ["a", "b", "c"], "items": ["发作业", "开签到"], "answer": ["B", "C"]},
    "测评": {"type": "测评", "stem": "满意度", "options": ["好", "差"], "option_scores": [5, 1], "select_num": 1},
    "口语测评": {"type": "口语测评", "stem": "朗读", "read_text": "Hello", "language": "英语"},
    "钟表": {"type": "钟表", "mode": "认读", "clocks": [{"period": "上午", "hour": 9, "minute": 30}]},
    "选词填空": {"type": "选词填空", "stem": "先 ##1## 后 ##2##", "options": ["预演", "回读", "删除"], "answer": ["A", "B"]},
    "选做": {"type": "选做题", "stem": "任选", "optional_num": 1, "score": 10,
           "children": [{"type": "单选", "stem": "一", "options": ["a", "b"], "answer": "A"}, {"type": "简答", "stem": "二", "answer": "x"}]},
    "写作": {"type": "写作", "stem": "谈边界", "answer": "范文", "min_words": 50},
}


def one(name, surface="bank"):
    return Q.normalize(ALL[name], surface)


def f(q, surface="work"):
    return Q.type_fields(q, surface)


def test_every_type_has_a_sample_and_surfaces_match_editor_menus():
    assert {Q.type_id(v["type"]) for v in ALL.values()} == set(Q.TYPES.values())
    assert 25 not in Q.SURFACES["work"] and {22, 23} & Q.SURFACES["exam"] == set()
    with pytest.raises(XxtError):
        Q.normalize(ALL["选做"], "work")
    with pytest.raises(XxtError):
        Q.normalize(ALL["钟表"], "exam")


def test_choice_fields():
    s = f(one("单选"))
    assert s[0] == ("defAnswer", "B") and ("A", "<p>提交</p>") in s
    m = f(one("多选"))
    assert [v for k, v in m if k == "defAnswer"] == ["A", "C"]
    e = dict(Q.exam_fields(one("多选", "exam")))
    assert e["defAnswer"] == "A,C" and e["Z"] == "" and e["C"] == "<p>发通知</p>"


def test_blank_fields_per_surface():
    q = one("填空")
    w = dict(f(q, "work"))
    assert w["wrapAnswer"] == "<p>预演</p>★<p>确认</p>" and w["1"] == "<p>预演</p>" and w["2"] == "<p>确认</p>"
    b = dict(f(q, "bank"))
    assert b["answer"] == w["wrapAnswer"] and "wrapAnswer" not in b
    assert dict(Q.exam_fields(q))["answer"] == w["wrapAnswer"]
    assert Q.EXAM_ENDPOINT[9] == Q.EXAM_ENDPOINT[2] == "editPaperBlankFillingV2"


def test_tf_and_subjective():
    assert dict(f(one("判断")))["answerForTF"] == "false"
    assert dict(Q.exam_fields(one("判断", "exam")))["answer"] == "false"
    w = dict(f(one("简答")))
    assert w["answer"] == "<p>确认写入</p>" and w["wordnum"] == ""
    assert dict(f(one("论述")))["answer"] == ""
    assert {Q.EXAM_ENDPOINT[t] for t in Q.SUBJECTIVE} == {"editPaperAnswerV2"}


def test_connection_and_sort_json():
    a = json.loads(Q.answer_json(one("连线")))
    assert a[0][1] == {"name": 2, "content": "<p>发考试</p>"} and a[1][0]["name"] == "A"
    assert a[2] == [{"name": 1, "content": "B"}, {"name": 2, "content": "A"}]
    s = json.loads(Q.answer_json(one("排序")))
    assert s[1] == {"answer": "DBAC"} and s[0][3] == {"name": "D", "content": "<p>选课</p>"}
    with pytest.raises(XxtError):
        Q.normalize({**ALL["排序"], "answer": "DBAA"}, "work")


def test_cloze_children_and_stem_marks():
    q = one("完型填空")
    assert "&nbsp;&nbsp;&nbsp;1&nbsp;&nbsp;&nbsp;" in q.stem_html and "##" not in q.stem_html
    kid = json.loads(Q.answer_json(q))[0]
    assert "typeId" not in kid and kid["name"] == "单选题" and "content" not in kid["data"]
    assert kid["data"]["answer"][1] == {"content": "<p>预演</p>", "isanswer": True, "name": "B"}
    with pytest.raises(XxtError):
        Q.normalize({**ALL["完型填空"], "stem": "没有空"}, "work")
    with pytest.raises(XxtError):
        Q.normalize({**ALL["完型填空"], "children": [{"type": "判断", "stem": "x", "answer": "对"}]}, "work")


def test_reading_children_and_scores():
    q = one("阅读理解")
    kids = json.loads(Q.answer_json(q))
    assert q.score == 10 and kids[0]["typeId"] == 0 and kids[1]["data"]["answer"] == '[{"answer":false}]'
    lst = json.loads(Q.answer_json(one("听力")))[0]["data"]
    assert lst["answer"] == '[{"answer":"<p>确认</p>"}]'
    o = one("选做")
    assert o.score == 10 and all(k.score == 10 for k in o.children)
    e = dict(Q.exam_fields(o))
    assert e["optionalNum"] == 1 and Q.EXAM_ENDPOINT[25] == "editReadComPrehensionClozeText"
    assert ("optionalNum", 1) in f(o, "bank") and ("typeField", 25) in f(o, "bank")


def test_procedure_json():
    a = json.loads(Q.answer_json(one("程序")))[0]
    assert a["languageName"] == "Python3.12.12" and a["languageIndex"] == "22" and a["procedureReviewMode"] == "1"
    assert a["answerCode"].endswith("print(1+1)</code></pre>") and a["exampleArr"] == [{"stdin": "", "stdout": "2", "memory": 65536, "time": 10000}]
    assert a["preparedCode"] == [{"codeNum": "22", "codeName": "Python3.12.12", "code": "# 作答"}]
    with pytest.raises(XxtError):
        Q.normalize({**ALL["程序"], "language": "Cobol"}, "work")
    with pytest.raises(XxtError):
        Q.normalize({**ALL["程序"], "cases": []}, "work")


def test_btype_evaluation_oral_clock_words_writing():
    b = json.loads(Q.answer_json(one("共用选项")))
    assert b[0]["title"] == "(1)-(2) 题共用备选答案：" and b[3][1] == {"name": 2, "content": "C"}
    ev = json.loads(Q.answer_json(one("测评")))
    assert ev == [{"selectNum": 1}, [{"name": "A", "content": "<p>好</p>", "score": 5}, {"name": "B", "content": "<p>差</p>", "score": 1}]]
    assert ("selectMaxNum", 2) in f(one("测评"))
    oral = json.loads(Q.answer_json(one("口语测评")))[0]
    assert oral == {"readText": "Hello", "language": "en", "slack": "2", "autoMark": "1", "hideReadText": ""}
    c = one("钟表")
    assert Q.content_html(c) == "选择钟面表示的时刻" and json.loads(Q.answer_json(c)) == [{"type": "0", "data": [{"period": "上午", "hour": "9", "minute": "30"}]}]
    w = json.loads(Q.answer_json(one("选词填空")))
    assert w[0][0] == {"name": "A", "content": "预演"} and w[1] == [{"name": 1, "content": "A"}, {"name": 2, "content": "B"}]
    wr = json.loads(Q.answer_json(one("写作")))[0]
    assert wr == {"answer": "范文", "grade": "cet4", "wordMinNum": "50", "wordnum": "15000"}


def test_input_is_escaped_and_validated():
    q = Q.normalize({"type": "简答", "stem": "<script>x</script>\n第二行", "answer": "<b>"}, "work")
    assert q.stem_html == "<p>&lt;script&gt;x&lt;/script&gt;</p><p>第二行</p>" and q.answer == "<p>&lt;b&gt;</p>"
    for bad in ({"type": "单选", "stem": "x", "options": ["a", "a"], "answer": "A"},
                {"type": "单选", "stem": "x", "options": ["a", "b"], "answer": "AB"},
                {"type": "多选", "stem": "x", "options": ["a", "b"], "answer": "A"},
                {"type": "判断", "stem": "x", "answer": "是"},
                {"type": "判断", "stem": "", "answer": "对"},
                {"type": "判断", "stem": "x", "answer": "对", "score": 0},
                {"type": "连线", "stem": "x", "left": ["a"], "right": ["b"], "answer": ["C"]},
                {"type": "钟表", "clocks": [{"period": "上午", "hour": 13, "minute": 0}]},
                {"type": "不存在", "stem": "x"}):
        with pytest.raises(XxtError):
            Q.normalize(bad, "bank")
