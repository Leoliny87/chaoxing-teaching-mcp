"""Class members and groups (班级管理 / 分组管理), verified on the test course 2026-11-07.

Members:  GET /mooc2-ans/tcm/clazz-student?courseid&clazzid&cpi&pageNum&pageShowNum  (HTML; rows carry personId)
调班:     GET /mooc2-ans/tcm/change-clazz?courseId&oldClazzId&newClazzId&personIds&cpi  -> {status, msg}
Groups:   GET /mooc2-ans/tcm/getclazzgroup?courseId&clazzId&cpi&clazzGroupPlanId&query (HTML, #group_<id>)
          GET /mooc2-ans/tcm/addclazzgroup?…&clsInnerGroupName                       -> {status, msg, id}
          GET /mooc2-ans/tcm/changepersongroup?courseId&classId&personIds&groupId&clazzGroupPlanId&cpi
Plans:    GET mobilelearn /v2/apis/task/getMoocGroupPlanList?classId&fid  (id 0 = the class's default plan)
          GET mobilelearn /v2/apis/task/getOneMoocGroupPlan?classId&fid&groupPlanId -> classGroupList[{id,name,studentcount}]
"""
from __future__ import annotations

import json
import re

from .xxt import M2, ML, XxtBase, XxtError, _safe_id

_MEMBERS_JS = """
const out=[];
for(let p=1;p<=50;p++){
  const h=await (await fetch('/mooc2-ans/tcm/clazz-student?courseid=%(c)s&clazzid=%(z)s&requireStu=&cpi=%(cpi)s&pageNum='+p+'&pageShowNum=100&orderContent=&schoolStatus=0&v=0&order=',{credentials:'include'})).text();
  const d=new DOMParser().parseFromString(h,'text/html');
  const trs=[...d.querySelectorAll('tr')].filter(t=>t.querySelector('[personId],[personid]')&&t.querySelectorAll('td').length>=8);
  for(const t of trs){const e=t.querySelector('[personId],[personid]');const td=t.querySelectorAll('td');
    out.push({person_id:e.getAttribute('personId')||e.getAttribute('personid'),name:(td[2]||{}).innerText?.trim()||'',student_no:(td[3]||{}).innerText?.trim()||''});}
  if(trs.length<100) break;
}
const seen=new Set(); return out.filter(x=>!seen.has(x.person_id)&&seen.add(x.person_id));
"""

_GROUPS_JS = """
const h=await (await fetch('/mooc2-ans/tcm/getclazzgroup?'+new URLSearchParams({courseId:'%(c)s',clazzId:'%(z)s',cpi:'%(cpi)s',clazzGroupPlanId:'%(plan)s',query:''}),{credentials:'include'})).text();
const d=new DOMParser().parseFromString(h,'text/html');
return [...d.querySelectorAll('[id^=group_]')].map(e=>{const t=e.innerText.replace(/\\s+/g,' ').trim();const m=t.match(/(\\d+)\\s*人/);
  return {group_id:e.id.slice(6),name:t.replace(/\\s*\\d+\\s*人.*$/,''),members:m?Number(m[1]):null};});
"""


def _pick(rows: list[dict], wanted: list[str], what: str) -> list[dict]:
    out = []
    for w in wanted:
        w = str(w).strip()
        hits = [r for r in rows if r.get("person_id") == w] or [r for r in rows if r.get("name") == w]
        if len(hits) != 1:
            raise XxtError(f"{what}里没有唯一匹配的学生「{w[:20]}」（按姓名或 person_id；重名请用 person_id）。")
        out.append(hits[0])
    return out


class ClassOps(XxtBase):
    def _members(self, c, cls: str) -> list[dict]:
        r = self.on(M2, _MEMBERS_JS % {"c": _safe_id(c.id), "z": _safe_id(cls), "cpi": _safe_id(c.cpi)})
        if not isinstance(r, list):
            raise XxtError("班级学生名单读取失败。")
        return r

    def _class_id(self, c, name_or_id: str) -> str:
        hits = [x for x in c.classes if str(x.get("clazz_id")) == str(name_or_id)] or [x for x in c.classes if x.get("name") == name_or_id]
        if len(hits) != 1:
            raise XxtError(f"找不到唯一的班级「{str(name_or_id)[:40]}」。")
        return _safe_id(hits[0]["clazz_id"])

    def preview_move_students(self, course: str, from_class: str, to_class: str, students: list[str]) -> dict:
        c = self.ctx(course)
        a, b = self._class_id(c, from_class), self._class_id(c, to_class)
        if a == b:
            raise XxtError("原班级和目标班级相同。")
        if not students or len(students) > 200:
            raise XxtError("一次调 1–200 名学生。")
        picked = _pick(self._members(c, a), students, "原班级")
        return {"from": a, "to": b, "students": [{"person_id": p["person_id"], "name": p["name"]} for p in picked]}

    def move_students(self, course: str, from_class: str, to_class: str, students: list[str]) -> dict:
        """调班, verified by both class lists afterwards."""
        c = self.ctx(course)
        p = self.preview_move_students(course, from_class, to_class, students)
        ids = [s["person_id"] for s in p["students"]]
        r = self.on(M2, "return await J('/mooc2-ans/tcm/change-clazz?'+new URLSearchParams(%s));" % json.dumps(
            {"courseId": _safe_id(c.id), "oldClazzId": p["from"], "newClazzId": p["to"], "personIds": ",".join(ids), "cpi": _safe_id(c.cpi)}),
            retry_safe=False)
        now_to = {m["person_id"] for m in self._members(c, p["to"])}
        now_from = {m["person_id"] for m in self._members(c, p["from"])}
        ok = isinstance(r, dict) and r.get("status") is True and all(i in now_to and i not in now_from for i in ids)
        out = {"ok": ok, "moved": [s["name"] for s in p["students"]], "to_class": p["to"]}
        if not ok:
            out.update(write_outcome="unknown", server=(r or {}).get("msg") if isinstance(r, dict) else None,
                       error="调班后两个班的名单不符合预期；请用 list_students 核查。")
        return out

    def group_plans(self, c, cls: str) -> list[dict]:
        fid = self._cookie_fid()
        r = self.on(ML, "return await J('/v2/apis/task/getMoocGroupPlanList?DB_STRATEGY=RANDOM&classId=%s&fid=%s');" % (_safe_id(cls), fid))
        plans = ((r or {}).get("data") or {}).get("moocGroupPlanList") if isinstance(r, dict) else None
        if not isinstance(plans, list):
            raise XxtError("分组方案读取失败。")
        return [{"plan_id": str(p.get("id")), "name": p.get("name"), "default": bool(p.get("defaultplan"))} for p in plans]

    def _plan_groups(self, cls: str, plan_id: str) -> list[dict]:
        fid = self._cookie_fid()
        r = self.on(ML, "return await J('/v2/apis/task/getOneMoocGroupPlan?DB_STRATEGY=RANDOM&classId=%s&fid=%s&groupPlanId=%s');"
                    % (_safe_id(cls), fid, re.sub(r"[^0-9\-]", "", str(plan_id)) or "0"))
        g = ((r or {}).get("data") or {}).get("classGroupList") if isinstance(r, dict) else None
        if not isinstance(g, list):
            raise XxtError("分组方案里的小组读取失败。")
        return [{"group_id": str(x.get("id")), "name": x.get("name"), "members": int(x.get("studentcount") or 0)} for x in g]

    def _cookie_fid(self) -> str:
        if self.fid:
            return _safe_id(self.fid)
        f = self.on(ML, "return (document.cookie.match(/(?:^|; )fid=([^;]*)/)||[])[1]||'';")
        return _safe_id(f) if f else ""

    def class_groups(self, course: str, class_name: str, plan: str = "") -> dict:
        c = self.ctx(course)
        cls = self._class_id(c, class_name)
        plans = self.group_plans(c, cls)
        pl = self._plan_of(plans, plan)
        return {"class_id": cls, "plans": plans, "plan": pl, "groups": self._plan_groups(cls, pl["plan_id"])}

    @staticmethod
    def _plan_of(plans: list[dict], plan: str) -> dict:
        if not plan:
            d = [p for p in plans if p["default"]] or plans[:1]
            if not d:
                raise XxtError("这个班没有分组方案。")
            return d[0]
        hits = [p for p in plans if p["plan_id"] == str(plan)] or [p for p in plans if p["name"] == plan]
        if len(hits) != 1:
            raise XxtError(f"找不到唯一的分组方案「{plan[:40]}」。可选：{[p['name'] for p in plans]}")
        return hits[0]

    def create_group(self, course: str, class_name: str, name: str, plan: str = "") -> dict:
        c = self.ctx(course)
        cls = self._class_id(c, class_name)
        name = (name or "").strip()
        if not name or len(name) > 30:
            raise XxtError("小组名称需为 1–30 字。")
        pl = self._plan_of(self.group_plans(c, cls), plan)
        args = {"c": _safe_id(c.id), "z": cls, "cpi": _safe_id(c.cpi), "plan": re.sub(r"[^0-9]", "", pl["plan_id"]) or "0"}
        if any(g["name"] == name for g in self.on(M2, _GROUPS_JS % args) or []):
            raise XxtError("已有同名小组；没有新建。")
        r = self.on(M2, "return await J('/mooc2-ans/tcm/addclazzgroup?'+new URLSearchParams(%s));" % json.dumps(
            {"courseId": args["c"], "clazzId": cls, "cpi": args["cpi"], "clazzGroupPlanId": args["plan"], "clsInnerGroupName": name},
            ensure_ascii=False), retry_safe=False)
        new = [g for g in self.on(M2, _GROUPS_JS % args) or [] if g["name"] == name]
        ok = isinstance(r, dict) and r.get("status") is True and len(new) == 1
        return {"ok": ok, "group": new[0] if new else None, "plan": pl["name"],
                **({} if ok else {"write_outcome": "unknown", "error": "新建后没有在分组列表里核实到唯一的新小组。"})}

    def assign_group(self, course: str, class_name: str, group: str, students: list[str], plan: str = "") -> dict:
        c = self.ctx(course)
        cls = self._class_id(c, class_name)
        if not students or len(students) > 200:
            raise XxtError("一次分 1–200 名学生。")
        pl = self._plan_of(self.group_plans(c, cls), plan)
        args = {"c": _safe_id(c.id), "z": cls, "cpi": _safe_id(c.cpi), "plan": re.sub(r"[^0-9]", "", pl["plan_id"]) or "0"}
        groups = [g for g in self.on(M2, _GROUPS_JS % args) or [] if g["group_id"] != "0"]
        hits = [g for g in groups if g["group_id"] == str(group)] or [g for g in groups if g["name"] == group]
        if len(hits) != 1:
            raise XxtError(f"找不到唯一的小组「{str(group)[:30]}」。可选：{[g['name'] for g in groups]}")
        g = hits[0]
        picked = _pick(self._members(c, cls), students, "这个班")
        before = int(g.get("members") or 0)
        r = self.on(M2, "return await J('/mooc2-ans/tcm/changepersongroup?'+new URLSearchParams(%s));" % json.dumps(
            {"courseId": args["c"], "classId": cls, "personIds": ",".join(p["person_id"] for p in picked), "groupId": g["group_id"],
             "clazzGroupPlanId": args["plan"], "cpi": args["cpi"]}), retry_safe=False)
        after = next((x for x in self.on(M2, _GROUPS_JS % args) or [] if x["group_id"] == g["group_id"]), {})
        ok = isinstance(r, dict) and r.get("status") is True and int(after.get("members") or 0) >= min(before + len(picked), len(picked))
        return {"ok": ok, "group": g["name"], "members_now": after.get("members"), "assigned": [p["name"] for p in picked],
                **({} if ok else {"write_outcome": "unknown", "error": "分组后小组人数不符合预期；请用 list_class_groups 核查。"})}
