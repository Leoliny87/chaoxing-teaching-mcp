"""Synthetic receipts only; no BrowserSkill or learning platform calls."""
# All identity fixtures in this file are synthetic and offline only.
import synthetic_data as F
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from xuexitong_mcp.bsk import BskError
from xuexitong_mcp.readiness import wait_homepage_course_ready

class FakeBrowser:
    session=F.CONTROL_013;tab=1;obs_text=F.CONTROL_018
    def __init__(self,receipts):self.receipts=iter(receipts);self.calls=[]
    def run(self,args):
        self.calls.append(args)
        value=next(self.receipts)
        if isinstance(value,Exception):raise value
        Path(args[args.index('--save-full')+1]).write_text('{}')
        return {'tab_id':1,'context_id':F.CONTROL_012,'observation_id':F.CONTROL_017,'state':{'mode':'ready','editing':False},
                'activity':[], 'observation':{'text':value,'truncated':False}}

class Tests(unittest.TestCase):
    def test_waits_for_target_and_two_equal_complete_observations(self):
        b=FakeBrowser(['heading "学习规划测试课程"','link "测试课程 置顶"','link "测试课程 置顶"'])
        result=wait_homepage_course_ready(b,'测试课程',interval=0)
        self.assertEqual(len(b.calls),3)
        self.assertFalse(result[0]['target_seen'])
        self.assertTrue(result[-1]['same_as_previous'])
        self.assertIn('--baseline',b.calls[-1])
        self.assertEqual(b.obs_text,'')

    def test_denied_sync_is_not_repeated_and_missing_target_never_authorizes_navigation(self):
        b=FakeBrowser(['link "测试课程"',BskError('permission_denied','changed',{'effect_state':'none'}),'link "测试课程"'])
        with self.assertRaises(BskError):wait_homepage_course_ready(b,'测试课程',interval=0)
        self.assertEqual(len(b.calls),2)
        b=FakeBrowser(['link "学习规划测试课程"']*3)
        with self.assertRaises(BskError) as e:wait_homepage_course_ready(b,'测试课程',samples=3,interval=0)
        self.assertEqual(e.exception.code,'readiness_timeout')
        self.assertTrue(all(args[:2]==['cooperate','sync'] for args in b.calls))

if __name__=='__main__':unittest.main()
