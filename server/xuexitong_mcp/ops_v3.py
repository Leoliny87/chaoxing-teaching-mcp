"""新版（fanyav3 Vue 外壳）教师端只读能力。

接口来源：2026-11-06 对新版教师端的只读探查（见 docs/COVERAGE.md）。所有请求都是
页面自己使用的同源 GET 接口，经 ``XxtBase.on`` 从对应域名的静态基准页发起。

* 课程外壳信息 ``coursemanagev3/base-info``：模块菜单、通知和讨论入口（含 bbsid）、
  活动班级。其他功能都从这里定位，避免依赖旧版 iframe 结构。
* 首页看板：待办、作业和考试预警、学情预警。
* 资源中心：各库数量统计和库列表。
* 教学任务（任务引擎 task.chaoxing.com）、课件库、实践库列表。

服务端字段原样返回（列表按上限截断），只做结构校验：结构不符时报错，
不会把失败当成空列表。
"""
from __future__ import annotations

import json
import time
import urllib.parse as up
from typing import Any

from .xxt import BASE_PAGE, M2, ML, STAT, Course, XxtBase, XxtError, _safe_id

TASK = "task.chaoxing.com"
BASE_PAGE.setdefault(TASK, "https://task.chaoxing.com/css/global.css")

SHELL_TTL = 600
MAX_ITEMS = 500


def _where(url: Any) -> dict:
    """Host and path of a link; signed query values are never returned."""
    try:
        u = up.urlsplit(str(url or ""))
    except ValueError:
        return {"host": "", "path": ""}
    return {"host": u.hostname or "", "path": u.path or ""}


def _diag(item: Any) -> dict:
    """Bounded failure labels for one panel: HTTP status, error label, server code; never body text."""
    if not isinstance(item, dict):
        return {}
    out = {k: item[k] for k in ("http_status", "error") if isinstance(item.get(k), (int, str)) and len(str(item[k])) < 32}
    body = item.get("body")
    if isinstance(body, dict):
        for k in ("code", "status", "result"):
            if isinstance(body.get(k), (int, bool)):
                out[f"server_{k}"] = body[k]
    return out


def _cap(v: Any) -> Any:
    if isinstance(v, list):
        return [_cap(x) for x in v[:MAX_ITEMS]]
    if isinstance(v, dict):
        return {k: _cap(x) for k, x in v.items()}
    return v


# One JS helper that fetches several same-origin JSON endpoints and reports each
# separately, so one failing panel does not hide the others.
_MULTI = r"""
const out={};
for(const [k,u] of Object.entries(%s)){
  try{const r=await fetch(u,{credentials:'include'}); if(!r.ok){out[k]={ok:false,http_status:r.status};continue}
      const t=await r.text(); let j; try{j=JSON.parse(t)}catch(e){out[k]={ok:false,error:'not_json'};continue}
      out[k]={ok:true,body:j};}
  catch(e){out[k]={ok:false,error:'fetch_failed'}}
}
return out;"""


class V3Ops(XxtBase):
    # ================================================================ course shell
    def shell_info(self, c: Course, refresh: bool = False) -> dict:
        """Parsed ``base-info`` for a course context (cached on the Course)."""
        cached = getattr(c, "_shell", None)
        if cached and not refresh and time.time() - getattr(c, "_shell_time", 0) < SHELL_TTL:
            return cached
        if not c.clazz_id:
            c = self.ctx(c.id)
        cid, clz, cpi = _safe_id(c.id), _safe_id(c.clazz_id), _safe_id(c.cpi)
        j = self.on(M2, f"return await J('/mooc2-ans/coursemanagev3/base-info?courseId={cid}&clazzId={clz}&cpi={cpi}');")
        if (not isinstance(j, dict) or j.get("status") is not True
                or not isinstance(j.get("courseNavigationListV3"), list)):
            raise XxtError("新版课程信息（base-info）返回无效；未继续。")

        def nav(items):
            out = []
            for e in items or []:
                if not isinstance(e, dict):
                    continue
                out.append({"name": e.get("translateName"), **_where(e.get("linkUrl")),
                            "open_type": e.get("openType"), "default": e.get("isDefault") == 1,
                            "children": nav(e.get("children"))})
            return out
        info = {
            "modules": nav(j["courseNavigationListV3"]),
            "notice_url": j.get("noticeUrl") or "",
            "discuss_url": j.get("discussUrl") or "",
            "activity_clazz_id": str(j.get("activityClazzId") or c.clazz_id),
            "belong_school_id": str((j.get("courseInfo") or {}).get("belongSchoolId") or ""),
        }
        c._shell, c._shell_time = info, time.time()  # type: ignore[attr-defined]
        return info

    def course_modules(self, course: str) -> dict:
        c = self.ctx(course)
        s = self.shell_info(c, refresh=True)
        cid, clz, cpi = _safe_id(c.id), _safe_id(c.clazz_id), _safe_id(c.cpi)
        r = self.on(M2, f"return await J('/mooc2-ans/coursemanagev3/resource-info?courseId={cid}&clazzId={clz}&cpi={cpi}');")
        if not isinstance(r, dict) or r.get("status") is not True or not isinstance(r.get("data"), list):
            raise XxtError("资源中心库列表返回无效；未返回不完整结果。")
        libs = [{"name": x.get("name"), **_where(up.urljoin("https://" + STAT + "/", str(x.get("href") or "")))}
                for x in r["data"] if isinstance(x, dict)]
        return {"course_id": c.id, "name": c.name, "modules": s["modules"], "resource_libraries": libs,
                "notice_entry": _where(s["notice_url"]), "discussion_entry": _where(s["discuss_url"]),
                "has_discussion": "bbsid=" in s["discuss_url"]}

    # ================================================================ teacher home dashboard
    def dashboard(self, course: str) -> dict:
        c = self.ctx(course)
        cid, clz, cpi = _safe_id(c.id), _safe_id(c.clazz_id), _safe_id(c.cpi)
        m2 = {
            "todo": f"/mooc2-ans/fanya3/t/todoList?courseId={cid}&cpi={cpi}",
            "work_alert": f"/mooc2-ans/work/teaching-alert?courseid={cid}&cpi={cpi}",
            "exam_progress": f"/mooc2-ans/exam/test/exam-progress-reminder?courseid={cid}&cpi={cpi}",
            "ai_evaluate_alert": f"/teaching-alert/stat/ai-evaluate?courseid={cid}&clazzid={clz}&cpi={cpi}",
        }
        st = {
            "study_board": f"/stat2/ai-study-alert/v3/board?courseid={cid}&clazzid={clz}&cpi={cpi}&ut=t",
            "high_risk": f"/stat2/ai-study-alert/v3/high-risk?courseid={cid}&clazzid={clz}&cpi={cpi}&ut=t",
        }
        raw = {**(self.on(M2, _MULTI % json.dumps(m2)) or {}), **(self.on(STAT, _MULTI % json.dumps(st)) or {})}
        out: dict[str, Any] = {"course_id": c.id, "name": c.name, "class_id": c.clazz_id}
        for key in list(m2) + list(st):
            item = raw.get(key)
            if not isinstance(item, dict) or not item.get("ok") or not isinstance(item.get("body"), dict) \
                    or item["body"].get("status") is not True:
                out[key] = {"ok": False, "error": "接口返回无效或失败；此项结果未知。"}
                continue
            body = item["body"]
            if key == "todo":
                out[key] = {"ok": True, "todos": _cap(body.get("data")), "lessons": _cap(body.get("lessonData"))}
            elif key == "work_alert":
                out[key] = {"ok": True, "data": _cap({k: v for k, v in body.items() if k != "status"})}
            else:
                out[key] = {"ok": True, "data": _cap(body.get("data"))}
        out["complete"] = all(isinstance(out[k], dict) and out[k].get("ok") for k in list(m2) + list(st))
        return out

    # ================================================================ resource center
    def resource_overview(self, course: str) -> dict:
        c = self.ctx(course)
        cid, clz, cpi = _safe_id(c.id), _safe_id(c.clazz_id), _safe_id(c.cpi)
        # Observed: the resource page itself calls these with an EMPTY enc; the
        # course-page enc is rejected with HTTP 403.
        base = f"courseid={cid}&clazzid={clz}&cpi={cpi}&enc=&ut=t"
        urls = {
            "courseware": f"/stat2/base-data/v3/coursewareInfo?{base}",
            "resources": f"/stat2/base-data/v3/resInfo?{base}&semester=undefined",
            "knowledge": f"/stat2/base-data/v3/knowledgeInfo?{base}&modelStyle=undefined&modelId=undefined",
            "assignments": f"/stat2/base-data/v3/workInfo?{base}&semester=undefined",
            "exams": f"/stat2/base-data/v3/examInfo?{base}&semester=undefined",
            "activity_library": f"/stat2/base-data/v3/activityLibraryInfo?courseid={cid}&cpi={cpi}&ut=t",
        }
        raw = self.on(STAT, _MULTI % json.dumps(urls)) or {}
        out: dict[str, Any] = {"course_id": c.id, "name": c.name}
        for k in urls:
            item = raw.get(k)
            ok = isinstance(item, dict) and item.get("ok") and isinstance(item.get("body"), dict) \
                and item["body"].get("status") is True and isinstance(item["body"].get("data"), dict)
            out[k] = {"ok": True, "data": _cap(item["body"]["data"])} if ok else {"ok": False, "error": "接口返回无效或失败；此项结果未知。", **_diag(item)}
        out["complete"] = all(out[k]["ok"] for k in urls)
        return out

    # ================================================================ 教学任务（任务引擎）
    def teaching_tasks(self, course: str, page: int = 1, page_size: int = 50, deleted: bool = False) -> dict:
        c = self.course(course)
        page, page_size = max(1, int(page)), max(1, min(int(page_size), 100))
        cid = _safe_id(c.id)
        j = self.on(TASK, f"return await J('/task/getTaskDataLists?searchKey=&flag=true&courseId={cid}&isDel={1 if deleted else 0}&page={page}&pageSize={page_size}');")
        if not isinstance(j, dict) or j.get("result") is not True or not isinstance(j.get("data"), list):
            raise XxtError("教学任务列表返回无效；不能视为空列表。")
        total = j.get("total")
        return {"course_id": c.id, "name": c.name, "page": page, "page_size": page_size, "deleted": deleted,
                "total": total, "items": _cap(j["data"]),
                "has_more": isinstance(total, int) and page * page_size < total}

    # ================================================================ 课件库
    def coursewares(self, course: str, page: int = 1, page_size: int = 50, folder_id: str = "0", keyword: str = "") -> dict:
        c = self.ctx(course)
        s = self.shell_info(c)
        page, page_size = max(1, int(page)), max(1, min(int(page_size), 100))
        q = up.urlencode({"DB_STRATEGY": "COURSEID", "STRATEGY_PARA": "courseId", "classId": _safe_id(s["activity_clazz_id"]),
                          "courseId": _safe_id(c.id), "page": page, "pageSize": page_size, "parentFolderId": _safe_id(folder_id),
                          "keyWord": keyword, "createUid": "", "orderByCreateTime": -1})
        j = self.on(ML, f"return await J('/v2/apis/activePlan/getCourseWareList?{q}');")
        if not isinstance(j, dict) or j.get("result") != 1 or not isinstance((j.get("data") or {}).get("list"), list):
            raise XxtError("课件库列表返回无效；不能视为空列表。")
        d = j["data"]
        return {"course_id": c.id, "name": c.name, "page": d.get("page"), "total_pages": d.get("totalPage"),
                "total": d.get("totalCount"), "items": _cap(d["list"])}

    # ================================================================ 实践库 / 已发布实践
    def practices(self, course: str, trash: bool = False, page: int = 1, page_size: int = 50) -> dict:
        c = self.course(course)
        cid, cpi = _safe_id(c.id), _safe_id(c.cpi)
        page, page_size = max(1, int(page)), max(1, min(int(page_size), 100))
        common = f"courseid={cid}&cpi={cpi}&isTrash={'true' if trash else 'false'}&types=&ps={page_size}&pn={page}&name="
        urls = {"published": f"/mooc2-ans/ai-evaluate/v2/manage/list?{common}&filterClazzIds=&status=",
                "library": f"/mooc2-ans/ai-evaluate/v2/library/list?{common}&folderId=0"}
        raw = self.on(M2, _MULTI % json.dumps(urls)) or {}
        out: dict[str, Any] = {"course_id": c.id, "name": c.name, "trash": trash}
        for k in urls:
            item = raw.get(k)
            body = item.get("body") if isinstance(item, dict) else None
            data = body.get("data") if isinstance(body, dict) else None
            if not (isinstance(body, dict) and body.get("status") is True and isinstance(data, dict)
                    and isinstance(data.get("list"), list)):
                out[k] = {"ok": False, "error": "接口返回无效或失败；此项结果未知。"}
                continue
            out[k] = {"ok": True, "page": data.get("page"), "items": _cap(data["list"])}
        return out
