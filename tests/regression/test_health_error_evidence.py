"""Offline regressions for failure evidence; never creates a real browser client."""
# All identity fixtures in this file are synthetic and offline only.
import synthetic_data as F
import json
from types import SimpleNamespace
import unittest

from xuexitong_mcp.bsk import BskError
from xuexitong_mcp.ops_activity import ActivityOps
from xuexitong_mcp import server


STEPS = ["doctor", "session", "login", "guard_navigation", "guard_read", "courses", "language_read"]


def refusal():
    error = BskError("permission_denied", "The strict observation changed before this action", {
        "reason": "observation_changed", "phase": "observation", "effect_state": "none",
        "page": "PRIVATE_PAGE", "token": "PRIVATE_TOKEN", "observation_id": F.CONTROL_007,
    }, raw="PRIVATE_RAW")
    error.xxt_stage, error.xxt_operation = "dispatch", "navigate"
    return error


def client(fail_at=None, error=None):
    calls = []
    error = error or refusal()

    def call(step, result):
        calls.append(step)
        if step == fail_at:
            raise error
        return result

    browser = SimpleNamespace(
        session=F.CONTROL_020, tab=7, preserve_tab=False,
        doctor=lambda: call("doctor", [{"name": "extension connected", "ok": True}]),
        ensure_session=lambda **kw: call("session", None),
        navigate=lambda *a, **kw: call("guard_navigation", "https://example.invalid/"),
    )
    c = SimpleNamespace(
        b=browser, fid="0",
        on=lambda *a, **kw: call("login", {"ok": True}),
        here=lambda script: call("guard_read", {"guard": True, "lang": "zh-CN"})
            if "__xxtNoAppGuard" in script else call("language_read", "我教的课"),
        courses=lambda **kw: call("courses", [object()]),
    )
    return c, calls


class Tests(unittest.TestCase):
    def test_course_failure_retains_actual_dispatch_evidence(self):
        c, calls = client("courses")
        result = ActivityOps.health(c)
        self.assertFalse(result["ok"])
        self.assertEqual(result["login"], "已登录")
        self.assertTrue(result["guard_extension"])
        self.assertEqual(result["browser_error"], {
            "reason": "observation_changed", "phase": "observation", "effect_state": "none",
            "stage": "dispatch", "operation": "navigate", "health_step": "courses",
        })
        self.assertEqual(calls, STEPS[:-1])
        self.assertTrue(c.b.preserve_tab)
        self.assertNotIn("ui_language", result)

    def test_each_failure_stops_at_its_step_without_cleanup_or_replay(self):
        for step in STEPS:
            with self.subTest(step=step):
                c, calls = client(step)
                result = ActivityOps.health(c)
                self.assertFalse(result["ok"])
                self.assertEqual(result["browser_error"]["health_step"], step)
                self.assertEqual(calls, STEPS[:STEPS.index(step)+1])
                self.assertTrue(c.b.preserve_tab)

    def test_success_keeps_the_original_checks_and_navigation_wait(self):
        c, calls = client()
        result = ActivityOps.health(c)
        self.assertTrue(result["ok"], result)
        self.assertEqual(calls, STEPS)
        self.assertNotIn("browser_error", result)
        self.assertFalse(c.b.preserve_tab)

    def test_health_and_server_keep_only_bounded_semantic_labels(self):
        e = refusal()
        e.data["semantic_diff"] = {
            "version": 1, "available": True, "comparison": "whole_page_signature",
            "same_signature": False, "truncated": False,
            "changes": [{"bucket": "nodes", "kind": "changed", "frame": "frame_1",
                         "row": 1, "fields": ["visible"], "private_value": "PRIVATE_VALUE"}],
        }
        c, _ = client("courses", e)
        health = ActivityOps.health(c)["browser_error"]
        old = server._state.copy()
        try:
            server._state.update(client=c, cfg=None)
            ordinary = server._err(e)["browser_error"]
        finally:
            server._state.clear()
            server._state.update(old)
        self.assertEqual(health, {**ordinary, "health_step": "courses"})
        self.assertEqual(health["semantic_diff"]["changes"][0]["fields"], ["visible"])
        self.assertNotIn("PRIVATE", json.dumps(health))

    def test_arbitrary_diagnostic_text_is_not_relayed(self):
        from xuexitong_mcp.privacy import safe_browser_error_details
        e = refusal()
        e.data.update(reason="https://private.invalid/?token=PRIVATE", phase=["PRIVATE"], effect_state=True)
        e.xxt_stage = "PRIVATE_STAGE"
        e.xxt_operation = "PRIVATE_OPERATION"
        e.data["semantic_diff"] = {"version": 1, "available": True, "changes": ["PRIVATE"]}
        self.assertEqual(safe_browser_error_details(e, health_step="PRIVATE_STEP"), {})

    def test_sync_error_never_claims_action_dispatch(self):
        e = refusal()
        e.xxt_stage = "sync"
        c, _ = client("courses", e)
        result = ActivityOps.health(c)["browser_error"]
        self.assertEqual(result["stage"], "sync")
        self.assertNotIn("operation", result)


if __name__ == "__main__":
    unittest.main()
