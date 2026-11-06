# All fixtures in this file are fabricated for offline tests; no account data.
"""Only successful passive observations may repeat while a page loads."""
import unittest
from xuexitong_mcp.xxt import XxtBase
from xuexitong_mcp.bsk import BskError,JsError

class Fake:
    def __init__(self,values):self.values=iter(values);self.calls=0
    def here(self,_):
        self.calls+=1;value=next(self.values)
        if isinstance(value,Exception):raise value
        return value

class Tests(unittest.TestCase):
    def test_successful_false_observations_may_settle(self):
        f=Fake([False,False,{'loaded':True}])
        self.assertEqual(XxtBase.wait_for(f,'read predicate',timeout=1,interval=0),{'loaded':True})
        self.assertEqual(f.calls,3)
    def test_errors_are_never_reissued_by_wait(self):
        for error in (BskError('permission_denied','denied'),BskError('timeout','unknown'),
                      BskError('control_not_ready','user activity'),JsError('page unavailable')):
            with self.subTest(error=error):
                f=Fake([error,True])
                with self.assertRaises(type(error)):XxtBase.wait_for(f,'read predicate',timeout=1,interval=0)
                self.assertEqual(f.calls,1)

if __name__=='__main__':unittest.main()
