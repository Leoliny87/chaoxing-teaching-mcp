"""Regression through the real server gate and NoticeOps, with no browser or network."""
# All identity fixtures in this file are synthetic and offline only.
import synthetic_data as F
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from xuexitong_mcp import server
from xuexitong_mcp.bsk import JsError
from xuexitong_mcp.ops_notice import NoticeOps, SNAPSHOT_JS


class Editor(NoticeOps):
    def __init__(self, folder):
        self.cfg = SimpleNamespace(log_dir=Path(folder))
        self.c = SimpleNamespace(id=F.NUMERIC_004, name="测试课程", classes=[{"clazz_id": F.NUMERIC_005, "name": "默认班级"}])
        self.page = "courses"
        self.refreshes = self.fills = self.sends = 0
        self.duplicate = False
        self.journal = []
        self.b = SimpleNamespace(session="owned", tab=123, preserve_tab=False,
                                 navigate=self.navigate, _act=self.send, wait_readiness=lambda: None)
        self.snapshot = dict(course_id=self.c.id, course_name=self.c.name, operation="add",
            selected=[dict(type="course", id=F.NUMERIC_005, name="默认班级")], cc_count=0,
            uuid="test-uuid", draft_uuid="test-draft", title="《测试课程》", plain="", html="",
            editor_empty=True, notice_id_empty=True, scheduled=[False], unread=[False],
            comment=[True], hide_read=[False], reminder_switches=[False]*8, send_controls=["发送"])

    def course(self, query):
        return self.c

    def courses(self, refresh=False):
        if refresh:
            self.refreshes += 1
            self.page = "courses"  # The real courses(refresh=True) navigates here.
        return [self.c] + ([SimpleNamespace(id=F.CONTROL_019, name="测试课程")] if self.duplicate else [])

    def ctx(self, course):
        return self.c

    def navigate(self, url):
        if "/pc/course/notice/richtextNotice?" not in url:
            raise AssertionError("Unexpected navigation")
        self.page = "editor"

    def here(self, js, **kwargs):
        if js == SNAPSHOT_JS:
            if self.page != "editor":
                raise JsError("Error: 通知编辑页不匹配")
            return deepcopy(self.snapshot)
        if "const expected=" in js:
            if self.page != "editor":
                raise AssertionError("Would fill wrong page")
            self.fills += 1
            self.snapshot.update(title="测试", plain="测试正文", html="<p>测试正文</p>", editor_empty=False)
            return {"filled": True}
        raise AssertionError("Unexpected page script")

    def send(self, *args, **kwargs):
        self.sends += 1

    def _notice_journal(self, entry):
        self.journal.append(entry)

    def notice_inventory(self, *args, **kwargs):
        return {"items": [{"notice_id": "a"*32, "uuid": "test-uuid", "title": "测试", "content": "测试正文",
            "receivers": [dict(course_id=F.NUMERIC_004, class_id=F.NUMERIC_005, name="默认班级", type=4)]}],
            "pagination": {"complete": True}}


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.editor = Editor(self.tmp.name)
        self.cfg = SimpleNamespace(write_allow_courses=["测试课程"])
        self.state = patch.dict(server._state, client=self.editor, cfg=self.cfg)
        self.state.start()
        self.addCleanup(self.state.stop)
        server._PLANS.clear()
        self.addCleanup(server._PLANS.clear)
        self.sleep = patch("xuexitong_mcp.ops_notice.time.sleep")
        self.sleep.start()
        self.addCleanup(self.sleep.stop)
        self.call = server._wrap(server.publish_notice, "write")
        self.args = dict(course=F.NUMERIC_004, title="测试", content="测试正文", class_name=F.NUMERIC_005)

    def preview(self):
        result = self.call(**self.args)
        self.assertTrue(result["ok"], result)
        self.assertIn("plan_id", result)
        self.assertEqual(self.editor.page, "editor")
        self.assertEqual((self.editor.fills, self.editor.sends), (0, 0))
        return result["plan_id"]

    def test_name_allowlist_does_not_navigate_after_preview(self):
        plan = self.preview()
        self.assertEqual(self.editor.refreshes, 1)
        result = self.call(**self.args, confirm=True, plan_id=plan)
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.editor.refreshes, 1)
        self.assertEqual((self.editor.fills, self.editor.sends), (1, 1))
        self.assertEqual(result["verification"], "matched_uuid_title_body_and_class")
        replay = self.call(**self.args, confirm=True, plan_id=plan)
        self.assertFalse(replay["ok"])
        self.assertEqual(self.editor.sends, 1)

    def test_id_allowlist_still_works(self):
        self.cfg.write_allow_courses = [F.NUMERIC_004]
        plan = self.preview()
        self.assertTrue(self.call(**self.args, confirm=True, plan_id=plan)["ok"])
        self.assertEqual(self.editor.refreshes, 0)

    def test_revoked_allowlist_stops_before_any_fill(self):
        plan = self.preview()
        self.cfg.write_allow_courses = []
        result = self.call(**self.args, confirm=True, plan_id=plan)
        self.assertFalse(result["ok"])
        self.assertEqual((self.editor.fills, self.editor.sends), (0, 0))

    def test_duplicate_course_names_still_rejected_at_preview(self):
        self.editor.duplicate = True
        result = self.call(**self.args)
        self.assertFalse(result["ok"])
        self.assertNotIn("plan_id", result)
        self.assertEqual((self.editor.fills, self.editor.sends), (0, 0))

    def test_changed_parameters_reject_before_execution(self):
        plan = self.preview()
        result = self.call(**{**self.args, "title": "changed"}, confirm=True, plan_id=plan)
        self.assertFalse(result["ok"])
        self.assertEqual((self.editor.fills, self.editor.sends), (0, 0))

    def test_changed_editor_still_rejects_without_navigating_back(self):
        plan = self.preview()
        self.editor.page = F.CONTROL_019
        result = self.call(**self.args, confirm=True, plan_id=plan)
        self.assertFalse(result["ok"])
        self.assertEqual(self.editor.page, F.CONTROL_019)
        self.assertEqual((self.editor.fills, self.editor.sends), (0, 0))


if __name__ == "__main__":
    unittest.main()
