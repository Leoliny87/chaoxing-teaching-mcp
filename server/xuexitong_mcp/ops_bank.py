"""题库管理 (questionList.js of mooc2-ans qbank, verified on the test course 2026-11-07).

List: POST /mooc2-ans/qbank/search {courseid, cpi, dirId, courseIds, sw, pageNum, pageSize, …, status}; rows of
questionBankRelationList are folders (type 0: id, dirName, questionCount) or questions (type 1: questionId, questionBank).
Folder: GET insertdir {dirName, courseid, pid, cpi}; rename update-dirname {dirName, courseid, pid, cpi, id}.
Move:   update-pid {courseid, cpi, operateId, operateCourseId, type (0 folder / 1 question), newPid}.
Delete: POST batch-updatestatus {courseid, cpi, questionIds, dirIds, status: 2} (to the bin, search status=2 lists it);
        restore with status 0.  Difficulty: update-difficulty {courseid, cpi, qids, difficulty}.
Labels: question-label/add {courseid, cpi, parentId, labelname}, /list {courseid, cpi, qid}, /delete {labelid};
        apply POST update-label?courseid&cpi&labelIds=<a,b,>&updateExamWord=false {qids}.
Edit:   the create form posted to qbank/add_question with questionBankId=<id> and isEdit=true.
"""
from __future__ import annotations

import html as _h
import json
import re

from .xxt import M2, XxtBase, XxtError, _safe_id

_QID = re.compile(r"\d{1,20}|[0-9a-f]{32}")
DIFFICULTY = {"易": 0.8, "中": 0.5, "难": 0.2}


def _qids(ids: list[str]) -> list[str]:
    out = [str(x).strip() for x in ids or [] if str(x).strip()]
    if not out or len(out) > 200 or any(not _QID.fullmatch(x) for x in out):
        raise XxtError("题目 ID 是 list_bank_questions 返回的 question_id，一次 1–200 个。")
    return out


class BankOps(XxtBase):
    def _bank_rows(self, c, dir_id: str = "0", keyword: str = "", status: str = "") -> list[dict]:
        """All rows of one folder (the search pages cap at 100 rows; read every page up to 20)."""
        body = {"courseid": c.id, "microTopicId": 0, "cpi": c.cpi, "dirId": _safe_id(dir_id or "0"), "courseIds": c.id, "qTypes": "", "eTypes": "",
                "difficulty": "", "sw": str(keyword or "")[:50], "pageNum": 1, "orderType": "", "orderByType": "", "orderByRight": "",
                "orderByName": "", "rightPercentFrom": "", "rightPercentTo": "", "pageSize": 100, "fromEdit": "", "topicIds": "",
                "courseTargetIds": "", "labelIds": "", "createrId": "", "needHtml": "", "hideEditBtn": "", "qbanksystem": 0,
                "hideLockDir": "", "dirCourseId": "", "topicIdStatus": "", "status": status}
        # the recycle bin is its own search (recycle-search, rows in `list`, no status flag)
        url = "/mooc2-ans/qbank/recycle-search" if status == "2" else "/mooc2-ans/qbank/search"
        if status == "2":
            body["orderType"] = "desc"
        r = self.on(M2, """
            const b=%s; const rows=[]; let total=null;
            for(let p=1;p<=20;p++){ b.pageNum=p; const j=await J(%s,POST(b));
              const arr=j&&(j.questionBankRelationList||j.list);
              if(!j||!Array.isArray(arr)||(j.status!==undefined&&j.status!==true)) return null;
              total=j.total; rows.push(...arr); if(!arr.length||rows.length>=total) break; }
            return {status:true,total,questionBankRelationList:rows};
        """ % (json.dumps(body, ensure_ascii=False), json.dumps(url)))
        rows = r.get("questionBankRelationList") if isinstance(r, dict) else None
        if not isinstance(rows, list) or r.get("status") is not True:
            raise XxtError("题库列表读取失败；没有继续。")
        out = []
        for x in rows:
            qb = x.get("questionBank") or {}
            if x.get("type") == 0:
                out.append({"kind": "folder", "id": str(x.get("id")), "name": x.get("dirName"), "questions": x.get("questionCount"), "pid": str(x.get("pid"))})
            else:
                stem = _h.unescape(re.sub(r"<[^>]+>", " ", str(qb.get("content") or "")))
                out.append({"kind": "question", "id": str(x.get("questionId") or qb.get("id")), "stem": re.sub(r"\s+", " ", stem).strip()[:120],
                            "difficulty": qb.get("difficulty"), "folder_id": str(qb.get("directoryId") or x.get("pid") or "0")})
        return out

    def _all_questions(self, c) -> dict[str, dict]:
        """Questions in the root and in every folder below it (a folder's own list holds only its items)."""
        out, todo, seen = {}, ["0"], set()
        while todo and len(seen) < 60:
            d = todo.pop()
            if d in seen:
                continue
            seen.add(d)
            for x in self._bank_rows(c, d):
                if x["kind"] == "question":
                    out[x["id"]] = {**x, "folder_id": d}
                else:
                    todo.append(x["id"])
        return out

    def _all_question_ids(self, c) -> set[str]:
        return set(self._all_questions(c))

    def bank_folders(self, course: str, parent: str = "0") -> list[dict]:
        c = self.course(course)
        return [x for x in self._bank_rows(c, parent) if x["kind"] == "folder"]

    def _folder(self, c, folder: str) -> dict:
        hits = [x for x in self._bank_rows(c) if x["kind"] == "folder" and (x["id"] == str(folder) or x["name"] == folder)]
        if len(hits) != 1:
            raise XxtError(f"题库根目录里没有唯一的文件夹「{str(folder)[:40]}」。")
        return hits[0]

    def create_bank_folder(self, course: str, name: str) -> dict:
        n = (name or "").strip()
        if not n or len(n) > 50:
            raise XxtError("文件夹名 1–50 字。")
        c = self.course(course)
        if any(x["kind"] == "folder" and x["name"] == n for x in self._bank_rows(c)):
            raise XxtError("题库根目录已有同名文件夹。")
        r = self.on(M2, "return await J('/mooc2-ans/qbank/insertdir?'+new URLSearchParams(%s));"
                    % json.dumps({"dirName": n, "courseid": c.id, "pid": "0", "cpi": c.cpi}, ensure_ascii=False), retry_safe=False)
        hit = [x for x in self._bank_rows(c) if x["kind"] == "folder" and x["name"] == n]
        out = {"ok": len(hit) == 1, "folder": n, "folder_id": hit[0]["id"] if hit else None}
        if not hit:
            out.update(write_outcome="unknown", error="新建后题库里没有这个文件夹。", server=r if isinstance(r, dict) else None)
        return out

    def move_bank_questions(self, course: str, qids: list[str], folder: str) -> dict:
        c = self.course(course)
        ids = _qids(qids)
        f = self._folder(c, folder) if str(folder) != "0" else {"id": "0", "name": "根目录"}
        r = self.on(M2, "return await J('/mooc2-ans/qbank/update-pid',POST(%s));"
                    % json.dumps({"courseid": c.id, "cpi": c.cpi, "operateId": ",".join(ids), "operateCourseId": c.id, "type": 1, "newPid": f["id"]}),
                    retry_safe=False)
        inside = {x["id"] for x in self._bank_rows(c, f["id"]) if x["kind"] == "question"}
        ok = set(ids) <= inside
        out = {"ok": ok, "folder": f["name"], "moved": [i for i in ids if i in inside]}
        if not ok:
            out.update(write_outcome="unknown", error="移动后文件夹里没有全部题目；请用 list_bank_questions 核查。", server=r if isinstance(r, dict) else None)
        return out

    def bank_status(self, course: str, qids: list[str], action: str) -> dict:
        """action: delete (to the bin) / restore (from the bin)."""
        c = self.course(course)
        ids = _qids(qids)
        st = {"delete": 2, "restore": 0}[action]
        r = self.on(M2, "return await J('/mooc2-ans/qbank/batch-updatestatus',POST(%s));"
                    % json.dumps({"courseid": c.id, "cpi": c.cpi, "questionIds": ",".join(ids), "dirIds": "", "status": st}), retry_safe=False)
        listed = self._all_question_ids(c)
        binned = {x["id"] for x in self._bank_rows(c, status="2") if x["kind"] == "question"}
        ok = (all(i not in listed for i in ids) and all(i in binned for i in ids)) if action == "delete" else \
             (all(i not in binned for i in ids) and all(i in listed for i in ids))
        out = {"ok": ok, "action": {"delete": "删除到回收站", "restore": "从回收站还原"}[action], "questions": ids}
        if not ok:
            out.update(write_outcome="unknown", error="操作后核对不通过；请用 list_bank_questions 核查。", server=r if isinstance(r, dict) else None)
        return out

    def set_bank_difficulty(self, course: str, qids: list[str], level: str) -> dict:
        if level not in DIFFICULTY:
            raise XxtError("难度只能是 易 / 中 / 难。")
        c = self.course(course)
        ids = _qids(qids)
        r = self.on(M2, "return await J('/mooc2-ans/qbank/update-difficulty',POST(%s));"
                    % json.dumps({"courseid": c.id, "cpi": c.cpi, "qids": ",".join(ids), "difficulty": DIFFICULTY[level]}), retry_safe=False)
        rows = self._all_questions(c)
        got = {i: (rows.get(i) or {}).get("difficulty") for i in ids}
        ok = all(v is not None and abs(float(v) - DIFFICULTY[level]) < 1e-6 for v in got.values())
        out = {"ok": ok, "difficulty": level, "read_back": got}
        if not ok:
            out.update(write_outcome="unknown", error="读回的难度不一致。", server=r if isinstance(r, dict) else None)
        return out

    def bank_labels(self, course: str, qid: str = "") -> list[dict]:
        c = self.course(course)
        r = self.on(M2, "return await F('/mooc2-ans/question-label/list?'+new URLSearchParams(%s));"
                    % json.dumps({"courseid": c.id, "cpi": c.cpi, "qid": qid or ""}))
        try:
            j = json.loads(r) if isinstance(r, str) else r
        except ValueError:
            j = None
        if not isinstance(j, dict) or j.get("status") is not True or not isinstance(j.get("data"), list):
            raise XxtError("题库标签读取失败。")
        checked = {str(x) for x in j.get("checkedIds") or []}
        out = []

        def walk(nodes, depth):
            for x in nodes or []:
                if isinstance(x, dict):
                    out.append({"id": str(x.get("id")), "name": x.get("name"), "parent_id": str(x.get("parentId")), "checked": str(x.get("id")) in checked})
                    if depth < 5:
                        walk(x.get("children"), depth + 1)
        walk(j["data"], 0)
        return out

    def create_bank_label(self, course: str, name: str) -> dict:
        n = (name or "").strip()
        if not n or len(n) > 30:
            raise XxtError("标签名 1–30 字。")
        c = self.course(course)
        if any(x["name"] == n for x in self.bank_labels(c.id)):
            raise XxtError("已有同名标签。")
        r = self.on(M2, "return await J('/mooc2-ans/question-label/add?'+new URLSearchParams(%s));"
                    % json.dumps({"courseid": c.id, "cpi": c.cpi, "parentId": 0, "labelname": n}, ensure_ascii=False), retry_safe=False)
        hit = [x for x in self.bank_labels(c.id) if x["name"] == n]
        out = {"ok": len(hit) == 1, "label": n, "label_id": hit[0]["id"] if hit else None}
        if not hit:
            out.update(write_outcome="unknown", error="新建后标签列表里没有它。", server=r if isinstance(r, dict) else None)
        return out

    def label_bank_questions(self, course: str, qids: list[str], labels: list[str]) -> dict:
        c = self.course(course)
        ids = _qids(qids)
        allx = self.bank_labels(c.id)
        lab = []
        for name in labels:
            hit = [x for x in allx if x["id"] == str(name) or x["name"] == name]
            if len(hit) != 1:
                raise XxtError(f"没有唯一的标签「{name}」；先用 create_bank_label 新建。")
            lab.append(hit[0])
        q = {"courseid": c.id, "cpi": c.cpi, "labelIds": "".join(x["id"] + "," for x in lab), "updateExamWord": "false"}
        r = self.on(M2, "return await J('/mooc2-ans/qbank/update-label?'+new URLSearchParams(%s),POST({qids:%s}));"
                    % (json.dumps(q), json.dumps(",".join(ids))), retry_safe=False)
        got = {i: sorted(x["id"] for x in self.bank_labels(c.id, i) if x["checked"]) for i in ids}
        want = sorted(x["id"] for x in lab)
        ok = all(v == want for v in got.values())
        out = {"ok": ok, "labels": [x["name"] for x in lab], "questions": ids}
        if not ok:
            out.update(write_outcome="unknown", error="读回的标签不一致。", read_back=got, server=r if isinstance(r, dict) else None)
        return out

    def edit_bank_question(self, course: str, qid: str, question: dict) -> dict:
        c = self.course(course)
        ids = _qids([qid])
        before = self._all_questions(c)
        if ids[0] not in before:
            raise XxtError("题库里没有这道题。")
        r = self.add_bank_question(c.id, question, edit_id=ids[0], dir_id=before[ids[0]]["folder_id"])
        rows = self._all_questions(c)
        want = re.sub(r"\s+", " ", str(question.get("stem") or "")).strip()[:60]
        now = (rows.get(ids[0]) or {}).get("stem") or ""
        ok = bool(r.get("ok")) and want[:30] in now and len(rows) == len(before)
        out = {"ok": ok, "question_id": ids[0], "stem_now": now[:120]}
        if not ok:
            out.update(write_outcome="unknown", error="保存后读回的题干不一致，或题目数变了（可能新建了一道）；请用 list_bank_questions 核查。",
                       server=r)
        return out
