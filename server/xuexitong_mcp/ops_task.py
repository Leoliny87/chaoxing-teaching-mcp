"""教学任务 (task engine) creation and publishing (chain verified on the test course, 2026-11-07).

Create:  GET /task/index?courseId&type=course (inline consts encryptedCourseId, encryptedType)
         -> GET /task/createTask?encryptedCourseId&encryptedType -> {encryTaskId, backToken, decryptCourseId}
         -> GET /task/newTaskToList?encryptedCourseId&encryTaskId&token (opens the draft)
         -> GET /task/onMountGetTaskData?taskId=<encry> (groups[0].id = default group, fkTaskId = numeric id)
         -> POST /task/taskCommit JSON {taskId, name, introduce, startDate/endDate as epoch ms, mode, selectedModes}
Points:  POST /homework/getMoocData {page, pageSize, searchKey, moocCourseId, isCheckedExist:"1"}
         -> POST /homework/checkAddition [{name, courseId, workLibraryId}]
         -> POST /taskPoint/saveTaskPoints {taskPoints:[{imageUrl, name, exist, externalDataId: workLibraryId, workType,
            localDataId: id, desc, courseId, fkGroupId, type: 4, fkTaskId, shareType: 0}]}
Publish: GET /peTaskPlan/taskPointCheckPublish?encryptedTaskId -> POST /taskReference/coursePublishAuthentication
         (returns the class-picker URL mooc2-ans/exam/test/publish-plugin; each .classitem carries data=classId and
         data-token) -> POST /taskReference/taskPublish {encryTaskId, coursePublishParam:[{classId(number), className,
         publishtype:0, token}], taskPublishParam:null}.  All bodies are JSON.
"""
from __future__ import annotations

import datetime as _dt
import json
import re

from .ops_v3 import TASK
from .xxt import M2, XxtBase, XxtError, _safe_id

_CN = _dt.timezone(_dt.timedelta(hours=8))
_PLUGIN = re.compile(r"^https://mooc2-ans\.chaoxing\.com/mooc2-ans/exam/test/publish-plugin\?[\w=&%.\-]*$")


def epoch_ms(s: str) -> int:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(_dt.datetime.strptime(s.strip(), fmt).replace(tzinfo=_CN).timestamp() * 1000)
        except ValueError:
            pass
    raise XxtError("时间格式为 YYYY-MM-DD HH:MM（北京时间）。")


_JS_HELPERS = """
const JP=async(u,d)=>{const r=await fetch(u,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json;charset=UTF-8'},body:JSON.stringify(d)});try{return await r.json()}catch(e){return {http:r.status}}};
const JG=async(u)=>{const r=await fetch(u,{credentials:'include'});try{return await r.json()}catch(e){return {http:r.status}}};
"""


class TaskOps(XxtBase):
    def _task_rows(self, cid: str) -> list[dict]:
        j = self.on(TASK, f"return await (await fetch('/task/getTaskDataLists?searchKey=&flag=true&courseId={cid}&isDel=0&page=1&pageSize=200',{{credentials:'include'}})).json();")
        d = j.get("data") if isinstance(j, dict) else None
        rows = d.get("list") or d.get("data") if isinstance(d, dict) else d
        if not isinstance(rows, list):
            raise XxtError("教学任务列表读取失败或结构不完整。")
        return rows

    def create_task(self, course: str, name: str, intro: str, start: str, end: str, library_ids: list[str]) -> dict:
        if not name.strip() or len(name) > 100:
            raise XxtError("任务名称需为 1–100 字。")
        s_ms, e_ms = epoch_ms(start), epoch_ms(end)
        if e_ms <= s_ms:
            raise XxtError("结束时间必须晚于开始时间。")
        wids = [_safe_id(x) for x in library_ids]
        c = self.course(course)
        cid = _safe_id(c.id)
        r = self.on(TASK, _JS_HELPERS + """
            const h=await (await fetch('/task/index?courseId=%(cid)s&type=course',{credentials:'include'})).text();
            const g=k=>(h.match(new RegExp('const '+k+' = "([^"]*)"'))||[])[1];
            const ec=g('encryptedCourseId'), et=g('encryptedType');
            if(!ec||!et) return {stage:'index'};
            const cr=await JG('/task/createTask?'+new URLSearchParams({encryptedCourseId:ec,encryptedType:et}));
            if(cr.code!==200||!cr.data||!cr.data.encryTaskId) return {stage:'create'};
            const d=cr.data, tid=d.encryTaskId;
            await fetch('/task/newTaskToList?'+(d.decryptCourseId?'encryptedCourseId='+encodeURIComponent(d.decryptCourseId)+'&':'')
              +'encryTaskId='+encodeURIComponent(tid)+'&token='+encodeURIComponent(d.backToken||''),{credentials:'include'});
            const t=await JG('/task/onMountGetTaskData?taskId='+encodeURIComponent(tid));
            const grp=t.data&&t.data.groups&&t.data.groups[0];
            if(t.code!==200||!grp) return {stage:'load',task_id:tid};
            const cm=await JP('/task/taskCommit',{taskId:tid,name:%(name)s,introduce:%(intro)s,introduceRichText:'',startDate:%(s)d,endDate:%(e)d,
              mode:'list',selectedModes:['list']});
            if(cm.code!==200||cm.result!==true) return {stage:'commit',task_id:tid};
            const added=[];
            for(const wid of %(wids)s){
              let w=null;
              for(let p=1;p<=10&&!w;p++){
                const L=await JP('/homework/getMoocData',{page:p,pageSize:50,searchKey:'',moocCourseId:'%(cid)s',isCheckedExist:'1'});
                const rows=(L.data&&L.data.data)||[]; w=rows.find(x=>x.workLibraryId===wid)||null; if(rows.length<50) break;
              }
              if(!w) return {stage:'find_work',task_id:tid,missing:wid,added};
              const ck=await JP('/homework/checkAddition',[{name:w.name,courseId:w.courseId,workLibraryId:w.workLibraryId}]);
              if(ck.result!==true) return {stage:'check_work',task_id:tid,missing:wid,added};
              const sv=await JP('/taskPoint/saveTaskPoints',{taskPoints:[{imageUrl:w.cover,name:w.name,exist:w.exist,externalDataId:w.workLibraryId,
                workType:w.workType,localDataId:w.id,desc:w.describe,courseId:w.courseId,fkGroupId:grp.id,type:4,fkTaskId:grp.fkTaskId,shareType:0}]});
              if(sv.code!==200||sv.result===false) return {stage:'save_point',task_id:tid,missing:wid,added};
              added.push(w.name);
            }
            const b=await JG('/task/onMountGetTaskData?taskId='+encodeURIComponent(tid));
            return {stage:'done',task_id:tid,name:b.data&&b.data.name,points:b.data&&b.data.taskPointsNumber,added};
        """ % {"cid": cid, "name": json.dumps(name), "intro": json.dumps(intro or ""), "s": s_ms, "e": e_ms,
               "wids": json.dumps(wids)}, retry_safe=False)
        if not isinstance(r, dict) or r.get("stage") != "done":
            stage = (r or {}).get("stage", "未知")
            tid = (r or {}).get("task_id")
            msg = f"新建任务在「{stage}」步骤失败" + ("；草稿任务已生成，请在教学任务列表核查后删除或补全" if tid else "；没有生成任务")
            raise XxtError(msg + "。")
        ok = r.get("name") == name and int(r.get("points") or 0) == len(wids)
        return {"ok": ok, "task_id": r["task_id"], "name": name, "task_points": r.get("added"),
                **({} if ok else {"write_outcome": "unknown", "error": "任务已提交但读回不一致；请用 list_teaching_tasks 核查。"})}

    def publish_task(self, course: str, task_id: str, class_ids: list[str]) -> dict:
        c = self.ctx(course)
        cid = _safe_id(c.id)
        if not re.fullmatch(r"[A-Za-z0-9@_\-]{10,80}", task_id or ""):
            raise XxtError("任务 ID 格式不对（应为 list_teaching_tasks 返回的加密 ID）。")
        want = {_safe_id(x) for x in class_ids}
        if not want:
            raise XxtError("必须明确指定发布班级。")
        r = self.on(TASK, _JS_HELPERS + """
            const ck=await JG('/peTaskPlan/taskPointCheckPublish?encryptedTaskId='+encodeURIComponent(%(t)s));
            if(ck.code!==200) return {stage:'check',msg:String(ck.message||'').slice(0,60)};
            const au=await JP('/taskReference/coursePublishAuthentication',{encryTaskId:%(t)s,courseId:'%(cid)s'});
            return (au.code===200&&typeof au.data==='string')?{stage:'ok',url:au.data}:{stage:'auth'};
        """ % {"t": json.dumps(task_id), "cid": cid}, retry_safe=False)
        if not isinstance(r, dict) or r.get("stage") != "ok" or not _PLUGIN.match(r.get("url") or ""):
            raise XxtError(f"发布前检查未通过（{(r or {}).get('stage')}{'：' + r['msg'] if isinstance(r, dict) and r.get('msg') else ''}）；没有发布。")
        cls = self.on(M2, """
            const h=await (await fetch(%s,{credentials:'include'})).text();
            const d=new DOMParser().parseFromString(h,'text/html');
            return [...d.querySelectorAll('.classitem[data][data-token]')].map(e=>({classId:e.getAttribute('data'),className:e.getAttribute('datatitle'),token:e.getAttribute('data-token')}));
        """ % json.dumps(r["url"]))
        picked = [x for x in (cls or []) if str(x.get("classId")) in want]
        if len(picked) != len(want) or any(not re.fullmatch(r"[0-9a-f]{32}", str(x.get("token"))) for x in picked):
            raise XxtError("发布对象里找不到指定班级或缺少发布凭据；没有发布。")
        param = [{"classId": int(x["classId"]), "className": x["className"], "publishtype": 0, "token": x["token"]} for x in picked]
        p = self.on(TASK, _JS_HELPERS + "return await JP('/taskReference/taskPublish',%s);" % json.dumps(
            {"encryTaskId": task_id, "coursePublishParam": param, "taskPublishParam": None}, ensure_ascii=False), retry_safe=False)
        row = [x for x in self._task_rows(cid) if x.get("taskId") == task_id]
        ok = isinstance(p, dict) and p.get("code") == 200 and p.get("result") is True and len(row) == 1 and row[0].get("publishStatus") is True
        return {"ok": ok, "task": row[0].get("name") if row else None, "classes": [x["className"] for x in picked],
                "students": row[0].get("taskStudentsNumber") if row else None,
                **({} if ok else {"write_outcome": "unknown", "error": "发布请求已发出但列表未显示已发布；请用 list_teaching_tasks 核查，不要重复发布。"})}
