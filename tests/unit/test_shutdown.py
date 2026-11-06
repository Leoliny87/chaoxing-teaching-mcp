"""One-shot owned-tab cleanup; fake BrowserSkill only."""
# All identity fixtures in this file are synthetic and offline only.
import synthetic_data as F
import logging,threading,unittest
from xuexitong_mcp.bsk import Bsk,BskError
class Fake:
 def __init__(self):
  self.lock=threading.RLock();self.session=F.CONTROL_020;self.tab=7;self.preserve_tab=False;self._shutdown_attempted=False
  self.log=logging.getLogger('test.cleanup');self.calls=[];self.active=False;self.denied=False;self.saved=False
 def _save_state(self):self.saved=True
 def run(self,args):
  self.calls.append(args)
  if args[:2]==['tab','list']:return {'tabs':[{'tab_id':7,'scope':'agent'},{'tab_id':8,'scope':'agent'}]}
  if args[:2]==['cooperate','sync']:return {'tab_id':7,'context_id':F.CONTROL_012,'observation_id':F.CONTROL_017,'state':{'mode':'ready','editing':False},'activity':[{}] if self.active else []}
  if self.denied:raise BskError('permission_denied','no',{'effect_state':'none'})
  return {'tab_id':7}
class Tests(unittest.TestCase):
 def test_only_owned_tab_closes_and_never_entire_session(self):
  f=Fake();Bsk.stop(f)
  self.assertEqual(f.calls[-1],['tab','close','7','--context',F.CONTROL_012,'--observation',F.CONTROL_017])
  self.assertTrue(f.saved);self.assertIsNone(f.tab)
  self.assertFalse(any(x[0]=='session' for x in f.calls))
 def test_pending_write_or_user_activity_keeps_tab(self):
  f=Fake();f.preserve_tab=True;Bsk.stop(f);self.assertEqual(f.calls,[])
  f=Fake();f.active=True;Bsk.stop(f);self.assertEqual(len(f.calls),2);self.assertEqual(f.tab,7)
 def test_denied_close_is_not_replayed_by_second_shutdown_hook(self):
  f=Fake();f.denied=True;Bsk.stop(f);Bsk.stop(f)
  self.assertEqual(len(f.calls),3);self.assertEqual(f.tab,7);self.assertFalse(f.saved)
if __name__=='__main__':unittest.main()
