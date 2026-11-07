"""课程设置（课程管理 → 课程管理）与自测模板（verified on the test course, 2026-11-07).

Settings page: GET mooc2-ans /mooc2-ans/tcm/getcoursesetting?courseid&cpi (HTML; each switch is an <input>
whose `checked` attribute is the saved state).  Every switch saves on its own with a GET (courseSet.js):
  updatecourseselftest{selftest} updatevideowatermark{videowatermark} updatecoursecommitment{courseCommitment}
  coursemanage/setsynactivestate{synActiveState} (read: coursemanage/getsynactivestate) visit/updatesmarkcourse{state}
  updateQueImportAllowCreateTopic updateAiQuestionExplain setaivideointerpret updateaiassistant{2|-1}
  updateportalShowAiAssistant updateallowdownload updateHiddenResourcesName updateteacherreview
  updateisprivately{0 试读全部,1 关闭,3 第一章,2 前三章} updateportaldefaultcolumn{1 详情,2 目录,3 评价}
  updatecoursestar{hiddenCourseStar: 1 关闭, 0 所有人, 2 本课学生} updatesendnoticetype{courseSendNotice,
  workSendNotice(=inbox&&chat), workSendInboxNotice, workSendChatNotice, examSendNotice}
  savecoursecommitment{content,title:""} (read getcoursecommitment)  POST updatecoursedata{courseName, teachers,
  infoContent, group1, studyModule, v, subjectId, courseUnitFid}.
Self-test template (the 自测 task point's dialog, mooc2-ans /self-test/template/create-pop?courseid&clazzid=0&type=2):
  POST /mooc2-ans/self-test/template/save {courseid, clazzid:0, cpi, id, title, type(0 模拟测验 / 1 刷题),
  templateType:2, limitTime, randomNum, questionFrom(0 题库 / 1 错题集), randomType(0 随机 / 2 按题型),
  randomTypeSet:[{selectNum,type,typeId}]} -> {status, id, title}; read back from create-pop?…&templateid=<id>
  (hidden inputs); counts from template/question-count and template/type-question.
"""
from __future__ import annotations

import json
import re

from .xxt import M2, XxtBase, XxtError, _safe_id

# name -> (selector of the switch in getcoursesetting, endpoint, parameter, on value, off value)
SWITCHES: dict[str, tuple[str, str, str, int, int]] = {
    "允许学生自测": ("#selftest", "/mooc2-ans/tcm/updatecourseselftest", "selftest", 1, 0),
    "章节视频水印": ("#videowatermark", "/mooc2-ans/tcm/updatevideowatermark", "videowatermark", 1, 0),
    "课程承诺书": ("input[name=showCourseCommitment]", "/mooc2-ans/tcm/updatecoursecommitment", "courseCommitment", 1, 0),
    "课堂活动自动保存到其他班级": ("#synActiveStateInput", "/mooc2-ans/coursemanage/setsynactivestate", "synActiveState", 1, 0),
    "标记为智慧课程": ("#setMarkSmartCourse", "/mooc2-ans/visit/updatesmarkcourse", "state", 1, 0),
    "题库导入自动新建知识点": ("#queImportAllowCreateTopicInput", "/mooc2-ans/tcm/updateQueImportAllowCreateTopic", "queImportAllowCreateTopic", 1, 0),
    "AI工作台": (".aiassistantinput", "/mooc2-ans/tcm/updateaiassistant", "aiAssistant", 2, -1),
    "学生端AI题目讲解": (".aiQuestionExplainInput", "/mooc2-ans/tcm/updateAiQuestionExplain", "aiQuestionExplain", 1, 0),
    "AI解析": (".aiVideoInterpretInput", "/mooc2-ans/tcm/setaivideointerpret", "aiVideoInterpret", 1, 0),
    "门户展示AI助教": (".portalShowAiAssistantinput", "/mooc2-ans/tcm/updateportalShowAiAssistant", "portalShowAiAssistant", 1, 0),
    "允许下载教学资源": (".allowdownloadinput", "/mooc2-ans/tcm/updateallowdownload", "allowDownload", 1, 0),
    "教学资源显示名称": (".hiddenStatus", "/mooc2-ans/tcm/updateHiddenResourcesName", "hiddenStatus", 1, 0),
    "发布评价需教师审核": (".teacherreviewinput", "/mooc2-ans/tcm/updateteacherreview", "teacherReview", 1, 0),
}
# name -> (endpoint, parameter, {label: (value, selector that is checked when this label is the saved value)})
CHOICES: dict[str, tuple[str, str, dict[str, tuple[int, str]]]] = {
    "章节试读": ("/mooc2-ans/tcm/updateisprivately", "isprivately",
             {"试读全部": (0, "#readAll"), "关闭试读": (1, "#closeRead"), "试读第一章": (3, "#readOne"), "试读前三章": (2, "#readThree")}),
    "门户默认栏目": ("/mooc2-ans/tcm/updateportaldefaultcolumn", "portaldefaultcolumn",
               {"详情": (1, "input[name=portaldefaultcolumn][value='1']"), "目录": (2, "input[name=portaldefaultcolumn][value='2']"),
                "评价": (3, "input[name=portaldefaultcolumn][value='3']")}),
    "课程评价": ("/mooc2-ans/tcm/updatecoursestar", "hiddenCourseStar",
             {"关闭": (1, ""), "所有人": (0, "input[name=coursestarstate][value='0']"), "本课学生": (2, "input[name=coursestarstate][value='2']")}),
}
NOTICES = {"开课时间通知": "#courseSendNotice", "作业收件箱通知": "#workSendInboxNotice", "作业群聊通知": "#workSendChatNotice", "考试通知": "#examSendNotice"}
TEXTS = {"课程说明": 500, "英文名称": 100, "课程承诺书内容": 5000}
# Left out on purpose: 学习监控/人脸识别/抓拍 (biometric checks on students), 学生端AI助教机器人 (needs an agreement
# accepted in a dialog), 知识共享协议, 克隆/映射/重新开课 (copies the course to other accounts), 课程密码, 课程名称
# (the write allowlist may name the course), 封面/Logo, 字幕.

_READ_JS = """
const q='courseid=%(c)s&cpi=%(cpi)s&courseId=%(c)s';
const d=D(await F('/mooc2-ans/tcm/getcoursesetting?'+q));
const on=s=>{const e=s&&d.querySelector(s);return e?e.hasAttribute('checked'):null};
const sw={}; for(const [k,s] of Object.entries(%(sw)s)) sw[k]=on(s);
let syn=null; try{const j=await J('/mooc2-ans/coursemanage/getsynactivestate?courseId=%(c)s&cpi=%(cpi)s'); if(j&&j.status) syn=j.synActiveState==1}catch(e){}
if(syn!==null) sw['课堂活动自动保存到其他班级']=syn;
const ch={}; for(const [k,v] of Object.entries(%(ch)s)){ let got=null; for(const [lab,s] of Object.entries(v)){ if(s&&on(s)) got=lab } ch[k]=got }
if(on('.coursestarinput')===false) ch['课程评价']='关闭';
if(on('.hideKnowledgeStatus')===false) ch['章节试读']='不展示章节';
const no={}; for(const [k,s] of Object.entries(%(no)s)) no[k]=on('#openCourseNot')===false?false:on(s);
const val=s=>{const e=d.querySelector(s);return e?(e.value!==undefined&&e.tagName!=='DIV'&&e.tagName!=='SPAN'?e.value:T(e)):null};
const basic={课程名称:val('#changeCourseName'),课程教师:val('#changeCourseTeachers'),英文名称:val('#changeCourseEnglish'),课程说明:(d.querySelector('#changeCourseSchools')||{}).textContent||'',
  _group1:(d.querySelector('#secondSelectInput')||{getAttribute:()=>null}).getAttribute('data-id'),_unit:(d.querySelector('#singSelectInput')||{getAttribute:()=>null}).getAttribute('data-id'),
  _v:val('#corusesetv'),_subject:val('#updateSubjectId')};
let commit=null; try{const j=await J('/mooc2-ans/tcm/getcoursecommitment?courseId=%(c)s&cpi=%(cpi)s'); commit=j&&j.content!=null?String(j.content):null}catch(e){}
return {switches:sw,choices:ch,notices:no,basic,commitment:commit};
"""


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def setting_request(name: str, value, cur: dict) -> tuple[str, str, dict]:
    """(method, endpoint, params) for one setting change; `cur` is the current read (for compound saves)."""
    if name in SWITCHES:
        if not isinstance(value, bool):
            raise XxtError(f"「{name}」是开关，value 用 true/false。")
        _, url, p, on, off = SWITCHES[name]
        return "GET", url, {p: on if value else off}
    if name in CHOICES:
        url, p, opts = CHOICES[name]
        if value not in opts:
            raise XxtError(f"「{name}」只能是：{'、'.join(opts)}。")
        return "GET", url, {p: opts[value][0]}
    if name in NOTICES:
        if not isinstance(value, bool):
            raise XxtError(f"「{name}」是开关，value 用 true/false。")
        st = dict(cur.get("notices") or {})
        if any(v is None for v in st.values()) or set(st) != set(NOTICES):
            raise XxtError("通知设置没有读全，没有修改。")
        st[name] = value
        inbox, chat = st["作业收件箱通知"], st["作业群聊通知"]
        return "GET", "/mooc2-ans/tcm/updatesendnoticetype", {
            "courseSendNotice": int(st["开课时间通知"]), "workSendNotice": int(inbox and chat), "workSendInboxNotice": int(inbox),
            "workSendChatNotice": int(chat), "examSendNotice": int(st["考试通知"])}
    if name in TEXTS:
        if not isinstance(value, str) or len(value) > TEXTS[name]:
            raise XxtError(f"「{name}」是文字，最多 {TEXTS[name]} 字。")
        if name == "课程承诺书内容":
            if not value.strip():
                raise XxtError("承诺书内容不能为空。")
            html = "".join(f"<p>{_esc(x)}</p>" for x in value.split("\n") if x.strip())
            return "POST", "/mooc2-ans/tcm/savecoursecommitment", {"content": html, "title": ""}
        b = cur.get("basic") or {}
        if not b.get("课程名称") or not b.get("课程教师"):
            raise XxtError("课程基本信息没有读全，没有修改。")
        body = {"courseName": b["课程名称"], "teachers": b["课程教师"], "infoContent": b.get("课程说明") or "", "group1": b.get("_group1") or "",
                "studyModule": b.get("英文名称") or "", "v": b.get("_v") or "0", "subjectId": b.get("_subject") or "", "courseUnitFid": b.get("_unit") or ""}
        body["infoContent" if name == "课程说明" else "studyModule"] = value
        return "POST", "/mooc2-ans/tcm/updatecoursedata", body
    raise XxtError(f"不支持的设置：{name}。可改：{'、'.join(list(SWITCHES) + list(CHOICES) + list(NOTICES) + list(TEXTS))}")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def read_value(name: str, cur: dict):
    for sec in ("switches", "choices", "notices"):
        if name in (cur.get(sec) or {}):
            return cur[sec][name]
    if name == "课程承诺书内容":
        return _strip_html(cur.get("commitment") or "")
    return (cur.get("basic") or {}).get(name)


def selftest_form(course_id: str, cpi: str, item: dict, type_counts: list[dict], total: int) -> dict:
    """The self-test template dialog's save body for one new_items entry (validated against the bank's counts)."""
    if not isinstance(item, dict):
        raise XxtError("自测的 new_items 每项是 {name, mode, minutes, count | by_type, source}。")
    title = str(item.get("name") or "").strip()
    if not title or len(title) > 100:
        raise XxtError("自测标题需为 1–100 字。")
    mode = str(item.get("mode") or "模拟测验")
    if mode not in ("模拟测验", "刷题"):
        raise XxtError("自测模式只能是 模拟测验（交卷后看答案，限时）或 刷题（每题做完看答案）。")
    source = str(item.get("source") or "题库")
    if source not in ("题库", "错题集"):
        raise XxtError("题目来源只能是 题库 或 错题集。")
    minutes = item.get("minutes")
    if mode == "模拟测验" and (not isinstance(minutes, int) or not 1 <= minutes <= 999999):
        raise XxtError("模拟测验要给 minutes（自测时间，分钟）。")
    by_type = item.get("by_type") or {}
    rtype, rset, num = 0, "", item.get("count")
    if by_type:
        if source != "题库":
            raise XxtError("按题型抽题只适用于题库来源。")
        names = {re.sub(r"题$", "", x["name"]): x for x in type_counts}
        sel = []
        for k, n in by_type.items():
            t = names.get(re.sub(r"题$", "", str(k)))
            if not t:
                raise XxtError(f"题库里没有「{k}」；有：{'、'.join(names)}。")
            if not isinstance(n, int) or not 1 <= n <= int(t["total"]):
                raise XxtError(f"「{k}」最多抽 {t['total']} 道。")
            sel.append({"selectNum": n, "type": int(t["data"]), "typeId": int(t["typeId"])})
        rtype, rset, num = 2, json.dumps(sel, separators=(",", ":")), sum(x["selectNum"] for x in sel)
    elif not isinstance(num, int) or num < 1:
        raise XxtError("给出抽题数量 count，或按题型 by_type（如 {\"单选\": 3}）。")
    elif source == "题库" and num > total:
        raise XxtError(f"题库只有 {total} 道题，抽题数量不能超过它。")
    if num > 500:
        raise XxtError("抽题数量不能大于 500 道。")
    return {"courseid": course_id, "clazzid": "0", "cpi": cpi, "id": "", "title": title, "type": "0" if mode == "模拟测验" else "1",
            "templateType": "2", "limitTime": str(minutes if mode == "模拟测验" else ""), "randomNum": str(num),
            "questionFrom": "0" if source == "题库" else "1", "randomType": str(rtype), "randomTypeSet": rset}


class SettingsOps(XxtBase):
    def course_settings(self, course: str) -> dict:
        c = self.course(course)
        r = self.on(M2, _READ_JS % {"c": _safe_id(c.id), "cpi": _safe_id(c.cpi), "sw": json.dumps({k: v[0] for k, v in SWITCHES.items()}),
                                   "ch": json.dumps({k: {lab: s for lab, (_, s) in v[2].items()} for k, v in CHOICES.items()}, ensure_ascii=False),
                                   "no": json.dumps(NOTICES, ensure_ascii=False)})
        if not isinstance(r, dict) or not isinstance(r.get("switches"), dict) or all(v is None for v in r["switches"].values()):
            raise XxtError("课程设置页读取失败或结构不完整（可能不是本课程的创建者）。")
        return r

    def set_course_setting(self, course: str, name: str, value) -> dict:
        c = self.course(course)
        before = self.course_settings(c.id)
        method, url, params = setting_request(name, value, before)
        base = {"courseid": c.id} if url.endswith("updatesmarkcourse") else {"courseId": c.id}
        q = {**base, "cpi": c.cpi, **params}
        r = self.on(M2, """
            const q=%(q)s; let t;
            if(%(post)s) t=await F(%(u)s,POST(q)); else t=await F(%(u)s+'?'+new URLSearchParams(q));
            try{return JSON.parse(t)}catch(e){return {raw:t.slice(0,80)}}
        """ % {"q": json.dumps(q, ensure_ascii=False), "u": json.dumps(url), "post": "true" if method == "POST" else "false"}, retry_safe=False)
        after = self.course_settings(c.id)
        got = read_value(name, after)
        want = _strip_html(value) if name == "课程承诺书内容" else value
        ok = isinstance(r, dict) and r.get("status") is not False and got == want
        out = {"ok": ok, "setting": name, "before": read_value(name, before), "after": got}
        if not ok:
            refused = isinstance(r, dict) and r.get("status") is False and got == out["before"]
            out.update(write_outcome="not_written" if refused else "unknown",
                       error=(f"服务端拒绝：{str(r.get('msg') or '未说明原因')[:80]}" if refused else "已提交但读回的值不一致；请用 get_course_settings 核查。"))
        return out

    def _selftest_options(self, c) -> dict:
        r = self.on(M2, """
            const q='courseid=%(c)s&clazzid=0&cpi=%(cpi)s';
            const n=await J('/mooc2-ans/self-test/template/question-count?'+q);
            const d=D(await F('/mooc2-ans/self-test/template/type-question?'+q+'&randomTypeSet='));
            return {total:n&&n.status?n.count:null,types:[...d.querySelectorAll('.typeQueNum')].map(e=>({data:e.getAttribute('data'),typeId:e.getAttribute('typeId'),
              total:T(e.nextElementSibling),name:T(e.closest('li')&&e.closest('li').querySelector('p'))}))};
        """ % {"c": _safe_id(c.id), "cpi": _safe_id(c.cpi)})
        if not isinstance(r, dict) or r.get("total") is None:
            raise XxtError("读取题库题量失败，没有新建自测。")
        return r

    def create_selftest_templates(self, c, items: list[dict]) -> list[dict]:
        """Create the self-test templates the 自测 task point dialog creates; each is read back before it is used."""
        opts = self._selftest_options(c)
        forms = [selftest_form(c.id, c.cpi, x, opts["types"], int(opts["total"])) for x in items]
        r = self.on(M2, """
            const made=[];
            for(const f of %(f)s){
              const s=await J('/mooc2-ans/self-test/template/save',POST(f));
              if(!s||!s.status||!s.id) return {stage:'save',msg:String((s&&s.msg)||'').slice(0,80),made};
              const d=D(await F('/mooc2-ans/self-test/template/create-pop?courseid='+f.courseid+'&clazzid=0&type=2&templateid='+s.id));
              const v=id=>(d.getElementById(id)||{}).value;
              made.push({id:s.id,title:s.title,back:{title:(d.getElementById('title')||{}).value,randomNum:v('randomNum'),limitTime:v('limitTime'),
                questionFrom:v('questionFrom'),randomType:v('randomType')}});
            }
            return {stage:'ok',made};
        """ % {"f": json.dumps(forms, ensure_ascii=False)}, retry_safe=False)
        if not isinstance(r, dict) or r.get("stage") != "ok":
            raise XxtError(f"新建自测模板失败：{(r or {}).get('msg') or '未知'}（已建 {len((r or {}).get('made') or [])} 个）；没有添加任务点。")
        for f, m in zip(forms, r["made"]):
            b = m.get("back") or {}
            if b.get("title") != f["title"] or str(b.get("randomNum")) != f["randomNum"] or str(b.get("questionFrom")) != f["questionFrom"]:
                raise XxtError(f"自测模板「{f['title']}」已保存但读回不一致；没有添加任务点。")
        return r["made"]
