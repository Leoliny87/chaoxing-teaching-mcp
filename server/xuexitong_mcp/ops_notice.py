"""Notice editor previews bound to an exact class and one new editor instance."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import secrets
import time

from .bsk import BskError
from .xxt import XxtError, _html, NOTICE, ML, _safe_id

SNAPSHOT_JS = r"""
if(location.hostname!=='notice.chaoxing.com'||location.pathname!='/pc/course/notice/richtextNotice') throw Error('通知编辑页不匹配');
const C=window.CourseSend_NoticeRtf;
if(!C||!C.isInitOver||typeof ue==='undefined') throw Error('通知编辑器未就绪');
const active=s=>[...document.querySelectorAll(s)].map(e=>e.classList.contains('active'));
return {course_id:String(C.courseId),course_name:C.courseName,operation:C.operation_type,
 selected:C.sendMap.values().map(x=>({type:x.type,id:String(x.id),name:x.name})),cc_count:C.toccMap.size(),
 uuid:C.uuidTemp,draft_uuid:document.querySelector('#draft_uuid')?.value||'',
 title:document.querySelector('.editContainer .title')?.value,plain:ue.getContentTxt(),html:ue.getContent(),
 editor_empty:!ue.hasContents(),notice_id_empty:!document.querySelector('#noticeIdCode')?.value,
 scheduled:active('.popSendSettingShowHide .scheduledSend .scheduled-send-switch'),
 unread:active('.popSendSettingShowHide .unread-remind-switch'),
 comment:active('.popSendSettingShowHide .commentSwitch .switch'),
 hide_read:active('.popSendSettingShowHide .hideReadSwitch .switch'),
 reminder_switches:active('.receiverSetting .switch'),
 send_controls:[...document.querySelectorAll('.editContainer .submitBtn')].map(e=>(e.textContent||'').trim())};
"""

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def check_scope(s, course_id, course_name, class_id):
    if not isinstance(s,dict) or s.get('course_id')!=course_id or s.get('course_name')!=course_name or s.get('operation')!='add':
        raise XxtError('当前通知编辑器课程或操作不匹配，停止。')
    selected=s.get('selected')
    if (not isinstance(selected,list) or len(selected)!=1 or selected[0].get('type')!='course'
            or selected[0].get('id')!=class_id or s.get('cc_count')!=0):
        raise XxtError('实际收件人不是预演指定的唯一班级或存在抄送，停止。')
    if (s.get('scheduled')!=[False] or s.get('unread')!=[False]
            or s.get('reminder_switches')!=[False]*8 or s.get('send_controls')!=['发送']
            or s.get('notice_id_empty') is not True):
        raise XxtError('定时、提醒、发送控件或新建状态不符合已验证范围，停止。')
    if not isinstance(s.get('uuid'),str) or not s['uuid'] or not isinstance(s.get('draft_uuid'),str):
        raise XxtError('没有可绑定的新通知标识，停止。')


class NoticeOps:
    def prepare_linked_activity_deletion(self,course,activity_id,class_id):
        c=self.ctx(course)
        if len([x for x in c.classes if x.get('clazz_id')==class_id])!=1:
            raise XxtError('活动目标班级不属于课程。')
        journal=self.cfg.log_dir/'notice-outcomes.jsonl'
        records=[json.loads(line) for line in journal.read_text().splitlines()] if journal.exists() else []
        outcomes=[r.get('state') for r in records if r.get('activity_id')==activity_id and r.get('state') in
                  ('activity_delete_attempted','activity_delete_unconfirmed','activity_recycled')]
        if outcomes and outcomes[-1]!='activity_recycled':
            raise XxtError('该活动已有结果未明的删除；先核查，禁止重复提交。')
        linked=[r for r in records if r.get('state')=='linked_activity_observed' and r.get('course_id')==course
                and r.get('class_id')==class_id and r.get('activity_id')==activity_id]
        matches=[a for a in self.activities(course,limit=1000,class_id=class_id) if a['activity_id']==activity_id]
        if (len(matches)!=1 or matches[0].get('active_type')!=45 or matches[0].get('class_id')!=class_id
                or not matches[0].get('notice_id')):
            raise XxtError('当前活动没有可验证的唯一通知与班级关联；不删除。')
        if not linked:
            # The platform's activity content.idCode is the actual notice ID.
            # Title/time similarity alone never establishes ownership.
            owned=[r for r in records if r.get('state')=='published' and r.get('course_id')==course
                   and r.get('class_id')==class_id and r.get('notice_id')==matches[0]['notice_id']]
            if len(owned)!=1 or not owned[0].get('uuid'):
                raise XxtError('活动关联的通知没有本服务唯一的成功创建回执；不删除。')
            link={'state':'linked_activity_observed','course_id':course,'class_id':class_id,
                  'activity_id':activity_id,'notice_id':owned[0]['notice_id'],'uuid':owned[0]['uuid'],
                  'title':matches[0]['title'],'start':matches[0]['start'],
                  'evidence_source':'activeList.content.idCode'}
            self._notice_journal(link)
            linked=[link]
        if (len(linked)!=1 or matches[0]['notice_id']!=linked[0]['notice_id'] or matches[0].get('title')!=linked[0]['title']
                or matches[0].get('start')!=linked[0]['start']):
            raise XxtError('活动与创建记录不匹配；不删除。')
        token=secrets.token_urlsafe(18)
        if not hasattr(self,'_linked_activity_deletions'):self._linked_activity_deletions={}
        self._linked_activity_deletions[token]={'course':course,'class_id':class_id,'target':matches[0],'created':time.time()}
        return {'deletion_id':token,'target':matches[0],'notice_id':linked[0]['notice_id']}

    def delete_linked_activity(self,course,activity_id,class_id,deletion_id):
        p=getattr(self,'_linked_activity_deletions',{}).pop(deletion_id,None)
        if not p or time.time()-p['created']>600 or (course,class_id,activity_id)!=(p['course'],p['class_id'],p['target']['activity_id']):
            raise XxtError('活动删除预演已失效；未提交。')
        before=[a for a in self.activities(course,limit=1000,class_id=class_id) if a['activity_id']==activity_id]
        if before!=[p['target']]:raise XxtError('活动在预演后发生变化；未删除。')
        self._notice_journal({'state':'activity_delete_attempted','course_id':course,'class_id':class_id,'activity_id':activity_id})
        result=self.on(ML,f"return await J('/ppt/taskAPI/setdel?aid={_safe_id(activity_id)}&status=1');",retry_safe=False)
        after=self.activities(course,limit=1000,class_id=class_id)
        absent=not any(a['activity_id']==activity_id for a in after)
        c=self.ctx(course)
        self.b.navigate(f'https://mobilelearn.chaoxing.com/page/active/recycleBinList?fid={self.fid}&courseId={course}&classId={class_id}&cpi={c.cpi}&enc={c.enc}')
        # Positive presence of this exact ID and a visible Restore control is
        # independent of absence from an incomplete active-list snapshot.
        recycle=self.here(f"""
          const wanted={json.dumps(activity_id)}, title={json.dumps(p['target']['title'])};
          if(location.hostname!=='mobilelearn.chaoxing.com'||location.pathname!='/page/active/recycleBinList')return {{valid:false}};
          const matches=[];
          for(const el of document.querySelectorAll('[onclick],[data-id],[data-activeid],[id]')){{
            if(!el.getClientRects().length)continue;
            const attrs=el.getAttributeNames().map(k=>el.getAttribute(k));
            if(!attrs.some(v=>v&&new RegExp('(^|[^0-9])'+wanted+'([^0-9]|$)').test(v)))continue;
            let node=el;
            for(let depth=0;node&&depth<5;depth++,node=node.parentElement){{
              const text=(node.innerText||'').trim();
              if(text.includes(title)&&text.includes('还原')){{matches.push({{id:wanted,text:text.slice(0,400)}});break;}}
            }}
          }}
          return {{valid:true,matches}};
        """)
        seen=isinstance(recycle,dict) and recycle.get('valid') is True and bool(recycle.get('matches'))
        ok=isinstance(result,dict) and result.get('status') in (1,'1') and absent and seen
        self._notice_journal({'state':'activity_recycled' if ok else 'activity_delete_unconfirmed','course_id':course,'class_id':class_id,'activity_id':activity_id})
        return {'ok':ok,'activity_id':activity_id,'server_status':result.get('status') if isinstance(result,dict) else None,
                'absent_from_active_list':absent,'recycle_row_verified':seen,'recycle_rows':recycle.get('matches',[]) if isinstance(recycle,dict) else [],
                'note':'本次仅移入回收站；未执行永久删除。'}

    def _notice_journal(self, entry):
        """Durable outcome breadcrumbs; no credentials or message body."""
        path=self.cfg.log_dir/'notice-outcomes.jsonl'
        path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
        try:
            os.fchmod(fd,0o600)
            os.write(fd,(json.dumps({'time':time.time(),**entry},ensure_ascii=False)+'\n').encode())
            os.fsync(fd)
        finally:os.close(fd)

    def prepare_notice(self, course, title, content, class_id):
        c=self.ctx(course)
        if not title or len(title)>128 or not content:
            raise XxtError('通知需要 1–128 字标题及非空纯文本正文。')
        classes=[x for x in c.classes if x.get('clazz_id')==class_id]
        if len(classes)!=1:raise XxtError('预演班级不属于目标课程。')
        request_digest=digest([c.id,class_id,title,content])
        journal=self.cfg.log_dir/'notice-outcomes.jsonl'
        if journal.exists():
            latest={}
            for line in journal.read_text().splitlines():
                try:r=json.loads(line)
                except ValueError:raise XxtError('通知结果台账损坏，停止提交并先核查。')
                if r.get('request_digest')==request_digest:latest[r.get('uuid')]=r.get('state')
            if 'attempted' in latest.values():raise XxtError('相同通知存在结果未明的提交；请先按 UUID 查实，不要再次发布。')
        self.b.navigate(f'https://notice.chaoxing.com/pc/course/notice/richtextNotice?courseId={c.id}&classId={_safe_id(class_id)}')
        s=self.here(SNAPSHOT_JS)
        check_scope(s,c.id,c.name,class_id)
        if s.get('editor_empty') is not True or s.get('title')!=f'《{c.name}》':
            raise XxtError('编辑页含既有内容，未覆盖；请先核查草稿。')
        token=secrets.token_urlsafe(18)
        p={'course_id':c.id,'course_name':c.name,'class_id':class_id,'title':title,'content':content,
           'request_digest':request_digest,'snapshot':s,'session':self.b.session,'tab':self.b.tab,'created':time.time()}
        if not hasattr(self,'_notice_preparations'):self._notice_preparations={}
        self._notice_preparations[token]=p
        return {'preparation_id':token,'class':{'id':class_id,'name':classes[0]['name']},
                'uuid':s['uuid'],'settings':{k:s[k] for k in ('scheduled','unread','comment','hide_read','reminder_switches')},
                'side_effects':'填写后页面会自动存草稿；发送可通知该班当前成员。班级成员不是原子冻结；删除不能保证撤回已送达提醒。'}

    def publish_prepared_notice(self,course,title,content,class_id,preparation_id):
        p=getattr(self,'_notice_preparations',{}).pop(preparation_id,None)
        if not p or time.time()-p['created']>600 or [course,class_id,title,content]!=[p['course_id'],p['class_id'],p['title'],p['content']]:
            raise XxtError('通知预演已失效或参数改变；没有提交。')
        if (self.b.session,self.b.tab)!=(p['session'],p['tab']):raise XxtError('预演标签已改变；没有提交。')
        s=self.here(SNAPSHOT_JS)
        check_scope(s,p['course_id'],p['course_name'],class_id)
        if s!=p['snapshot']:raise XxtError('通知编辑页在预演后发生改变；没有填写或发送。')
        expected={'course_id':course,'class_id':class_id,'uuid':s['uuid']}
        js=f"""
        const expected={json.dumps(expected)}, C=window.CourseSend_NoticeRtf;
        if(location.hostname!=='notice.chaoxing.com'||location.pathname!='/pc/course/notice/richtextNotice'||
          !C||String(C.courseId)!==expected.course_id||C.uuidTemp!==expected.uuid) throw Error('编辑器身份改变');
        const recipients=C.sendMap.values();
        if(recipients.length!==1||recipients[0].type!=='course'||String(recipients[0].id)!==expected.class_id||C.toccMap.size()!==0) throw Error('收件人改变');
        const title=document.querySelector('.editContainer .title');
        if(!title||typeof ue==='undefined'||ue.hasContents())throw Error('表单内容改变');
        title.value={json.dumps(title)}; ['input','keyup','change'].forEach(n=>title.dispatchEvent(new Event(n,{{bubbles:true}})));
        ue.setContent({json.dumps(_html(content))});ue.fireEvent('contentChange');
        return {{filled:true}};
        """
        self.here(js,retry_safe=False)
        filled=self.here(SNAPSHOT_JS)
        check_scope(filled,course,p['course_name'],class_id)
        if (filled.get('uuid')!=s['uuid'] or filled.get('title')!=title
                or (filled.get('plain') or '').strip()!=content.strip()
                or any(filled[k]!=s[k] for k in ('comment','hide_read'))):
            raise XxtError('填写后的正文或设置核对失败；未点击发送，页面可能已保存本轮草稿。')
        journal={'course_id':course,'class_id':class_id,'uuid':s['uuid'],'draft_uuid':s['draft_uuid'],'request_digest':p['request_digest']}
        self._notice_journal({**journal,'state':'attempted'})
        selector='.editContainer .submitBtn'
        def click(ctx,obs):
            return ['click','--selector',selector,'--context',ctx,'--observation',obs,
                    '--expect',json.dumps([{'target':selector,'field':'text','equals':'发送'}],ensure_ascii=False)]
        try:
            self.b._act(click,retry_safe=False,need_obs=True)
        except BskError as e:
            if e.not_dispatched:self._notice_journal({**journal,'state':'not_dispatched'})
            raise
        time.sleep(3.5)
        self.b.wait_readiness()
        inv=self.notice_inventory(course,1000,full_content=True)
        matches=[n for n in inv['items'] if n.get('uuid')==s['uuid']]
        if (len(matches)!=1 or matches[0]['title']!=title
                or content.replace('\r\n','\n').strip()!=matches[0].get('content','').replace('\r\n','\n').strip()):
            raise XxtError('发送结果未确认；不要重发，请按预演 UUID 核查通知和草稿。')
        n=matches[0]
        if n.get('receivers')!=[{'course_id':course,'class_id':class_id,'name':s['selected'][0]['name'],'type':4}]:
            raise XxtError('通知已出现，但返回收件范围与预演未匹配；停止后续写入并核查。')
        self._notice_journal({**journal,'state':'published','notice_id':n['notice_id']})
        return {'ok':True,'notice':n,'verification':'matched_uuid_title_body_and_class','pagination':inv['pagination'],
                'warning':'删除通知不能保证撤回已送达提醒；平台可能同时创建通知活动。'}

    def prepare_notice_deletion(self, course, notice_id):
        c=self.course(course)
        if not notice_id or _safe_id(notice_id)!=notice_id:raise XxtError('需要准确通知 ID。')
        inv=self.notice_inventory(c.id,1000,full_content=True)
        if not inv['pagination'].get('complete'):raise XxtError('通知遍历未到已验证的终点，停止删除。')
        matches=[n for n in inv['items'] if n['notice_id']==notice_id]
        if len(matches)!=1:raise XxtError('未找到唯一通知 ID，停止。')
        n=matches[0]
        # This first live deletion implementation only handles our own successful
        # notices with durable receipts. Existing objects remain preview-only.
        journal=self.cfg.log_dir/'notice-outcomes.jsonl'
        owned=False
        deletion_states=[]
        if journal.exists():
            for line in journal.read_text().splitlines():
                r=json.loads(line)
                if r.get('state')=='published' and r.get('course_id')==c.id and r.get('notice_id')==notice_id and r.get('uuid')==n.get('uuid'):owned=True
                if r.get('notice_id')==notice_id and r.get('state') in ('delete_attempted','delete_unconfirmed','deleted'):
                    deletion_states.append(r['state'])
        if deletion_states and deletion_states[-1]!='deleted':raise XxtError('通知存在结果未明的删除，禁止重复提交。')
        if not owned:raise XxtError('当前删除实现只清理本服务已记录成功创建的测试通知；不删除既有通知。')
        if n.get('send_tag') not in (1,'1'):raise XxtError('通知发送类型尚未验证，停止删除。')
        # Counts change as recipients read; they are deliberately not approval targets.
        target={k:n[k] for k in ('notice_id','uuid','title','content','receivers','send_tag')}
        token=secrets.token_urlsafe(18)
        if not hasattr(self,'_notice_deletions'):self._notice_deletions={}
        self._notice_deletions[token]={'course':c.id,'target':target,'created':time.time()}
        return {'deletion_id':token,'target':target,'pagination':inv['pagination']}

    def delete_prepared_notice(self,course,notice_id,deletion_id):
        p=getattr(self,'_notice_deletions',{}).pop(deletion_id,None)
        if not p or time.time()-p['created']>600 or p['course']!=course or p['target']['notice_id']!=notice_id:
            raise XxtError('删除预演已失效或目标改变；未删除。')
        inv=self.notice_inventory(course,1000,full_content=True)
        matches=[n for n in inv['items'] if n['notice_id']==notice_id]
        if not inv['pagination'].get('complete') or len(matches)!=1 or any(matches[0].get(k)!=v for k,v in p['target'].items()):
            raise XxtError('删除前通知内容或完整列表已变化；未删除。')
        entry={'course_id':course,'notice_id':notice_id,'uuid':p['target']['uuid']}
        self._notice_journal({**entry,'state':'delete_attempted'})
        r=self.on(NOTICE,f"return await J('/pc/course/notice/delNoitce',POST({{noticeId:{json.dumps(notice_id)},sendTag:'1'}}));",retry_safe=False)
        after=self.notice_inventory(course,1000)
        absent=after['pagination'].get('complete') is True and not any(x['notice_id']==notice_id for x in after['items'])
        ok=isinstance(r,dict) and r.get('status') is True and absent
        self._notice_journal({**entry,'state':'deleted' if ok else 'delete_unconfirmed'})
        return {'ok':ok,'notice_id':notice_id,'server_status':r.get('status') if isinstance(r,dict) else None,
                'observed_absent':absent,'pagination':after['pagination'],
                'warning':'仅核验本次通知列表移除，不保证推送、活动或审计记录随之消失。'}
