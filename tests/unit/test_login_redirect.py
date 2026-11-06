"""Offline regression for the DSH run's observed Chaoxing login redirect."""
# All identity fixtures in this file are synthetic and offline only.
import synthetic_data as F
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from xuexitong_mcp.bsk import Bsk, BskError, FIXED_HOMEPAGE
from xuexitong_mcp.ops_activity import ActivityOps
from xuexitong_mcp import server


class RedirectBrowser:
    cfg=SimpleNamespace(t_navigate=40)
    session=F.CONTROL_021
    tab=None
    preserve_tab=False
    def __init__(self,url):self.url_after=url;self.calls=[];self.saved=False;self.waited=False
    def run(self,args,**kwargs):
        self.calls.append(args)
        if args[:2]==['tab','list']:
            return {'tabs':[{'tab_id':7,'url':'about:blank','scope':'agent'}]}
        if args[0]=='navigate':return {'tab_id':7,'final_url':self.url_after,'reached':'load'}
        raise AssertionError('No additional browser operation is permitted')
    def _save_state(self):self.saved=True
    def wait_readiness(self,*args):self.waited=True


class LoginRedirectTests(unittest.TestCase):
    def test_observed_login_redirect_stops_before_sync_and_keeps_page(self):
        b=RedirectBrowser('https://passport2.chaoxing.com/login?refer=PRIVATE_TEMP_VALUE')
        with self.assertRaises(BskError) as caught:Bsk._initialize_owned_tab(b)
        self.assertEqual(caught.exception.code,'login_required')
        self.assertTrue(b.saved and b.preserve_tab)
        self.assertTrue(b._login_handoff)
        self.assertFalse(b.waited)
        self.assertEqual([x[0] for x in b.calls],['tab','navigate'])
        self.assertNotIn('PRIVATE_TEMP_VALUE',str(caught.exception))

    def test_login_word_or_other_origin_does_not_misclassify(self):
        for url in [FIXED_HOMEPAGE,'https://example.invalid/login','https://passport2.chaoxing.com.example.invalid/login',
                    'https://i.mooc.chaoxing.com/space/login-course']:
            b=RedirectBrowser(url);Bsk._initialize_owned_tab(b)
            self.assertTrue(b.waited)
            self.assertFalse(b.preserve_tab)

    def test_health_handoff_has_no_further_browser_calls(self):
        class Browser:
            session=F.CONTROL_021;tab=7
            def doctor(self):return [{'name':'fixture','ok':True}]
            def ensure_session(self, **kwargs):raise BskError('login_required','Manual login required')
        fake=SimpleNamespace(b=Browser())
        with patch('pathlib.Path.read_text',side_effect=FileNotFoundError):
            result=ActivityOps.health(fake)
        self.assertFalse(result['ok']);self.assertTrue(result['needs_human'])
        self.assertEqual(result['login'],'未登录')
        self.assertEqual(result['session'],{'session':F.CONTROL_021,'tab':7})
        self.assertEqual(result['login_url'],FIXED_HOMEPAGE)
        self.assertNotIn('guard_extension',result)

    def test_other_tools_report_login_handoff_without_health_retry(self):
        with patch.dict(server._state,{'client':None}):
            result=server._err(BskError('login_required','Manual login required'))
        self.assertTrue(result['needs_human']);self.assertFalse(result['ok'])
        self.assertNotIn('可先调用 health_check',result['hint'])


if __name__=='__main__':unittest.main()
