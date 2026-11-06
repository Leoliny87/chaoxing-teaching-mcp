"""Safety behavior tests with fake editors; never starts a browser."""
# All identity fixtures in this file are synthetic and offline only.
import synthetic_data as F
import json,time,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from xuexitong_mcp.ops_notice import NoticeOps,check_scope,digest
from xuexitong_mcp.xxt import XxtError
from xuexitong_mcp.bsk import Bsk,BskError

def snapshot():
 return {'course_id':F.NUMERIC_004,'course_name':'测试课程','operation':'add','selected':[{'id':F.NUMERIC_005,'name':'默认班级','type':'course'}],
  'cc_count':0,'uuid':'new-test-uuid','draft_uuid':'new-test-draft','title':'《测试课程》','plain':'','html':'','editor_empty':True,
  'notice_id_empty':True,'scheduled':[False],'unread':[False],'comment':[True],'hide_read':[False],'reminder_switches':[False]*8,'send_controls':['发送']}

class Tests(unittest.TestCase):
 def test_changed_recipient_or_delivery_channel_is_rejected(self):
  good=snapshot();check_scope(good,F.NUMERIC_004,'测试课程',F.NUMERIC_005)
  for key,value in [('course_id',F.CONTROL_019),('selected',[{'id':F.CONTROL_019,'type':'course'}]),('cc_count',1),
                    ('scheduled',[True]),('unread',[True]),('reminder_switches',[False]*7+[True]),('send_controls',['发送','发送'])]:
   bad={**good,key:value}
   with self.subTest(key=key),self.assertRaises(XxtError):check_scope(bad,F.NUMERIC_004,'测试课程',F.NUMERIC_005)

 def test_unknown_submission_is_durable_and_not_prepared_again(self):
  with tempfile.TemporaryDirectory() as tmp:
   initial=snapshot();filled={**initial,'title':'测试','plain':'测试正文','html':'<p>测试正文</p>','editor_empty':False}
   class Fake(NoticeOps):
    cfg=SimpleNamespace(log_dir=Path(tmp))
    b=SimpleNamespace(session=F.CONTROL_020,tab=1)
    snapshots=iter([initial,{'filled':True},filled])
    def here(self,*a,**kw):return next(self.snapshots)
    def ctx(self,course):return SimpleNamespace(id=course,name='测试课程',classes=[{'clazz_id':F.NUMERIC_005,'name':'默认班级'}])
   f=Fake();clicks=[]
   def click(*a,**kw):clicks.append(1);raise BskError('timeout','unknown')
   f.b._act=click
   f._notice_preparations={'plan':{'course_id':F.NUMERIC_004,'course_name':'测试课程','class_id':F.NUMERIC_005,'title':'测试','content':'测试正文',
     'request_digest':digest([F.NUMERIC_004,F.NUMERIC_005,'测试','测试正文']),'snapshot':initial,'session':F.CONTROL_020,'tab':1,'created':time.time()}}
   with self.assertRaises(BskError):f.publish_prepared_notice(F.NUMERIC_004,'测试','测试正文',F.NUMERIC_005,'plan')
   self.assertEqual(clicks,[1]);self.assertEqual(f._notice_preparations,{})
   log=Path(tmp)/'notice-outcomes.jsonl'
   self.assertEqual(json.loads(log.read_text())['state'],'attempted')
   with self.assertRaises(XxtError):f.prepare_notice(F.NUMERIC_004,'测试','测试正文',F.NUMERIC_005)
   self.assertEqual(clicks,[1])

 def test_native_write_timeout_and_known_not_dispatched_are_not_replayed(self):
  for detail in ({},{'effect_state':'none'}):
   class Fake:
    calls=0
    def sync(self,_=None):return F.CONTROL_012,F.CONTROL_017
    def run(self,*a,**kw):self.calls+=1;raise BskError('timeout','timeout',detail)
   f=Fake()
   with self.assertRaises(BskError):Bsk._act(f,lambda c,o:['click','sender'],retry_safe=False,need_obs=True)
   self.assertEqual(f.calls,1)

 def test_deletion_does_not_touch_preexisting_notice_or_incomplete_inventory(self):
  with tempfile.TemporaryDirectory() as tmp:
   class Fake(NoticeOps):
    cfg=SimpleNamespace(log_dir=Path(tmp))
    def course(self,_):return SimpleNamespace(id=F.NUMERIC_004)
    complete=True
    def notice_inventory(self,*a,**kw):return {'items':[{'notice_id':'a'*32,'uuid':'existing','send_tag':1}], 'pagination':{'complete':self.complete}}
    def on(self,*a,**kw):raise AssertionError('No write expected')
   f=Fake()
   with self.assertRaises(XxtError):f.prepare_notice_deletion(F.NUMERIC_004,'a'*32)
   f.complete=False
   with self.assertRaises(XxtError):f.prepare_notice_deletion(F.NUMERIC_004,'a'*32)
if __name__=='__main__':unittest.main()
