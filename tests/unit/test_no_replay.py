"""Errors never cause a second browser dispatch or session recovery."""
# All identity fixtures in this file are synthetic and offline only.
import synthetic_data as F
import unittest
from xuexitong_mcp.bsk import Bsk, BskError

class Fake:
    tab=7
    def __init__(self, result): self.result=result; self.calls=[]
    def ensure_session(self): pass
    def sync(self, *_): return F.CONTROL_012,F.CONTROL_017
    def run(self, args, **_):
        self.calls.append(args)
        if isinstance(self.result, Exception): raise self.result
        return self.result

class Tests(unittest.TestCase):
    def test_transient_or_known_not_dispatched_reads_never_replay(self):
        for code in ('timeout','cdp_failed','permission_denied','session_not_found'):
            for op in ('sync','action'):
                f=Fake(BskError(code,'still settling',{'effect_state':'none','dispatched':False}))
                with self.subTest(code=code,op=op), self.assertRaises(BskError):
                    if op=='sync': Bsk.sync(f)
                    else: Bsk._act(f,lambda *_:['evaluate'],retry_safe=True,need_obs=True)
                self.assertEqual(len(f.calls),1)

    def test_human_activity_and_wrong_tab_stop_before_dispatch(self):
        base={'tab_id':7,'context_id':F.CONTROL_012,'observation_id':F.CONTROL_017,'state':{'mode':'ready'}}
        for changes in ({'tab_id':8},{'activity':[{}]},{'state':{'mode':'ready','editing':True}}):
            f=Fake({**base,**changes})
            with self.subTest(changes=changes), self.assertRaises(BskError): Bsk.sync(f)
            self.assertEqual(f.calls,[['cooperate','sync','--tab-id','7']])

if __name__=='__main__': unittest.main()
