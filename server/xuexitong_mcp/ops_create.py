"""Assignment / exam creation and exam publishing (chains verified on the test course, 2026-11-07).

Assignment:  work/questionInit (workid '' for the first question, then the
returned workid) -> work/toEditWorkQuestion per question -> GET work/save-work.
Exam paper:  GET exam/createAnEmptyPaper -> exam/update-exampaper-title ->
exam/add-empty-paperquestion -> exam/editPaperTrueFalseV2 per question.
Exam publish: POST exam/test/publish.

Only true/false questions are verified end to end; other types are refused.
"""
from __future__ import annotations

import html as _h
import json
import time
import urllib.parse as up
import uuid

from .ops_write import _ok
from .xxt import M2, XxtBase, XxtError, _safe_id


def tf_questions(questions: list[dict]) -> list[dict]:
    out = []
    if not questions:
        raise XxtError("至少需要一道题。")
    for i, q in enumerate(questions, 1):
        q = dict(q or {})
        qtype = str(q.get("type") or "判断").replace("题", "")
        if qtype != "判断":
            raise XxtError(f"第 {i} 题：当前只验证了判断题的新建接口，「{qtype}」尚未验证，没有创建。")
        stem = str(q.get("stem") or "").strip()
        ans = str(q.get("answer") or "").strip()
        if not stem:
            raise XxtError(f"第 {i} 题题干为空。")
        if ans not in ("对", "错"):
            raise XxtError(f"第 {i} 题判断答案必须是 对 或 错。")
        score = float(5 if q.get("score") in (None, "") else q["score"])  # an explicit 0 must be rejected, not defaulted
        if not 0 < score <= 100:
            raise XxtError(f"第 {i} 题分值必须在 0–100 之间。")
        out.append({"stem": stem, "answer": ans, "score": score, "analysis": str(q.get("analysis") or "")})
    return out


def _j(r: dict) -> dict:
    j = r.get("json") if isinstance(r, dict) else None
    return j if isinstance(j, dict) else {}


class CreateOps(XxtBase):
    def create_work_tf(self, course: str, title: str, questions: list[dict]) -> dict:
        qs = tf_questions(questions)
        c = self.ctx(course)
        cid, clz, cpi = _safe_id(c.id), _safe_id(c.clazz_id), _safe_id(c.cpi)
        wid, done = "", 0
        for i, q in enumerate(qs, 1):
            init = self._call(M2, "/mooc2-ans/work/questionInit", "POST", {
                "courseid": cid, "clazzid": clz, "cpi": cpi, "workid": wid, "relationid": 0, "title": title, "directoryid": 0,
                "grading": 0, "questionGroup": 0, "originType": 3, "courseQuestionTypeId": 3})
            j = _j(init)
            if init.get("http") != 200 or j.get("status") is not True or not str(j.get("questionid", "")).isdigit():
                raise XxtError(f"第 {i} 题初始化失败；作业可能已部分创建（workid={wid or '未知'}），请在作业库核查，不要重复创建。")
            wid = _safe_id(j["workid"])
            e = self._call(M2, "/mooc2-ans/work/toEditWorkQuestion", "POST", {
                "queNumMaxSize": "", "courseid": cid, "clazzid": clz, "chapterId": 0, "fromChapter": 0, "workid": wid,
                "directoryid": 0, "cpi": cpi, "enc": c.enc, "grading": 0, "questionGroup": 0, "mooc": 1,
                "questionid": j["questionid"], "workLibraryRelationid": j["relationid"], "type": 3, "typeName": "判断题",
                "courseQuestionTypeId": 3, "wrapAnswer": "", "answerForTF": "true" if q["answer"] == "对" else "false",
                "title": title, "qTypeValue": 3, "updateSignal": "true", "score": f"{q['score']:.1f}",
                "content": f"<p>{_h.escape(q['stem'])}</p>",
                "answerAnalysis": f"<p>{_h.escape(q['analysis'])}</p>" if q["analysis"] else "",
                "difficulty": 0.8, "easy": 0, "topicId": 0, "schoolTopicIds": "", "labelIdArr": ""})
            if e.get("http") != 200 or _j(e).get("success") is not True:
                raise XxtError(f"第 {i} 题保存失败；作业 {wid} 已部分创建，请在作业库核查。")
            done += 1
        s = self._call(M2, "/mooc2-ans/work/save-work?" + up.urlencode({
            "courseid": cid, "clazzid": clz, "cpi": cpi, "workid": wid, "title": title, "grading": 0, "directoryid": 0,
            "workStatus": 0, "questionGroup": 0}))
        lib = [x for x in self.assignment_library_first_page(cid).get("items", []) if str(x.get("id")) == wid]
        ok = _ok(s) and len(lib) == 1 and str(lib[0].get("questions")) == str(done)
        return {"ok": ok, "library_id": wid, "title": title, "questions": done,
                **({} if ok else {"write_outcome": "unknown", "error": "作业已提交但作业库核对不一致；请在作业库核查。"})}

    def create_paper_tf(self, course: str, title: str, questions: list[dict]) -> dict:
        qs = tf_questions(questions)
        c = self.ctx(course)
        cid, clz, cpi = _safe_id(c.id), _safe_id(c.clazz_id), _safe_id(c.cpi)
        p = self._call(M2, f"/mooc2-ans/exam/createAnEmptyPaper?_={int(time.time() * 1000)}&courseid={cid}&clazzid={clz}&pid=0&parallelpaper=0")
        pid = str(_j(p).get("paperId") or "")
        if not pid.isdigit():
            raise XxtError("创建空试卷失败；没有继续。")
        t = self._call(M2, "/mooc2-ans/exam/update-exampaper-title", "POST",
                       {"courseid": cid, "clazzid": clz, "cpi": cpi, "ut": "t", "paperid": pid, "title": title})
        if not _ok(t):
            raise XxtError(f"试卷 {pid} 已创建但标题未保存；请在试卷库核查。")
        done = 0
        for i, q in enumerate(qs, 1):
            a = self._call(M2, "/mooc2-ans/exam/add-empty-paperquestion", "POST", {
                "courseid": cid, "clazzid": clz, "cpi": cpi, "ut": "t", "paperid": pid, "relationid": str(uuid.uuid4()),
                "qtype": 3, "courseQuestionTypeId": 0, "groupId": 0})
            d = _j(a).get("data") if isinstance(_j(a).get("data"), dict) else {}
            if not _ok(a) or not str(d.get("paperQuestionId", "")).isdigit():
                raise XxtError(f"第 {i} 题添加失败；试卷 {pid} 已部分创建，请在试卷库核查。")
            e = self._call(M2, "/mooc2-ans/exam/editPaperTrueFalseV2", "POST", {
                "paperid": pid, "courseid": cid, "isOpen": 1, "score": q["score"], "content": f"<p>{_h.escape(q['stem'])}</p>",
                "easy": 0, "difficulty": 0.8, "topicId": 0, "labelIdArr": "", "schoolTopicIds": "",
                "answerAnalysis": f"<p>{_h.escape(q['analysis'])}</p>" if q["analysis"] else "",
                "typeId": d["paperLibraryRelationId"], "answer": "true" if q["answer"] == "对" else "false", "type": 3,
                "questionId": d["paperQuestionId"], "targetData": ""})
            if e.get("http") != 200 or str(_j(e).get("paperQuestionId")) != str(d["paperQuestionId"]):
                raise XxtError(f"第 {i} 题保存失败；试卷 {pid} 已部分创建，请在试卷库核查。")
            done += 1
        hits = [x for x in self.papers(cid) if str(x.get("paper_id")) == pid]
        ok = len(hits) == 1 and hits[0].get("title") == title
        return {"ok": ok, "paper_id": pid, "title": title, "questions": done,
                **({} if ok else {"write_outcome": "unknown", "error": "试卷已提交但试卷库核对不一致；请在试卷库核查。"})}

    EXAM_DEFAULTS = {"makeup": 0, "blankobj": 1, "completionIngoreCase": 0, "blankIgnoreComma": 0, "multiHalfScore": 0,
                     "passingStandard": "", "retestNum": 0, "allowLookpaper": 0, "allowAnswer": 0, "allowScore": 0,
                     "allowViewRightwrong": 0, "allowPaste": 0, "phoneUploadable": 0, "forbidCloudFile": 0,
                     "forbidPhonePhoto": 0, "forbidPhoneRecording": 0, "finishStandard": 0, "submitLimitTimeMode": 0,
                     "submitLimitTime": 10, "entryLimitTime": "", "identifyCode": 0, "examCode": 0, "examCodeExpiredTime": 0,
                     "clientExam": 0, "examNotes": "", "pcExamNotes": "", "showRank": 0, "randomSort": 0, "randomOptions": 0,
                     "randomNum": 0, "switchScreenNumberLimit": 0, "switchScreenThresholdTime": 0, "forbidMultiterminal": 1,
                     "terminalFeatureVerify": 0, "terminalUnlockWay": 1, "randomDifferPaper": 0, "examInform": 1,
                     "scheduledInformTime": 0, "examNotice": "", "endNoticeTime": 0, "endNoticeTimeMinute": 0,
                     "evaluation": 0, "evaluationNum": 0, "evaluationStandard": "", "evaluationStartTime": "",
                     "evaluationEndTime": "", "anonymousSubmitter": 0, "anonymousMarker": 0, "allowIp": "", "viewTypeScore": 0,
                     "allowLookObjScore": 0, "scoreStandard": 0, "expiredAutoSubmit": 1, "switchScreenControl": 0,
                     "snapshotMonitor": 0, "snapshotInterval": 0, "notAllowExit": 1, "pcclientSwitchout": 0,
                     "keepLastAnswer": 0, "allowAnswerBack": 1, "allowDownloadAttachment": 1, "allowCopy": 0, "examTips": "",
                     "limitTimeType": 0, "questypeLimitTime": ""}
    EXAM_OPTIONS = {"allowLookpaper", "allowAnswer", "allowScore", "allowViewRightwrong", "randomSort", "randomOptions",
                    "forbidMultiterminal", "switchScreenControl", "switchScreenNumberLimit", "notAllowExit",
                    "expiredAutoSubmit", "retestNum", "passingStandard", "showRank", "allowPaste", "allowCopy",
                    "multiHalfScore"}

    def publish_exam_v3(self, course: str, paper_id: str, class_ids: list[str], start: str, end: str,
                        limit_minutes: int, options: dict | None = None) -> dict:
        c = self.ctx(course)
        opts = dict(options or {})
        bad = set(opts) - self.EXAM_OPTIONS
        if bad:
            raise XxtError(f"不支持的考试设置：{sorted(bad)}；可用：{sorted(self.EXAM_OPTIONS)}")
        if not class_ids:
            raise XxtError("必须明确指定发放班级。")
        if not 1 <= int(limit_minutes) <= 1440:
            raise XxtError("考试时长需在 1–1440 分钟之间。")
        pid = _safe_id(paper_id)
        before = {e["id"] for e in self.exams(c.id)}
        form = {**self.EXAM_DEFAULTS, **{k: int(v) if isinstance(v, bool) else v for k, v in opts.items()},
                "courseid": c.id, "clazzid": c.clazz_id, "paperid": pid, "ut": "t", "cpi": c.cpi,
                "publishObj": json.dumps([{"classid": int(_safe_id(x)), "publishType": 0} for x in class_ids]),
                "startTime": start, "endTime": end, "limitTime": int(limit_minutes)}
        r = self._call(M2, "/mooc2-ans/exam/test/publish", "POST", form)
        new = [e for e in self.exams(c.id) if e["id"] not in before and str(e.get("paper_id")) == pid]
        ok = _ok(r) and len(new) >= 1
        return {"ok": ok, "published": new,
                **({} if ok else {"write_outcome": "unknown", "error": "发布后未能核实新的考试；请用 list_exams 查看，不要重复发布。"})}
