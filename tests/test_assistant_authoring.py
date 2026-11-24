import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from xuexitong_mcp import ops_assistant_authoring as mod
from xuexitong_mcp.xxt import XxtError


C = SimpleNamespace(id="5", cpi="7", name="Example")
CRIT = [{"dimension": "Evidence", "description": "Check the sample", "score": 100}]
FAQ = {"qa_cell": "Question\nAnswer", "cells": ["Question\nAnswer", "手动添加"]}


@pytest.fixture
def env(monkeypatch):
    api = Mock()
    api.ctx.return_value = C
    w = Mock(c=C, api=api)
    monkeypatch.setattr(mod, "Workbench", lambda client, course: w)
    tools = {}

    def register(*unused):
        def save(f):
            tools[f.__name__] = f
            return f

        return save

    check = Mock(return_value=C)
    path = Mock()
    fingerprint = Mock()
    mod.register_assistant_authoring(
        register, lambda: api, check, lambda c, action, **k: k, path, fingerprint
    )
    return SimpleNamespace(
        api=api, w=w, tools=tools, check=check, path=path, fp=fingerprint
    )


def test_register_all_distinct_operations(env):
    assert len(env.tools) == 10
    env.w.page.return_value = {"items": []}
    assert env.tools["list_assistant_documents"]("5", "3", 2) == {"items": []}
    env.check.assert_not_called()
    env.w.library.assert_called_once_with("3")
    env.w.page.assert_called_once_with("documents", 2)


def test_existing_faq_preserved_and_verified(env):
    fn = env.tools["add_assistant_faq"]
    env.w.page.return_value = FAQ
    preview = fn("course", "Question", "Answer")
    assert (
        fn("course", "Question", "Answer", True, preview["bind"]["source_digest"])[
            "created"
        ]
        is False
    )
    with pytest.raises(XxtError):
        fn("course", "Question", "Ans")
    env.w.click.assert_not_called()


def test_new_faq_no_duplicate_after_click_and_verify(env):
    fn = env.tools["add_assistant_faq"]
    env.w.page.side_effect = [None, None, FAQ]
    stamp = fn("course", "Question", "Answer")["bind"]["source_digest"]
    assert fn("course", "Question", "Answer", True, stamp)["ok"]
    assert len(env.w.click.call_args_list) == 2


def test_stale_faq_preview_never_writes(env):
    fn = env.tools["add_assistant_faq"]
    env.w.page.return_value = None
    with pytest.raises(XxtError):
        fn("course", "Question", "Answer", True, "old")
    env.w.click.assert_not_called()


def test_full_multiline_answer_required():
    assert mod.faq_has_answer(
        {"qa_cell": "问： Q\n答： Alpha\nBeta"}, "Alpha Beta", "Q"
    )
    assert not mod.faq_has_answer({"qa_cell": "Q\nFull answer"}, "answer", "Q")


def test_library_edit_keeps_other_settings_and_reads_back(env):
    w = env.w
    fn = env.tools["save_assistant_library"]
    w.page.side_effect = [None, None, {"id": "3", "name": "New"}]

    def js(body, data=None, **kwargs):
        if "title.value,desc.value" in body:
            return ["New", "D"] if w.page.call_count == 3 else ["Old", "Original"]
        return True

    w.js.side_effect = js
    stamp = fn("5", "New", "D", "3")["bind"]["source_digest"]
    assert fn("5", "New", "D", "3", True, stamp) == {
        "ok": True,
        "library_id": "3",
        "name": "New",
        "description": "D",
    }
    assert any(
        "title.value!==arg[0][0]" in call.args[0] for call in w.js.call_args_list
    )


def test_pin_already_set_is_idempotent(env):
    fn = env.tools["set_assistant_library_pinned"]
    env.w.library.return_value = {"id": "3", "name": "Known", "pinned": True}
    stamp = fn("5", "3", True)["bind"]["source_digest"]
    assert fn("5", "3", True, True, stamp)["ok"]
    env.w.click.assert_not_called()


def test_refuse_duplicate_document_without_upload(env, tmp_path):
    f = tmp_path / "exam.txt"
    f.write_text("sample")
    env.path.return_value = f
    env.w.page.return_value = {"name": "exam.txt"}
    with pytest.raises(XxtError):
        env.tools["upload_assistant_document"]("5", "3", str(f), True, "a" * 64)
    env.api._snapshot.assert_not_called()


def test_upload_snapshot_and_readback(env, tmp_path):
    src = tmp_path / "doc.txt"
    src.write_text("hello")
    snapdir = tmp_path / "temp"
    snapdir.mkdir()
    dest = snapdir / src.name
    dest.write_bytes(src.read_bytes())
    env.path.return_value = src
    env.w.page.return_value = None
    env.w.document.return_value = {"name": src.name}
    env.fp.return_value = {"size": 5, "sha256": "a" * 64}
    env.api._snapshot.return_value = (snapdir, dest, {"name": src.name})
    env.w.js.side_effect = lambda body, *a, **k: (
        "#dropdown-menu-1 li:first-child" if "return '#'" in body else True
    )
    fn = env.tools["upload_assistant_document"]
    draft = fn("5", "2", str(src))
    assert fn("5", "2", str(src), True, draft["bind"]["file_sha256"])["ok"]
    env.api.b.upload_selector.assert_called_once_with(
        "#dropdown-menu-1 li:first-child", str(dest)
    )
    assert not dest.exists() and src.read_text() == "hello"


def test_segment_stale_preview_never_saves(env):
    env.w.page.return_value = {"id": "x", "text": "changed"}
    env.w.js.return_value = {"text": "before"}
    with pytest.raises(XxtError):
        env.tools["edit_assistant_document_segment"](
            "5", "2", "doc.txt", "x", "After", True, "bad"
        )
    assert not any("await parent.fnExit" in c.args[0] for c in env.w.js.call_args_list)


def test_real_practice_draft_saved_then_reread(env):
    env.api.on.return_value = {"status": True, "data": {"list": []}}
    env.api.here.side_effect = [True, {"ok": True, "practice_id": "draft-1"}]
    env.api.wait_for.return_value = True
    fn = env.tools["create_course_practice_draft"]
    result = fn(
        "5", "Example", "Ask", "Teacher", "Student", "Explain", "Start", CRIT, True
    )
    assert result["published"] is False and result["practice_id"] == "draft-1"
    save = env.api.here.call_args
    assert save.kwargs == {"retry_safe": False}
    assert "isPublish:'false'" in save.args[0] and "load-data" in save.args[0]


@pytest.mark.parametrize(
    "crit", [[], [{}], [{"dimension": "A", "description": "B", "score": 101}]]
)
def test_invalid_rubrics_are_not_sent(crit):
    with pytest.raises(XxtError):
        mod.practice_fields("T", "R", "A", "S", "D", "", crit)


def test_practice_duplicate_or_unknown_list_aborts(env):
    fn = env.tools["create_course_practice_draft"]
    for row in [{"name": "Example"}, {"uuid": "x"}]:
        env.api.on.return_value = {"status": True, "data": {"list": [row]}}
        with pytest.raises(XxtError):
            fn(
                "5",
                "Example",
                "Ask",
                "Teacher",
                "Student",
                "Explain",
                "Start",
                CRIT,
                True,
            )
    env.api.b.navigate.assert_not_called()


def test_origin_not_trusted_or_unrelated_course_frame_rejected():
    api = Mock()
    api.wait_for.side_effect = [
        True,
        True,
        "https://example.org/v1/front/goCourseKnowledgeBase",
    ]
    with pytest.raises(XxtError):
        mod.Workbench(api, C).open()
    assert api.b.navigate.call_count == 1


def test_empty_rows_without_a_zero_total_are_not_an_empty_library():
    w = mod.Workbench(Mock(), C)
    w.js = Mock(side_effect=[{"current": 1, "more": False, "total": "5"}, True])
    w.rows = Mock(return_value=[])
    with pytest.raises(XxtError):
        w.page("libraries")


def test_unverified_faq_never_reports_created(env):
    fn = env.tools["add_assistant_faq"]
    env.w.page.side_effect = [None, None, None]
    stamp = fn("5", "Question", "Answer")["bind"]["source_digest"]
    result = fn("5", "Question", "Answer", True, stamp)
    assert result["ok"] is False and result["write_outcome"] == "unknown"
    assert "created" not in result


def test_faq_answer_and_source_cannot_be_mistaken_for_the_question():
    row = {
        "qa_cell": "First question\nSecond question",
        "cells": ["First question\nSecond question", "手动添加"],
    }
    assert not mod.faq_match(row, "Second question")
    assert not mod.faq_match(row, "手动添加")
