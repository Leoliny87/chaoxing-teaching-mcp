"""Chapter inserts round 2: AI-format rendering, placeholders, chapter vote form."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp.ops_chapter2 import ai_format_html, put_back, split_for_format, vote_form  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402


def test_ai_format_html_follows_the_page():
    h = ai_format_html([{"styleName": "h0", "content": "T<b>"}, {"styleName": "normal", "content": "x"},
                        {"styleName": "h2", "content": "y"}], "科技蓝")
    assert h.startswith("<h1>T&lt;b&gt;</h1>")     # "h0" becomes h1 without a template style, as on the page
    assert '<p class="ai-format-normal">x</p>' in h and 'class="ai-format-h2">y</h2>' in h
    assert ai_format_html([{"styleName": "toc 1", "content": "z"}], "通用模板2") == '<p style="font-size: 10.5pt;color: #161616;text-align: justify;">z</p>'


def test_placeholders_round_trip():
    desc = '<p>A</p><p><img src="x.png"></p><table><tr><td>1</td></tr></table><p>see <a href="u">link</a></p>'
    text, keep = split_for_format(desc)
    assert text == "A\n[图片1]\n[表格1]\nsee [链接1]" and [k for k, _ in keep] == ["[表格1]", "[图片1]", "[链接1]"]
    back = put_back("<p>A</p><p>[图片1]</p><p>[表格1]</p><p>see [链接1]</p>", keep)
    assert '<img src="x.png">' in back and "<table>" in back and '<a href="u">link</a>' in back


def test_vote_form_fields():
    f = dict(vote_form("9", "T", [{"type": "单选", "stem": "s", "options": ["a", "b"]}, {"type": "判断", "stem": "t", "required": True}],
                       None, False, True))
    assert f["timelong"] == "-1" and f["questioncount"] == "2" and f["question_type_2"] == "16" and f["question_ismust_2"] == "1"
    assert f["isanony"] == "1" and f["isUsed"] == "on"
    with pytest.raises(XxtError):
        vote_form("9", "T", [{"type": "填空", "stem": "s"}], None, False, False)
