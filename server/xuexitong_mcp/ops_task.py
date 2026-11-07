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

    def task_point_options(self, course: str, task_id: str, kind: str, keyword: str = "") -> dict:
        """What the 添加任务点 dialog of `kind` offers for this task (names and ids only)."""
        spec = POINT_KINDS.get(kind)
        if not spec:
            raise XxtError(f"任务点类型只能是：{'、'.join(POINT_KINDS)}。")
        if not re.fullmatch(r"[A-Za-z0-9@_\-]{10,80}", task_id or ""):
            raise XxtError("任务 ID 格式不对（应为 list_teaching_tasks 返回的加密 ID）。")
        c = self.ctx(course)
        lst = self.on(TASK, _JS_HELPERS + _POINT_LIST_JS % {"t": json.dumps(task_id), "pages": 4, "url": json.dumps(spec["list"]),
                                                            "key": json.dumps(str(keyword or "")[:50]), "cid": _safe_id(c.id)})
        if not isinstance(lst, dict) or lst.get("stage") != "ok":
            raise XxtError(f"读取{kind}列表失败。")
        rows = _flatten(lst["rows"]) if spec.get("tree") else [x for x in lst["rows"] if isinstance(x, dict)]
        nk, ik = spec["by"]
        return {"kind": kind, "task_points": lst.get("points"), "total": lst.get("total") if lst.get("total") is not None else len(rows),
                "items": [{"name": str(x.get(nk) or "")[:120], "id": str(x.get(ik) or "")} for x in rows][:200],
                **({"from_materials": "也可用 materials 直接把课程资料（云盘文件）加为此类任务点"} if spec.get("file") else {})}

    def add_task_points(self, course: str, task_id: str, kind: str, items: list[str] | None = None,
                        materials: list[str] | None = None) -> dict:
        """Add task points of any kind to a teaching task's first group; verified by the task's point count."""
        spec = POINT_KINDS.get(kind)
        if not spec:
            raise XxtError(f"任务点类型只能是：{'、'.join(POINT_KINDS)}。")
        if not re.fullmatch(r"[A-Za-z0-9@_\-]{10,80}", task_id or ""):
            raise XxtError("任务 ID 格式不对（应为 list_teaching_tasks 返回的加密 ID）。")
        names = [str(x).strip() for x in (items or []) if str(x).strip()]
        mats = [str(x).strip() for x in (materials or []) if str(x).strip()]
        if not names and not mats:
            raise XxtError("至少给出一个要添加的条目（items）或课程资料（materials）。")
        if mats and "file" not in spec:
            raise XxtError("只有 视频、文档、音频 可以直接用课程资料（materials）添加。")
        if len(names) + len(mats) > 50:
            raise XxtError("一次最多添加 50 个任务点。")
        c = self.ctx(course)
        cid = _safe_id(c.id)
        lst = self.on(TASK, _JS_HELPERS + _POINT_LIST_JS % {"t": json.dumps(task_id), "pages": 20 if names else 1, "url": json.dumps(spec["list"]),
                                                            "key": json.dumps(""), "cid": cid})
        if not isinstance(lst, dict) or lst.get("stage") != "ok":
            raise XxtError(f"读取任务或{kind}列表失败（{(lst or {}).get('stage') if isinstance(lst, dict) else '无结果'}）。")
        rows = _flatten(lst["rows"]) if spec.get("tree") else [x for x in lst["rows"] if isinstance(x, dict)]
        nk, ik = spec["by"]
        picked = []
        for w in names:
            hits = [x for x in rows if str(x.get(ik)) == w] or [x for x in rows if str(x.get(nk) or "").strip() == w]
            if len(hits) != 1:
                have = [str(x.get(nk) or "")[:40] for x in rows][:30]
                raise XxtError(f"「{w[:60]}」在{kind}列表里没有唯一匹配（按名称或 ID）。列表里有：{have}")
            picked.append(hits[0])
        if spec.get("check") and picked:
            chk = [{"name": o.get("name"), "courseId": o.get("courseId"), ik: o.get(ik)} for o in picked]
            r = self.on(TASK, _JS_HELPERS + "return await JP(%s,%s);" % (json.dumps(spec["check"]), json.dumps(chk, ensure_ascii=False)))
            if not isinstance(r, dict) or r.get("result") is not True:
                raise XxtError(f"任务引擎拒绝添加：{str((r or {}).get('message') or '未说明原因')[:120]}；没有添加。")
        files = []
        for m in mats:
            it = self._course_resource(c, m)
            content = it.get("content")
            try:
                content = json.loads(content) if isinstance(content, str) else (content or {})
            except ValueError:
                content = {}
            if not isinstance(content, dict) or not content.get("objectId"):
                raise XxtError(f"课程资料「{m[:60]}」不是云盘文件，不能作为{kind}任务点。")
            nm = str(it.get("dataName") or content.get("name") or kind)
            files.append({"name": nm.rsplit(".", 1)[0] if "." in nm else nm, "objectId": content["objectId"],
                          "suffix": str(content.get("suffix") or (nm.rsplit(".", 1)[1] if "." in nm else "")).replace(".", ""),
                          "cover": content.get("thumbnail") or "", "source": "云盘"})
        before = int(lst.get("points") or 0)
        extra = {"fkGroupId": lst["group"], "type": spec["type"], "fkTaskId": lst["fk"], "shareType": 0}
        r = self.on(TASK, _JS_HELPERS + """
            const made=[];
            for(const f of %(files)s){
              const a=await JP(%(furl)s,f);
              if(!a||a.result!==true||!a.data) return {stage:'file',msg:String((a&&a.message)||'').slice(0,80),made};
              made.push(a.data);
            }
            return {stage:'ok',made};
        """ % {"files": json.dumps(files, ensure_ascii=False), "furl": json.dumps(spec.get("file") or "")}, retry_safe=False) if files else {"stage": "ok", "made": []}
        if not isinstance(r, dict) or r.get("stage") != "ok":
            raise XxtError(f"把课程资料登记为{kind}失败：{(r or {}).get('msg') or '未知'}；没有添加任务点。")
        points = [{**task_point_item(kind, o), **extra} for o in picked + list(r.get("made") or [])]
        sv = self.on(TASK, _JS_HELPERS + """
            const sv=await JP('/taskPoint/saveTaskPoints',{taskPoints:%(pts)s});
            const b=await JG('/task/onMountGetTaskData?taskId='+encodeURIComponent(%(t)s));
            return {code:sv&&sv.code,result:sv&&sv.result,msg:String((sv&&sv.message)||'').slice(0,120),after:b.data&&b.data.taskPointsNumber};
        """ % {"pts": json.dumps(points, ensure_ascii=False), "t": json.dumps(task_id)}, retry_safe=False)
        after = int((sv or {}).get("after") or 0) if isinstance(sv, dict) else 0
        ok = isinstance(sv, dict) and sv.get("code") == 200 and sv.get("result") is not False and after == before + len(points)
        out = {"ok": ok, "kind": kind, "added": [p.get("name") for p in points], "task_points_before": before, "task_points_after": after}
        if not ok:
            refused = isinstance(sv, dict) and (sv.get("code") not in (200, None) or sv.get("result") is False) and after == before
            out.update(write_outcome="not_written" if refused else "unknown",
                       error=(f"服务端拒绝：{sv.get('msg') or '未说明原因'}" + ("（多半是这些条目已经在任务里，服务端去重后没有可添加的）" if "为空" in str(sv.get("msg")) else "")
                              if refused else "已提交但任务点数量不符；请用 list_teaching_tasks 核查，不要重复添加。"))
        return out

# ---------------------------------------------------------------- task points of every kind
# The 添加任务点 dialogs each load a list and turn the chosen rows into saveTaskPoints items
# (port of the editor's addTaskPointsSubmit).  type = taskPointsType; list = POST endpoint;
# by = (name field, id field) used to pick rows; mooc = the list takes moocCourseId.
_IMG = "https://p.ananas.chaoxing.com/star3/origin/"
POINT_KINDS: dict[str, dict] = {
    "作业": {"type": 4, "list": "/homework/getMoocData", "by": ("name", "workLibraryId"), "mooc": True, "check": "/homework/checkAddition"},
    "考试": {"type": 5, "list": "/exam/getMoocData", "by": ("name", "paperId"), "mooc": True, "check": "/exam/checkAddition"},
    "章节": {"type": 8, "list": "/taskChapter/getData", "by": ("name", "id"), "mooc": True, "tree": True},
    "知识点": {"type": 1, "list": "/knowledgePoints/getMoocData", "by": ("name", "knowledgePointsId"), "mooc": True},
    "主题讨论": {"type": 14, "list": "/discuss/getData", "by": ("title", "uuid"), "mooc": True},
    "分组任务": {"type": 18, "list": "/groupTask/getData", "by": ("activeName", "activeId"), "mooc": True},
    "AI课堂": {"type": 15, "list": "/aiCoach/getMoocData", "by": ("name", "relationUuid"), "mooc": True},
    "任务": {"type": 16, "list": "/taskTypeTaskPoints/getData", "by": ("name", "taskId"), "mooc": True},
    "视频": {"type": 10, "list": "/video/getData", "by": ("name", "videoId"), "file": "/video/addOrEdit"},
    "文档": {"type": 11, "list": "/document/getData", "by": ("name", "documentId"), "file": "/document/addOrEdit"},
    "音频": {"type": 22, "list": "/audio/getData", "by": ("name", "audioId"), "file": "/audio/addOrEdit"},
    "问卷": {"type": 6, "list": "/questionnaire/getData", "by": ("name", "questionnaireId")},
    "审批": {"type": 7, "list": "/examineAndApprove/getData", "by": ("name", "examineAndApproveId")},
    "测验": {"type": 13, "list": "/quizTest/getData", "by": ("name", "categoryId")},
    "自定义": {"type": 9, "list": "/customizeTaskPoints/getData", "by": ("name", "uuid")},
    "线下课堂": {"type": 2, "list": "/offlineClassroom/getData", "by": ("name", "offlineClassroomId")},
    "线上课堂": {"type": 3, "list": "/onlineClassroom/getData", "by": ("name", "onlineClassroomId")},
    "仿真": {"type": 19, "list": "/simulation/getData", "by": ("name", "simulationId")},
}


def task_point_item(kind: str, o: dict) -> dict:
    """One list row -> the item addTaskPointsSubmit builds for it (without fkGroupId/type/fkTaskId/shareType)."""
    t = POINT_KINDS[kind]["type"]
    ex = bool(o.get("exist")) if o.get("exist") is not None else False
    base = {"imageUrl": o.get("cover"), "name": o.get("name"), "exist": ex}
    if t == 4:
        return {**base, "externalDataId": o.get("workLibraryId"), "workType": o.get("workType"), "localDataId": o.get("id"),
                "desc": o.get("describe"), "courseId": o.get("courseId")}
    if t == 5:
        return {**base, "externalDataId": o.get("paperId"), "localDataId": o.get("id"), "desc": o.get("describe"),
                "courseId": o.get("courseId"), "paperType": o.get("paperType")}
    if t == 8:
        return {**base, "localDataId": "", "externalDataId": o.get("id"), "desc": "", "courseId": o.get("courseId")}
    if t == 1:
        return {**base, "externalDataId": o.get("knowledgePointsId"), "localDataId": o.get("id"), "desc": o.get("describe"),
                "courseId": o.get("courseId"), "planLabelNameList": o.get("planLabelNameList")}
    if t == 14:
        return {"imageUrl": _IMG + "1a3af242b2dda0f825c9794b86205a85.png", "name": o.get("title"), "exist": False,
                "externalDataId": o.get("uuid"), "localDataId": "", "desc": ""}
    if t == 18:
        return {"imageUrl": _IMG + "ad74b7d7f25f7150f145e0cb38e2d6db.png", "name": o.get("activeName"), "exist": bool(o.get("exist")),
                "externalDataId": o.get("activeId"), "courseId": o.get("courseId")}
    if t == 15:
        return {**base, "externalDataId": o.get("relationUuid"), "localDataId": o.get("id"), "desc": o.get("describe"), "courseId": o.get("courseId")}
    if t == 16:
        return {**base, "externalDataId": o.get("taskId"), "desc": o.get("describe")}
    if t in (10, 11, 22):
        key = {10: "videoId", 11: "documentId", 22: "audioId"}[t]
        return {**base, "localDataId": o.get("id"), "externalDataId": o.get(key), "desc": o.get("describe")}
    if t in (6, 7):
        key = {6: "questionnaireId", 7: "examineAndApproveId"}[t]
        return {**base, "externalDataId": o.get(key), "localDataId": o.get("id"), "desc": o.get("describe"), "courseId": "",
                "originalFid": o.get("originalFid")}
    if t == 13:
        return {**base, "externalDataId": o.get("categoryId"), "localDataId": o.get("id"), "desc": o.get("describe"),
                "answerUrl": o.get("answerUrl"), "manageUrl": o.get("manageUrl")}
    if t == 9:
        return {**base, "localDataId": o.get("id"), "externalDataId": o.get("uuid"), "desc": o.get("describe"),
                "customTypeId": o.get("customTypeId"), "url": o.get("url"), "courseId": o.get("courseId")}
    if t in (2, 3):
        key = {2: "offlineClassroomId", 3: "onlineClassroomId"}[t]
        return {**base, "externalDataId": o.get(key), "localDataId": o.get("id"), "desc": o.get("describe"), "courseId": o.get("courseId"),
                "classId": o.get("classId"), "startDate": o.get("startDate"), "endDate": o.get("endDate")}
    if t == 19:
        return {**base, "externalDataId": o.get("simulationId"), "localDataId": o.get("id"), "desc": o.get("describe"),
                "simulationUrl": o.get("simulationUrl")}
    raise XxtError(f"不支持的任务点类型：{kind}")


def _flatten(rows: list) -> list:
    out = []
    for r in rows or []:
        if isinstance(r, dict):
            out.append(r)
            out += _flatten(r.get("children") or [])
    return out


_POINT_LIST_JS = """
const t=await JG('/task/onMountGetTaskData?taskId='+encodeURIComponent(%(t)s));
const grp=t.data&&t.data.groups&&t.data.groups[0];
if(t.code!==200||!grp) return {stage:'load'};
const rows=[]; let total=null;
for(let p=1;p<=%(pages)d;p++){
  const j=await JP(%(url)s,{page:p,pageSize:50,searchKey:%(key)s,currTaskId:grp.fkTaskId,currentGroupId:grp.id,moocCourseId:'%(cid)s',isCheckedExist:'1'});
  if(!j||j.code!==200) return {stage:'list'};
  const d=j.data; const arr=Array.isArray(d)?d:(d&&(d.data||d.list))||[];
  rows.push(...arr); total=d&&d.total; if(Array.isArray(d)||arr.length<50) break;
}
return {stage:'ok',group:grp.id,fk:grp.fkTaskId,points:t.data.taskPointsNumber,rows,total};
"""
