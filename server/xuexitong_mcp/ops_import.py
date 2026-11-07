"""Question-bank import (题库「批量导入」, verified on the test course, 2026-11-08).

The list page's own upload (insertTemplate.js importQuestion): multipart POST to
  https://mooc1.chaoxing.com/import-export-ans/import/importquestions?courseId&cpi      (.xls / .xlsx)
  https://mooc1.chaoxing.com/import-export-ans/import/importquestion-que?courseId&cpi   (.ti files)
fields file, pid (target folder, 0 = root), enc (#importQuestionEnc of qbank/questionlist), uuid, pMessage, status
(#initStatus), updateSameQue (update identical questions instead of skipping them), plainText (1 = cell text is plain
text, so "<b>" stays literal), importDir (.ti: keep the file's folders).  Reply: {status, totalNum, insertSuccessNum,
insertFailedNum, insertFailedContent, ignoreNum, ignoreContent, notCreateDirNum, qidList, errorFileUrl}.

Template (import-export-ans/template/importQuestionTemplateNew.xls, version v2): one header row, then one row per
question; composite types put each sub-question on its own row below.  Columns 目录 (a "/A/B" path, created when
missing; empty = root), 题目类型, 自定义题型, 大题题干, 小题题型, 小题题干, 正确答案, 答案解析, 难易度, 知识点, 标签 (；-separated),
选项数, 选项A… .  Questions given as data are written to that layout as .xlsx (xlsx.py) with plainText=1.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import uuid as _uuid
from pathlib import Path

from .questions import LABEL, normalize_list, type_id, letters, _tf
from .xlsx import build_xlsx
from .xxt import M2, XxtBase, XxtError, _safe_id

HEADER = ["目录", "题目类型", "自定义题型", "大题题干", "小题题型", "小题题干", "正确答案", "答案解析", "难易度", "知识点", "标签", "选项数"] + \
    [f"选项{x}" for x in letters(26)]
IMPORT_TYPES = {0, 1, 2, 3, 4, 5, 6, 9, 11, 13, 14, 15, 20, 25}
LEVELS = ("易", "中", "难")
IMPORT_BASE = "https://mooc1.chaoxing.com/import-export-ans"
MAX_QUESTIONS = 500


def folder_path(folder: str) -> str:
    """"" -> root; "A" or "/A/B" -> "/A/B"."""
    f = str(folder or "").strip().strip("/")
    if not f:
        return ""
    parts = [x.strip() for x in f.split("/")]
    if any(not x or len(x) > 50 or re.search(r"[\x00-\x1f]", x) for x in parts) or len(parts) > 5:
        raise XxtError("目录写成「/一级/二级」，每级 1–50 字，最多 5 级。")
    return "/" + "/".join(parts)


def _txt(v) -> str:
    return str(v if v is not None else "").strip()


def _opts_row(opts: list) -> list[str]:
    return [str(len(opts))] + [_txt(o) for o in opts]


def _sub_row(k: dict, kt: int) -> list:
    """A sub-question row of 阅读理解 / 选做 / 完型填空 (小题题型, 小题题干, 正确答案, 答案解析, …, 选项数, 选项…)."""
    pre = ["", "", "", "", LABEL[kt], _txt(k.get("stem")), "", _txt(k.get("analysis")), "", "", ""]
    if kt in (0, 1):
        pre[6] = "".join(sorted(str(x).upper() for x in (k["answer"] if isinstance(k["answer"], list) else list(str(k["answer"]).replace(",", "")))))
        return pre + _opts_row(k["options"])
    if kt == 2:
        a = k.get("answer")
        return pre + _opts_row(a if isinstance(a, list) else [a])
    if kt == 3:
        pre[6] = "A" if _tf(k.get("answer"), "") else "B"
        return pre + ["2", "正确", "错误"]
    pre[6] = "A" if _txt(k.get("answer")) else ""
    return pre + (["1", _txt(k.get("answer"))] if _txt(k.get("answer")) else [""])


def excel_rows(questions: list[dict], folder: str = "") -> tuple[list[list], list[dict]]:
    """Validate with the shared question model, then lay the plain text out in the template's columns.
    Returns (rows incl. header, [{type, stem}] per top-level question in file order)."""
    if not isinstance(questions, list) or not 1 <= len(questions) <= MAX_QUESTIONS:
        raise XxtError(f"一次导入 1–{MAX_QUESTIONS} 道题。")
    qs = normalize_list(questions, "bank")
    path = folder_path(folder)
    rows, expect = [HEADER], []
    for i, (raw, q) in enumerate(zip(questions, qs), 1):
        if q.t not in IMPORT_TYPES:
            raise XxtError(f"第 {i} 题：「{q.label}」不能用 Excel 批量导入（支持："
                           f"{'、'.join(LABEL[t] for t in sorted(IMPORT_TYPES))}）；请改用 add_bank_question 逐题添加。")
        lv = _txt(raw.get("difficulty")) or "中"
        if lv not in LEVELS:
            raise XxtError(f"第 {i} 题：难度只能是 易、中、难。")
        tags = raw.get("tags") or []
        if not isinstance(tags, list) or any(not _txt(t) or "；" in str(t) or ";" in str(t) for t in tags):
            raise XxtError(f"第 {i} 题：tags 是标签名列表，标签名里不能有分号。")
        head = [path, q.label, "", _txt(raw.get("stem")), "", "", "", _txt(raw.get("analysis")), lv,
                _txt(raw.get("knowledge")), "；".join(_txt(t) for t in tags)]
        kids: list[list] = []
        if q.t in (0, 1):
            head[6] = "".join(q.answer)
            head += _opts_row(raw["options"])
        elif q.t in (2, 9):
            a = raw.get("answer")
            head += _opts_row(a if isinstance(a, list) else [a])
        elif q.t == 3:
            head[6] = "A" if q.answer else "B"
            head += ["2", "正确", "错误"]
        elif q.t in (4, 5, 6):
            ans = _txt(raw.get("answer"))
            head[6] = "A" if ans else ""
            head += ["1", ans] if ans else [""]
        elif q.t == 11:
            head[6] = "".join(q.answer)
            head += [f"{len(raw['left'])}+{len(raw['right'])}"] + [_txt(x) for x in raw["left"]] + [_txt(x) for x in raw["right"]]
        elif q.t == 13:
            head[6] = q.answer
            head += _opts_row(raw["options"])
        elif q.t == 20:
            head += _opts_row(raw["options"])
            kids = [["", "", "", "", "", _txt(it), a] for it, a in zip(raw["items"], q.answer)]
        elif q.t in (14, 15, 25):
            head += [str(q.extra["optional_num"])] if q.t == 25 else [""]
            kids = [_sub_row(k, type_id(k.get("type"))) for k in raw["children"]]
        if len(head) > len(HEADER) or any(len(k) > len(HEADER) for k in kids):
            raise XxtError(f"第 {i} 题：选项太多（Excel 模板最多 26 列选项）。")
        rows.append(head)
        rows.extend(kids)
        expect.append({"type": q.label, "stem": _txt(raw.get("stem"))})
    return rows, expect


class ImportOps(XxtBase):
    def _import_file(self, c, path: Path, sha: str, *, kind: str, update_same: bool, plain_text: bool, keep_dirs: bool) -> dict:
        """Stage the file on the bank list page and send it the way the page does."""
        tmp, snap, meta = self._snapshot(str(path), sha)
        try:
            self.b.navigate(f"https://mooc2-ans.chaoxing.com/mooc2-ans/qbank/questionlist?{self.q(c)}&v=6", settle=1.0, readiness=False)
            self._stage(snap, meta)
            r = self.here("""
                const g=id=>((document.getElementById(id)||{}).value||'');
                if(g('moocImportExportUrl')!==%(base)s||!/^[0-9a-f]{32}$/.test(g('importQuestionEnc'))) return {stage:'page'};
                const f=document.getElementById('mcp-file').files[0]; if(!f) return {stage:'file'};
                const fd=new FormData(); fd.append('file',f,f.name); fd.append('pid','0'); fd.append('enc',g('importQuestionEnc'));
                fd.append('uuid',%(uuid)s); fd.append('pMessage',g('pMessage')||'false'); fd.append('status',g('initStatus'));
                if(%(ti)s&&%(dirs)s) fd.append('importDir',true);
                fd.append('updateSameQue',%(upd)s); fd.append('plainText',%(plain)s);
                const r=await fetch(%(base)s+'/import/'+(%(ti)s?'importquestion-que':'importquestions')+'?courseId=%(cid)s&cpi=%(cpi)s',
                  {method:'POST',body:fd,credentials:'include'});
                let j=null; try{j=await r.json()}catch(e){}
                return {stage:'done',http:r.status,j};
            """ % {"base": json.dumps(IMPORT_BASE), "uuid": json.dumps(_uuid.uuid4().hex), "ti": "true" if kind == "ti" else "false",
                   "dirs": "true" if keep_dirs else "false", "upd": "true" if update_same else "false", "plain": "1" if plain_text else "0",
                   "cid": _safe_id(c.id), "cpi": _safe_id(c.cpi)}, retry_safe=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if not isinstance(r, dict) or r.get("stage") != "done":
            return {"ok": False, "write_outcome": "not_written", "error": f"导入在「{(r or {}).get('stage', '未知')}」阶段没有发出；题库没有变化。"}
        j = r.get("j") if isinstance(r.get("j"), dict) else None
        if r.get("http") != 200 or j is None:
            return {"ok": False, "write_outcome": "unknown", "error": f"导入接口回 HTTP {r.get('http')}；请用 list_bank_questions 核查有没有导入。"}
        clean = lambda s: re.sub(r"<[^>]+>", " ", str(s or "")).strip()[:300]
        return {"status": j.get("status") is True, "total": j.get("totalNum"), "imported": j.get("insertSuccessNum"),
                "failed": j.get("insertFailedNum") or 0, "failed_rows": clean(j.get("insertFailedContent")),
                "skipped_same": j.get("ignoreNum") or 0, "skipped_rows": clean(j.get("ignoreContent")),
                "folder_not_created": j.get("notCreateDirNum") or 0, "message": clean(j.get("msg")),
                "qids": [str(x) for x in (j.get("qidList") or []) if re.fullmatch(r"[0-9a-f]{32}|\d{1,20}", str(x))],
                "has_error_file": bool(j.get("errorFileUrl"))}

    def import_bank_questions(self, course: str, questions: list[dict], folder: str = "", update_same: bool = False) -> dict:
        rows, expect = excel_rows(questions, folder)
        c = self.ctx(course)
        before = set(self._all_questions(c))
        d = Path(tempfile.mkdtemp(prefix="xxt-imp-"))
        try:
            f = d / "questions.xlsx"
            f.write_bytes(build_xlsx(rows, "课程题库"))
            from .ops_upload import sha256_file
            res = self._import_file(c, f, sha256_file(f), kind="excel", update_same=update_same, plain_text=True, keep_dirs=False)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        if "status" not in res:
            return res
        return self._check_import(c, res, before, expect)

    def import_bank_file(self, course: str, file_path: str, sha: str, update_same: bool = False, plain_text: bool = False,
                         keep_dirs: bool = False) -> dict:
        p = Path(file_path)
        kind = "ti" if p.suffix.lower() == ".ti" else "excel"
        c = self.ctx(course)
        before = set(self._all_questions(c))
        res = self._import_file(c, p, sha, kind=kind, update_same=update_same, plain_text=plain_text, keep_dirs=keep_dirs)
        if "status" not in res:
            return res
        return self._check_import(c, res, before, None)

    def _check_import(self, c, res: dict, before: set[str], expect: list[dict] | None) -> dict:
        """The bank must have exactly `imported` new questions (the .ti import returns no qidList, so new ids come from a
        before/after scan); questions given as data are also checked one by one for type and stem."""
        # identical questions already in the bank are skipped and named by row number ("1、2、")
        skipped = {int(x) for x in re.findall(r"\d+", res["skipped_rows"])} if res["skipped_same"] else set()
        base = {k: res[k] for k in ("total", "imported", "failed", "failed_rows", "skipped_same", "skipped_rows", "folder_not_created", "message")}
        if res["status"] and not res["imported"] and res["skipped_same"] and res["skipped_same"] == res["total"]:
            return {"ok": False, "write_outcome": "not_written", **base,
                    "error": "这些题目题库里都已经有了（内容相同），平台全部跳过，题库没有变化。"}
        bank = self._all_questions(c)
        new = [q for q in bank if q not in before]
        ids = res["qids"] or new
        found = [bank.get(q) for q in ids]
        checks = {"accepted": res["status"], "none_failed": res["failed"] == 0,
                  "new_in_bank": len(new) == res["imported"] and bool(new) and set(ids) == set(new) and all(found)}
        dups = []
        if expect is not None:
            dups = [e["stem"][:60] for i, e in enumerate(expect, 1) if i in skipped]
            want = [e for i, e in enumerate(expect, 1) if i not in skipped]
            checks["count"] = len(ids) == len(want) and res["imported"] == len(want) and len(skipped) == res["skipped_same"]
            norm = lambda s: re.sub(r"\s+", " ", str(s)).strip()[:30]
            if res["qids"]:     # qidList is in file order
                checks["stems"] = all(f and norm(f["stem"]) == norm(e["stem"]) for f, e in zip(found, want))
                checks["types"] = all(f and f.get("type") == e["type"] for f, e in zip(found, want))
            else:               # only a before/after scan: compare as multisets
                checks["stems"] = sorted(norm((f or {}).get("stem", "")) for f in found) == sorted(norm(e["stem"]) for e in want)
                checks["types"] = sorted(str((f or {}).get("type")) for f in found) == sorted(str(e["type"]) for e in want)
        out = {"ok": all(checks.values()), "checks": checks, **base,
               **({"skipped_duplicates": dups} if dups else {}),
               "questions": [{"question_id": q, "type": (f or {}).get("type"), "stem": (f or {}).get("stem", "")[:60], "folder_id": (f or {}).get("folder_id")}
                             for q, f in zip(ids, found)][:200]}
        if not out["ok"]:
            out.update(write_outcome="unknown" if res["status"] else "not_written",
                       error=("服务端拒绝导入：" + res["message"]) if not res["status"]
                       else f"导入结果核对不一致（{[k for k, v in checks.items() if not v]}）；请用 list_bank_questions 核查，不要重复导入。")
        elif res["skipped_same"]:
            out["note"] = (f"有 {res['skipped_same']} 道题题库里已经有了（内容相同），平台跳过了它们。"
                           "内容改过的题会作为新题导入（即使 update_same=true），旧题不会被改。")
        return out

    # ------------------------------------------------------------------ 智能导入 (free text, recognized by the platform)
    def _smart_parse(self, c, text: str) -> dict:
        """POST /sqp/api/parse?courseid&cpi {html} from the static base page (the smart-import page itself keeps
        re-rendering), then smart_qjson() turns the recognized `paper` into the qjson 「加入题库」 sends."""
        t = str(text or "")
        if not t.strip() or len(t) > 50000:
            raise XxtError("文本 1–50000 字。")
        lines = [x.rstrip() for x in t.replace("\r\n", "\n").split("\n")]
        r = self.on(M2, """
            const d=D(await F('/mooc2-ans/qbank/smartimport?courseid=%(cid)s&cpi=%(cpi)s&qbanksystem=0&microTopicId=0'));
            const g=id=>{const e=d.getElementById(id);return e?(e.getAttribute('value')||''):''};
            const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            const html=%(lines)s.map(l=>'<p>'+esc(l)+'</p>').join('');
            const j=await J('/sqp/api/parse?courseid=%(cid)s&cpi=%(cpi)s',POST({html,isParseLatexCode:'false',isParseLatexFormula:'false'}));
            return {paper:j&&j.paper,hid:{enc:g('importQuestionEnc'),base:g('moocImportExportUrl'),paperLibraryId:g('paperLibraryId'),
              workLibraryId:g('workLibraryId'),createPaperLibrary:g('createPaperLibrary'),createWorkLibrary:g('createWorkLibrary'),
              pMessage:g('pMessage'),initStatus:g('initStatus'),groupId:g('groupId')}};
        """ % {"cid": _safe_id(c.id), "cpi": _safe_id(c.cpi), "lines": json.dumps(lines, ensure_ascii=False)})
        if not isinstance(r, dict) or not isinstance(r.get("paper"), list):
            raise XxtError("平台的智能识别没有返回结果；没有导入。")
        qs = smart_qjson(r["paper"])
        if not qs:
            raise XxtError("平台没有从文本里识别出题目；请按「1. 题干 / A. 选项 / 答案：A」的格式写。")
        if len(qs) > MAX_QUESTIONS:
            raise XxtError(f"一次最多 {MAX_QUESTIONS} 道题。")
        miss = [str(ln.get("plain") or "")[:80] for q in r["paper"] if isinstance(q, dict) for ln in (q.get("lines") or [])
                if isinstance(ln, dict) and ln.get("notMatch")]
        items = [smart_item(q) for q in qs]
        # the page refuses 「加入题库」 while an objective question has no answer (checkObjectiveQuesHasEmptyAnswer)
        empty = [f"{i}. {x['type']}：{x['stem'][:40]}" for i, x, q in zip(range(1, len(qs) + 1), items, qs)
                 if q.get("type") in (0, 1, 2, 3, 9) and not x["answered"]]
        if empty:
            raise XxtError("这些客观题平台没有识别到答案，平台不允许这样加入题库：" + "；".join(empty[:10])
                           + "。请在题目下单独写一行「答案：…」；组合题要用 {{ }} 括起，小题也要编号。")
        import hashlib
        return {"qs": qs, "hid": r.get("hid") or {}, "miss": miss, "items": items,
                "digest": hashlib.sha256(json.dumps(qs, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()}

    def smart_import_preview(self, course: str, text: str) -> dict:
        c = self.ctx(course)
        r = self._smart_parse(c, text)
        return {"digest": r["digest"], "items": r["items"], "unrecognized_lines": r["miss"][:50]}

    def smart_import_bank_text(self, course: str, text: str, digest: str, folder: str = "") -> dict:
        c = self.ctx(course)
        pid = self._folder(c, folder)["id"] if folder else "0"
        r = self._smart_parse(c, text)
        if r["digest"] != digest:
            return {"ok": False, "write_outcome": "not_written", "error": "这次识别结果和预演时不一样；没有导入，请重新预演。"}
        h = r["hid"]
        if h.get("base") != IMPORT_BASE or not re.fullmatch(r"[0-9a-f]{32}", str(h.get("enc") or "")):
            return {"ok": False, "write_outcome": "not_written", "error": "智能导入页缺少导入凭据；没有导入。"}
        before = set(self._all_questions(c))
        data = {"courseId": str(c.id), "isMutex": 0, "pid": str(pid), "cpi": str(c.cpi), "enc": h["enc"], "insertQuestion": "true",
                "paperLibraryId": h.get("paperLibraryId") or "", "workLibraryId": h.get("workLibraryId") or "",
                "createWorkLibrary": "true" if h.get("createWorkLibrary") == "true" else "false",
                "createPaperLibrary": "true" if h.get("createPaperLibrary") == "true" else "false",
                "needQid": "true" if h.get("pMessage") == "true" else "false", "uuid": _uuid.uuid4().hex, "microTopicId": "",
                "groupId": h.get("groupId") or "0", "initStatus": h.get("initStatus") or "",
                "qjson": json.dumps(with_ids(r["qs"]), ensure_ascii=False)}
        res = self.on(M2, """
            const r=await fetch(%s+'/import/import-question',{method:'POST',credentials:'include',
              headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'},body:new URLSearchParams(%s)});
            let j=null; try{j=await r.json()}catch(e){}
            return {http:r.status,j};
        """ % (json.dumps(IMPORT_BASE), json.dumps(data, ensure_ascii=False)), retry_safe=False)
        j = res.get("j") if isinstance(res, dict) and isinstance(res.get("j"), dict) else None
        if not isinstance(res, dict) or res.get("http") != 200 or j is None:
            return {"ok": False, "write_outcome": "unknown",
                    "error": f"导入接口回 HTTP {(res or {}).get('http')}；请用 list_bank_questions 核查，不要重复导入。"}
        clean = lambda s: re.sub(r"<[^>]+>", " ", str(s or "")).strip()[:300]
        out = {"status": j.get("status") is True, "total": j.get("totalNum"), "imported": j.get("insertSuccessNum"),
               "failed": j.get("insertFailedNum") or 0, "failed_rows": clean(j.get("insertFailedContent")),
               "skipped_same": j.get("ignoreNum") or 0, "skipped_rows": clean(j.get("ignoreContent")), "folder_not_created": 0,
               "message": clean(j.get("msg")), "qids": []}
        return self._check_import(c, out, before, [{"type": x["type"], "stem": x["stem"]} for x in r["items"]])


# ---------------------------------------------------------------------- smart-import qjson (a port of the page's makeupQ)
SMART_TYPES = {"QuestionChoice": "单选题", "MultiChoice": "多选题", "QuestionGapFilling": "填空题", "QuestionYesNo": "判断题",
               "QuestionCommon": "简答题", "QuestionClozeTest": "完型填空", "QuestionComposite": "阅读理解",
               "QuestionSameChoose": "共用选项题", "QuestionChooseWordGapFilling": "选词填空", "QuestionWriting": "写作题"}
_COMMON = {"名词解释": 5, "论述题": 6, "计算题": 7}
_WRITING = {1: {"subject": 1, "grade": "十二", "literaryForm": "narrative", "wordnum": "15000"}, 2: {"subject": 2, "grade": "delea1"},
            3: {"subject": 3, "grade": "delfa1"}, 0: {"subject": 0, "grade": "cet4"}}
_WRITING_LANG = ((r"中文写作|汉语写作|chinese\s*writing|写作语言\s*[:：]\s*中文", 1),
                 (r"西班牙语写作|西语写作|spanish\s*writing|写作语言\s*[:：]\s*(西班牙语|西语)", 2),
                 (r"法语写作|法文写作|french\s*writing|写作语言\s*[:：]\s*(法语|法文)", 3),
                 (r"英文写作|英语写作|english\s*writing|写作语言\s*[:：]\s*(英文|英语)", 0))


def _writing_subject(s: str):
    for pat, v in _WRITING_LANG:
        if re.search(pat, s or "", re.I):
            return v
    return None


def smart_q(q: dict) -> dict:
    qt: dict = {}
    for src, dst in (("content", "content"), ("answerKey", "analysis"), ("knowledge", "knowledge"), ("label", "label"),
                     ("target", "target"), ("score", "score")):
        if q.get(src):
            qt[dst] = q[src]
    if q.get("difficulty"):
        qt["difficulty"] = q["difficulty"]
        qt["easy"] = q.get("easy")
    t = q.get("type")
    qt["name"] = SMART_TYPES.get(t)
    qt["typeAlias"] = q.get("typeAlias") or qt["name"]
    if q.get("questions"):
        qt["answer"] = []
        for sub in q["questions"]:
            s = smart_q(sub)
            if s:
                name, typ = s.pop("name", None), s.pop("type", None)
                qt["answer"].append({"name": name, "type": typ, "data": s})
    if t in ("QuestionChoice", "MultiChoice"):
        ans = set(q.get("answer") or [])
        qt["answer"] = [{"content": o.get("value"), "name": o.get("name"), **({"isanswer": True} if o.get("name") in ans else {})}
                        for o in (q.get("options") or [])]
        qt["type"], qt["name"] = (1, "多选题") if t == "MultiChoice" else (0, "单选题")
        qt["typeAlias"] = q.get("typeAlias") or qt["name"]
        return qt
    if t == "QuestionGapFilling":
        qt["answer"] = [{"content": a, "name": str(k + 1)} for k, a in enumerate(q.get("answer") or [])]
        if q.get("isMutex") in (0, 1):
            qt["isMutex"] = q["isMutex"]
        qt["type"] = 9 if qt["typeAlias"] == "分录题" else 2
        return qt
    if t == "QuestionYesNo":
        qt["answer"], qt["type"] = [{"answer": q.get("answerValue") is True}], 3
        return qt
    if t == "QuestionCommon":
        if q.get("answer"):
            qt["answer"] = [{"answer": ", ".join(str(x) for x in q["answer"])}]
        qt["type"] = _COMMON.get(qt["typeAlias"], 4)
        return qt
    if t == "QuestionClozeTest":
        qt["type"] = 14
    if t == "QuestionComposite":
        qt["type"] = 15
    if t in ("QuestionSameChoose", "QuestionChooseWordGapFilling"):
        qt["type"], qt["answer"] = (20 if t == "QuestionSameChoose" else 24), q.get("answerList")
    if t == "QuestionWriting":
        qt["type"], qt["name"] = 26, "写作题"
        qt["typeAlias"] = q.get("typeAlias") or "写作题"
        sub = q.get("subject")
        sub = int(sub) if str(sub).isdigit() else _writing_subject(str(q.get("content") or q.get("writingLanguage") or ""))
        meta = _WRITING.get(sub, {})
        a = q.get("answer")
        w = {"answer": ("".join(a) if isinstance(a, list) else str(a)) if a else ""}
        if meta.get("subject") is not None:
            w["subject"] = str(meta["subject"])
        w["grade"] = q.get("grade") or meta.get("grade")
        if q.get("literaryForm") or meta.get("literaryForm"):
            w["literaryForm"] = q.get("literaryForm") or meta.get("literaryForm")
        if q.get("wordnum") or meta.get("wordnum"):
            w["wordnum"] = str(q.get("wordnum") or meta.get("wordnum"))
        qt["answer"] = [w]
    return qt


def smart_qjson(paper: list) -> list[dict]:
    """makeupPaper: keep the recognized questions that got a type, numbered from 0."""
    out = []
    for q in paper or []:
        if isinstance(q, dict):
            x = smart_q(q)
            if x.get("type") is not None:
                x["id"] = len(out)
                out.append(x)
    return out


def with_ids(qs: list[dict]) -> list[dict]:
    """Composite sub-questions carry a client guid (left out of the preview digest)."""
    out = json.loads(json.dumps(qs))
    for q in out:
        for sub in q.get("answer") or [] if isinstance(q.get("answer"), list) else []:
            if isinstance(sub, dict) and "data" in sub:
                sub["id"] = str(_uuid.uuid4())
    return out


def _html_text(s) -> str:
    import html as _h
    return _h.unescape(re.sub(r"<[^>]+>", " ", str(s or "")))


def smart_item(q: dict) -> dict:
    stem = re.sub(r"[ \t\r\n\xa0]+", " ", _html_text(q.get("content"))).strip()[:80]
    ans = q.get("answer") or []
    kids = [a for a in ans if isinstance(a, dict) and "data" in a]
    if kids:
        answered = True
    elif q.get("type") in (0, 1):
        answered = any(isinstance(a, dict) and a.get("isanswer") for a in ans)
    else:
        answered = any(isinstance(a, dict) and (a.get("answer") not in (None, "") or a.get("content") not in (None, "")) for a in ans)
    out = {"type": LABEL.get(q.get("type"), q.get("name")), "stem": stem, "answered": answered, "children": len(kids)}
    if q.get("typeAlias") and q["typeAlias"] != out["type"]:
        out["alias"] = q["typeAlias"]      # a custom type name such as 【案例分析】
    return out
