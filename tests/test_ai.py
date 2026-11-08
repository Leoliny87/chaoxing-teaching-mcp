"""章节「智能编写」和「AI 校正」：prompts, markdown rendering, check items, tool registration."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp.ops_ai import (  # noqa: E402
    APPLY_JS, ARTICLE_TYPES, article_prompt, check_item, default_sections, md_html, outline_prompt)


def test_prompts_follow_the_page():
    theme = " 帮我生成一篇 字母通用文章"
    assert outline_prompt(theme, ["引言", "结尾"], 300) == \
        "<文章主题> 帮我生成一篇 字母通用文章</文章主题><目录结构>引言;结尾;</目录结构><文章字数>300</文章字数>"
    assert article_prompt(theme, "# 字母", "", 300, []) == \
        "<文章主题> 帮我生成一篇 字母通用文章</文章主题><目录结构># 字母</目录结构><文章字数>300</文章字数><写作风格>智能匹配;</写作风格>"
    assert "<年级或对象>小学</年级或对象>" in article_prompt(theme, "x", "小学", 300, ["通俗易懂"])
    assert default_sections(ARTICLE_TYPES["通用文章"]) == ["引言", "结尾"]
    assert default_sections(ARTICLE_TYPES["实习报告"]) == ["结尾", "实习目的与意义", "实习成果"]
    assert default_sections(None) == ["引言"]


def test_markdown_subset():
    h = md_html("# 标题\n第一段**粗**。\n第二段\n\n- a\n- b\n1. x\n> 引\n| a | b |\n|---|---|\n| 1 | 2 |\n"
                "[链接](https://e.com/?a=1&b=2) [坏](javascript:alert(1)) <script>\n---")
    assert h.startswith("<h1>标题</h1><p>第一段<strong>粗</strong>。</p><p>第二段</p><ul><li>a</li><li>b</li></ul><ol><li>x</li></ol>")
    assert "<blockquote><p>引</p></blockquote>" in h and "<td>1</td><td>2</td>" in h
    assert '<a href="https://e.com/?a=1&amp;b=2" target="_blank">链接</a>' in h
    assert "javascript:" not in h.split("[坏]")[0] and "<script>" not in h and "&lt;script&gt;" in h and h.endswith("<hr>")


def test_check_item_reads_the_marked_word():
    it = check_item({"type": "idiom", "wrongWord": '要<span class="ai-error">再接再励</span>，按',
                     "correctWord": '要<span class="ai-correct">再接再厉</span>，按'}, 3)
    assert it == {"index": 3, "type": "成语检查", "context": "要再接再励，按", "wrong": "再接再励", "suggestion": "再接再厉",
                  "before": "要", "after": "，"}
    assert check_item({"type": "punct", "wrongWord": "no span", "correctWord": "x"}, 0) is None
    assert check_item({"type": "spell", "wrongWord": '<span class="ai-error">按部就搬</span>', "correctWord": "按部就班"}, 1)["suggestion"] == "按部就班"
    assert "f.hit=true" in APPLY_JS and "FIXES.slice().reverse()" in APPLY_JS


def test_ai_tools_registered_teacher_only():
    from xuexitong_mcp import server as srv
    from xuexitong_mcp.policy import STUDENT_BASE
    kinds = {n: k for n, k, *_ in srv.TOOLS}
    new = {"get_ai_writing_options": "read", "add_ai_writing_option": "write", "delete_ai_writing_option": "destructive",
           "ai_write_chapter": "write", "ai_check_chapter": "read", "stop_ai_check": "write", "apply_ai_corrections": "write",
           "upload_panorama": "write"}
    assert all(kinds.get(n) == k for n, k in new.items())
    assert not set(new) & set(STUDENT_BASE)
