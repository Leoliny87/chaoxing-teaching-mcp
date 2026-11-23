"""Student attachment previews and single-use confirmation."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from xuexitong_mcp import server as srv  # noqa: E402
from xuexitong_mcp.bsk import BskError  # noqa: E402
from xuexitong_mcp.config import Config  # noqa: E402
from xuexitong_mcp.ops_student import StudentOps  # noqa: E402
from xuexitong_mcp.ops_upload import UploadOps  # noqa: E402
from xuexitong_mcp.xxt import XxtError  # noqa: E402


@pytest.fixture()
def assignment_tool(tmp_path, monkeypatch):
    course = SimpleNamespace(id="27", clazz_id="19", name="测试课程")
    course_ref = f"{course.id}_{course.clazz_id}"
    work = {
        "assignment_id": "38",
        "title": "附件练习",
        "status": "未交",
        "questions": [{"no": 1, "type": 4, "type_name": "简答题", "stem": "附上自己的作答。"}],
    }
    calls = []

    class Client:
        def _stu_course(self, q):
            assert q in (course_ref, course.name)
            return course

        def read_my_assignment(self, course_id, work_ref):
            assert course_id in (course_ref, course.name) and work_ref in (work["assignment_id"], work["title"])
            return work

        def answer_my_assignment(self, *args, **kwargs):
            calls.append((args, kwargs))
            return {"ok": True}

    allowed = tmp_path / "uploads"
    allowed.mkdir()
    file = allowed / "[合成]作答.txt"
    file.write_bytes(b"my test answer\n")
    cfg = Config()
    cfg.upload_allow_dirs = [str(allowed)]
    cfg.write_allow_courses = [course.id]
    monkeypatch.setattr(srv, "_state", dict(srv._state, client=Client(), cfg=cfg,
                                            budget=None, allowed={"submit_my_assignment"}, profile="student"))
    monkeypatch.setattr(srv, "_PLANS", {})
    tool = srv._wrap(srv.submit_my_assignment, srv.W)
    return tool, work, calls, file


@pytest.mark.parametrize("answers", [{}, {"1": "我自己的作答"}])
def test_attachment_preview_and_confirmation_bind_assignment_and_file(assignment_tool, answers):
    submit, _, calls, file = assignment_tool
    attachments = {"#1": str(file)}
    preview = submit("测试课程", "附件练习", answers, attachments=attachments)
    fingerprint = {"name": "-合成-作答.txt", "size": file.stat().st_size,
                   "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
    assert preview["dry_run"] and preview["assignment_id"] == "38"
    assert preview["course"]["class_id"] == "19"
    assert preview["attachments"] == [{"no": 1, **fingerprint}]
    assert preview["unanswered"] == [] and "确认提交" in preview["next"] and not calls

    result = submit("测试课程", "附件练习", answers, True, "确认提交",
                    attachments=attachments, plan_id=preview["plan_id"])
    assert result["ok"] and calls == [
        (("27_19", "38", answers), {"submit": True, "attachments": {"1": [{"path": str(file), **fingerprint}]}})
    ]
    assert not submit("测试课程", "附件练习", answers, True, "确认提交",
                      attachments=attachments, plan_id=preview["plan_id"])["ok"]
    assert len(calls) == 1


def test_attachment_list_previews_and_binds_each_file_in_order(assignment_tool):
    submit, _, calls, text = assignment_tool
    pdf = text.with_name("附件.pdf")
    pdf.write_bytes(b"%PDF-1.4 synthetic")
    attachments = {"1": [str(pdf), str(text)]}
    previews = [
        {"no": 1, "name": name, "size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p, name in [(pdf, pdf.name), (text, "-合成-作答.txt")]
    ]
    preview = submit("测试课程", "38", {}, attachments=attachments)
    assert preview["attachments"] == previews and not calls
    result = submit("测试课程", "38", {}, True, "确认提交",
                    attachments=attachments, plan_id=preview["plan_id"])
    records = [{"path": str(p), "name": info["name"], "size": info["size"], "sha256": info["sha256"]}
               for p, info in zip((pdf, text), previews)]
    assert result["ok"] and calls == [(("27_19", "38", {}), {"submit": True, "attachments": {"1": records}})]


def test_attachment_list_cannot_be_reordered_at_confirmation(assignment_tool):
    submit, _, calls, first = assignment_tool
    second = first.with_name("另一份.txt")
    second.write_bytes(b"synthetic")
    preview = submit("测试课程", "38", {}, attachments={"1": [str(first), str(second)]})
    assert preview["dry_run"]
    result = submit("测试课程", "38", {}, True, "确认提交",
                    attachments={"1": [str(second), str(first)]}, plan_id=preview["plan_id"])
    assert not result["ok"] and not calls


@pytest.mark.parametrize("changed", ["attachments", "answers", "assignment", "confirm_text"])
def test_attachment_confirmation_rejects_changes(assignment_tool, changed):
    submit, _, calls, file = assignment_tool
    planned = {"course": "测试课程", "assignment": "附件练习", "answers": {}, "attachments": {"1": str(file)}}
    preview = submit(**planned)
    assert preview["dry_run"]
    different = {"attachments": {"1": str(file) + ".other"}, "answers": {"1": "different"},
                 "assignment": "38", "confirm_text": "同意"}
    arguments = {**planned, "confirm_text": "确认提交", changed: different[changed]}
    assert not submit(**arguments, confirm=True, plan_id=preview["plan_id"])["ok"]
    assert not calls


def test_attachment_confirmation_rechecks_upload_scope_for_every_file(assignment_tool, tmp_path):
    submit, _, calls, file = assignment_tool
    sibling_root = tmp_path / "sibling"
    sibling_root.mkdir()
    sibling_file = sibling_root / "另一份.txt"
    sibling_file.write_bytes(b"synthetic")
    srv._state["cfg"].upload_allow_dirs.append(str(sibling_root))
    attachments = {"1": [str(file), str(sibling_file)]}
    preview = submit("测试课程", "38", {}, attachments=attachments)
    assert preview["dry_run"]
    srv._state["cfg"].upload_allow_dirs.remove(str(sibling_root))
    result = submit("测试课程", "38", {}, True, "确认提交",
                    attachments=attachments, plan_id=preview["plan_id"])
    assert not result["ok"] and not calls


@pytest.mark.parametrize("state", ["submitted", "draft", "other_type", "multiple_questions",
                                    "multiple_attachment_keys", "unlisted_path", "over_limit",
                                    "empty_list", "too_many_files", "duplicate_safe_name"])
def test_attachment_preview_rejects_unsupported_work_or_file(assignment_tool, tmp_path, state):
    submit, work, calls, file = assignment_tool
    attachments = {"1": str(file)}
    if state == "submitted":
        work["status"] = "待批阅"
    elif state == "draft":
        work["questions"][0]["current"] = "已经暂存的作答"
    elif state == "other_type":
        work["questions"][0]["type"] = 0
    elif state == "multiple_questions":
        work["questions"].append(dict(work["questions"][0], no=2))
    elif state == "multiple_attachment_keys":
        attachments["2"] = str(file)
    elif state == "unlisted_path":
        elsewhere = tmp_path / "other.txt"
        elsewhere.write_bytes(b"synthetic")
        attachments["1"] = str(elsewhere)
    elif state == "over_limit":
        with file.open("r+b") as stream:
            stream.truncate(500 * 1024 ** 2 + 1)
    elif state == "empty_list":
        attachments["1"] = []
    elif state == "too_many_files":
        attachments["1"] = [str(file)] * 11
    elif state == "duplicate_safe_name":
        duplicate = file.with_name("-合成-作答.txt")
        duplicate.write_bytes(b"different synthetic bytes")
        attachments["1"] = [str(file), str(duplicate)]
    result = submit("测试课程", "38", {}, attachments=attachments)
    assert not result["ok"] and "plan_id" not in result and not calls


def test_text_only_submit_keeps_existing_client_call(assignment_tool):
    submit, _, calls, _ = assignment_tool
    preview = submit("测试课程", "附件练习", {"1": "作答"}, False, "")
    assert "attachments" not in preview
    result = submit("测试课程", "附件练习", {"1": "作答"}, True, "确认提交", plan_id=preview["plan_id"])
    assert result["ok"] and calls == [(("测试课程", "附件练习", {"1": "作答"}), {"submit": True})]


def test_editor_receipt_correlates_generic_image_and_audio_attachments():
    receipts = [
        {"id": "a" * 32, "name": "报告.pdf", "size": "20B", "kind": "file"},
        {"id": "b" * 32, "name": None, "size": None, "kind": "image"},
        {"id": "c" * 32, "name": "朗读.mp3", "size": None, "kind": "audio"},
    ]
    attached = []
    for receipt, name in zip(receipts, ("报告.pdf", "图片.PNG", "朗读.mp3"), strict=True):
        result = StudentOps._read_inserted_work_attachment(attached, [*attached, receipt], {"name": name, "size": 20})
        assert result == receipt
        attached.append(result)
    assert attached == receipts


@pytest.mark.parametrize("failure", ["replacement", "ambiguous", "duplicate_id", "wrong_name", "wrong_size", "wrong_kind"])
def test_editor_receipt_rejects_unverified_insertion(failure):
    previous = {"id": "a" * 32, "name": "已有.txt", "size": "10B", "kind": "file"}
    inserted = {"id": "b" * 32, "name": "报告.pdf", "size": "20B", "kind": "file"}
    after = [previous, inserted]
    if failure == "replacement":
        after[0] = dict(previous, name="替换.txt")
    elif failure == "ambiguous":
        after.append(dict(inserted, id="c" * 32))
    elif failure == "duplicate_id":
        inserted["id"] = previous["id"]
    elif failure == "wrong_name":
        inserted["name"] = "别的报告.pdf"
    elif failure == "wrong_size":
        inserted["size"] = "21B"
    elif failure == "wrong_kind":
        inserted.update(kind="image", name=None)
    with pytest.raises(XxtError):
        StudentOps._read_inserted_work_attachment([previous], after, {"name": "报告.pdf", "size": 20})


def _unexpected_browser_action(*args, **kwargs):
    pytest.fail("unexpected browser action")


def test_all_attachment_snapshots_are_checked_before_opening_dialog(tmp_path):
    student = object.__new__(StudentOps)
    student.b = SimpleNamespace(click_selector=_unexpected_browser_action, run=_unexpected_browser_action)
    student.here = _unexpected_browser_action
    snapshot_dirs = []

    def snapshot(path, digest):
        tmp, real_copy, metadata = UploadOps._snapshot(student, path, digest)
        snapshot_dirs.append(tmp)
        return tmp, real_copy, metadata

    student._snapshot = snapshot
    files = []
    for name, data in (("first.txt", b"first"), ("second.pdf", b"previous")):
        path = tmp_path / name
        path.write_bytes(data)
        files.append({"path": str(path), "name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    # Keep the size unchanged so only a content check can detect the edit.
    (tmp_path / "second.pdf").write_bytes(b"modified")
    with pytest.raises(XxtError, match="哈希不同"):
        student._attach_files_in_work("42", files, [])
    assert len(snapshot_dirs) == 1 and not snapshot_dirs[0].exists()


@pytest.mark.parametrize("effect", ["none", "unknown"])
def test_receipt_reader_retries_only_a_read_only_document_transition(effect):
    student = object.__new__(StudentOps)
    calls = []
    refusal = BskError("permission_denied", "document changed", {"reason": "document_changed", "effect_state": effect})

    def wait(script, *, timeout, interval):
        calls.append(("wait", script))
        if len(calls) == 1:
            raise refusal
        return True

    student.wait_for = wait
    student.b = SimpleNamespace(observe=lambda: calls.append(("observe", None)),
                                click_selector=_unexpected_browser_action, run=_unexpected_browser_action)
    script = "return true;"
    if effect == "none":
        assert student._wait_work_evidence(script, 10) is True
        assert calls == [("wait", script), ("observe", None), ("wait", script)]
    else:
        with pytest.raises(BskError) as caught:
            student._wait_work_evidence(script, 10)
        assert caught.value is refusal and calls == [("wait", script)]


@pytest.mark.parametrize("details_match", [True, False])
def test_attachment_only_submission_needs_saved_attachment_receipt(details_match):
    student = object.__new__(StudentOps)
    submits = []
    navigations = []
    student.b = SimpleNamespace(preserve_tab=False, navigate=lambda url, **kwargs: navigations.append(url))
    student.build_answers = _unexpected_browser_action
    file = {"path": "/tmp/报告.pdf", "name": "报告.pdf", "size": 20, "sha256": "0" * 64}
    receipt = {"id": "b" * 32, "name": file["name"], "size": "20B", "kind": "file"}

    def attach(qid, files, text_ops):
        assert qid == "42" and files == [file] and text_ops == []
        return [receipt]

    student._attach_files_in_work = attach
    student._click_work_attachment_submit = lambda qid, receipts: submits.append((qid, receipts))
    results = iter([True, {"files": [receipt] if details_match else []}])
    student._wait_work_evidence = lambda script, timeout: next(results)
    detail_url = "https://example.invalid/submit-detail"
    student._work_list = lambda c: [{"assignment_id": "38", "status": "待批阅", "_url": detail_url}]

    result = student._submit_work_attachment(
        SimpleNamespace(id="27"), {"assignment_id": "38", "title": "附件练习", "status": "未交"},
        [{"no": 1, "type": 4, "qid": "42", "current": ""}], {}, True, {"1": [file]},
    )
    assert submits == [("42", [receipt])] and navigations == [detail_url]
    assert result["ok"] is details_match and student.b.preserve_tab is not details_match
    if details_match:
        assert result["attachments"] == [{"no": 1, "name": "报告.pdf", "size": 20, "kind": "file"}]
    else:
        assert result["write_outcome"] == "unknown"
