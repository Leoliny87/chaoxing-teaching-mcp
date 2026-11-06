"""Offline tests: fakes only; never invoke the real browser or platform."""
# All identity fixtures in this file are synthetic and offline only.
import synthetic_data as F
import unittest
import logging
import os
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from xuexitong_mcp import server
from xuexitong_mcp import config
from xuexitong_mcp.xxt import Course, XxtBase, XxtError, _best
from xuexitong_mcp.ops_activity import ActivityOps
from xuexitong_mcp.ops_course import CourseOps
from xuexitong_mcp.ops_content import ContentOps
from xuexitong_mcp.privacy import redact_text
from xuexitong_mcp.bsk import _RedactLogFilter, Bsk, BskError, FIXED_BROWSER_INSTANCE, FIXED_HOMEPAGE


class FakeClient:
    def __init__(self):
        self.c = SimpleNamespace(id=F.NUMERIC_004, name="测试课程", classes=[
            {"clazz_id": F.NUMERIC_001, "name": "甲班"},
            {"clazz_id": F.NUMERIC_002, "name": "乙班"},
        ])
        self.course_list = [self.c]
        self.calls = []

    def course(self, _):
        return self.c

    def courses(self, refresh=False):
        return self.course_list

    def ctx(self, _):
        return self.c

    def papers(self, _):
        return [{"paper_id": "12", "title": "卷一"}]

    def publish_notice(self, *a):
        self.calls.append(("notice", a))
        return {"ok": True}

    def create_assignment(self, *a):
        self.calls.append(("assignment", a))
        return {"ok": True}

    def publish_exam(self, *a):
        self.calls.append(("exam", a))
        return {"ok": True}

    def publish_assignment(self, *a):
        self.calls.append(("publish_assignment", a))
        return {"ok": True}

    def create_topic(self, *a):
        self.calls.append(("discussion", a))
        return {"ok": True}

    def start_checkin(self, *a):
        self.calls.append(("checkin", a)); return {"ok": True}

    def pick_student(self, *a):
        self.calls.append(("pick", a)); return {"ok": True}

    def start_quick_answer(self, *a):
        self.calls.append(("quick", a)); return {"ok": True}

    def start_vote(self, *a):
        self.calls.append(("vote", a)); return {"ok": True}

    def assignment_library_first_page(self, course):
        self.calls.append(("library_read", (course,)))
        return {"page": 1, "total_pages": 2, "visible_count": 1,
                "items": [{"id": F.CONTROL_013, "title": "示例"}], "has_more": True, "complete": False}


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.old_state = dict(server._state)
        self.fake = FakeClient()
        server._state.update(client=self.fake, cfg=SimpleNamespace(write_allow_courses=["测试课程"]))
        server._PLANS.clear()

    def tearDown(self):
        server._state.clear()
        server._state.update(self.old_state)
        server._PLANS.clear()

    def test_empty_and_duplicate_name_fail_closed(self):
        server._state["cfg"].write_allow_courses = []
        with self.assertRaises(XxtError):
            server._check_write("测试课程")
        server._state["cfg"].write_allow_courses = ["测试课程"]
        self.fake.course_list.append(SimpleNamespace(id=F.CONTROL_019, name="测试课程"))
        with self.assertRaises(XxtError):
            server._check_write("测试课程")
        server._state["cfg"].write_allow_courses = [F.NUMERIC_004]
        self.assertEqual(server._check_write("测试课程").id, F.NUMERIC_004)

    def test_environment_cannot_broaden_course_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "config.toml"
            p.write_text('write_allow_courses = ["测试课程"]\n')
            for env, expected in (({}, ["测试课程"]), ({"XUEXITONG_MCP_WRITE_ALLOW":"测试课程,其他课"}, ["测试课程"]),
                                  ({"XUEXITONG_MCP_WRITE_ALLOW":"其他课"}, []), ({"XUEXITONG_MCP_WRITE_ALLOW":""}, [])):
                with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                    self.assertEqual(config.load(p).write_allow_courses, expected)
            p.write_text('write_allow_courses = []\n')
            with patch.dict(os.environ, {"XUEXITONG_MCP_WRITE_ALLOW":"测试课程"}, clear=True):
                self.assertEqual(config.load(p).write_allow_courses, [])
            for invalid in ('"测试课程"', '["测试课程", 123]', '[""]', 'true'):
                p.write_text('write_allow_courses = ' + invalid + '\n')
                with self.subTest(invalid=invalid), patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
                    config.load(p)

    def test_target_id_must_identify_exactly_one_row(self):
        rows = [{"id":"1", "other":"one", "title":"甲"}, {"id":"2", "other":"two", "title":"乙"}]
        self.assertEqual(_best(rows, "1", id_keys=("id", "other"))["title"], "甲")
        self.assertEqual(_best([{"id":"1", "other":"1", "title":"甲"}], "1", id_keys=("id", "other"))["title"], "甲")
        for bad in ([{"id":"1", "title":"甲"}, {"id":"1", "title":"乙"}],
                    [{"id":"1", "title":"甲"}, {"other":"1", "title":"乙"}]):
            with self.subTest(rows=bad), self.assertRaises(XxtError):
                _best(bad, "1", id_keys=("id", "other"))
        with self.assertRaises(XxtError): _best([{"id":None, "title":"甲"}], "None")

    def test_write_tool_without_confirmation_cannot_register(self):
        def unsafe_tool(course): return {"ok": True}
        for kind in (server.W, server.D):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                server._wrap(unsafe_tool, kind)
        for name, kind, _, fn in server.TOOLS:
            if kind in (server.W, server.D):
                self.assertIn("confirm", __import__("inspect").signature(fn).parameters, name)

    def test_notice_preview_is_complete_but_has_no_executable_plan(self):
        wrapped = server._wrap(server.publish_notice, server.W)
        body = "甲" * 501 + "末尾"
        preview = wrapped(course="测试课程", title="测试", content=body)
        self.assertEqual(preview["details"]["content"], body)
        self.assertTrue(preview["preview_only"])
        self.assertNotIn("plan_id", preview)
        self.assertFalse(wrapped(course="测试课程", title="测试", content=body, confirm=True)["ok"])
        self.assertEqual(self.fake.calls, [])

    def test_executable_plan_matches_exact_content_once(self):
        def fake_publish(course, title, content, confirm=False):
            if not confirm:
                return server._dry(self.fake.c, "测试", title=title, content=content)
            self.fake.calls.append((course, title, content))
            return {"ok": True}
        wrapped = server._wrap(fake_publish, server.W)
        body = "甲" * 501 + "末尾"
        preview = wrapped(course="测试课程", title="测试", content=body)
        self.assertFalse(wrapped(course="测试课程", title="测试", content=body + " ", confirm=True, plan_id=preview["plan_id"])["ok"])
        self.assertFalse(self.fake.calls)
        preview = wrapped(course="测试课程", title="测试", content=body)
        self.assertTrue(wrapped(course="测试课程", title="测试", content=body, confirm=True, plan_id=preview["plan_id"])["ok"])
        self.assertEqual(self.fake.calls[0][-1], body)
        self.assertFalse(wrapped(course="测试课程", title="测试", content=body, confirm=True, plan_id=preview["plan_id"])["ok"])

    def test_failed_execution_warns_to_check_state_without_retry(self):
        for failure in ("return", "exception"):
            calls = []
            def fake_write(course, confirm=False):
                if not confirm: return server._dry(self.fake.c, "测试")
                calls.append(course)
                if failure == "exception": raise BskError("timeout", "unknown", {"effect_state":"unknown"})
                return {"ok":False, "error":"结果尚未出现"}
            wrapped = server._wrap(fake_write, server.W)
            preview = wrapped(course="测试课程")
            result = wrapped(course="测试课程", confirm=True, plan_id=preview["plan_id"])
            self.assertFalse(result["ok"])
            self.assertEqual(result["write_outcome"], "unknown")
            self.assertIn("先", result["hint"])
            self.assertEqual(calls, [F.NUMERIC_004])
            self.assertFalse(wrapped(course="测试课程", confirm=True, plan_id=preview["plan_id"])["ok"])
            self.assertEqual(calls, [F.NUMERIC_004])

    def test_error_reporting_does_not_reinitialize_client(self):
        server._state["client"] = None
        with patch.object(server, "client", side_effect=AssertionError("do not initialize")):
            result = server._err(RuntimeError("test failure"))
        self.assertFalse(result["ok"])
        self.assertIn("RuntimeError", result["error"])

    def test_assignment_reminder_is_preview_only_with_recipient_identity(self):
        self.fake.submissions = lambda *_: {"id":"a1", "assignment":"作业", "unsubmitted":[{"name":"示例学生", "person_id":F.CONTROL_022}]}
        self.fake.remind_assignment = lambda *a: self.fake.calls.append(("remind", a))
        wrapped = server._wrap(server.remind_assignment, server.W)
        preview = wrapped(course="测试课程", assignment="作业")
        self.assertTrue(preview["preview_only"])
        self.assertEqual(preview["details"]["unsubmitted"], [{"name":"示例学生", "person_id":F.CONTROL_022}])
        self.assertNotIn("plan_id", preview)
        self.assertFalse(wrapped(course="测试课程", assignment="作业", confirm=True)["ok"])
        self.assertEqual(self.fake.calls, [])

    def test_assignment_requires_class_and_is_preview_only(self):
        wrapped = server._wrap(server.create_assignment, server.W)
        self.assertFalse(wrapped(course="测试课程", title="作业")["ok"])
        p = wrapped(course="测试课程", title="作业", class_name="甲班")
        self.assertEqual(p["details"]["classes"], [{"id": F.NUMERIC_001, "name": "甲班"}])
        self.assertTrue(p["preview_only"])
        self.assertNotIn("plan_id", p)
        self.assertFalse(wrapped(course="测试课程", title="作业", class_name="甲班", confirm=True)["ok"])
        self.assertEqual(self.fake.calls, [])

    def test_exam_requires_class_and_is_preview_only(self):
        wrapped = server._wrap(server.publish_exam, server.W)
        self.assertFalse(wrapped(course="测试课程", paper="卷一")["ok"])
        p = wrapped(course="测试课程", paper="卷一", class_name="乙班")
        self.assertEqual(p["details"]["classes"], [{"id": F.NUMERIC_002, "name": "乙班"}])
        self.assertTrue(p["preview_only"])
        self.assertNotIn("plan_id", p)
        self.assertFalse(wrapped(course="测试课程", paper="卷一", class_name="乙班", confirm=True)["ok"])
        self.assertEqual(self.fake.calls, [])

    def test_publish_assignment_requires_class_and_is_preview_only(self):
        wrapped = server._wrap(server.publish_assignment, server.W)
        args = {"course": "测试课程", "library_id": "55", "title": "作业"}
        self.assertFalse(wrapped(**args)["ok"])
        p = wrapped(**args, class_name="甲班")
        self.assertEqual(p["details"]["classes"], [{"id": F.NUMERIC_001, "name": "甲班"}])
        self.assertTrue(p["preview_only"])
        self.assertNotIn("plan_id", p)
        self.assertFalse(wrapped(**args, class_name="甲班", confirm=True)["ok"])
        self.assertEqual(self.fake.calls, [])

    def test_create_exam_is_preview_only(self):
        self.fake.create_exam = lambda *a: self.fake.calls.append(("create_exam", a))
        wrapped = server._wrap(server.create_exam, server.W)
        args = {"course":"测试课程", "title":"卷", "questions":[{"type":"判断", "stem":"题", "answer":"对"}]}
        p = wrapped(**args)
        self.assertTrue(p["preview_only"])
        self.assertEqual(p["details"]["questions"][0]["stem"], "题")
        self.assertNotIn("plan_id", p)
        self.assertFalse(wrapped(**args, confirm=True)["ok"])
        self.assertEqual(self.fake.calls, [])

    def test_lower_level_refuses_empty_class_selection(self):
        with self.assertRaises(XxtError):
            XxtBase._select_classes_js(self.fake, self.fake.c, None)

    def test_activity_previews_require_and_freeze_one_class(self):
        cases = [(server.pick_student, {"course":"测试课程", "title":"选人"}),
                 (server.start_quick_answer, {"course":"测试课程", "content":"抢答"}),
                 (server.start_vote, {"course":"测试课程", "content":"投票"})]
        for fn, args in cases:
            with self.subTest(tool=fn.__name__):
                wrapped = server._wrap(fn, server.W)
                self.assertFalse(wrapped(**args)["ok"])
                preview = wrapped(**args, class_name="甲班")
                self.assertEqual(preview["details"]["classes"], [{"id":F.NUMERIC_001, "name":"甲班"}])
                result = wrapped(**args, class_name="甲班", confirm=True, plan_id=preview["plan_id"])
                self.assertTrue(result["ok"])
                self.assertEqual(self.fake.calls[-1][1][-1], F.NUMERIC_001)

    def test_activity_validation_and_location_is_preview_only(self):
        checkin = server._wrap(server.start_checkin, server.W)
        loc = checkin(course="测试课程", class_name="甲班", sign_type="位置", address="学校")
        self.assertTrue(loc["preview_only"])
        self.assertNotIn("plan_id", loc)
        self.assertFalse(checkin(course="测试课程", class_name="甲班", sign_type="位置", address="学校", confirm=True)["ok"])
        self.assertFalse(checkin(course="测试课程", class_name="甲班", sign_type="签到码", code="12")["ok"])
        p = checkin(course="测试课程", class_name="甲班", sign_type="手势", gesture="1a234")
        self.assertEqual(p["details"]["gesture"], "1234")
        self.assertTrue(p["preview_only"])
        self.assertNotIn("plan_id", p)
        self.assertFalse(checkin(course="测试课程", class_name="甲班", sign_type="手势", gesture="1a234", confirm=True)["ok"])
        self.assertFalse(server._wrap(server.pick_student, server.W)(course="测试课程", class_name="甲班", count=0)["ok"])
        self.assertFalse(server._wrap(server.start_vote, server.W)(course="测试课程", class_name="甲班", content="x", options=F.CONTROL_019)["ok"])
        self.assertEqual(self.fake.calls, [])

    def test_activity_class_revalidates_and_keeps_cached_default(self):
        original = Course(id="1", name="test", cpi="2", clazz_id=F.NUMERIC_001,
                          classes=[{"clazz_id":F.NUMERIC_001, "name":"甲"}, {"clazz_id":F.NUMERIC_002, "name":"乙"}])
        class FakeActivity:
            def ctx(self, course, refresh=False):
                self.refreshed = refresh
                return original
        client = FakeActivity()
        selected = ActivityOps._activity_class(client, "1", F.NUMERIC_002)
        self.assertTrue(client.refreshed)
        self.assertEqual(selected.clazz_id, F.NUMERIC_002)
        self.assertEqual(original.clazz_id, F.NUMERIC_001)
        with self.assertRaises(XxtError): ActivityOps._activity_class(client, "1", "")
        with self.assertRaises(XxtError): ActivityOps._activity_class(client, "1", "999")
        original.classes.append({"clazz_id":F.NUMERIC_002, "name":"重复"})
        with self.assertRaises(XxtError): ActivityOps._activity_class(client, "1", F.NUMERIC_002)

    def test_course_context_uses_current_controlled_tab_and_stops_on_denial(self):
        course = Course(id="123", name="测试课程", cpi="456")
        class Browser:
            navigations = []
            denied = False
            def navigate(self, url, **_kw):
                self.navigations.append(url)
                if self.denied:
                    raise BskError("permission_denied", "denied", {"effect_state":"none"})
                return f'https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/tch?courseid=123&clazzId={F.NUMERIC_003}&cpi=456&enc=fake&t=1'
            def href(self): raise AssertionError("no fallback needed")
        class Client:
            b = Browser()
            cfg = SimpleNamespace(course_ctx_ttl=60)
            def course(self, _): return course
            def on(self, *_): return [{"clazz_id":F.NUMERIC_003, "name":"测试班"}]
        client = Client()
        selected = XxtBase.ctx(client, "测试课程", refresh=True)
        self.assertEqual(selected.clazz_id, F.NUMERIC_003)
        self.assertEqual(len(client.b.navigations), 1)
        self.assertIn("courseId=123", client.b.navigations[0])
        self.assertEqual(selected.classes, [{"clazz_id":F.NUMERIC_003, "name":"测试班"}])
        client.b.denied = True
        with self.assertRaises(BskError): XxtBase.ctx(client, "测试课程", refresh=True)
        self.assertEqual(len(client.b.navigations), 2)
        self.assertEqual(course.classes, [])
        self.assertEqual(course.enc, "")

    def test_activity_listing_and_verification_use_bound_class(self):
        course = Course(id="1", name="test", cpi="2", clazz_id=F.NUMERIC_001,
                        classes=[{"clazz_id":F.NUMERIC_001, "name":"甲"}, {"clazz_id":F.NUMERIC_002, "name":"乙"}])
        class FakeActivity:
            fid = "3"
            b = SimpleNamespace(href=lambda: "")
            def ctx(self, _): return course
            def on(self, host, body):
                self.body = body
                return {"valid":True, "items":[]}
            def activities(self, _course, limit=30, *, class_id=""):
                self.seen_class = class_id
                return [{"activity_id":"9", "title":"new", "status_name":"进行中"}]
        client = FakeActivity()
        self.assertEqual(ActivityOps.activities(client, "1", class_id=F.NUMERIC_002), [])
        self.assertIn(f'classId={F.NUMERIC_002}', client.body)
        self.assertEqual(course.clazz_id, F.NUMERIC_001)
        with self.assertRaises(XxtError): ActivityOps.activities(client, "1", class_id="999")
        with patch("xuexitong_mcp.ops_activity.time.sleep"):
            info = ActivityOps._started(client, Course(id="1", name="test", cpi="2", clazz_id=F.NUMERIC_002), "new", set())
        self.assertEqual(info["activity_id"], "9")
        self.assertEqual(client.seen_class, F.NUMERIC_002)

    def test_activity_started_must_match_new_class_scoped_record(self):
        class Fake:
            b = SimpleNamespace(href=lambda: "https://example.invalid/page?activeId=9")
            rows = []
            def activities(self, _course, limit=30, *, class_id=""):
                self.seen = (limit, class_id)
                return self.rows
        client = Fake()
        course = Course(id="1", name="test", cpi="2", clazz_id=F.NUMERIC_002)
        with patch("xuexitong_mcp.ops_activity.time.sleep"):
            for bad in ([], [{"activity_id":"9", "title":"旧标题", "status_name":"进行中"}],
                        [{"activity_id":"10", "title":"新标题", "status_name":"进行中"}]):
                client.rows = bad
                with self.subTest(rows=bad), self.assertRaises(XxtError):
                    ActivityOps._started(client, course, "新标题", set())
            client.rows = [{"activity_id":"9", "title":"新标题", "status_name":"进行中"}]
            with self.assertRaises(XxtError):
                ActivityOps._started(client, course, "新标题", {"9"})
            self.assertEqual(ActivityOps._started(client, course, "新标题", set())["activity_id"], "9")
            self.assertEqual(client.seen, (1000, F.NUMERIC_002))
            client.b = SimpleNamespace(href=lambda: "")
            client.rows.append({"activity_id":"10", "title":"新标题", "status_name":"进行中"})
            with self.assertRaises(XxtError):
                ActivityOps._started(client, course, "新标题", set())

    def test_activity_menu_uses_guarded_clicks_and_stops_on_denial(self):
        class FakeBrowser:
            calls = []
            denied = False
            def navigate(self, *a, **kw): self.calls.append("navigate")
            def click_selector(self, selector, **kw):
                self.calls.append(("selector", selector))
                if self.denied:
                    raise BskError("permission_denied", "covered", {"effect_state":"none"})
            def click_label(self, pattern, **kw): self.calls.append(("label", pattern))
        class FakeActivity:
            b = FakeBrowser()
            def _act_list_url(self, _): return "https://example.invalid/list"
            def wait_for(self, *a, **kw): return True
            def here(self, body):
                self.assert_guard = body
                return True
        client = FakeActivity()
        ActivityOps._open_add_activity(client, object(), "签到")
        self.assertEqual(client.b.calls[1], ("selector", ".add-activate-icon"))
        self.assertIn("签到", client.b.calls[2][1])
        self.assertNotIn(".click(", client.assert_guard)
        client.b.calls = []
        client.b.denied = True
        with self.assertRaises(BskError): ActivityOps._open_add_activity(client, object(), "签到")
        self.assertEqual(client.b.calls, ["navigate", ("selector", ".add-activate-icon")])

    def test_pick_student_retains_created_activity_when_selection_denied(self):
        class Browser:
            calls = []
            def fill_label(self, *a, **kw): self.calls.append("fill")
            def click_label(self, pattern, **kw):
                self.calls.append(pattern)
                if "开始选人" in pattern:
                    raise BskError("permission_denied", "not permitted", {"effect_state":"none"})
        class Activity:
            b = Browser()
            def _activity_class(self, *_): return SimpleNamespace(id="1", clazz_id="2")
            def activities(self, *_a, **_kw): return []
            def _open_add_activity(self, *_): pass
            def _started(self, *_): return {"activity_id":"5", "status":"进行中"}
            def here(self, *_): raise AssertionError("do not read after denied selection")
        client = Activity()
        got = ActivityOps.pick_student(client, "测试课程", "选人", 1, "2")
        self.assertFalse(got["ok"])
        self.assertTrue(got["activity_created"])
        self.assertEqual(got["activity_id"], "5")
        self.assertIsNone(got["picked"])
        self.assertEqual(len(client.b.calls), 3)
        self.assertIn("不要重复", got["error"])

    def test_inbox_errors_do_not_become_empty_results(self):
        class Inbox:
            result = None
            def on(self, *_): return self.result
        client = Inbox()
        for bad in (None, {}, {"valid":False}, {"valid":True,"items":None}):
            client.result = bad
            with self.subTest(bad=bad), self.assertRaises(XxtError):
                ActivityOps.inbox(client)
        client.result = {"valid":True,"items":[{"id":"1","read":False},{"id":"2","read":True}]}
        self.assertEqual(ActivityOps.inbox(client, unread_only=True), [{"id":"1","read":False}])

    def test_discussion_response_errors_are_not_empty_lists(self):
        class Topics:
            result = None
            def ctx(self, _): return SimpleNamespace(id="1")
            def _bbsid(self, _): return "abc"
            def on(self, *_): return self.result
        client = Topics()
        for bad in (None, {}, {"valid":False}, {"valid":True,"items":None}):
            client.result = bad
            with self.subTest(bad=bad), self.assertRaises(XxtError):
                ContentOps.topics(client, "测试课程")
        client.result = {"valid":True,"items":[{"topic_id":"a", "title":"标题"}]}
        self.assertEqual(ContentOps.topics(client, "测试课程"), [{"topic_id":"a", "title":"标题"}])

    def test_read_page_refuses_disallowed_current_url_without_navigation(self):
        class Browser:
            def href(self): return "https://example.invalid/"
            def navigate(self, *_a, **_kw): raise AssertionError("must not navigate")
        class Reader:
            b = Browser()
            def here(self, *_): raise AssertionError("must not read")
        with self.assertRaises(XxtError): ActivityOps.read_page(Reader())

    def test_end_activity_binds_class_and_refuses_changed_status(self):
        self.fake._activity_class = lambda course, class_id: SimpleNamespace(id=course, clazz_id=class_id)
        self.fake._find_activity = lambda c, _: {"activity_id":"a1", "title":"活动", "type":"签到", "status":"1", "status_name":"进行中"}
        self.fake.end_activity = lambda *a: self.fake.calls.append(("end", a)) or {"ok":True}
        wrapped = server._wrap(server.end_activity, server.W)
        self.assertFalse(wrapped(course="测试课程", activity="活动")["ok"])
        p = wrapped(course="测试课程", activity="活动", class_name="甲班")
        self.assertEqual(p["details"]["classes"], [{"id":F.NUMERIC_001, "name":"甲班"}])
        self.assertTrue(wrapped(course="测试课程", activity="活动", class_name="甲班", confirm=True, plan_id=p["plan_id"])["ok"])
        self.assertEqual(self.fake.calls[-1][1], (F.NUMERIC_004, "a1", F.NUMERIC_001))
        self.fake._find_activity = lambda c, _: {"activity_id":"a1", "title":"活动", "type":"签到", "status":"2", "status_name":"已结束"}
        self.assertFalse(wrapped(course="测试课程", activity="活动", class_name="甲班")["ok"])

        class FakeEnd:
            b = SimpleNamespace(navigate=lambda *a, **kw: self.fail("must not navigate"))
            def _activity_class(self, *a): return SimpleNamespace(id="1", clazz_id=F.NUMERIC_001)
            def _find_activity(self, *a): return {"status":"2", "status_name":"已结束"}
        with self.assertRaises(XxtError): ActivityOps.end_activity(FakeEnd(), "1", "a1", F.NUMERIC_001)

    def test_delete_activity_is_preview_only_and_class_scoped(self):
        self.fake._activity_class = lambda course, class_id: SimpleNamespace(id=course, clazz_id=class_id)
        self.fake._find_activity = lambda c, _: {"activity_id":"a1", "title":"活动", "type":"签到", "status":"2", "status_name":"已结束"}
        self.fake.delete_activity = lambda *a: self.fake.calls.append(("delete", a))
        wrapped = server._wrap(server.delete_activity, server.D)
        preview = wrapped(course="测试课程", activity="活动", class_name="乙班")
        self.assertTrue(preview["preview_only"])
        self.assertEqual(preview["details"]["classes"], [{"id":F.NUMERIC_002, "name":"乙班"}])
        self.assertNotIn("plan_id", preview)
        self.assertFalse(wrapped(course="测试课程", activity="活动", class_name="乙班", confirm=True)["ok"])
        self.assertEqual(self.fake.calls, [])

    def test_discussion_previews_complete_effective_content(self):
        wrapped = server._wrap(server.create_discussion, server.W)
        draft = wrapped(course="测试课程", title="标题")
        self.assertEqual(draft["details"]["content"], "标题")
        self.assertTrue(draft["preview_only"])
        self.assertNotIn("plan_id", draft)
        body = "内容" * 300
        self.assertEqual(wrapped(course="测试课程", title="标题", content=body)["details"]["content"], body)
        self.fake.topics = lambda *_: [{"topic_id": "t1", "title": "标题"}]
        self.fake.delete_topic = lambda *a: self.fake.calls.append(("delete", a))
        deleted = server._wrap(server.delete_discussion, server.D)
        draft = deleted(course="测试课程", topic="标题")
        self.assertTrue(draft["preview_only"])
        self.assertNotIn("plan_id", draft)
        self.assertFalse(deleted(course="测试课程", topic="标题", confirm=True)["ok"])
        self.assertFalse(wrapped(course="测试课程", title="标题", confirm=True)["ok"])
        self.assertEqual(self.fake.calls, [])

    def test_health_reports_false_for_login_or_language_failure(self):
        class FakeBrowser:
            session = F.CONTROL_013
            tab = F.CONTROL_013
            def doctor(self): return [{"name": F.CONTROL_013, "ok": True}]
            def ensure_session(self, **kwargs): pass
            def navigate(self, *a, **kw): pass

        class HealthFake:
            b = FakeBrowser()
            fid = F.CONTROL_013
            logged_in = True
            language = "我教的课"
            def on(self, *a, **kw): return {"ok": self.logged_in}
            def here(self, query):
                return {"guard": True, "lang": "zh-CN"} if "navigator.language" in query else self.language
            def courses(self, refresh=False): return [F.CONTROL_013]

        fake = HealthFake()
        self.assertTrue(ActivityOps.health(fake)["ok"])
        fake.logged_in = False
        self.assertFalse(ActivityOps.health(fake)["ok"])
        fake.logged_in = True
        fake.language = "Teaching"
        self.assertFalse(ActivityOps.health(fake)["ok"])

    def test_health_surfaces_permission_error_without_retry(self):
        class Browser:
            session = None
            tab = None
            calls = 0
            def doctor(self): return [{"name":F.CONTROL_013, "ok":True}]
            def ensure_session(self, **kwargs):
                self.calls += 1
                raise BskError("permission_denied", "No observable document", {"reason":"not_observable", "effect_state":"none", "secret":"must-not-leak"})
        class Client:
            b = Browser()
        client = Client()
        result = ActivityOps.health(client)
        self.assertFalse(result["ok"])
        self.assertIn("permission_denied", result["error"])
        self.assertEqual(result["browser_error"], {"reason":"not_observable", "effect_state":"none", "health_step":"session"})
        self.assertEqual(client.b.calls, 1)

    def test_output_redacts_urls_and_nested_temporary_parameters(self):
        def fake_read():
            return {"url": "https://example.test/page?rbtoken=FAKESECRET&course=1",
                    "text": "details https://example.test/link%3Ftoken%3DFAKESECRET%26x%3D1",
                    "nested": [{"error": "rbtoken=FAKESECRET failure", "rbtoken": "FAKESECRET"}]}
        result = server._wrap(fake_read, server.R)()
        self.assertNotIn("FAKESECRET", str(result))
        self.assertIn("https://example.test/page?[参数已隐藏]", result["url"])

    def test_redaction_preserves_write_preview_exact_content(self):
        text = "请阅读 https://example.test/?chapter=1"
        result = server._wrap(server.publish_notice, server.W)(course="测试课程", title="提示", content=text)
        self.assertEqual(result["details"]["content"], text)

    def test_log_filter_removes_tokens_from_formatted_messages(self):
        record = logging.LogRecord("test", logging.ERROR, __file__, 1,
                                   "failure %s", ("rbtoken=FAKESECRET",), None)
        self.assertTrue(_RedactLogFilter().filter(record))
        self.assertNotIn("FAKESECRET", record.getMessage())
        self.assertNotIn("FAKESECRET", redact_text("https://example.test/x?rbtoken=FAKESECRET"))
        self.assertNotIn("FAKESECRET", redact_text('{"rbtoken":"FAKESECRET"}'))

    def test_library_tool_is_read_only_and_preserves_pagination(self):
        result = server._wrap(server.list_assignment_library, server.R)(course="测试课程")
        self.assertTrue(result["has_more"])
        self.assertFalse(result["complete"])
        self.assertEqual(self.fake.calls, [("library_read", ("测试课程",))])
        self.assertIn("list_assignment_library", [x[0] for x in server.TOOLS])

    def test_permission_denial_does_not_retry_sync_or_action(self):
        class Denied:
            calls = 0
            def ensure_session(self): pass
            def sync(self, *_): return (F.CONTROL_012, F.CONTROL_017)
            def run(self, *a, **kw):
                self.calls += 1
                raise BskError("permission_denied", "not dispatched", {"effect_state":"none"})
        client = Denied()
        with self.assertRaises(BskError):
            Bsk.sync(client)
        self.assertEqual(client.calls, 1)
        client.calls = 0
        with self.assertRaises(BskError):
            Bsk._act(client, lambda c, o: ["read"], retry_safe=True, need_obs=True)
        self.assertEqual(client.calls, 1)

    def test_mcp_permission_denial_preserves_reason_and_does_not_advise_retry(self):
        def fake_read():
            raise BskError("permission_denied", "Page changed", {"reason":"cooperation_sync_required", "effect_state":"none", "secret":"not-output"})
        result = server._wrap(fake_read, server.R)()
        self.assertFalse(result["ok"])
        self.assertEqual(result["browser_error"], {"reason":"cooperation_sync_required", "effect_state":"none"})
        self.assertIn("停止自动重试", result["hint"])
        self.assertNotIn("not-output", str(result))

    def test_permission_denial_stage_diagnostics_never_retry_or_leak_arguments(self):
        class Fake:
            def __init__(self, fail_at):
                self.fail_at = fail_at
                self.calls = []
            def sync(self, *_):
                self.calls.append("sync")
                if self.fail_at == "sync":
                    raise BskError("permission_denied", "changed", {"reason": "document_changed", "effect_state": "none"})
                return F.CONTROL_012, F.CONTROL_017
            def run(self, args, **_kw):
                self.calls.append("dispatch")
                raise BskError("permission_denied", "changed", {"reason": "document_changed", "effect_state": "none"})

        for stage in ("sync", "dispatch"):
            fake = Fake(stage)
            with self.assertRaises(BskError) as caught:
                Bsk._act(fake, lambda *_: ["navigate", "https://example.invalid/?token=SECRET"], retry_safe=True, need_obs=True)
            result = server._err(caught.exception)
            self.assertEqual(result["browser_error"]["stage"], stage)
            self.assertEqual(fake.calls, ["sync"] if stage == "sync" else ["sync", "dispatch"])
            if stage == "dispatch":
                self.assertEqual(result["browser_error"]["operation"], "navigate")
            self.assertNotIn("SECRET", str(result))

    def test_semantic_diagnostic_keeps_only_fixed_labels_and_preserves_denial(self):
        data = {"version": 1, "available": True, "comparison": "whole_page_signature", "same_signature": False,
                "truncated": False, "changes": [{"bucket": "nodes", "kind": "changed", "frame": "frame_1",
                "row": 2, "fields": ["name", "text"], "before": "PRIVATE", "node_id": "PRIVATE"}],
                "url": "https://example.invalid/?token=PRIVATE"}
        result = server._err(BskError("permission_denied", "changed", {"reason": "observation_changed",
                             "effect_state": "none", "semantic_diff": data}))
        self.assertFalse(result["ok"])
        self.assertEqual(result["browser_error"]["effect_state"], "none")
        self.assertEqual(result["browser_error"]["semantic_diff"]["changes"][0]["fields"], ["name", "text"])
        self.assertNotIn("PRIVATE", str(result))
        self.assertIn("停止自动重试", result["hint"])

    def test_semantic_diagnostic_rejects_free_text_and_bounds_output(self):
        from xuexitong_mcp.privacy import safe_semantic_diff
        row = {"bucket": "nodes", "kind": "changed", "frame": "frame_1", "row": 1, "fields": ["value"]}
        good = {"version": 1, "available": True, "comparison": "whole_page_signature", "same_signature": False,
                "truncated": False, "changes": [row] * 30}
        limited = safe_semantic_diff(good)
        self.assertEqual(len(limited["changes"]), 16)
        self.assertTrue(limited["truncated"])
        for change in [{**row, "fields": ["PRIVATE"]}, {**row, "frame": "PRIVATE"}, {**row, "row": True},
                       {**row, "bucket": []}, {**row, "kind": {}}, {**row, "fields": [[]]}]:
            self.assertIsNone(safe_semantic_diff({**good, "changes": [change]}))
        self.assertIsNone(safe_semantic_diff({"version": True, "available": False, "reason": "PRIVATE"}))
        self.assertIsNone(safe_semantic_diff({"version": 1, "available": False, "reason": []}))
        self.assertEqual(safe_semantic_diff({"version": 1, "available": False, "reason": "capture_missing", "secret": "PRIVATE"}),
                         {"version": 1, "available": False, "reason": "capture_missing"})

    def test_course_query_first_navigates_to_list_and_stops_on_denial(self):
        class Browser:
            _act = Bsk._act
            navigate = Bsk.navigate
            def __init__(self):
                self.cfg = SimpleNamespace(t_navigate=40)
                self.calls = []
            def sync(self, *_):
                self.calls.append(("sync",))
                return F.CONTROL_012, F.CONTROL_017
            def run(self, args, **_kw):
                self.calls.append(tuple(args))
                raise BskError("permission_denied", "changed", {"reason": "document_changed", "effect_state": "none"})
        browser = Browser()
        candidate = XxtBase(SimpleNamespace(fid="", course_list_ttl=600), bsk=browser)
        server._state["client"] = candidate
        result = server._wrap(server.list_courses, server.R)(keyword="测试课程")
        self.assertFalse(result["ok"])
        self.assertEqual(result["browser_error"]["stage"], "dispatch")
        self.assertEqual(result["browser_error"]["operation"], "navigate")
        self.assertEqual(len(browser.calls), 2)
        self.assertEqual(browser.calls[0], ("sync",))
        self.assertEqual(browser.calls[1][0:2], (
            "navigate",
            "https://mooc2-ans.chaoxing.com/mooc2-ans/visit/interaction?moocDomain=https://mooc1-1.chaoxing.com/mooc-ans"))
        self.assertIn("--context", browser.calls[1])
        self.assertIn("--observation", browser.calls[1])

    def test_sync_not_ready_or_missing_receipt_stops_without_action(self):
        class SyncFake:
            calls = 0
            def ensure_session(self): pass
            def run(self, *_args, **_kwargs):
                self.calls += 1
                return {"ready": False, "context_id": F.CONTROL_024, "observation_id": F.CONTROL_024}
        sync_fake = SyncFake()
        with self.assertRaises(BskError) as caught:
            Bsk.sync(sync_fake)
        self.assertEqual(caught.exception.code, "control_not_ready")
        self.assertEqual(sync_fake.calls, 1)
        self.assertIn("已停止操作", server._err(caught.exception)["hint"])

        class ActionFake:
            calls = []
            def sync(self, *_args): return F.CONTROL_012, None
            def run(self, *_args, **_kwargs): self.calls.append("dispatch")
        action_fake = ActionFake()
        with self.assertRaises(BskError) as caught:
            Bsk._act(action_fake, lambda *_: ["navigate", "https://example.invalid"], retry_safe=True, need_obs=True)
        self.assertEqual(caught.exception.code, "sync_incomplete")
        self.assertEqual(action_fake.calls, [])
        self.assertIn("勿自动重试", server._err(caught.exception)["hint"])

    def test_incremental_or_failed_sync_never_reuses_old_observation_text(self):
        class Fake:
            obs_text = ""
            tab = None
            def __init__(self):
                self.replies = [
                    {"state":{"mode":"ready"}, "context_id": F.CONTROL_009, "observation_id": F.CONTROL_014, "observation": {"text": '@e1 button "旧按钮"'}},
                    {"state":{"mode":"ready"}, "context_id": F.CONTROL_010, "observation_id": F.CONTROL_015, "changes": []},
                    {"state":{"mode":"ready"}, "context_id": F.CONTROL_011, "observation_id": F.CONTROL_016, "observation": {"text": "部分文本", "truncated": True}},
                    BskError("permission_denied", "changed", {"effect_state": "none"}),
                ]
            def ensure_session(self): pass
            def run(self, *_args, **_kwargs):
                item = self.replies.pop(0)
                if isinstance(item, Exception): raise item
                return item
        fake = Fake()
        Bsk.sync(fake)
        self.assertIn("旧按钮", fake.obs_text)
        Bsk.sync(fake)
        self.assertEqual(fake.obs_text, "")
        Bsk.sync(fake)
        self.assertEqual(fake.obs_text, "")
        fake.obs_text = '@e1 button "旧按钮"'
        with self.assertRaises(BskError): Bsk.sync(fake)
        self.assertEqual(fake.obs_text, "")

    def test_ref_action_does_not_use_stale_text_on_incremental_receipt(self):
        class Fake:
            obs_text = ""
            calls = []
            def sync(self): return F.CONTROL_012, F.CONTROL_017
            def find_ref(self, *_args, **_kwargs): raise AssertionError("must not use absent observation")
            def run(self, *_args, **_kwargs): self.calls.append("dispatch")
        fake = Fake()
        with self.assertRaises(BskError) as caught:
            Bsk._ref_action(fake, "click", "旧按钮", [], retry_safe=False)
        self.assertEqual(caught.exception.code, "observation_unavailable")
        self.assertEqual(fake.calls, [])

    def test_passive_observe_uses_sync_context_and_rejects_partial_results(self):
        class Fake:
            tab = 123
            obs_text = ""
            calls = []
            response = {"tab_id": 123, "text": "当前页面", "truncated": False}
            def sync(self):
                self.obs_text = ""
                return "current-ctx", "strict-obs"
            def run(self, args):
                self.calls.append(args)
                return self.response
        fake = Fake()
        self.assertEqual(Bsk.observe(fake), "当前页面")
        self.assertEqual(fake.calls, [["observe", "--tab-id", "123", "--context", "current-ctx"]])
        self.assertEqual(fake.obs_text, "")  # not a strict-action baseline
        for changes in ({"truncated": True}, {"tab_id": 456}, {"next_cursor": "next"}, {"text": ""}, {"truncated": None}):
            fake.response = {"tab_id": 123, "text": "当前页面", "truncated": False, **changes}
            with self.assertRaises(BskError): Bsk.observe(fake)

    def test_bsk_session_is_pinned_to_local_browser_and_missing_profile_fails_closed(self):
        class Fake:
            log = logging.getLogger("test")
            session = None
            tab = None
            browsers = []
            starts = []
            created = 0
            def run(self, args, **kwargs):
                if args == ["browsers"]: return {"value": self.browsers}
                self.starts.append(args)
                return {"session_id":F.CONTROL_013, "browser_instance_id":FIXED_BROWSER_INSTANCE}
            def _initialize_owned_tab(self): self.created += 1
        client = Fake()
        with self.assertRaises(BskError): Bsk.start_session(client)
        self.assertEqual(client.starts, [])
        client.browsers = [{"instance_id":F.CONTROL_019}]
        with self.assertRaises(BskError): Bsk.start_session(client)
        self.assertEqual(client.starts, [])
        client.browsers = [{"instance_id":FIXED_BROWSER_INSTANCE, "unresponsive":True}]
        with self.assertRaises(BskError): Bsk.start_session(client)
        self.assertEqual(client.starts, [])
        client.browsers = [{"instance_id":FIXED_BROWSER_INSTANCE, "unresponsive":False}]
        Bsk.start_session(client)
        self.assertEqual(client.starts, [["session", "start", "--browser", FIXED_BROWSER_INSTANCE]])
        self.assertEqual(client.created, 1)

    def test_new_session_navigates_its_single_blank_tab_and_stops_on_refusal(self):
        class Fake:
            cfg = SimpleNamespace(t_navigate=40)
            tab = None
            obs_text = F.CONTROL_018
            url = ""
            saved = 0
            calls = []
            denied = False
            reached = "load"
            tabs = [{"tab_id":7,"url":"about:blank","scope":"agent"}]
            def run(self, args, **_kwargs):
                self.calls.append(args)
                if args[0:2] == ["tab","list"]: return {"tabs":self.tabs}
                if self.denied: raise BskError("permission_denied", "denied", {"effect_state":"none"})
                return {"tab_id":7,"final_url":FIXED_HOMEPAGE,"reached":self.reached}
            def _save_state(self): self.saved += 1
            def wait_readiness(self, course_name=None): self.anchor = course_name
        client = Fake()
        Bsk._initialize_owned_tab(client)
        self.assertEqual(client.calls[0], ["tab","list","--scope","agent"])
        self.assertEqual(client.calls[1], ["navigate",FIXED_HOMEPAGE,"--tab-id","7","--wait-until","load"])
        self.assertEqual((client.tab,client.url,client.saved), (7,FIXED_HOMEPAGE,1))
        client.calls=[];client.denied=True
        with self.assertRaises(BskError): Bsk._initialize_owned_tab(client)
        self.assertEqual(len(client.calls),2)
        self.assertEqual(client.saved,1)
        client.calls=[];client.denied=False;client.reached="domcontentloaded"
        with self.assertRaises(BskError) as caught: Bsk._initialize_owned_tab(client)
        self.assertEqual(caught.exception.code,"initial_load_incomplete")
        self.assertEqual(len(client.calls),2)
        self.assertEqual(client.saved,1)
        client.calls=[];client.tabs=[{"tab_id":7,"url":"about:blank"},{"tab_id":8,"url":"about:blank"}]
        with self.assertRaises(BskError): Bsk._initialize_owned_tab(client)
        self.assertEqual(len(client.calls),1)

    def test_existing_sessions_are_reused_only_for_fixed_profile(self):
        class Fake:
            def run(self, *_a, **_kw):
                return {"value":[{"session_id":F.CONTROL_023, "browser_instance_id":FIXED_BROWSER_INSTANCE},
                                 {"session_id":F.CONTROL_026, "browser_instance_id":F.CONTROL_019},
                                 {"session_id":F.CONTROL_025}]}
        self.assertEqual(Bsk._live_sessions(Fake()), [F.CONTROL_023])

    def test_permission_denial_stops_ref_action_and_session_recovery(self):
        class Denied:
            calls = 0
            recovered = 0
            obs_text = '@e1 button "read"'
            log = logging.getLogger("test")
            tab = 9
            def sync(self): return (F.CONTROL_012, F.CONTROL_017)
            def find_ref(self, *a, **kw): return "@e1"
            def run(self, *a, **kw):
                self.calls += 1
                raise BskError("permission_denied", "not dispatched", {"effect_state": "none"})
            def _new_tab(self):
                raise BskError("permission_denied", "not observable", {"effect_state": "none"})
            def recover_session(self): self.recovered += 1
            def eval(self, *_):
                raise BskError("permission_denied", "blocked")
        client = Denied()
        with self.assertRaises(BskError):
            Bsk._ref_action(client, "click", "read", [], retry_safe=True)
        self.assertEqual(client.calls, 1)
        with self.assertRaises(BskError):
            Bsk.recover_tab(client)
        self.assertEqual(client.recovered, 0)
        with self.assertRaises(BskError):
            Bsk.href(client)
        with self.assertRaises(BskError):
            Bsk._live_sessions(client)

    def test_denied_tab_selection_does_not_open_replacement(self):
        class DeniedSelection:
            session = None
            tab = None
            lock = __import__("threading").RLock()
            log = logging.getLogger("test")
            created = 0
            def _live_sessions(self): return ["existing"]
            def run(self, *a, **kw):
                raise BskError("permission_denied", "not observable", {"effect_state": "none"})
            def _new_tab(self): self.created += 1
            def start_session(self): self.created += 1
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "state.json"
            state.write_text('{"session":"existing","tab":9}')
            client = DeniedSelection()
            with patch("xuexitong_mcp.bsk.STATE_FILE", state):
                with self.assertRaises(BskError):
                    Bsk.ensure_session(client)
            self.assertEqual(client.created, 0)

    def test_denied_wait_and_course_context_stop_without_fallback(self):
        class DeniedWait:
            calls = 0
            def here(self, _):
                self.calls += 1
                raise BskError("permission_denied", "observation changed", {"effect_state": "none"})
        waiting = DeniedWait()
        with self.assertRaises(BskError):
            XxtBase.wait_for(waiting, "return true", timeout=2, interval=0)
        self.assertEqual(waiting.calls, 1)

        course = SimpleNamespace(id="1", name="test", cpi="2", enc=F.CONTROL_018, t=F.CONTROL_018,
                                 clazz_id=F.CONTROL_018, classes=[{"clazz_id": F.CONTROL_018}], ctx_time=123)
        class DeniedContext:
            cfg = SimpleNamespace(course_ctx_ttl=60)
            b = SimpleNamespace(navigate=lambda *a, **kw: "https://example.test/?clazzId=3")
            def course(self, _): return course
            def on(self, *a, **kw):
                raise BskError("permission_denied", "blocked", {"effect_state": "none"})
        with self.assertRaises(BskError):
            XxtBase.ctx(DeniedContext(), "test", refresh=True)
        self.assertEqual(course.classes, [])
        self.assertEqual(course.enc, "")
        self.assertEqual(course.ctx_time, 0)

    def test_chapter_list_rejects_unverified_empty_and_partial_results(self):
        class FakeChapters:
            response = None
            def course(self, _): return SimpleNamespace(id="1", cpi="2")
            def on(self, *a, **kw): return self.response
        client = FakeChapters()
        for response in (None, {}, {"__raw": "login page"}, {"data": None},
                         {"data": [], "success": False},
                         {"data": [{"id": 1, "title": "chapter", "children": {}}]},
                         {"data": [{"id": 1, "title": "a"}, {"id": 1, "title": "b"}]},
                         {"data": [{"id": None, "title": "chapter"}]},
                         {"data": [{"id": 1, "title": ""}]}):
            client.response = response
            with self.subTest(response=response), self.assertRaises(XxtError):
                CourseOps.chapters(client, "test")
        client.response = {"data": []}
        self.assertEqual(CourseOps.chapters(client, "test"), [])
        client.response = {"data": [{"id": 1, "title": "parent", "layer": 1,
                                      "children": [{"id": 2, "title": "child", "layer": 2}]}]}
        chapters = CourseOps.chapters(client, "test")
        self.assertEqual([(x["chapter_id"], x["number"], x["parent_id"]) for x in chapters],
                         [("1", "1", "0"), ("2", "1.1", "1")])

    def test_activity_list_rejects_failed_or_incomplete_response(self):
        class FakeActivities:
            fid = "3"
            response = None
            def ctx(self, _): return SimpleNamespace(id="1", clazz_id="2")
            def on(self, *a, **kw): return self.response
        client = FakeActivities()
        for response in (None, {}, {"valid": False, "items": []},
                         {"valid": True, "items": None}):
            client.response = response
            with self.subTest(response=response), self.assertRaises(XxtError):
                ActivityOps.activities(client, "test")
        client.response = {"valid": True, "items": []}
        self.assertEqual(ActivityOps.activities(client, "test"), [])
        client.response = {"valid": True, "items": [{"activity_id": "1", "title": "t",
                            "type": "通知", "active_type": 45, "status": "2"}]}
        rows = ActivityOps.activities(client, "test", status="已结束")
        self.assertEqual((len(rows), rows[0]["status_name"]), (1, "已结束"))

    def test_read_page_does_not_navigate_unverified_urls(self):
        class FakeBrowser:
            navigations = []
            def navigate(self, url, **kw): self.navigations.append(url)
            def href(self): return "https://mobilelearn.chaoxing.com/page/active/activeList"
        class FakePage:
            b = FakeBrowser()
            def here(self, _): return {"title": "current", "text": "visible"}
        page = FakePage()
        for url in ("https://mooc2-ans.chaoxing.com/safe-looking",
                    "https://mooc2-ans.chaoxing.com/ai-knowledge"):
            with self.subTest(url=url), self.assertRaises(XxtError):
                ActivityOps.read_page(page, url=url)
        self.assertEqual(page.b.navigations, [])
        self.assertEqual(ActivityOps.read_page(page)["text"], "visible")
        self.assertEqual(page.b.navigations, [])

    def test_upload_and_chapter_delete_remain_preview_only(self):
        self.fake.chapters = lambda *_: [{"chapter_id": "12", "number": "1", "title": "示例"},
                                        {"chapter_id": "13", "number": "1.1", "title": "子章节"}]
        self.fake.delete_chapter = lambda *a: self.fake.calls.append(("delete_chapter", a))
        self.fake.upload_material = lambda *a: self.fake.calls.append(("upload", a))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "approved.txt"
            path.write_text("preview", encoding="utf-8")
            server._state["cfg"].upload_allow_dirs = [d]
            upload = server._wrap(server.upload_material, server.W)
            draft = upload(course="测试课程", file_path=str(path))
            self.assertTrue(draft["dry_run"])
            self.assertTrue(draft["preview_only"])
            self.assertNotIn("plan_id", draft)
            self.assertEqual(draft["details"]["sha256"], __import__("hashlib").sha256(b"preview").hexdigest())
            path.write_text("changed", encoding="utf-8")
            changed = upload(course="测试课程", file_path=str(path))
            self.assertNotEqual(draft["details"]["sha256"], changed["details"]["sha256"])
            result = upload(course="测试课程", file_path=str(path), confirm=True)
            self.assertFalse(result["ok"])
            self.assertIn("暂仅支持预演", result["error"])
        delete = server._wrap(server.delete_chapter, server.D)
        draft = delete(course="测试课程", chapter="1")
        self.assertTrue(draft["dry_run"])
        self.assertTrue(draft["preview_only"])
        self.assertNotIn("plan_id", draft)
        self.assertEqual(draft["details"]["sub_chapters"], [{"id": "13", "number": "1.1", "title": "子章节"}])
        self.fake.chapters = lambda *_: [{"chapter_id": "12", "number": "1", "title": "示例"}]
        self.assertEqual(delete(course="测试课程", chapter="1")["details"]["sub_chapters"], [])
        result = delete(course="测试课程", chapter="1", confirm=True)
        self.assertFalse(result["ok"])
        self.assertIn("暂仅支持预演", result["error"])
        self.assertEqual(self.fake.calls, [])

    def test_upload_preview_does_not_follow_final_symlink_or_read_fifo(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / "target.txt"
            target.write_text("payload", encoding="utf-8")
            symlink = root / "link.txt"
            symlink.symlink_to(target)
            with self.assertRaises(XxtError):
                server._upload_preview_digest(symlink)
            fifo = root / "pipe"
            os.mkfifo(fifo)
            with self.assertRaises(XxtError):
                server._upload_preview_digest(fifo)
            original = target.stat()
            changed = SimpleNamespace(st_dev=original.st_dev, st_ino=original.st_ino,
                                      st_size=original.st_size, st_mtime_ns=original.st_mtime_ns + 1,
                                      st_ctime_ns=original.st_ctime_ns)
            with patch.object(Path, "stat", return_value=changed):
                with self.assertRaises(XxtError):
                    server._upload_preview_digest(target)

    def test_grade_export_is_preview_only_and_screenshot_is_not_read_only(self):
        self.fake.export_grades = lambda *a: self.fake.calls.append(("export", a))
        server._state["cfg"].download_dir = Path("/tmp/example-grades")
        export = server._wrap(server.export_grades, server.W)
        missing = export(course="测试课程")
        self.assertFalse(missing["ok"])
        draft = export(course="测试课程", class_name="甲班")
        self.assertTrue(draft["preview_only"])
        self.assertEqual(draft["details"]["class_id"], F.NUMERIC_001)
        self.assertEqual(draft["details"]["output_directory"], "/tmp/example-grades")
        self.assertNotIn("plan_id", draft)
        result = export(course="测试课程", class_name="甲班", confirm=True)
        self.assertFalse(result["ok"])
        self.assertIn("暂仅支持预演", result["error"])
        self.assertEqual(self.fake.calls, [])
        kind = next(kind for name, kind, _, _ in server.TOOLS if name == "screenshot")
        self.assertFalse(server._HINTS[kind]["readOnlyHint"])

    def test_grades_preserve_explicit_zero_weight_and_zero_score(self):
        class FakeGrades:
            _COLS = CourseOps._COLS
            response = {"valid": True, "weight": {"video": 0, "work": 20, "test": None},
                        "rows": [{"userName": "test", "video": 0, "work": 0, "score": 0}]}
            def ctx(self, _): return SimpleNamespace(id="1", name="test", cpi="2")
            def resolve_class(self, *_): return "3"
            def on(self, *a, **kw): return self.response
        client = FakeGrades()
        result = CourseOps.grades(client, "test")
        self.assertEqual(result["weights_percent"], {"章节任务点": 0, "作业": 20})
        self.assertEqual(result["students"][0]["章节任务点"], 0)
        self.assertEqual(result["students"][0]["作业"], 0)
        self.assertEqual(result["students"][0]["综合成绩"], 0)
        self.assertNotIn("考试", result["students"][0])
        for bad in (None, {}, {"valid": False, "weight": {}, "rows": []},
                    {"valid": True, "weight": {}, "rows": None}, {"valid": True, "weight": {}, "rows": [None]}):
            client.response = bad
            with self.subTest(response=bad), self.assertRaises(XxtError):
                CourseOps.grades(client, "test")

    def test_notice_read_rejects_incomplete_and_delete_stays_preview_only(self):
        class FakeNoticeRead:
            response = None
            def course(self, _): return SimpleNamespace(id="1")
            def on(self, *a, **kw): return self.response
        client = FakeNoticeRead()
        for response in (None, {}, {"valid": False, "items": []}, {"valid": True, "items": None}):
            client.response = response
            with self.subTest(response=response), self.assertRaises(XxtError):
                ContentOps.notices(client, "test")
        client.response = {"valid": True, "items": [], "pagination": {"complete": True}}
        self.assertEqual(ContentOps.notices(client, "test"), [])
        self.fake.notices = lambda *a, **kw: [{"notice_id": "n1", "title": "测试通知", "time": "today"}]
        self.fake.delete_notice = lambda *a: self.fake.calls.append(("delete_notice", a))
        delete = server._wrap(server.delete_notice, server.D)
        draft = delete(course="测试课程", notice="测试通知")
        self.assertTrue(draft["preview_only"])
        self.assertNotIn("plan_id", draft)
        self.assertEqual(draft["details"]["notice_id"], "n1")
        rejected = delete(course="测试课程", notice="测试通知", confirm=True)
        self.assertFalse(rejected["ok"])
        self.assertIn("plan_id", rejected["error"])
        self.assertEqual(self.fake.calls, [])

    def test_unverified_delete_paths_cannot_submit_after_preview(self):
        self.fake._find_assignment = lambda *a: {"id": "a1", "title": "作业"}
        self.fake.exams = lambda *_: [{"id": "e1", "paper_id": F.CONTROL_022, "title": "考试"}]
        self.fake.papers = lambda *_: [{"paper_id": F.CONTROL_022, "title": "试卷"}]
        self.fake.materials = lambda *_: [{"material_id": "m1", "title": "资料"}]
        for name in ("delete_assignment", "delete_exam", "delete_paper", "delete_material"):
            setattr(self.fake, name, lambda *a, _name=name: self.fake.calls.append((_name, a)))
        cases = [(server.delete_assignment, {"course": "测试课程", "assignment": "作业"}),
                 (server.delete_exam, {"course": "测试课程", "exam": "考试", "delete_paper": True}),
                 (server.delete_exam_paper, {"course": "测试课程", "paper": "试卷"}),
                 (server.delete_material, {"course": "测试课程", "material": "资料"})]
        for fn, args in cases:
            with self.subTest(tool=fn.__name__):
                wrapped = server._wrap(fn, server.D)
                draft = wrapped(**args)
                self.assertTrue(draft["preview_only"])
                self.assertNotIn("plan_id", draft)
                self.assertTrue(draft["limitation"])
                result = wrapped(**args, confirm=True)
                self.assertFalse(result["ok"])
                self.assertIn("暂仅支持预演", result["error"])
        self.assertEqual(self.fake.calls, [])

    def test_read_views_do_not_infer_filtered_lists_or_click_dom(self):
        c = SimpleNamespace(id="1", clazz_id="2", cpi="3")
        class Browser:
            def navigate(self, *args, **kwargs): pass
        class Checkin:
            b = Browser()
            fid = "4"
            def ctx(self, *_): return c
            def _find_activity(self, *_): return {"activity_id": "5", "title": "签到", "status_name": "结束"}
            def wait_for(self, *_a, **_kw): return True
            def here(self, js):
                if '.click(' in js: raise AssertionError('must not click DOM')
                return {"signed": "1", "unsigned": "2", "rate": "33%", "list": ["可见项"]}
        got = ActivityOps.checkin_status(Checkin(), "测试课程", "签到")
        self.assertEqual(got["visible_list"], ["可见项"])
        self.assertIsNone(got["signed_list"])
        self.assertIsNone(got["unsigned_list"])

        class Exam:
            b = Browser()
            def ctx(self, *_): return c
            def exams(self, *_): return [{"id": "6", "paper_id": "7", "title": "考试"}]
            def wait_for(self, *_a, **_kw): return True
            def here(self, js):
                if '.click(' in js: raise AssertionError('must not click DOM')
                return {"total": "3", "submitted": "1", "unsubmitted": "2"} if 'document.body.innerText' in js else [{"姓名": "可见项"}]
        got = ContentOps.exam_marklist(Exam(), "测试课程", "考试")
        self.assertEqual(got["visible_rows"], [{"姓名": "可见项"}])
        self.assertIsNone(got["submitted_rows"])
        self.assertIsNone(got["unsubmitted_rows"])

if __name__ == "__main__":
    unittest.main()
