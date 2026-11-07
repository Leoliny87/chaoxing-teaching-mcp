"""Read-only pages: course home (todo + alerts), 学情统计 sections, teaching calendar, download center, AI助教
(endpoints captured from the pages themselves, 2026-11-07; every one is a plain GET returning JSON).
"""
from __future__ import annotations

import json
import time

import re

from .xxt import BASE_PAGE, M2, ML, STAT, XxtBase, XxtError, _safe_id

ROBOT = "robot-lc.chaoxing.com"
BASE_PAGE.setdefault(ROBOT, "https://robot-lc.chaoxing.com/favicon.ico")

STATS: dict[str, tuple[str, list[str]]] = {
    "基础数据": (STAT, ["/stat2/base-data/v3/activeLog", "/stat2/base-data/v3/resInfo", "/stat2/base-data/v3/workInfo", "/stat2/base-data/v3/examInfo",
                    "/stat2/base-data/v3/testInfo", "/stat2/base-data/v3/bbsInfo", "/stat2/base-data/v3/activeInfo", "/stat2/base-data/v3/selfInfo",
                    "/stat2/base-data/v3/aiEvaluateInfo", "/stat2/base-data/v3/taskEngineInfo"]),
    "学情统计": (STAT, ["/stat2/teach-data/monitor", "/stat2/teach-data/pv", "/stat2/teach-data/jobnum", "/stat2/teach-data/testnum",
                    "/stat2/teach-data/worknum", "/stat2/teach-data/examnum", "/stat2/teach-data/sign", "/stat2/teach-data/points",
                    "/stat2/teach-data/bbs", "/stat2/teach-data/self-exam", "/stat2/teach-data/groupTask", "/stat2/teach-data/videoTest",
                    "/stat2/teach-data/live"]),
    "学习监控": (STAT, ["/stat2/study-monitor/v2/studyList"]),
}


def compact(v, depth: int = 0, items: int = 30):
    """Trim long lists and strings so a stats read stays readable."""
    if depth > 6:
        return "…"
    if isinstance(v, list):
        out = [compact(x, depth + 1, items) for x in v[:items]]
        return out + ([f"…另有 {len(v) - items} 项"] if len(v) > items else [])
    if isinstance(v, dict):
        return {k: compact(x, depth + 1, items) for k, x in v.items()}
    if isinstance(v, str) and len(v) > 300:
        return v[:300] + "…"
    return v


class ReadOps(XxtBase):
    def _get_many(self, host: str, paths: list[str], params: dict) -> dict:
        r = self.on(host, """
            const out={}; const q=new URLSearchParams(%s).toString();
            for(const p of %s){ try{ const r=await fetch(p+'?'+q,{credentials:'include'}); const t=await r.text();
              try{ out[p]=JSON.parse(t) }catch(e){ out[p]={http:r.status,not_json:true} } }catch(e){ out[p]={error:String(e).slice(0,80)} } }
            return out;
        """ % (json.dumps(params), json.dumps(paths)))
        if not isinstance(r, dict):
            raise XxtError("读取失败。")
        return r

    def course_home(self, course: str, cls: str = "") -> dict:
        c = self.ctx(course)
        z = _safe_id(self.resolve_class(c, cls))
        cid, cpi = _safe_id(c.id), _safe_id(c.cpi)
        a = self._get_many(M2, ["/mooc2-ans/fanya3/t/todoList"], {"courseId": cid, "cpi": cpi})
        b = self._get_many(M2, ["/mooc2-ans/work/teaching-alert", "/mooc2-ans/exam/test/exam-progress-reminder"], {"courseid": cid, "cpi": cpi})
        d = self._get_many(M2, ["/teaching-alert/stat/ai-evaluate"], {"courseid": cid, "clazzid": z, "cpi": cpi})
        s = self._get_many(STAT, ["/stat2/ai-study-alert/v3/board", "/stat2/ai-study-alert/v3/high-risk"], {"courseid": cid, "clazzid": z, "cpi": cpi, "ut": "t"})
        todo = (a.get("/mooc2-ans/fanya3/t/todoList") or {}).get("data")
        if not isinstance(todo, list):
            raise XxtError("首页待办读取失败。")
        fmt = lambda x: {"title": x.get("title"), "when": x.get("timeFormat") or x.get("sortTimeStr"), "type": x.get("type")}
        return compact({
            "class_id": z,
            "todo": [fmt(x) for x in todo],
            "assignment_alerts": (b.get("/mooc2-ans/work/teaching-alert") or {}).get("data"),
            "exam_alerts": (b.get("/mooc2-ans/exam/test/exam-progress-reminder") or {}).get("data"),
            "ai_practice_alerts": (d.get("/teaching-alert/stat/ai-evaluate") or {}).get("data"),
            "study_board": (s.get("/stat2/ai-study-alert/v3/board") or {}).get("data"),
            "high_risk": (s.get("/stat2/ai-study-alert/v3/high-risk") or {}).get("data"),
            "note": "学生姓名等是课程数据，只供教师本人查看。"})

    def learning_stats(self, course: str, cls: str, section: str) -> dict:
        c = self.ctx(course)
        z = _safe_id(self.resolve_class(c, cls))
        if section == "课堂报告":
            r = self.on(ML, """
                const uid=(document.cookie.match(/(?:^|; )_uid=(\\d+)/)||[])[1]||'';
                const q=new URLSearchParams({classId:'%(z)s',uid,stime:'',size:'20',courseId:'%(c)s',from:''});
                const j=await J('/v2/apis/course/getReportData?'+q); return j;
            """ % {"z": z, "c": _safe_id(c.id)})
            if not isinstance(r, dict):
                raise XxtError("课堂报告读取失败。")
            return {"section": section, "class_id": z, "data": compact(r.get("data", r))}
        if section not in STATS:
            raise XxtError(f"section 只能是：{'、'.join(list(STATS) + ['课堂报告'])}（学生成绩用 get_grades）。")
        host, paths = STATS[section]
        params = {"courseid": c.id, "clazzid": z, "cpi": c.cpi, "ut": "t", "pEnc": "", "enc": "", "semester": ""}
        if section == "学习监控":
            params.update(pageNo=1, pageSize=50, q="", studyStatus="", type="")
        r = self._get_many(host, paths, params)
        out = {}
        for p, j in r.items():
            name = p.rsplit("/", 1)[-1]
            out[name] = compact(j.get("data", j) if isinstance(j, dict) and "data" in j and "status" in j else j)
        if all(isinstance(v, dict) and (v.get("not_json") or v.get("error")) for v in out.values()):
            raise XxtError(f"{section}读取失败。")
        return {"section": section, "class_id": z, "data": out, "note": "统计数据含学生姓名，只供教师本人查看。"}

    def teaching_calendar(self, course: str, start: str = "", end: str = "") -> dict:
        c = self.course(course)
        s = start or time.strftime("%Y-%m-%d", time.localtime(time.time() - 7 * 86400))
        e = end or time.strftime("%Y-%m-%d", time.localtime(time.time() + 30 * 86400))
        r = self.on(M2, """
            const cal=await J('/mooc2-ans/course/calendar/list?courseId=%(c)s&cpi=%(cpi)s');
            const ids=((cal&&cal.data)||[]).map(x=>x.id).filter(Boolean);
            const sch=await J('/mooc2-ans/course/calendar/schedule/list?'+new URLSearchParams({courseId:'%(c)s',cpi:'%(cpi)s',calendarIdListStr:ids.join(','),startDate:%(s)s,endDate:%(e)s}));
            return {cal,sch};
        """ % {"c": _safe_id(c.id), "cpi": _safe_id(c.cpi), "s": json.dumps(s), "e": json.dumps(e)})
        if not isinstance(r, dict) or not isinstance(r.get("cal"), dict):
            raise XxtError("教学日历读取失败。")
        return {"from": s, "to": e, "calendars": compact((r["cal"] or {}).get("data")), "schedule": compact((r.get("sch") or {}).get("data"))}

    def download_center(self, course: str) -> list[dict]:
        c = self.course(course)
        r = self.on(M2, """
            const d=D(await F('/mooc2-ans/tcm/downloadcenter?courseid=%(c)s&cpi=%(cpi)s&courseId=%(c)s'));
            const rows=[...d.querySelectorAll('ul.dataBody_td, tr')].map(u=>[...u.querySelectorAll('li,td')].map(T).filter(Boolean)).filter(x=>x.length>=3);
            return rows.map(x=>({name:x[0],created:x[1],status:x[2]}));
        """ % {"c": _safe_id(c.id), "cpi": _safe_id(c.cpi)})
        if not isinstance(r, list):
            raise XxtError("下载中心读取失败。")
        return [x for x in r if x.get("name") not in ("文件名",)]

    def ai_assistant(self, course: str) -> dict:
        """The course's AI助教: robot settings, knowledge-base settings and the teacher's conversation list (read only)."""
        c = self.ctx(course)
        r = self.on(M2, "return await J('/mooc2-ans/coursemanagev3/base-info?courseId=%s&clazzId=%s&cpi=%s');"
                    % (_safe_id(c.id), _safe_id(c.clazz_id), _safe_id(c.cpi)))
        nav = (r or {}).get("courseNavigationListV3") or [] if isinstance(r, dict) else []
        link = next((x.get("linkUrl") for x in nav if isinstance(x, dict) and x.get("translateName") == "AI助教"), "") or ""
        if link and "robotId=" not in link and re.match(r"https://robot-lc\.chaoxing\.com/v1/front/course/goWorkbench\?", link):
            # the nav entry is a redirect (goWorkbench); the robot id is in the page it lands on
            # it answers 200 with a page that forwards by script: the robot id is in that page (or in the final URL)
            link = self.on(ROBOT, "const r=await fetch(%s,{credentials:'include'}); const t=await r.text(); return r.url+' '+t.slice(0,20000);"
                           % json.dumps(link)) or ""
        m = re.search(r"(?:robotId|courseRobotId)['\"]?\s*[=:]\s*['\"]?([0-9a-f]{32})", str(link))
        u = re.search(r"unitId['\"]?\s*[=:]\s*['\"]?(\d+)", str(link))
        if not m:
            return {"enabled": False, "note": "课程导航里没有 AI助教，或课程没有开启 AI 工作台。"}
        rid, unit = m.group(1), (u.group(1) if u else str(self.fid or ""))
        out = self.on(ROBOT, """
            const q='unitId=%(u)s&robotId=%(r)s';
            const g=async p=>{try{return await J(p)}catch(e){return {error:String(e).slice(0,60)}}};
            return {info:await g('/v1/front/robot/info/%(r)s?'+q+'&courseRole=1'),kb:await g('/v1/front/knowledge/getAiKbSetting?'+q),
              conversations:await g('/v1/front/conversationList?pageNo=1&pageSize=20&'+q)};
        """ % {"u": _safe_id(unit), "r": rid})
        if not isinstance(out, dict):
            raise XxtError("AI助教读取失败。")
        inf = (out.get("info") or {}).get("data") or {}
        robot = {k: v for k, v in inf.items() if isinstance(v, (str, int, bool)) and not re.search(r"(?i)id$|key|token|secret|enc", k)}
        return {"enabled": True, "robot": compact(dict(list(robot.items())[:15])),
                "knowledge_base": compact((out.get("kb") or {}).get("data")), "conversations": compact((out.get("conversations") or {}).get("data"))}
