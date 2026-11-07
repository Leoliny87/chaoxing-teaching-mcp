"""Classroom activities through the endpoints the activity page itself uses (verified 2026-11-07).

All calls go from a mobilelearn page.  type 0 = save as draft (未开始), 1 = start now (students are notified).

选人     POST /v2/apis/selectperson/{saveSelectPerson|beginSelectPerson}  form
抢答     POST /v2/apis/answer/{saveAnswer|beginAnswer}?<short fields>      body: title, imgUrl, ...
投票     GET  /widget/quickvote/{saveQVote|publishActive}?1=1&question_options_<i>=A...  (index 1-4 = preset)
主题讨论 POST /v2/apis/discuss/{saveDiscuss|startDiscuss}                 form
评分     POST /v2/apis/score/saveOrStartScore (type 0/1)                    form
计时器   GET  /widget/renwu/{sa|st}  mun, sec, ascFlg/otherId (1 正计时, 0 倒计时)
"""
from __future__ import annotations

import json
import time
import uuid

from .questions import letters, normalize_list, num
from .xxt import ML, XxtBase, XxtError, _safe_id

# 随堂练习 editor (/page/quiz/addOrUpdateQuizV2): its question objects, our type id -> editor type id
QUIZ_TYPE = {0: 0, 1: 1, 2: 2, 3: 16, 4: 4}


def quiz_questions(raw: list[dict]) -> list[dict]:
    """Questions -> the editor's vm.questionList entries (shape of its own addQuestion templates)."""
    qs = normalize_list(raw, "quiz")
    if len(qs) > 100:
        raise XxtError("随堂练习一次最多 100 道题。")
    out = []
    for q in qs:
        d = {"content": q.stem_html, "rightAnswer": "", "jsonConfig": {"integralType": 2 if q.t == 4 else 1},
             "integral": num(q.score), "recArray": [], "keyUuid": str(uuid.uuid4()), "type": QUIZ_TYPE[q.t]}
        if q.t in (0, 1):
            d["answer"] = [{"name": L, "content": o, "recs": []} for L, o in zip(letters(len(q.options)), q.options)]
            d["rightAnswer"] = "".join(q.answer)
            if q.t == 1:
                d.update(amin=1, amax=len(q.options), answerAnalysis=f"1,{len(q.options)}")
        elif q.t == 2:
            d["jsonConfig"]["xposition"] = 0
            d["answer"] = [{"name": str(i), "content": a} for i, a in enumerate(q.answer, 1)]
            d["rightAnswer"] = "A"          # what the editor itself stores for blanks
        elif q.t == 3:
            d["answer"] = [{"optionPercent": 0, "name": "1", "answerNum": 0, "content": "对"},
                           {"optionPercent": 0, "name": "2", "answerNum": 0, "content": "错"}]
            d["rightAnswer"] = "对" if q.answer else "错"
        else:
            d["answer"] = [{"answer": q.answer, "recs": []}]
        out.append(d)
    return out


def quiz_form(course_id: str, class_id: str, title: str, questions: list[dict], minutes: float | None, s: dict) -> dict:
    """The form the quiz editor's 保存 (saveOrUpdate2) and 开始 (publish2) buttons post; defaults are the editor's own."""
    title = (title or "").strip()
    if not title or len(title) > 200:
        raise XxtError("标题需为 1–200 字。")
    flag = lambda k, d: 1 if s.get(k, d) else 0   # noqa: E731
    return {"questions": json.dumps(quiz_questions(questions), ensure_ascii=False, separators=(",", ":")),
            "testPaperId": "", "courseId": course_id, "classId": class_id, "planId": "", "activeId": "", "timelong": _ms(minutes),
            "isclone": "", "isCourseware": 0, "foreignType": "", "picId": "", "classroomPlanId": 0, "pageNum": "", "pageId": "",
            "isPPTLibrary": 0, "isTeachingCalendar": 0, "popPage": 0, "isLibrary": 0, "isTeachingPlanLibrary": 0,
            "ifSendToOtherClass": 0, "sendToOtherClassList": "", "fyktBigClassChatId": "", "onlyAttendForCurrentClass": 0,
            "fykbParas": "", "publishContent": "", "aTitle": title, "isscanresult": 0, "isPrompt": 0, "promptBeforeTime": 10,
            "isAutoSubmit": flag("auto_submit", True), "isSaveToReservoir": flag("save_to_bank", True), "tkDirId": "", "tkDirName": "",
            "tkDirData": "", "isLookAnswer": flag("show_answer", True), "isMultipleScore": 0, "isStuEditAnswer": flag("allow_edit", True),
            "fillBlankCaseInsensitive": flag("blank_ignore_case", False), "noAnswerPasting": flag("no_paste", False),
            "isTimedSend": 0, "releaseTime": "", "ifOpenPartialAttend": 0, "ifForbidUnsignedAttend": 0, "selectClassStudentIdListStr": ""}


QN_TYPE = {"单选": 0, "多选": 1, "简答": 4, "判断": 16}


def questionnaire_form(course_id: str, class_id: str, title: str, questions: list[dict], minutes: float | None,
                       start: bool, s: dict) -> list[tuple[str, str]]:
    """The #formId the 问卷 editor serializes for 保存 (question/saveOrUpdate) and 开始 (question/publish).

    Questions carry no answers: [{type: 单选|多选|简答|判断, stem, options: [...] (单选/多选), required: bool}].
    """
    title = (title or "").strip()
    if not title or len(title) > 200:
        raise XxtError("标题需为 1–200 字。")
    if not isinstance(questions, list) or not 1 <= len(questions) <= 100:
        raise XxtError("问卷需要 1–100 道题。")
    f: list[tuple[str, object]] = [
        ("content", title), ("activeId", ""), ("classId", class_id), ("courseId", course_id), ("hiddenClassId", ""), ("hiddenCourseId", ""),
        ("testPaperId", ""), ("questioncount", len(questions)), ("isclone", ""), ("timelong", _ms(minutes)), ("planId", ""),
        ("isCourseware", 0), ("isPPTLibrary", 0), ("isTeachingPlanLibrary", 0), ("isTeachingCalendar", 0), ("foreignType", ""),
        ("classroomPlanId", 0), ("pageNum", ""), ("pageId", ""), ("popPage", 0), ("isLibrary", 0), ("classroomDataId", 0),
        ("sendToOtherClassList", ""), ("ifSendToOtherClass", 0), ("fyktBigClassChatId", ""), ("activeLibFolderId", ""), ("fromtype", ""),
        ("questionDescription", str(s.get("description") or "")[:1000]), ("fykbParas", "")]
    for i, q in enumerate(questions, 1):
        where = f"第 {i} 题："
        if not isinstance(q, dict):
            raise XxtError(f"{where}格式应为对象。")
        t = QN_TYPE.get(str(q.get("type") or "").strip().removesuffix("题"))
        if t is None:
            raise XxtError(f"{where}问卷题型只能是：{'、'.join(QN_TYPE)}。")
        stem = str(q.get("stem") or "").strip()
        if not stem or len(stem) > 2000:
            raise XxtError(f"{where}题干需为 1–2000 字。")
        f += [(f"question_type_{i}", t), ("questionId", 0), (f"question_content_{i}", stem)]
        if t in (0, 1):
            opts = q.get("options") or []
            if not isinstance(opts, list) or not 2 <= len(opts) <= 26 or any(not str(o or "").strip() for o in opts):
                raise XxtError(f"{where}单选/多选需要 2–26 个非空选项。")
            for j, (L, o) in enumerate(zip(letters(len(opts)), opts)):
                f += [(f"question_options_{i}", L), (f"question_option_{i}_{j}", str(o).strip())]
            if t == 1:
                f.append((f"answerLimit_{i}", ""))
        elif t == 16:
            f += [(f"question_options_{i}", "1"), (f"question_option_{i}_0", "对"), (f"question_options_{i}", "2"), (f"question_option_{i}_1", "错")]
        f += [(f"knowledgePoint_{i}", ""), (f"question_ismust_{i}", 1 if q.get("required") else 0)]
    f += [("credit", int(s.get("points", 5))), ("isscanresult", 1 if s.get("show_result") else 0), ("isanony", 1 if s.get("anonymous") else 0),
          ("isPrompt", 0), ("promptBeforeTime", 10), ("isSaveToReservoir", 1 if s.get("save_to_library", True) else 0),
          ("isSaveAct", 0 if start else 1), ("wjkDirId", "")]
    return [(k, str(v)) for k, v in f]


_QN_JS = """
const f=new URLSearchParams(); for(const [k,v] of %(form)s) f.append(k,v);
if(!%(start)s){
  const g=await J('/v2/apis/active/groupPlanList?courseId='+f.get('courseId')+'&classId='+f.get('classId'));
  if(!g||g.result!=1||!g.data||!g.data.length) return {err:'没有活动分组'};
  f.set('planId', String(g.data[0].id));
}
const r=await fetch('/v2/apis/question/'+(%(start)s?'publish':'saveOrUpdate'),
  {method:'POST',credentials:'include',headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest'},body:f.toString()});
let j=null; try{j=await r.json()}catch(e){}
return {http:r.status,j};
"""


_EVAL_OTHER = {
    "teacherOtherConfig": {"partScoreForTeacher": 0, "partScoreForTeacherArray": [], "partScoreEvaluationDimensionsForTeacherArray": [],
                           "hideEvaluationForTeacher": 0, "hideEvaluationScoreForTeacher": 0, "hideEvaluationCommentForTeacher": 0},
    "withInOtherConfig": {"onlyLeaderForWithIn": 0, "evaluateAllMembersBeforeScoreForWithIn": 0, "noNameForWithIn": 0, "partScoreForWithIn": 0,
                          "partScoreForWithInArray": [], "partScoreEvaluationDimensionsForWithInArray": [], "hideEvaluationForWithIn": 0,
                          "hideEvaluationScoreForWithIn": 0, "hideEvaluationCommentForWithIn": 0, "limitEvaluationRatioForWithIn": 0,
                          "limitEvaluationRatioDetailForWithIn": []},
    "betweenOtherConfig": {"onlyLeaderForBetween": 0, "onlyLeaderForBetweenType": 0, "betweenMarkAssignGroupInfo": {}, "noNameForBetween": 0,
                           "partScoreForBetween": 0, "partScoreForBetweenArray": [], "partScoreEvaluationDimensionsForBetweenArray": [],
                           "groupNumsMarkforBetween": 0, "hideEvaluationForBetween": 0, "hideEvaluationScoreForBetween": 0,
                           "hideEvaluationCommentForBetween": 0, "limitEvaluationRatioForBetween": 0, "limitEvaluationRatioDetailForBetween": []},
    "selfOtherConfig": {"partScoreForSelf": 0, "partScoreForSelfArray": [], "partScoreEvaluationDimensionsForSelfArray": []}}
_STAR = {"partScoreStartArray": [], "evaluationOtherConfigForStar": {
    "withInOtherConfigForStar": {"noNameForWithInForStar": 0, "onlyLeaderForWithInForStar": 0},
    "betweenOtherConfigForStar": {"groupNumsMarkforBetweenForStar": 0, "onlyLeaderForBetweenForStar": 0, "noNameForBetweenForStar": 0}},
    "evaluationWeightCountForStar": {"weightSelf": 0, "weightWithInGroup": 0, "weightBetween": 0, "weightTeacher": 0},
    "isUseFiveStarEvaluation": 1, "isEmptyForFiveStarEvaluation": 0, "threeOrFiveStarEvaluationDetailArray": []}


def group_task_form(course_id: str, class_id: str, cpi: str, title: str, content: str, minutes: float | None, start: bool, s: dict) -> dict:
    """The form the 分组任务 editor's 保存 / 立即开始 (comomonVue.saveOrBegin) posts, in 不分组（个人任务）mode.

    Grouped mode needs an existing grouping plan of students; it is not offered here (the test class has no students).
    """
    from .questions import p as _p
    title = (title or "").strip()
    if not title or len(title) > 200:
        raise XxtError("标题需为 1–200 字。")
    if len(content or "") > 20000:
        raise XxtError("任务内容最多 20000 字。")
    js = lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":"))   # noqa: E731
    return {"fid": "", "classId": class_id, "courseId": course_id, "activeId": 0, "title": title, "content": _p(content),
            "planId": 0, "planName": "", "timeLong": _ms(minutes), "moocGroupPlanId": 0,
            "groupType": 3, "groupNum": 0, "maxStuNumOneGroup": 1, "isnorm": 1, "isSpecialPersonalTask": 1,
            "markType": 1 if s.get("star") else 0,
            "evaluationWeightCount": js({"weightTeacher": 100, "weightWithInGroup": 0, "weightBetween": 0, "weightSelf": 0}),
            "evaluationOtherConfig": js(_EVAL_OTHER), "ifUseStarEvaluation": 1 if s.get("star") else 0, "starEvaluationDetail": js(_STAR),
            "evaluationTimeType": 1, "evaluationStartTime": "", "evaluationEndTimeType": 1, "evaluationEndTime": "", "isCourseware": 0,
            "picId": "", "beginOrSave": 1 if start else 0, "fromDetail": "", "activeLibrary": 0, "pptLibrary": 0, "classroomPlanId": "",
            "pageNum": "", "isTeachingCalendar": 0, "isTeachingPlanLibrary": 0, "isOpenTimer": 0, "isOpenPrompt": 0, "promptTime": 0,
            "onlyLeaderSubmit": 0, "isNeedSaveMarkHistory": 0, "useMarkHistoryId": 0, "ifSendToOtherClass": 0, "sendToOtherClassList": "",
            "ifOpenPartialAttend": 0, "ifForbidUnsignedAttend": 0, "selectClassStudentIdListStr": "[]", "isOpenRandomLeader": 0,
            "ifOpenViewOtherWorks": 1 if s.get("view_others") else 0, "openViewOtherWorksType": 1, "viewOtherWorksHideScore": 1,
            "ifHideStuPersonalScore": 0, "ifAllowEvaluateNoCommitTeam": 0, "popPage": 0, "parentActiveIdForPopPage": 0,
            "parentActiveIdForLibrary": 0, "libraryEdit": 0, "activeLibFolderId": "", "returnType": 1, "cpi": cpi, "fykbParas": "",
            "useNoteEditor": 1, "knowledgePoints": "", "fromtype": ""}


_TASK_JS = """
const f=new URLSearchParams(%(form)s);
f.set('fid', (document.cookie.match(/(?:^|; )fid=([^;]*)/)||[])[1]||'');
const r=await fetch('/v2/apis/task/saveOrBeginTask?DB_STRATEGY=PRIMARY_KEY&STRATEGY_PARA=activeId&DB_STRATEGY=COURSEID&STRATEGY_PARA=courseId&&DB_STRATEGY=PRIMARY_KEY&STRATEGY_PARA=classroomPlanId',
  {method:'POST',credentials:'include',headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest'},body:f.toString()});
let j=null; try{j=await r.json()}catch(e){}
return {http:r.status,j};
"""


_SUFFIX_TYPE = {**{x: 1001 for x in ("ppt", "pptx")}, "pdf": 1006,
                **{x: 1005 for x in ("mp3", "amr", "wma", "rm", "midi", "ape", "wav", "cd", "3gpp", "m4a")},
                **{x: 1004 for x in ("mp4", "avi", "mov", "wmv", "mkv", "vob", "flv", "rmvb", "m4v", "f4v", "mpg", "3gp")},
                **{x: 1002 for x in ("doc", "docx")}, **{x: 1007 for x in ("xls", "xlsx", "xlt", "xlsm")},
                **{x: 1003 for x in ("jpg", "png", "jpeg", "bmp", "gif")}, "txt": 1008}


def resource_entry(item: dict) -> dict | None:
    """Port of the activity page's dealResourceData for one 课程资料 list item (None = a type the page skips)."""
    cata = int(item.get("cataid") or 0)
    title = item.get("dataName")
    c = item.get("content")
    if isinstance(c, str):
        try:
            c = json.loads(c)
        except ValueError:
            c = {}
    c = c if isinstance(c, dict) else {}
    if cata in (100000001, 100000006):
        return {"title": title, "logo": c.get("logopath") or "", "subtitle": "", "resourceType": 1, "resourceData": item}
    if cata == 100000015:
        return {"title": title, "logo": (c.get("resLogo") or "") if c.get("logopath") else "", "subtitle": "", "resourceType": 5, "resourceData": item}
    if cata == 100000019:
        suffix = str(c.get("suffix") or "")
        rtype = _SUFFIX_TYPE.get(suffix, 1000)
        logo = (c.get("thumbnail") or "") if rtype == 1003 else ""
        return {"title": title, "logo": logo, "resourceType": rtype, "resourceData": item}
    if cata == 100000020:
        return {"title": title, "resourceType": 3, "resourceData": item}
    if cata == 100000021:
        return {"title": title, "resourceType": 4, "resourceData": item}
    if cata == 100000026:
        return {"title": title, "logo": "https://appswh.chaoxing.com/res/images/app/vclass/temp.png", "subtitle": "", "resourceData": item}
    return None


_RES_LIST_JS = """
const j=await J('/v2/apis/resource/getCourseResourceList?DB_STRATEGY=RANDOM&courseId=%(course)s&rootId=%(root)s');
if(!j||j.result!=1||!Array.isArray(j.data)) return {valid:false};
return {valid:true, items:j.data};
"""
_RES_PUSH_JS = """
const f=new URLSearchParams(%(form)s);
const r=await fetch('/v2/apis/resource/newRsourceActive?DB_STRATEGY=RANDOM',
  {method:'POST',credentials:'include',headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest'},body:f.toString()});
let j=null; try{j=await r.json()}catch(e){}
return {http:r.status,j};
"""


# 保存 needs an activity group (the page asks with a 保存到 popup; first group = its default). 开始 does not.
_QUIZ_JS = """
const f=new URLSearchParams(%(form)s);
if(!%(start)s){
  const g=await J('/v2/apis/active/groupPlanList?courseId='+f.get('courseId')+'&classId='+f.get('classId'));
  if(!g||g.result!=1||!g.data||!g.data.length) return {err:'没有活动分组'};
  f.set('planId', String(g.data[0].id));
}
const r=await fetch('/v2/apis/quiz/'+(%(start)s?'publish2':'saveOrUpdate2')+'?DB_STRATEGY=COURSEID&STRATEGY_PARA=courseId',
  {method:'POST',credentials:'include',headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest'},body:f.toString()});
let j=null; try{j=await r.json()}catch(e){}
return {http:r.status,j};
"""

KINDS = {"选人": 11, "抢答": 4, "投票": 43, "主题讨论": 5, "评分": 23, "计时器": 47, "学生反馈": 46, "白板": 49, "抽签": 80}
_COOKIE = "__COOKIE__:"   # value filled in the page from a cookie (uid / fid) right before the post
VOTE_PRESETS = {"赞同/反对": 1, "正确/错误": 2, "选A/选B": 3, "选A/选B/选C/选D": 4}
_VOTE_LABELS = {1: ["赞同", "反对"], 2: ["正确", "错误"], 3: ["A", "B"], 4: ["A", "B", "C", "D"]}
_COMMON = {"ifSendToOtherClass": 0, "sendToOtherClassList": "", "fyktBigClassChatId": "", "fykbParas": "",
           "ifOpenPartialAttend": 0, "ifForbidUnsignedAttend": 0}


def _ms(minutes: float) -> int:
    return -1 if minutes is None or minutes < 0 else int(float(minutes) * 60_000)


def build_request(kind: str, course_id: str, class_id: str, title: str, start: bool, s: dict) -> tuple[str, str, dict, dict]:
    """Return (method, path, query, form) for one activity.  Pure, so it is unit-tested."""
    if kind not in KINDS:
        raise XxtError(f"活动类型只能是：{'、'.join(KINDS)}。")
    title = (title or "").strip()
    if kind not in ("计时器", "白板", "学生反馈") and (not title or len(title) > 200):
        raise XxtError("标题/内容需为 1–200 字。")
    if len(title) > 200:
        raise XxtError("标题最多 200 字。")
    minutes = s.get("minutes", 60 if kind in ("投票", "评分", "主题讨论", "学生反馈", "白板") else 5)
    base = {"courseId": course_id, "classId": class_id}
    if kind == "选人":
        n = int(s.get("count", 1))
        if not 1 <= n <= 50:
            raise XxtError("选人人数 1–50。")
        form = {**base, "title": title, "connectWithSign": 0, "audioON": 0, "selectNumByOnce": n, "pics": "", "activeId": 0,
                "planId": "", "timeLong": _ms(minutes), **_COMMON, "selectClassStudentIdListStr": "[]", "ifOpenSelectGroup": 0,
                "currentSelectGroupPlanId": 0}
        return "POST", f"/v2/apis/selectperson/{'beginSelectPerson' if start else 'saveSelectPerson'}", {}, form
    if kind == "抢答":
        q = {**base, "activeId": 0, "planId": "", "timeLong": _ms(minutes), "timerSeconds": 0, "isScoreButton": 0, "credit1": 0,
             "credit2": 0, "credit3": 0, "ifSendToOtherClass": 0, "fyktBigClassChatId": "", "allowAnswerStuNum": "",
             "ifWatiStuInPosition": "", "ifAnswerNeedEnter": "", "ifCorrectAnswerReward": "", "ifOpenPartialAttend": 0,
             "ifForbidUnsignedAttend": 0}
        form = {"title": title, "imgUrl": "", "sendToOtherClassList": "", "fykbParas": "", "correctAnswerContent": "",
                "selectClassStudentIdListStr": ""}
        return "POST", f"/v2/apis/answer/{'beginAnswer' if start else 'saveAnswer'}", q, form
    if kind == "投票":
        idx = VOTE_PRESETS.get(str(s.get("options", "选A/选B/选C/选D")))
        if not idx:
            raise XxtError(f"投票选项只能是：{'、'.join(VOTE_PRESETS)}。")
        letters = "ABCD"[:len(_VOTE_LABELS[idx])]
        q = {"1": 1}
        form = {**base, "activeId": 0, "testPaperId": "", "questionId": "", "planId": "", "index": idx, "timeLong": _ms(minutes),
                "isResult": 1 if s.get("show_result") else 0, "isCourseware": 0, "title": title, "integral": int(s.get("points", 2)),
                "isPrompt": 0, "promptBeforeTime": "", "isAnony": 1 if s.get("anonymous") else 0, "classroomDataId": "", "picId": "",
                "foreignType": 1, "foreignId": "", "classroomPlanId": "", "pageNum": "", "pageId": "", "isPPTLibrary": "",
                "isTeachingCalendar": "", "selectClassStudentIdListStr": "", "isTeachingPlanLibrary": 0, "knowledgePoints": "",
                **_COMMON, **{f"question_option_{idx}_{i}": lab for i, lab in enumerate(_VOTE_LABELS[idx])}}
        q["_opts"] = [(f"question_options_{idx}", L) for L in letters]
        return "GET", f"/widget/quickvote/{'publishActive' if start else 'saveQVote'}", q, form
    if kind == "主题讨论":
        # the page turns activeId 0 into null (sent empty); 0 makes startDiscuss look up activity 0 ("未查询到活动信息")
        form = {**base, "activeName": title, "objectIds": "", "activeId": "", "timeLong": _ms(minutes), "planId": "",
                "noAllowReply": 0, "allowStudentsAnonymity": 1 if s.get("anonymous") else 0, "normalCountScores": 0,
                "allowViewReply": 0 if s.get("hide_others") else 1, "integral": int(s.get("points", 0)),
                "enableReplyWords": int(s.get("min_words", 0)), "enableReplyTimes": int(s.get("reply_times", 0)),
                "isPrompt": 0, "promptBeforeTime": "", "ifSendToOtherClass": 0, "sendToOtherClassList": "",
                "fyktBigClassChatId": "", "fykbParas": ""}
        return "POST", f"/v2/apis/discuss/{'startDiscuss' if start else 'saveDiscuss'}", {}, form
    if kind == "评分":
        items = s.get("criteria") or []
        if items and (not isinstance(items, list) or any(not isinstance(x, dict) or not str(x.get("name") or "").strip() for x in items)):
            raise XxtError("评分标准 criteria 是 [{name, score}] 列表。")
        full = float(s.get("score", sum(float(x.get("score", 0)) for x in items) or 10))
        form = {**base, "title": title, "planId": "", "normContentList": json.dumps([str(x["name"]) for x in items], ensure_ascii=False),
                "normScoreList": json.dumps([float(x.get("score", 0)) for x in items]), "timeLong": _ms(minutes),
                "isanony": 1 if s.get("anonymous") else 0, "isresult": 1 if s.get("show_result") else 0,
                "ifaveraged": 1 if s.get("average") else 0, "isnorm": 1 if items else 0, "objects": "", "type": 1 if start else 0,
                "activeId": 0, "asynKey": 0, "score": full, "ifSendToOtherClass": 0, "sendToOtherClassList": "",
                "ifOpenPartialAttend": 0, "ifForbidUnsignedAttend": 0, "selectClassStudentIdListStr": "", "fyktBigClassChatId": "",
                "fykbParas": ""}
        return "POST", "/v2/apis/score/saveOrStartScore", {}, form
    if kind == "学生反馈":
        form = {**base, "foreignId": "", "foreignType": "", "picId": "", "uid": _COOKIE + "_uid", "fid": _COOKIE + "fid",
                "planId": "", "planName": "", "activeId": "", "isCourseware": 0, "classroomDataId": "", "imgs": "",
                "title": title or "学生反馈", "timeLong": _ms(minutes), "versionType": 1, "fykbParas": ""}
        return "POST", f"/widget/CWareDataController/{'beginFeedback' if start else 'saveFeedback'}", {}, form
    if kind == "白板":
        form = {**base, "planId": "", "timelong": _ms(minutes), "activeId": "", "whiteBoardTitle": title or "白板", "fykbParas": ""}
        return "POST", f"/widget/whiteboard/{'startwb' if start else 'savewb'}", {}, form
    if kind == "抽签":
        n = int(s.get("count", 1))
        if not 1 <= n <= 50:
            raise XxtError("抽签人数 1–50。")
        form = {**base, "title": title, "selectNumByOnce": n, "pics": "", "activeId": "", "planId": 0, "timeLong": _ms(minutes),
                "isresult": 1 if s.get("show_result") else 0, "fykbParas": "", "ifSendToOtherClass": 0, "sendToOtherClassList": "",
                "score": int(s.get("points", 2)), "signatureList": "[]", "activeType": 80, "ifOpenPartialAttend": 0,
                "selectClassStudentIdListStr": "", "selectedStudentsStr": ""}
        return "POST", f"/v2/apis/drawLots/{'beginDrawLots' if start else 'saveDrawLots'}", {"DB_STRATEGY": "COURSEID", "STRATEGY_PARA": "courseId"}, form
    # 计时器
    down = bool(s.get("countdown"))
    mun, sec = int(s.get("minutes", 0) or 0), int(s.get("seconds", 0) or 0)
    if down and mun == 0 and sec == 0:
        raise XxtError("倒计时时长不能为 0。")
    q = {"mun": mun, "sec": sec, "courseId": course_id, "otherId": 0 if down else 1, "ascFlg": 0 if down else 1, "activeId": "",
         "foreignType": 0, "classId": class_id, "isCourseware": 0, "planId": "", "classroomDataId": "", "picId": 0, "foreignId": 0,
         "classroomPlanId": "", "pageNum": "", "pageId": "", "fykbParas": ""}
    return "GET", f"/widget/renwu/{'st' if start else 'sa'}", q, {}


class ActiveOps(XxtBase):
    def create_activity(self, course: str, class_id: str, kind: str, title: str, start: bool, settings: dict | None = None) -> dict:
        c = self.ctx(course)
        cls = self._class_of(c, class_id)
        method, path, q, form = build_request(kind, _safe_id(c.id), cls, title, start, dict(settings or {}))
        opts = q.pop("_opts", [])
        before = {a["activity_id"] for a in self.activities(c.id, limit=1000, class_id=cls)}
        r = self.on(ML, """
            const q=new URLSearchParams(%s); for(const [k,v] of %s) q.append(k,v);
            const f=new URLSearchParams(%s);
            const ck=n=>(document.cookie.match(new RegExp('(?:^|; )'+n+'=([^;]*)'))||[])[1]||'';
            for(const [k,v] of [...f]) if(v.startsWith('__COOKIE__:')) f.set(k, ck(v.slice(11)));
            let url=%s+(q.toString()?('?'+q.toString()):'');
            let opt={credentials:'include',headers:{'X-Requested-With':'XMLHttpRequest'}};
            if(%s==='GET'){ url+=(url.includes('?')?'&':'?')+f.toString(); }
            else { opt.method='POST'; opt.headers['Content-Type']='application/x-www-form-urlencoded; charset=UTF-8'; opt.body=f.toString(); }
            const r=await fetch(url,opt); let j=null; try{j=await r.json()}catch(e){}
            return {http:r.status,j};
        """ % (json.dumps({k: str(v) for k, v in q.items()}, ensure_ascii=False), json.dumps(opts),
               json.dumps({k: str(v) for k, v in form.items()}, ensure_ascii=False), json.dumps(path), json.dumps(method)), retry_safe=False)
        return self._activity_result(c, cls, before, r, kind=kind, started=bool(start))

    def _class_of(self, c, class_id: str) -> str:
        cls = _safe_id(class_id)
        if cls not in {str(x.get("clazz_id")) for x in c.classes}:
            raise XxtError("班级不属于这门课。")
        return cls

    def _activity_result(self, c, cls: str, before: set, r, **info) -> dict:
        """Read back: the server said ok AND the class activity list has a new entry."""
        j = (r or {}).get("j") if isinstance(r, dict) else None
        good = isinstance(j, dict) and (j.get("result") == 1 or j.get("status") in (1, True))
        new = []
        for _ in range(4):
            new = [a for a in self.activities(c.id, limit=1000, class_id=cls) if a["activity_id"] not in before]
            if new:
                break
            time.sleep(1.5)
        ok = bool(good) and len(new) >= 1
        err = (r or {}).get("err") if isinstance(r, dict) else None
        refused = isinstance(j, dict) and j.get("result") == 0 and not new
        if refused or (err and not new):
            return {"ok": False, **info, "write_outcome": "not_written",
                    "error": f"服务端拒绝：{str(j.get('errorMsg') or j.get('msg') or '未说明原因')[:200]}" if refused else f"未发送：{err}"}
        return {"ok": ok, **info, "activity": new[0] if new else None,
                **({} if ok else {"write_outcome": "unknown", "server": {k: (j or {}).get(k) for k in ("result", "status", "msg", "errorMsg")} if isinstance(j, dict) else err,
                                  "error": "服务端未确认或活动列表里没有新活动；请用 list_activities 查看，不要重复创建。"})}

    def create_quiz(self, course: str, class_id: str, title: str, questions: list[dict], start: bool, minutes: float | None = 60,
                    settings: dict | None = None) -> dict:
        """随堂练习: post what the quiz editor's 保存 / 开始 buttons post (from the static base page; the editor re-renders too much)."""
        c = self.ctx(course)
        cls = self._class_of(c, class_id)
        form = quiz_form(_safe_id(c.id), cls, title, questions, minutes, dict(settings or {}))
        before = {a["activity_id"] for a in self.activities(c.id, limit=1000, class_id=cls)}
        r = self.on(ML, _QUIZ_JS % {"form": json.dumps({k: str(v) for k, v in form.items()}, ensure_ascii=False),
                                    "start": "true" if start else "false"}, retry_safe=False)
        return self._activity_result(c, cls, before, r, kind="随堂练习", started=bool(start), questions=len(json.loads(form["questions"])))

    def create_questionnaire(self, course: str, class_id: str, title: str, questions: list[dict], start: bool,
                             minutes: float | None = 60, settings: dict | None = None) -> dict:
        """问卷: post the form the questionnaire editor serializes for 保存 / 开始."""
        c = self.ctx(course)
        cls = self._class_of(c, class_id)
        form = questionnaire_form(_safe_id(c.id), cls, title, questions, minutes, start, dict(settings or {}))
        before = {a["activity_id"] for a in self.activities(c.id, limit=1000, class_id=cls)}
        r = self.on(ML, _QN_JS % {"form": json.dumps(form, ensure_ascii=False), "start": "true" if start else "false"}, retry_safe=False)
        return self._activity_result(c, cls, before, r, kind="问卷", started=bool(start), questions=len(questions))

    def _course_resource(self, c, material: str, folder_id: str = "0") -> dict:
        r = self.on(ML, _RES_LIST_JS % {"course": _safe_id(c.id), "root": _safe_id(folder_id or "0")})
        if not isinstance(r, dict) or not r.get("valid"):
            raise XxtError("课程资料列表读取失败。")
        want = str(material or "").strip()
        hits = [x for x in r["items"] if str(x.get("dataId")) == want] or [x for x in r["items"] if str(x.get("dataName") or "") == want]
        if len(hits) != 1:
            names = [str(x.get("dataName") or "")[:40] for x in r["items"]][:30]
            raise XxtError(f"没找到唯一的资料「{want[:60]}」（按资料 ID 或完整名称匹配）。这一层的资料：{names}")
        if resource_entry(hits[0]) is None:
            raise XxtError("这种资料（如文件夹）不能作为活动推送。")
        return hits[0]

    def push_material(self, course: str, class_id: str, material: str, folder_id: str = "0") -> dict:
        """资料 activity: push one 课程资料 to the class activity list (what 发起活动 → 资料 does)."""
        c = self.ctx(course)
        cls = self._class_of(c, class_id)
        item = self._course_resource(c, material, folder_id)
        before = {a["activity_id"] for a in self.activities(c.id, limit=1000, class_id=cls)}
        form = {"courseId": _safe_id(c.id), "classId": cls,
                "resourceData": json.dumps([resource_entry(item)], ensure_ascii=False, separators=(",", ":"))}
        r = self.on(ML, _RES_PUSH_JS % {"form": json.dumps(form, ensure_ascii=False)}, retry_safe=False)
        return self._activity_result(c, cls, before, r, kind="资料", material=str(item.get("dataName") or "")[:100])

    def create_group_task(self, course: str, class_id: str, title: str, content: str, start: bool,
                          minutes: float | None = 1440, settings: dict | None = None) -> dict:
        """分组任务 in 不分组（个人任务）mode: post what the task editor's 保存 / 立即开始 post."""
        c = self.ctx(course)
        cls = self._class_of(c, class_id)
        form = group_task_form(_safe_id(c.id), cls, _safe_id(c.cpi), title, content, minutes, start, dict(settings or {}))
        before = {a["activity_id"] for a in self.activities(c.id, limit=1000, class_id=cls)}
        r = self.on(ML, _TASK_JS % {"form": json.dumps({k: str(v) for k, v in form.items()}, ensure_ascii=False)}, retry_safe=False)
        return self._activity_result(c, cls, before, r, kind="分组任务", started=bool(start), mode="个人任务")
