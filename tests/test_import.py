"""Bank import: template rows from question data, and the xlsx writer."""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp.ops_import import HEADER, excel_rows, folder_path  # noqa: E402
from xuexitong_mcp.xlsx import build_xlsx  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402


def test_rows_for_each_type():
    rows, expect = excel_rows([
        {"type": "单选", "stem": "s1", "options": ["A", "B", "C"], "answer": "B", "difficulty": "易", "tags": ["t1", "t2"]},
        {"type": "判断", "stem": "s2", "answer": "错"},
        {"type": "填空", "stem": "s3 ____", "answer": ["2;二"]},
        {"type": "简答", "stem": "s4", "answer": "ref"},
        {"type": "连线", "stem": "s5", "left": ["a", "b"], "right": ["B", "A"], "answer": "BA"},
        {"type": "共用选项", "stem": "s6", "options": ["1", "2"], "items": ["一", "二"], "answer": "AB"},
        {"type": "阅读理解", "stem": "s7", "children": [{"type": "单选", "stem": "c1", "options": ["x", "y"], "answer": "A"},
                                                      {"type": "判断", "stem": "c2", "answer": "对"}]},
        {"type": "完型填空", "stem": "a ##1## b", "children": [{"type": "单选", "options": ["p", "q"], "answer": "B"}]},
        {"type": "选做", "stem": "s9", "optional_num": 1, "children": [{"type": "简答", "stem": "c", "answer": "9"}]},
    ], "/第一章")
    assert rows[0] == HEADER and len(expect) == 9
    assert rows[1][:12] == ["/第一章", "单选题", "", "s1", "", "", "B", "", "易", "", "t1；t2", "3"] and rows[1][12:] == ["A", "B", "C"]
    assert rows[2][6] == "B" and rows[2][11:] == ["2", "正确", "错误"] and rows[2][8] == "中"
    assert rows[3][11:] == ["1", "2;二"] and rows[4][6] == "A" and rows[4][11:] == ["1", "ref"]
    assert rows[5][6] == "BA" and rows[5][11:] == ["2+2", "a", "b", "B", "A"]
    assert rows[6][11:] == ["2", "1", "2"] and rows[7] == ["", "", "", "", "", "一", "A"] and rows[8][6] == "B"
    assert rows[10][4:7] == ["单选题", "c1", "A"] and rows[11][4:7] == ["判断题", "c2", "A"]
    assert rows[13][4:7] == ["单选题", "", "B"] and rows[13][11:] == ["2", "p", "q"]
    assert rows[14][11] == "1" and rows[15][4:7] == ["简答题", "c", "A"]


@pytest.mark.parametrize("qs,folder", [
    ([{"type": "计算", "stem": "x", "answer": "1"}], ""),            # not importable by Excel
    ([{"type": "单选", "stem": "x", "options": ["a", "b"], "answer": "A", "difficulty": "很难"}], ""),
    ([{"type": "单选", "stem": "x", "options": ["a", "b"], "answer": "A", "tags": ["a;b"]}], ""),
    ([{"type": "判断", "stem": "x", "answer": "对"}], "/a//b"),
    ([], ""),
])
def test_rows_refused(qs, folder):
    with pytest.raises(XxtError):
        excel_rows(qs, folder)


def test_folder_path():
    assert folder_path("") == "" and folder_path("a") == "/a" and folder_path("/a/b/") == "/a/b"


def test_xlsx_cells_round_trip():
    data = build_xlsx([["h1", "h2"], ["a<b>&", "", "c\x01"]], "课程题库")
    z = zipfile.ZipFile(io.BytesIO(data))
    sst = z.read("xl/sharedStrings.xml").decode()
    sheet = z.read("xl/worksheets/sheet1.xml").decode()
    assert "a&lt;b&gt;&amp;" in sst and "\x01" not in sst and 'r="C2"' in sheet and 'r="B2"' not in sheet
    assert "课程题库" in z.read("xl/workbook.xml").decode()


def test_smart_qjson_matches_the_page():
    """Input and expected output captured from the smart-import page's own makeupPaper (2026-11-08)."""
    from xuexitong_mcp.ops_import import smart_item, smart_qjson, with_ids
    paper = [
        {"answerKey": "大写", "answer": ["A"], "type": "QuestionChoice", "typeAlias": "单选题", "content": "s1",
         "options": [{"name": "A", "value": "A"}, {"name": "B", "value": "B"}]},
        {"answerValue": True, "answer": ["正确"], "type": "QuestionYesNo", "content": "s2"},
        {"gapCount": 1, "answer": ["2"], "type": "QuestionGapFilling", "content": "s3 ____"},
        {"difficulty": "易", "answer": ["ABC"], "type": "QuestionCommon", "difficultyValue": 0, "content": "s4"},
        {"type": "Unknown", "content": "ignored"},
    ]
    assert smart_qjson(paper) == [
        {"content": "s1", "analysis": "大写", "name": "单选题", "typeAlias": "单选题", "type": 0, "id": 0,
         "answer": [{"content": "A", "name": "A", "isanswer": True}, {"content": "B", "name": "B"}]},
        {"content": "s2", "name": "判断题", "typeAlias": "判断题", "answer": [{"answer": True}], "type": 3, "id": 1},
        {"content": "s3 ____", "name": "填空题", "typeAlias": "填空题", "type": 2, "answer": [{"content": "2", "name": "1"}], "id": 2},
        {"content": "s4", "difficulty": "易", "easy": None, "name": "简答题", "typeAlias": "简答题", "answer": [{"answer": "ABC"}], "type": 4, "id": 3},
    ]
    comp = smart_qjson([{"type": "QuestionComposite", "content": "r", "questions": [paper[0], paper[1]]}])[0]
    assert comp["type"] == 15 and [a["type"] for a in comp["answer"]] == [0, 3] and all("id" not in a for a in comp["answer"])
    assert all(len(a["id"]) == 36 for a in with_ids([comp])[0]["answer"])
    assert smart_item(comp) == {"type": "阅读理解", "stem": "r", "answered": True, "children": 2}
