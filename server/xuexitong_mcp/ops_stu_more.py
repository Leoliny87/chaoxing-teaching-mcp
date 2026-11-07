"""Student side: 学习记录 and 错题集 (pages of the student course shell, verified 2026-11-08).

学习记录: stat2-ans /study-data/index?courseid&clazzid&cpi&ut=s&t&stuenc carries a hidden #pEnc; with it every
/stat2/study-data/<part>?clazzid&courseid&cpi&ut=s&pEnc is a GET returning the student's own numbers.
错题集: POST mooc2-ans /mooc2-ans/wrongque/data {clazzid, courseid, cpi, keyWord, topicArr, type, stuId} -> HTML list.
Wrong questions are returned without the correct answer or analysis (students get no answer-reading tools).
"""
from __future__ import annotations

import json
import re

from .xxt import M2, STAT, XxtError, _safe_id

PARTS = {"任务点": "job", "签到": "sign", "课程积分": "point", "成绩": "score", "作业": "work", "章节测验": "test",
         "临近截止": "nearTask", "已逾期": "behindTask", "自测": "self-exam"}


class StudentMoreOps:
    def my_study_record(self, course: str) -> dict:
        c = self._stu_ctx(course)
        p = c.params
        q = {"courseid": p["courseid"], "clazzid": p["clazzid"], "cpi": p["cpi"], "ut": "s", "t": p["t"], "stuenc": p["enc"]}
        r = self.on(STAT, """
            const page='/study-data/index?'+new URLSearchParams(%s);
            const d=D(await F(page));
            const pEnc=(d.querySelector('#pEnc')||{}).value; if(!pEnc) return {stage:'pEnc'};
            const q=new URLSearchParams({clazzid:%s,courseid:%s,cpi:%s,ut:'s',pEnc}).toString();
            const out={}; const ref={referrer:location.origin+page};   // these endpoints answer 403 without the page as referrer
            for(const [k,p] of Object.entries(%s)){ try{ const j=await J('/stat2/study-data/'+p+'?'+q,ref); out[k]=j&&j.data!==undefined&&j.status!==undefined?j.data:j }catch(e){ out[k]=null } }
            return {stage:'ok',out};
        """ % (json.dumps(q), json.dumps(p["clazzid"]), json.dumps(p["courseid"]), json.dumps(p["cpi"]), json.dumps(PARTS, ensure_ascii=False)))
        if not isinstance(r, dict) or r.get("stage") != "ok":
            raise XxtError("学习记录读取失败（签名缺失）。")
        o = r["out"]
        if all(v is None for v in o.values()):
            raise XxtError("学习记录读取失败。")
        job, sign, work, test = o.get("任务点") or {}, o.get("签到") or {}, o.get("作业") or {}, o.get("章节测验") or {}
        return {"course": c.name,
                "summary": {"任务点": f"{job.get('job', 0)}/{job.get('publishJobNum', 0)}" if isinstance(job, dict) else None,
                            "签到": {k: sign.get(k) for k in ("attendanceCount", "absenceCount", "lateCount", "allCount")} if isinstance(sign, dict) else None,
                            "作业": {k: work.get(k) for k in ("finishCount", "receivedNum", "finishPer")} if isinstance(work, dict) else None,
                            "章节测验": {k: test.get(k) for k in ("testNum", "receivedNum", "finishPer")} if isinstance(test, dict) else None},
                "detail": o, "note": "这是学生本人的学习数据。"}

    def my_wrong_questions(self, course: str, keyword: str = "") -> dict:
        c = self._stu_ctx(course)
        p = c.params
        r = self.on(M2, """
            const page=D(await F('/mooc2-ans/wrongque/page?'+new URLSearchParams(%(q)s)));
            const stuId=(page.querySelector('#stuId')||{}).value||'';
            const h=await F('/mooc2-ans/wrongque/data',POST({clazzid:%(z)s,courseid:%(c)s,cpi:%(cpi)s,keyWord:%(k)s,topicArr:'',type:'',stuId}));
            const d=D(h);
            const items=[...d.querySelectorAll('.wrong-topic-item, .questionLi, li.topic, .wrongQue, .que-item, [data-qid], [qid]')];
            const pick=e=>{ const c=e.cloneNode(true); c.querySelectorAll('.rightAnswer,.right-answer,.correctAnswer,.answerRight,.analysis,.answerAnalysis,.jiexi,[class*=right_answer],[class*=Analysis]').forEach(x=>x.remove());
              return {type:T(e.querySelector('.type,.que-type,.qtype')),text:T(c).slice(0,600)} };
            return {stage:'ok', empty:/暂无错题/.test(T(d.body))||!T(d.body), items:items.map(pick)};
        """ % {"q": json.dumps({"courseid": p["courseid"], "clazzid": p["clazzid"], "cpi": p["cpi"], "ut": "s", "t": p["t"], "stuenc": p["enc"]}),
               "z": json.dumps(p["clazzid"]), "c": json.dumps(p["courseid"]), "cpi": json.dumps(p["cpi"]), "k": json.dumps(str(keyword or "")[:50])})
        if not isinstance(r, dict) or r.get("stage") != "ok":
            raise XxtError("错题集读取失败。")
        items = [x for x in r.get("items") or [] if x.get("text")]
        # never pass on a correct answer even if the page layout changes: drop any line that announces one
        for x in items:
            x["text"] = re.split(r"(正确答案|参考答案|答案解析|解析[:：])", x["text"])[0].strip()
        return {"course": c.name, "count": len(items), "items": items,
                "note": "只给出题目和你自己的作答，不提供正确答案；请自己复习或向老师、辅导服务提问。"}
