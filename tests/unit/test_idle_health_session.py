"""Known idle expiry may renew health's read-only session; no error replays."""
# All identity fixtures in this file are synthetic and offline only.
import synthetic_data as F
import threading,unittest
from xuexitong_mcp.bsk import Bsk,BskError

class Browser:
    session=F.CONTROL_018;tab=7;url=F.CONTROL_018;obs_text=F.CONTROL_018;preserve_tab=False
    def __init__(self, failure=None):
        self.failure=failure;self.lock=threading.RLock();self.calls=[]
    def run(self,args,**kwargs):
        self.calls.append(args)
        if self.failure:raise self.failure
        return {'tabs':[{'tab_id':7,'scope':'agent'}]}
    def _save_state(self):self.calls.append('save_empty_state')
    def start_session(self):
        self.calls.append('start_fixed_session');self.session='new';self.tab=8

class Tests(unittest.TestCase):
    def test_normal_health_reuses_current_session(self):
        b=Browser();Bsk.ensure_session(b,renew_idle_readonly=True)
        self.assertEqual(b.calls,[['tab','list','--scope','agent']]);self.assertEqual(b.session,F.CONTROL_018)
    def test_only_confirmed_idle_expiry_starts_one_new_read_session(self):
        b=Browser(BskError('not_found','ended',{'reason':'session_idle_timeout'}))
        Bsk.ensure_session(b,renew_idle_readonly=True)
        self.assertEqual(b.calls,[['tab','list','--scope','agent'],'save_empty_state','start_fixed_session'])
        self.assertEqual((b.session,b.tab),('new',8))
    def test_refusals_transport_and_unknown_endings_never_recover(self):
        for err in [BskError('permission_denied','denied',{'reason':'session_idle_timeout'}),
                    BskError('timeout','timeout'),BskError('not_found','unknown',{}),
                    BskError('not_found','stopped',{'reason':'manual_stop'})]:
            b=Browser(err)
            with self.assertRaises(BskError):Bsk.ensure_session(b,renew_idle_readonly=True)
            self.assertEqual(len(b.calls),1);self.assertEqual(b.session,F.CONTROL_018)
    def test_unresolved_write_is_never_replaced_and_default_path_unchanged(self):
        b=Browser(BskError('not_found','ended',{'reason':'session_idle_timeout'}));b.preserve_tab=True
        with self.assertRaises(BskError):Bsk.ensure_session(b,renew_idle_readonly=True)
        self.assertEqual(len(b.calls),1)
        ordinary=Browser();Bsk.ensure_session(ordinary)
        self.assertEqual(ordinary.calls,[])
    def test_idle_login_handoff_can_restart_without_replaying_login(self):
        b=Browser(BskError('not_found','ended',{'reason':'session_idle_timeout'}))
        b.preserve_tab=True;b._login_handoff=True
        Bsk.ensure_session(b,renew_idle_readonly=True)
        self.assertEqual(b.calls.count('start_fixed_session'),1)
        self.assertFalse(b.preserve_tab);self.assertFalse(b._login_handoff)

if __name__=='__main__':unittest.main()
