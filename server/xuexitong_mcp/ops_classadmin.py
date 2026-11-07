"""课程管理 → 班级管理 / 教师团队 / 成绩权重 / 操作日志 (endpoints from the pages' own scripts, verified on the test
course 2026-11-07).

Class settings (GET, the switches' own handlers in classManage.js / setupClass.js; read back from
tcm/getclazzsetting?courseid&clazzid&cpi, each switch is recognised by its onclick handler):
  允许学生加入 update-enableinvitecode{enableinvitecode}  加入班级需教师同意 coursemanage/intoclazzvalidation{intoclazzvalidation}
  允许学生退课 update-clazzretire{isRetire}  忽略视频拖拽及窗口切换 update-videoctrl{ignoreVideoCtrl}
  对学生隐藏班级 updatehideclazz{hideClazz}  已结课 update-clazzstate{clazzState}  人数上限 update-stunumlimit{limitCount}
Class name: update-clazzname{courseid, clazzName, cpi, clazzid}.
Students: remove delete-clazzstu{personIds} (goes to 退课日志 tcm/drop-clazz-log, restored by
tcm/recoverystudy{personDropIds}); add from another class of this course addstubyclazz{addClazzId, clazzId}.
Teacher team: tcm/teacher-team-manage (#teamteacherContent ul.dataBody_td[uid]).
Score weights (经典模式): tcm/scoreweightdata?courseId&clazzId&cpi holds #weightForm (POST /mooc2-ans/tcm/setWeights?<form>
with body customWeightJson, classIdStr).  Join log: coursemanage/stuaddclazzlog.
"""
from __future__ import annotations

import json
import re

from .xxt import M2, XxtBase, XxtError, _safe_id

# name -> (onclick handler in getclazzsetting, endpoint, parameter, camelCase ids?)
CLASS_SWITCHES: dict[str, tuple[str, str, str, bool]] = {
    "允许学生加入": ("updateEnableInvitecode", "/mooc2-ans/tcm/update-enableinvitecode", "enableinvitecode", False),
    "加入班级需教师同意": ("updateIntoClazzValidation", "/mooc2-ans/coursemanage/intoclazzvalidation", "intoclazzvalidation", True),
    "允许学生退课": ("changeisretire", "/mooc2-ans/tcm/update-clazzretire", "isRetire", False),
    "忽略视频拖拽及窗口切换": ("ignoreVideoCtrl", "/mooc2-ans/tcm/update-videoctrl", "ignoreVideoCtrl", False),
    "对学生隐藏班级": ("hideClazz", "/mooc2-ans/tcm/updatehideclazz", "hideClazz", True),
}
# classic-mode weight form fields
WEIGHTS = {"章节任务点": "video", "章节测验": "ceyan", "作业": "work", "考试": "test", "AI实践": "aiEvaluate", "分组任务": "pbl",
           "签到": "attend", "课程积分": "active", "讨论": "bbs", "章节学习次数": "visitTime", "阅读": "readTime", "直播": "liveTime",
           "互动测验": "interactiveQuestion", "泛雅课堂": "chaoxingClassTime", "线下": "offline"}
# these need extra limits the page asks for when > 0; the tool only keeps their current value
_NEEDS_LIMIT = {"visitTime", "readTime", "liveTime", "chaoxingClassTime", "offline"}

_CLASS_READ_JS = """
const d=D(await F('/mooc2-ans/tcm/getclazzsetting?courseid=%(c)s&clazzid=%(z)s&cpi=%(cpi)s'));
const st=d.querySelector('#clazzState'); if(!st) return null;
const sw={}; for(const [k,fn] of Object.entries(%(sw)s)){const e=[...d.querySelectorAll('input[onclick]')].find(x=>(x.getAttribute('onclick')||'').startsWith(fn+'('));
  sw[k]=e?e.hasAttribute('checked'):null}
const lim=d.querySelector('.select-num');
return {switches:sw,已结课:st.getAttribute('value')==='1',人数上限:lim?Number(lim.getAttribute('value')):null};
"""


def weight_changes(current: dict, new: dict) -> dict:
    """Validate a classic-mode weight change: names known, integers 0–100, total 100; returns form-field -> value."""
    if not isinstance(new, dict) or not new:
        raise XxtError(f"weights 是 {{名称: 百分比}}，可用：{'、'.join(WEIGHTS)}。")
    out = {}
    for k, v in new.items():
        f = WEIGHTS.get(k)
        if not f:
            raise XxtError(f"没有「{k}」这一项；可用：{'、'.join(WEIGHTS)}。")
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 100:
            raise XxtError(f"「{k}」要是 0–100 的整数。")
        if f in _NEEDS_LIMIT and v > 0 and int(current.get(f) or 0) == 0:
            raise XxtError(f"「{k}」要另设计分上限，请在学习通里设置。")
        out[f] = v
    total = sum(int(current.get(f) or 0) for f in WEIGHTS.values() if f not in out) + sum(out.values())
    if total != 100:
        raise XxtError(f"各项权重之和必须是 100%，改完是 {total}%。")
    return out


class ClassAdminOps(XxtBase):
    def _cls(self, c, cls: str) -> str:
        hits = [x for x in c.classes if str(x.get("clazz_id")) == str(cls)] or [x for x in c.classes if x.get("name") == cls]
        if len(hits) != 1:
            raise XxtError(f"找不到唯一的班级「{str(cls)[:40]}」。")
        return _safe_id(hits[0]["clazz_id"])

    # ------------------------------------------------------------------ class settings
    def class_settings(self, course: str, cls: str) -> dict:
        c = self.ctx(course)
        z = self._cls(c, cls)
        r = self.on(M2, _CLASS_READ_JS % {"c": _safe_id(c.id), "z": z, "cpi": _safe_id(c.cpi),
                                          "sw": json.dumps({k: v[0] for k, v in CLASS_SWITCHES.items()}, ensure_ascii=False)})
        if not isinstance(r, dict) or all(v is None for v in (r.get("switches") or {}).values()):
            raise XxtError("班级设置读取失败。")
        return {"class_id": z, **r}

    def set_class_setting(self, course: str, cls: str, name: str, value) -> dict:
        c = self.ctx(course)
        z = self._cls(c, cls)
        before = self.class_settings(c.id, z)
        if name in CLASS_SWITCHES:
            if not isinstance(value, bool):
                raise XxtError(f"「{name}」是开关，value 用 true/false。")
            _, url, p, camel = CLASS_SWITCHES[name]
            q = {("courseId" if camel else "courseid"): c.id, ("clazzId" if camel else "clazzid"): z, "cpi": c.cpi, p: int(value)}
        elif name == "已结课":
            if not isinstance(value, bool):
                raise XxtError("「已结课」用 true（立即结课）/ false（取消结课）。")
            url, q = "/mooc2-ans/tcm/update-clazzstate", {"courseid": c.id, "clazzid": z, "cpi": c.cpi, "clazzState": int(value)}
        elif name == "人数上限":
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 20000:
                raise XxtError("人数上限是 0–20000 的整数。")
            url, q = "/mooc2-ans/tcm/update-stunumlimit", {"courseid": c.id, "clazzid": z, "cpi": c.cpi, "limitCount": value}
        else:
            raise XxtError(f"可改的班级设置：{'、'.join(list(CLASS_SWITCHES) + ['已结课', '人数上限'])}。")
        r = self.on(M2, "return await J(%s+'?'+new URLSearchParams(%s));" % (json.dumps(url), json.dumps(q)), retry_safe=False)
        after = self.class_settings(c.id, z)
        get = (lambda s: s["switches"].get(name)) if name in CLASS_SWITCHES else (lambda s: s.get(name))
        ok = isinstance(r, dict) and r.get("status") is not False and get(after) == value
        out = {"ok": ok, "class_id": z, "setting": name, "before": get(before), "after": get(after)}
        if not ok:
            refused = isinstance(r, dict) and r.get("status") is False
            out.update(write_outcome="not_written" if refused else "unknown",
                       error=f"服务端拒绝：{str(r.get('msg') or '')[:80]}" if refused else "读回的值不一致；请用 get_class_settings 核查。")
        return out

    def rename_class(self, course: str, cls: str, new_name: str) -> dict:
        n = (new_name or "").strip()
        if not n or len(n) > 100:
            raise XxtError("班级名称 1–100 字。")
        c = self.ctx(course)
        z = self._cls(c, cls)
        if any(x.get("name") == n for x in c.classes):
            raise XxtError("已有同名班级。")
        old = next(x["name"] for x in c.classes if str(x["clazz_id"]) == z)
        r = self.on(M2, "return await J('/mooc2-ans/tcm/update-clazzname?'+new URLSearchParams(%s));"
                    % json.dumps({"courseid": c.id, "clazzName": n, "cpi": c.cpi, "clazzid": z}, ensure_ascii=False), retry_safe=False)
        c2 = self.ctx(c.id, refresh=True)
        now = next((x["name"] for x in c2.classes if str(x["clazz_id"]) == z), None)
        ok = now == n
        out = {"ok": ok, "class_id": z, "old_name": old, "new_name": now}
        if not ok:
            out.update(write_outcome="unknown", error="改名后读回不一致。", server=r if isinstance(r, dict) else None)
        return out

    # ------------------------------------------------------------------ students
    def remove_students(self, course: str, cls: str, person_ids: list[str]) -> dict:
        c = self.ctx(course)
        z = self._cls(c, cls)
        ids = [_safe_id(x) for x in person_ids]
        before = {m["person_id"]: m for m in self._members(c, z)}
        if not ids or not set(ids) <= set(before):
            raise XxtError("要移除的学生必须都在这个班里；名单已变化，请重新预演。")
        r = self.on(M2, "return await J('/mooc2-ans/tcm/delete-clazzstu?'+new URLSearchParams(%s));"
                    % json.dumps({"courseid": c.id, "clazzid": z, "cpi": c.cpi, "personIds": ",".join(ids) + ","}), retry_safe=False)
        after = {m["person_id"] for m in self._members(c, z)}
        gone = [i for i in ids if i not in after]
        others_kept = (set(before) - set(ids)) <= after
        names = {before[i]["name"] for i in gone}
        logs = [x for x in self.drop_log(c.id, z) if x.get("name") in names]
        ok = isinstance(r, dict) and r.get("status") is True and len(gone) == len(ids) and others_kept
        out = {"ok": ok, "removed": [before[i]["name"] for i in gone], "class_id": z,
               "recoverable": [{"drop_id": x["drop_id"], "name": x["name"], "time": x.get("time")} for x in logs]}
        if not ok:
            out.update(write_outcome="unknown", error="移除后名单不符合预期；请用 list_students 核查。", server=r if isinstance(r, dict) else None)
        return out

    def drop_log(self, course: str, cls: str = "0") -> list[dict]:
        """退课日志 per class (the page's 全部班级 view comes back empty); the operator IP column is left out."""
        c = self.ctx(course)
        zs = [_safe_id(x["clazz_id"]) for x in c.classes] if str(cls) == "0" else [self._cls(c, cls)]
        r = self.on(M2, """
            const out=[];
            for(const z of %(zs)s){
              const d=D(await F('/mooc2-ans/tcm/drop-clazz-log?courseId=%(c)s&clazzId='+z+'&cpi=%(cpi)s&kw=&pageNum=1'));
              if(!d.querySelector('#recoverDropIds')) return null;
              for(const u of d.querySelectorAll('ul.dataBody_td')){ const li=[...u.querySelectorAll(':scope>li')].map(T); const b=u.querySelector('.recoverystudy[data]');
                if(b) out.push({drop_id:b.getAttribute('data'),class_id:z,name:li[1],class:li[2],action:li[3],time:li[5]}); }
            }
            return out;
        """ % {"c": _safe_id(c.id), "zs": json.dumps(zs), "cpi": _safe_id(c.cpi)})
        if not isinstance(r, list):
            raise XxtError("退课日志读取失败。")
        return r

    def recover_students(self, course: str, drop_ids: list[str]) -> dict:
        c = self.ctx(course)
        ids = [_safe_id(x) for x in drop_ids]
        log = {str(x.get("drop_id")): x for x in self.drop_log(c.id)}
        if not ids or not set(ids) <= set(log):
            raise XxtError("退课日志里没有这些记录；请用 list_class_logs 查看。")
        r = self.on(M2, "return await J('/mooc2-ans/tcm/recoverystudy?'+new URLSearchParams(%s));"
                    % json.dumps({"courseid": c.id, "personDropIds": ",".join(ids), "cpi": c.cpi}), retry_safe=False)
        left = {str(x.get("drop_id")) for x in self.drop_log(c.id)}
        back = {}
        for i in ids:
            z = log[i]["class_id"]
            back[i] = any(m["name"] == log[i]["name"] for m in self._members(c, z))
        ok = isinstance(r, dict) and r.get("status") is True and not (set(ids) & left) and all(back.values())
        out = {"ok": ok, "recovered": [{"name": log[i]["name"], "class": log[i]["class"], "in_class_again": back[i]} for i in ids]}
        if not ok:
            out.update(write_outcome="unknown", error="恢复后退课日志里还有这些记录；请用 list_students 核查。", server=r if isinstance(r, dict) else None)
        return out

    def add_students_from_class(self, course: str, to_cls: str, from_cls: str) -> dict:
        c = self.ctx(course)
        z, src = self._cls(c, to_cls), self._cls(c, from_cls)
        if z == src:
            raise XxtError("两个班级相同。")
        want = {m["person_id"]: m["name"] for m in self._members(c, src)}
        if not want:
            raise XxtError("来源班级没有学生。")
        r = self.on(M2, "return await J('/mooc2-ans/tcm/addstubyclazz?'+new URLSearchParams(%s));"
                    % json.dumps({"addClazzId": src, "courseId": c.id, "clazzId": z, "cpi": c.cpi}), retry_safe=False)
        now = {m["person_id"] for m in self._members(c, z)}
        ok = isinstance(r, dict) and r.get("status") is True and set(want) <= now
        out = {"ok": ok, "class_id": z, "added": [want[i] for i in want if i in now], "server_total": (r or {}).get("total") if isinstance(r, dict) else None}
        if not ok:
            out.update(write_outcome="unknown", error="添加后名单不符合预期；请用 list_students 核查。")
        return out

    def join_log(self, course: str) -> list[dict]:
        c = self.ctx(course)
        r = self.on(M2, """
            const d=D(await F('/mooc2-ans/coursemanage/stuaddclazzlog?courseId=%(c)s&cpi=%(cpi)s&addStuType=&clazzId=0&kw=&pageNum=1'));
            if(!d.querySelector('#stuChangeLogClazzId')) return null;
            return [...d.querySelectorAll('tbody tr')].map(tr=>[...tr.querySelectorAll('td')].map(T));
        """ % {"c": _safe_id(c.id), "cpi": _safe_id(c.cpi)})
        if not isinstance(r, list):
            raise XxtError("加班日志读取失败。")
        keys = ("name", "number", "class", "how", "date")
        return [dict(zip(keys, x)) for x in r if len(x) >= 5]

    # ------------------------------------------------------------------ teacher team
    def teacher_team(self, course: str) -> list[dict]:
        c = self.course(course)
        r = self.on(M2, """
            const d=D(await F('/mooc2-ans/tcm/teacher-team-manage?courseid=%(c)s&cpi=%(cpi)s&requireTea=&orderContentTeam=ID&orderTeam=up&role=0'));
            const box=d.querySelector('#teamteacherContent'); if(!box) return null;
            return [...box.querySelectorAll('ul.dataBody_td[uid]')].map(u=>({name:T(u.querySelector('.dataBody_name')),role:T(u.querySelector('.dataBody_read')),
              number:T(u.querySelector('.dataBody_down')),department:T(u.querySelector('.dataBody_depart')),joined:T(u.querySelector('.dataBody_time .xueyinremove')),
              person_id:(u.querySelector('[personid]')||{getAttribute:()=>null}).getAttribute('personid')}));
        """ % {"c": _safe_id(c.id), "cpi": _safe_id(c.cpi)})
        if not isinstance(r, list):
            raise XxtError("教师团队读取失败（可能不是课程创建者）。")
        return r

    # ------------------------------------------------------------------ score weights
    def _weight_form(self, c, z: str) -> dict:
        r = self.on(M2, """
            const d=D(await F('/mooc2-ans/tcm/scoreweightdata?courseId=%(c)s&clazzId=%(z)s&cpi=%(cpi)s'));
            const f=d.querySelector('#weightForm'); if(!f) return null;
            const pairs=[]; for(const e of f.elements){ if(!e.name||e.disabled) continue; if((e.type==='checkbox'||e.type==='radio')&&!e.checked) continue; pairs.push([e.name,e.value]); }
            const v=s=>{const e=d.querySelector(s);return e?e.value:''};
            return {action:f.getAttribute('action'),pairs,weightType:v('#weightType'),attendType:v('#attendStatisticType'),bbsType:v('#bbsStatisticType'),
              attendAttendance:v('.attendTypeDiv .newVersion .attendAttendance'),attendLimit:v('.attendTypeDiv .oldVersion .attendLimit'),attendMinLimit:v('.attendTypeDiv .oldVersion .attendMinLimit'),
              bbsNew:[v('.bbsTypeDiv .newVersion .bbsLimit'),v('.bbsTypeDiv .newVersion .bbsReplyLimit'),v('.bbsTypeDiv .newVersion .bbsPraiseLimit')],
              bbsOld:[v('.bbsTypeDiv .oldVersion .bbsLimit'),v('.bbsTypeDiv .oldVersion .bbsReplyLimit'),v('.bbsTypeDiv .oldVersion .bbsPraiseLimit')],
              statisticVersion:v('#statisticVersion')};
        """ % {"c": _safe_id(c.id), "z": z, "cpi": _safe_id(c.cpi)})
        if not isinstance(r, dict) or r.get("action") != "/mooc2-ans/tcm/setWeights":
            raise XxtError("成绩权重读取失败（可能没有权限或班级已归档）。")
        return r

    def score_weights(self, course: str, cls: str) -> dict:
        c = self.ctx(course)
        z = self._cls(c, cls)
        f = self._weight_form(c, z)
        vals = dict(f["pairs"])
        return {"class_id": z, "mode": {"0": "经典模式"}.get(str(f.get("weightType")), f"其他模式（{f.get('weightType')}）"),
                "weights_percent": {k: int(vals.get(v) or 0) for k, v in WEIGHTS.items()}}

    def set_score_weights(self, course: str, cls: str, weights: dict) -> dict:
        c = self.ctx(course)
        z = self._cls(c, cls)
        f = self._weight_form(c, z)
        if str(f.get("weightType")) != "0":
            raise XxtError("这个班用的不是经典模式权重；请在学习通里调整。")
        vals = dict(f["pairs"])
        change = weight_changes(vals, weights)
        pairs = [(k, str(change[k]) if k in change else v) for k, v in f["pairs"]]
        if f.get("statisticVersion") == "true":
            pairs += ([("attendAttendance", f["attendAttendance"])] if str(f.get("attendType")) == "0"
                      else [("attendLimit", f["attendLimit"]), ("attendMinLimit", f["attendMinLimit"])])
            b = f["bbsNew"] if str(f.get("bbsType")) == "0" else f["bbsOld"]
            pairs += [("bbsLimit", b[0]), ("bbsReplyLimit", b[1]), ("bbsPraiseLimit", b[2])]
        at, pr = vals.get("allTaskType"), vals.get("passRateType")
        ai = 0 if (at == "1" and pr == "1") else 1 if (at == "0" and pr == "1") else 2 if at == "1" else 3
        pairs += [("cleanCustomScoreVal", "0"), ("aiEvaluateType", str(ai))]
        r = self.on(M2, """
            const q=new URLSearchParams(); for(const [k,v] of %s) q.append(k,v);
            return await J('/mooc2-ans/tcm/setWeights?'+q.toString(),POST({customWeightJson:'[]',classIdStr:'%s'}));
        """ % (json.dumps(pairs, ensure_ascii=False), z), retry_safe=False)
        now = self.score_weights(c.id, z)["weights_percent"]
        want = {k: change.get(v, int(vals.get(v) or 0)) for k, v in WEIGHTS.items()}
        ok = isinstance(r, dict) and r.get("status") is True and now == want
        out = {"ok": ok, "class_id": z, "weights_percent": now}
        if not ok:
            refused = isinstance(r, dict) and r.get("status") is False
            out.update(write_outcome="not_written" if refused else "unknown",
                       error=f"服务端拒绝：{str(r.get('msg') or '')[:80]}" if refused else "保存后读回的权重不一致；请用 get_score_weights 核查。")
        return out
