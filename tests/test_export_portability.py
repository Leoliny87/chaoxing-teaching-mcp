# All fixtures in this file are fabricated for offline tests; no account data.
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from xuexitong_mcp import bsk, config, server

class PortableBoundaryTests(unittest.TestCase):
    def test_missing_browser_binding_stops_before_any_command(self):
        calls = []
        fake = SimpleNamespace(run=lambda *a, **k: calls.append(a))
        with patch.object(bsk, 'FIXED_BROWSER_INSTANCE', ''):
            with self.assertRaises(bsk.BskError):
                bsk.Bsk.start_session(fake)
        self.assertEqual(calls, [])

    def test_empty_defaults_do_not_inherit_owner_write_or_upload_authority(self):
        cfg = config.Config()
        self.assertEqual(cfg.write_allow_courses, [])
        self.assertEqual(cfg.upload_allow_dirs, [])
        with patch.dict(os.environ, {'XUEXITONG_MCP_WRITE_ALLOW': '测试课程'}):
            cfg = config.load(os.environ['XUEXITONG_MCP_CONFIG'])
        self.assertEqual(cfg.write_allow_courses, [])

    def test_preview_does_not_grant_autonomous_write_permission(self):
        course = SimpleNamespace(id='fixture-course', name='测试课程')
        preview = server._dry(course, 'synthetic action')
        self.assertIn('明确同意', preview['next'])
        self.assertNotIn('无需', preview['next'])
