"""Student side: 学习记录 and 错题集 (pages of the student course shell, verified 2026-11-08).

学习记录: stat2-ans /study-data/index?courseid&clazzid&cpi&ut=s&t&stuenc carries a hidden #pEnc; with it every
/stat2/study-data/<part>?clazzid&courseid&cpi&ut=s&pEnc is a GET returning the student's own numbers.
错题集: POST mooc2-ans /mooc2-ans/wrongque/data {clazzid, courseid, cpi, keyWord, topicArr, type, stuId} -> HTML,
one `.topic-list` per wrong question (verified live against a 200-question sample). The correct answer
(`.answer-default` "正确答案：…"), the `.option-correct`/`.option-wrong` option markers and the `.topic-analysis`
explanation ("答案解析：…") are stripped before any text is read; only the question, the student's own
`.answer-my` and the knowledge-point tag (`.topic-zhoshi-main`) survive. stuId is '0' for self-view — identity
comes from the session, not the field.
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
            const stuId=(page.querySelector('#stuId')||{}).value||'';   // '0' = self; identity comes from the session
            const h=await F('/mooc2-ans/wrongque/data',POST({clazzid:%(z)s,courseid:%(c)s,cpi:%(cpi)s,keyWord:%(k)s,topicArr:'',type:'-1',stuId}));
            const d=D(h);
            const lists=[...d.querySelectorAll('.topic-list')];
            const pick=e=>{
              const c=e.cloneNode(true);
              // The data HTML carries the correct answer (.answer-default "正确答案：…"), the
              // per-option .option-correct/.option-wrong markers and the .topic-analysis
              // explanation ("答案解析：…"). Strip all of them before reading any text; keep
              // only the knowledge-point tag (.topic-zhoshi-main), which reveals no answer.
              c.querySelectorAll('.answer-default,.topic-analysis:not(.topic-zhoshi-main),.element-invisible-hidden').forEach(x=>x.remove());
              c.querySelectorAll('.option-correct,.option-wrong').forEach(x=>x.classList.remove('option-correct','option-wrong'));
              const ts=[...c.querySelectorAll('.topic-title span')].find(s=>/^\\[.+\\]$/.test(T(s)));
              const rec=c.querySelector('.delete-con[recordId]');
              return {type:ts?T(ts):'',
                      question:T(c.querySelector('.topic-txt')).slice(0,600),
                      options:[...c.querySelectorAll('.topic-option-list .option-txt')].map(o=>T(o)),
                      my_answer:T(c.querySelector('.answer-my')).replace(/^我的答案[:：]?\\s*/,''),
                      knowledge_point:T(c.querySelector('.topic-zhoshi-main .topic-analysis-txt')),
                      record_id:rec?(rec.getAttribute('recordId')||''):''};
            };
            return {stage:'ok', empty:!lists.length||/暂无错题/.test(T(d.body)), items:lists.map(pick)};
        """ % {"q": json.dumps({"courseid": p["courseid"], "clazzid": p["clazzid"], "cpi": p["cpi"], "ut": "s", "t": p["t"], "stuenc": p["enc"]}),
               "z": json.dumps(p["clazzid"]), "c": json.dumps(p["courseid"]), "cpi": json.dumps(p["cpi"]), "k": json.dumps(str(keyword or "")[:50])})
        if not isinstance(r, dict) or r.get("stage") != "ok":
            raise XxtError("错题集读取失败。")
        items = [x for x in r.get("items") or [] if x.get("question") or x.get("options")]
        # Defense in depth: even if the platform renames its answer markup, never let an
        # answer/explanation marker survive into any field we hand back to the student.
        leak = re.compile(r"(正确答案|参考答案|标准答案|答案解析|解析[:：])")
        for x in items:
            for k in ("type", "question", "my_answer", "knowledge_point"):
                if isinstance(x.get(k), str):
                    x[k] = leak.split(x[k])[0].strip()
            x["options"] = [o for o in (leak.split(o)[0].strip() for o in x.get("options") or [] if isinstance(o, str)) if o]
        return {"course": c.name, "count": len(items), "items": items,
                "note": "只给出题目和你自己的作答，不提供正确答案和解析；要弄懂错题请自己复习或用 ask_tutor 提问。"}

    def my_course_graph(self, course: str) -> dict:
        """课程图谱 as the student sees it: stat2 /study-knowledge/index, then GET /stat2/study-knowledge/stu-detail/data
        {clazzid, courseid, cpi, ut:s, pEnc, topicName, personId=cpi, parentId} (with the page as referrer)."""
        c = self._stu_ctx(course)
        p = c.params
        q = {"courseid": p["courseid"], "clazzid": p["clazzid"], "cpi": p["cpi"], "ut": "s", "t": p["t"], "stuenc": p["enc"]}
        r = self.on(STAT, r"""
            const page='/study-knowledge/index?'+new URLSearchParams(%s);
            const d=D(await F(page)); const v=id=>(d.getElementById(id)||{}).value||'';
            if(!v('enc-courseId')) return {stage:'page'};
            const base={clazzid:v('enc-clazzId'),courseid:v('enc-courseId'),cpi:v('enc-cpi'),ut:v('enc-ut'),pEnc:v('pEnc')};
            const j=await J('/stat2/study-knowledge/stu-detail/data?'+new URLSearchParams({...base,topicName:'',personId:base.cpi,parentId:'0'}),
              {referrer:location.origin+page});
            return {stage:'ok',data:j&&j.data};
        """ % json.dumps(q))
        if not isinstance(r, dict) or r.get("stage") != "ok" or not isinstance(r.get("data"), list):
            raise XxtError("课程图谱读取失败。")
        pct = lambda x: round(float(x) * 100, 1) if isinstance(x, (int, float)) and x <= 1 else x   # noqa: E731
        out: list[dict] = []

        def walk(items, level):
            for x in items or []:
                if not isinstance(x, dict):
                    continue
                out.append({"name": x.get("topic"), "level": level,
                            "prerequisites": [y.get("name") for y in x.get("beforeList") or [] if isinstance(y, dict)],
                            "followups": [y.get("name") for y in x.get("afterList") or [] if isinstance(y, dict)],
                            "related": [y.get("name") for y in x.get("relationList") or [] if isinstance(y, dict)],
                            "completion_rate": pct(x.get("completeWeightRate")), "mastery_rate": pct(x.get("graspWeightRate")),
                            "tasks_done": f"{x.get('completeCount', 0)}/{x.get('publishCount', 0)}" if "publishCount" in x else None,
                            "materials": x.get("courseDataCount")})
                walk(x.get("childrenList"), level + 1)
        walk(r["data"], 1)
        return {"course": c.name, "count": len(out), "points": out,
                "outline": "\n".join("  " * (x["level"] - 1) + str(x["name"]) for x in out),
                "note": "完成率看知识点关联的任务点、作业、考试、章节测验的完成情况；掌握率看这些题目的得分。统计可能延迟 2 小时以内。"}
