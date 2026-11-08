"""Parallel papers (平行试卷: several sub-papers with the same structure, one handed out at random per student).

Endpoints (from creat-parallel-paper.js / copy-parallel-paper.js, verified on the test course, 2026-11-08), all mooc2-ans:
  new       GET  /exam/createAnEmptyPaper?courseid&clazzid&pid=0&parallelpaper=1          -> {paperId}
  title     POST /exam/update-exampaper-title {courseid, clazzid, cpi, ut, paperid, title, randomPaperRenameSync}
            (randomPaperRenameSync=1 also renames the sub-papers to "<title>(1)", "<title>(2)", …)
  add       POST /exam/complete-choose-paper?courseid&clazzid&cpi&paperid {selectedPaperData=[{pid, cid}]}
            copies the chosen library papers as sub-papers in a background task;
            GET /exam/choose-paper-status?…&paperid -> taskStatus running | success.  Finishing while the task
            runs silently finishes with the sub-papers copied so far, so the task must be done first.
  remove    GET  /exam/delete-childpaper?courseid&paperid=<sub-paper>&cpi   (takes effect at once)
  finish    GET  /exam/create-parallel-paper?clazzid&courseid&paperid&cpi&ut&easy=0|1|2 (易/中/难)
            -> status false + 「各子卷类型、题型、题量、分值需保持一致」 when the structures differ.
  settings  POST /exam/update-exampaper-serialnumber {…, serialnumber 0 连续 | 1 按题型},
            POST /exam/update-exampaper-questiongroup {…, questionGroup 0 按题型归类 | 1 不按题型归类}
  read      GET  /exam/parallel-paper?courseid&clazzid&cpi&paperid&ut=t  (.testPrallelBody_td rows: title, sub id on
            .rename_yes[paperid], structure "单选题 1，题型分值：5.0，…", questions, score)
  library   paperlist rows: paperLibLookPaper(type, id, '1') marks a parallel paper, .random "平行试卷: N套",
            .incomplete "[未完成]".  A paper's structure is in lookpaper's ".title" headings "一、 单选题（共1题，5分）".
Publishing, deleting and restoring a parallel paper use the same endpoints as any paper.
"""
from __future__ import annotations

import json
import re
import time

from .xxt import M2, XxtBase, XxtError, _best, _safe_id

DIFFICULTY = {"易": 0, "中": 1, "难": 2}
NUMBERING = {"连续": 0, "按题型": 1}
MAX_SUBS = 20
_EMOJI = re.compile(r"[\U00010000-\U0010FFFF]")


def parse_structure(text: str) -> tuple:
    """「单选题 1，题型分值：5.0，判断题 1，题型分值：5.0」 or lookpaper headings → ((type, count, score), …)."""
    s = str(text or "")
    rows = re.findall(r"([一-鿿]{1,8}题)\s*(\d+)\s*，\s*题型分值：\s*([\d.]+)", s)
    if not rows:
        rows = re.findall(r"([一-鿿]{1,8}题)\s*（共\s*(\d+)\s*题\s*，\s*([\d.]+)\s*分）", s)
    return tuple((t, int(n), round(float(v), 2)) for t, n, v in rows)


def show_structure(st: tuple) -> str:
    return "，".join(f"{t} {n} 题共 {v:g} 分" for t, n, v in st) or "（空）"


def check_title(title: str) -> str:
    t = str(title or "").strip()
    if not t or len(t) > 50:
        raise XxtError("试卷标题 1–50 字。")
    if _EMOJI.search(t):
        raise XxtError("试卷标题不能含表情符号。")
    return t


def plan_subs(current: list[dict], add: list[dict], remove: list[str]) -> dict:
    """Pure check of an add/remove plan.  current: sub rows {sub_id, title, structure(tuple)}; add: library papers
    {paper_id, title, structure}; remove: sub ids.  Every sub-paper must end with one structure, 1–20 of them."""
    keep = [s for s in current if s["sub_id"] not in set(remove)]
    after = len(keep) + len(add)
    if not 1 <= after <= MAX_SUBS:
        raise XxtError(f"平行试卷要有 1–{MAX_SUBS} 套子卷（改完后是 {after} 套）。")
    shapes = {s["structure"] for s in keep} | {p["structure"] for p in add}
    if any(not s for s in shapes):
        raise XxtError("有试卷读不到题型结构（可能是空卷）；空卷不能做子卷。")
    if len(shapes) > 1:
        raise XxtError("各子卷的题型、题量、分值必须一致，现在有：" + "；".join(sorted(show_structure(s) for s in shapes)))
    return {"keep": [s["title"] for s in keep], "after": after, "structure": show_structure(next(iter(shapes)))}


class PaperOps(XxtBase):
    def _pq(self, c, pid: str) -> str:
        return f"courseid={_safe_id(c.id)}&clazzid={_safe_id(c.clazz_id)}&cpi={_safe_id(c.cpi)}&paperid={_safe_id(pid)}"

    def paper_structure(self, course: str, paper_id: str) -> tuple:
        c = self.ctx(course)
        heads = self.on(M2, """
            const d=D(await F('/mooc2-ans/exam/lookpaper?courseid=%s&clazzid=-1&cpi=%s&ut=t&paperid=%s'));
            return [...d.querySelectorAll('.title')].map(T).filter(x=>/题/.test(x));""" % (_safe_id(c.id), _safe_id(c.cpi), _safe_id(paper_id)))
        return parse_structure(" ".join(heads or []))

    def _parallel_page(self, c, pid: str) -> dict | None:
        r = self.on(M2, """
            const d=D(await F('/mooc2-ans/exam/parallel-paper?%s&ut=t'));
            if(!d.getElementById('paperid')) return null;
            const v=id=>{const e=d.getElementById(id);return e?(e.getAttribute('value')||''):''};
            const easy=d.querySelector('#selectBox p span');
            return {title:v('examPaperOldTitle'),easy:easy?easy.getAttribute('value'):'',serial:v('serialNumberMode'),group:v('questionGroup'),
              subs:[...d.querySelectorAll('.testPrallelBody_td')].map(x=>{const li=x.querySelectorAll(':scope>li');
                const y=x.querySelector('.rename_yes');return {sub_id:y?y.getAttribute('paperid'):'',title:T(x.querySelector('.rename_title')),
                structure:T(x.querySelector('[id^=structure_]')),questions:T(li[2]),score:T(li[3])}})};""" % self._pq(c, pid))
        return r if isinstance(r, dict) else None

    def _parallel(self, c, paper: str) -> dict:
        p = _best(self.papers(c.id), paper, id_keys=("paper_id",))
        if p.get("parallel") is None:
            raise XxtError(f"「{p['title']}」不是平行试卷。")
        return p

    def parallel_paper(self, course: str, paper: str) -> dict:
        c = self.ctx(course)
        p = self._parallel(c, paper)
        pg = self._parallel_page(c, p["paper_id"])
        if pg is None:
            raise XxtError("平行试卷编辑页读取失败；不能视为没有子卷。")
        inv = {v: k for k, v in DIFFICULTY.items()}
        subs = [{"sub_id": s["sub_id"], "title": s["title"], "structure": show_structure(parse_structure(s["structure"])),
                 "questions": s["questions"], "score": s["score"]} for s in pg["subs"]]
        return {"paper_id": p["paper_id"], "title": pg["title"] or p["title"], "finished": not p.get("unfinished"),
                "difficulty": inv.get(int(pg["easy"]) if str(pg["easy"]).isdigit() else -1, pg["easy"]),
                "numbering": "按题型" if pg["serial"] == "1" else "连续", "group_by_type": pg["group"] != "1",
                "sub_papers": subs, "consistent": len({parse_structure(s["structure"]) for s in pg["subs"]}) <= 1,
                "published_times": p.get("published"),
                "note": "发布、删除、还原平行试卷用 publish_exam、delete_exam_paper、restore_deleted；每个学生随机拿到其中一套。"}

    # ------------------------------------------------------------------ planning (used by the previews)
    def library_papers_for_parallel(self, course: str, papers: list[str]) -> list[dict]:
        if not isinstance(papers, list) or not papers or len(papers) > MAX_SUBS:
            raise XxtError(f"请给出 1–{MAX_SUBS} 份试卷（标题或ID）。")
        c = self.ctx(course)
        lib = self.papers(c.id)
        out, seen = [], set()
        for q in papers:
            p = _best(lib, str(q), id_keys=("paper_id",))
            if p["paper_id"] in seen:
                raise XxtError(f"「{p['title']}」重复了。")
            if p.get("parallel") is not None:
                raise XxtError(f"「{p['title']}」本身是平行试卷，不能做子卷。")
            seen.add(p["paper_id"])
            out.append({"paper_id": p["paper_id"], "title": p["title"], "questions": p.get("questions"), "score": p.get("score"),
                        "structure": self.paper_structure(c.id, p["paper_id"])})
        return out

    def parallel_subs(self, course: str, paper_id: str) -> list[dict]:
        c = self.ctx(course)
        pg = self._parallel_page(c, paper_id)
        if pg is None:
            raise XxtError("平行试卷编辑页读取失败。")
        return [{"sub_id": s["sub_id"], "title": s["title"], "structure": parse_structure(s["structure"])} for s in pg["subs"]]

    # ------------------------------------------------------------------ writes
    def _add_and_wait(self, c, pid: str, add_ids: list[str]) -> dict:
        r = self.on(M2, """
            const Q=%(q)s;
            const j=await J('/mooc2-ans/exam/complete-choose-paper?'+Q,POST({selectedPaperData:JSON.stringify(%(sel)s)}));
            if(!j||j.status!==true) return {stage:'add',msg:String((j&&j.msg)||'').slice(0,80)};
            let st=null;
            for(let i=0;i<60;i++){ st=await J('/mooc2-ans/exam/choose-paper-status?'+Q);
              if(st&&st.taskStatus&&st.taskStatus!=='running') break; await new Promise(r=>setTimeout(r,1000)); }
            return {stage:'done',task:st&&st.taskStatus,msg:String((st&&st.msg)||'').slice(0,80)};
        """ % {"q": json.dumps(self._pq(c, pid)), "sel": json.dumps([{"pid": _safe_id(x), "cid": _safe_id(c.id)} for x in add_ids])},
            retry_safe=False, timeout=90)
        return r if isinstance(r, dict) else {"stage": "none"}

    def _finish(self, c, pid: str, easy: int) -> dict:
        r = self.on(M2, "return await J('/mooc2-ans/exam/create-parallel-paper?%s&ut=t&easy=%d');" % (self._pq(c, pid), int(easy)),
                    retry_safe=False)
        return r if isinstance(r, dict) else {}

    def _post_setting(self, c, pid: str, path: str, field: str, value) -> bool:
        r = self.on(M2, "return await J('/mooc2-ans/exam/%s',POST(%s));" % (path, json.dumps({
            "courseid": _safe_id(c.id), "clazzid": _safe_id(c.clazz_id), "cpi": _safe_id(c.cpi), "ut": "t",
            "paperid": _safe_id(pid), field: str(value)}, ensure_ascii=False)), retry_safe=False)
        return not isinstance(r, dict) or r.get("status") is not False

    def _set_title(self, c, pid: str, title: str, sync: bool) -> dict:
        r = self.on(M2, "return await J('/mooc2-ans/exam/update-exampaper-title',POST(%s));" % json.dumps({
            "courseid": _safe_id(c.id), "clazzid": _safe_id(c.clazz_id), "cpi": _safe_id(c.cpi), "ut": "t",
            "paperid": _safe_id(pid), "title": title, "randomPaperRenameSync": 1 if sync else 0}, ensure_ascii=False), retry_safe=False)
        return r if isinstance(r, dict) else {}

    def _apply_settings(self, c, pid: str, numbering: str, group_by_type: bool | None) -> list[str]:
        bad = []
        if group_by_type is not None and not self._post_setting(c, pid, "update-exampaper-questiongroup", "questionGroup", 0 if group_by_type else 1):
            bad.append("题型归类")
        if numbering and not self._post_setting(c, pid, "update-exampaper-serialnumber", "serialnumber", NUMBERING[numbering]):
            bad.append("题目序号")
        return bad

    def _verify(self, c, pid: str, want_titles: list[str], title: str, easy: int, numbering: str, group_by_type: bool | None) -> dict:
        row = [x for x in self.papers(c.id) if x["paper_id"] == str(pid)]
        pg = self._parallel_page(c, pid) or {"subs": []}
        got = sorted(s["title"] for s in pg["subs"])
        checks = {"listed": len(row) == 1, "finished": bool(row) and not row[0].get("unfinished"),
                  "count": bool(row) and row[0].get("parallel") == len(want_titles), "subs": got == sorted(want_titles),
                  "title": bool(row) and row[0]["title"] == title, "difficulty": str(pg.get("easy")) == str(easy),
                  "same_structure": len({parse_structure(s["structure"]) for s in pg["subs"]}) == 1}
        if numbering:
            checks["numbering"] = pg.get("serial") == str(NUMBERING[numbering])
        if group_by_type is not None:
            checks["group_by_type"] = pg.get("group") == ("0" if group_by_type else "1")
        return {"checks": checks, "sub_papers": [{"sub_id": s["sub_id"], "title": s["title"]} for s in pg["subs"]]}

    def _validate_settings(self, difficulty: str, numbering: str, group_by_type: bool | None) -> None:
        if difficulty and difficulty not in DIFFICULTY:
            raise XxtError("难度只能是 易、中、难。")
        if numbering and numbering not in NUMBERING:
            raise XxtError("题目序号只能是 连续 或 按题型。")
        if numbering == "按题型" and group_by_type is False:
            raise XxtError("不按题型归类时，题目序号只能是 连续。")

    def create_parallel_paper(self, course: str, title: str, paper_ids: list[str], difficulty: str = "易",
                              numbering: str = "", group_by_type: bool | None = None) -> dict:
        title = check_title(title)
        self._validate_settings(difficulty or "易", numbering, group_by_type)
        c = self.ctx(course)
        lib = {x["paper_id"]: x for x in self.papers(c.id)}
        missing = [x for x in paper_ids if str(x) not in lib]
        if missing:
            return {"ok": False, "write_outcome": "not_written", "error": f"试卷 {missing} 已不在试卷库；没有创建。"}
        easy = DIFFICULTY[difficulty or "易"]
        r = self.on(M2, "return await J('/mooc2-ans/exam/createAnEmptyPaper?_='+Date.now()+'&courseid=%s&clazzid=%s&pid=0&parallelpaper=1');"
                    % (_safe_id(c.id), _safe_id(c.clazz_id)), retry_safe=False)
        pid = str((r or {}).get("paperId") or "") if isinstance(r, dict) else ""
        if not pid.isdigit():
            return {"ok": False, "write_outcome": "unknown", "error": "新建平行试卷没有返回试卷ID；请在试卷库核查有没有多出「新建试卷…」。"}
        partial = {"ok": False, "write_outcome": "unknown", "paper_id": pid}
        t = self._set_title(c, pid, title, False)
        if t.get("status") is not True:
            return {**partial, "error": f"平行试卷 {pid} 已建，但标题没保存（{str(t.get('msg') or '')[:60]}）；请在试卷库核查。"}
        a = self._add_and_wait(c, pid, [str(x) for x in paper_ids])
        if a.get("stage") != "done" or a.get("task") != "success":
            return {**partial, "error": f"平行试卷 {pid} 已建，但子卷复制没有完成（{a.get('msg') or a.get('task') or a.get('stage')}）；它在试卷库里是「未完成」。"}
        bad = self._apply_settings(c, pid, numbering, group_by_type)
        f = self._finish(c, pid, easy)
        v = self._verify(c, pid, [lib[str(x)]["title"] for x in paper_ids], title, easy, numbering, group_by_type)
        ok = f.get("status") is True and not bad and all(v["checks"].values())
        out = {"ok": ok, "paper_id": pid, "title": title, "difficulty": difficulty or "易", **v}
        if not ok:
            out.update(write_outcome="unknown", error=("服务端没有完成创建：" + str(f.get("msg") or "")[:80]) if f.get("status") is not True
                       else f"平行试卷 {pid} 核对不一致（{[k for k, x in v['checks'].items() if not x] or bad}）；请用 get_parallel_paper 核查。")
        return out

    def update_parallel_paper(self, course: str, paper_id: str, add_ids: list[str], remove_ids: list[str], title: str = "",
                              sync_titles: bool = False, difficulty: str = "", numbering: str = "", group_by_type: bool | None = None) -> dict:
        self._validate_settings(difficulty, numbering, group_by_type)
        c = self.ctx(course)
        p = self._parallel(c, paper_id)
        subs = self.parallel_subs(c.id, p["paper_id"])
        have = {s["sub_id"]: s for s in subs}
        gone = [x for x in remove_ids if x not in have]
        if gone:
            return {"ok": False, "write_outcome": "not_written", "error": f"子卷 {gone} 已不在这份平行试卷里；没有修改。"}
        lib = {x["paper_id"]: x for x in self.papers(c.id)}
        if any(str(x) not in lib for x in add_ids):
            return {"ok": False, "write_outcome": "not_written", "error": "要加入的试卷已不在试卷库；没有修改。"}
        pg = self._parallel_page(c, p["paper_id"]) or {}
        easy = DIFFICULTY[difficulty] if difficulty else int(pg.get("easy") or 0)
        new_title = check_title(title) if title else p["title"]
        changed = []
        for sid in remove_ids:
            r = self.on(M2, "return await J('/mooc2-ans/exam/delete-childpaper?courseid=%s&paperid=%s&cpi=%s');"
                        % (_safe_id(c.id), _safe_id(sid), _safe_id(c.cpi)), retry_safe=False)
            if not isinstance(r, dict) or r.get("status") is not True:
                return {"ok": False, "write_outcome": "unknown" if changed else "not_written", "changed": changed,
                        "error": f"移除子卷「{have[sid]['title']}」失败；请用 get_parallel_paper 核查。"}
            changed.append(f"移除 {have[sid]['title']}")
        if add_ids:
            a = self._add_and_wait(c, p["paper_id"], [str(x) for x in add_ids])
            if a.get("stage") != "done" or a.get("task") != "success":
                return {"ok": False, "write_outcome": "unknown", "changed": changed,
                        "error": f"加入子卷没有完成（{a.get('msg') or a.get('task') or a.get('stage')}）；请用 get_parallel_paper 核查。"}
            changed.append("加入 " + "、".join(lib[str(x)]["title"] for x in add_ids))
        if title or sync_titles:
            t = self._set_title(c, p["paper_id"], new_title, sync_titles)
            if t.get("status") is not True:
                return {"ok": False, "write_outcome": "unknown", "changed": changed, "error": "标题没保存：" + str(t.get("msg") or "")[:60]}
            changed.append("改标题" + ("并同步到子卷" if sync_titles else ""))
        bad = self._apply_settings(c, p["paper_id"], numbering, group_by_type)
        f = self._finish(c, p["paper_id"], easy)
        want = [s["title"] for s in subs if s["sub_id"] not in set(remove_ids)] + [lib[str(x)]["title"] for x in add_ids]
        if sync_titles:  # the platform names synced sub-papers "<title>(1)", "<title>(2)", …
            want = [f"{new_title}({i})" for i in range(1, len(want) + 1)]
        v = self._verify(c, p["paper_id"], want, new_title, easy, numbering, group_by_type)
        ok = f.get("status") is True and not bad and all(v["checks"].values())
        out = {"ok": ok, "paper_id": p["paper_id"], "title": new_title, "changed": changed, **v}
        if not ok:
            out.update(write_outcome="unknown", error=("服务端没有完成：" + str(f.get("msg") or "")[:80]) if f.get("status") is not True
                       else f"核对不一致（{[k for k, x in v['checks'].items() if not x] or bad}）；请用 get_parallel_paper 核查。")
        return out

    # ------------------------------------------------------------------ 试卷库 导入 / 导出
    def _paper_page_vals(self, c) -> dict:
        r = self.on(M2, r"""
            const d=D(await F('/mooc2-ans/exam/paperlist?clazzid=-1&courseid=%s&ut=t&cpi=%s&topicid=0'));
            const g=id=>{const e=d.getElementById(id); return e?(e.getAttribute('value')||''):''};
            return {base:g('moocImportExportUrl'),importEnc:g('importEnc'),exportEnc:g('importExportEnc'),version:g('examExcelExportVersion')||'v2',classId:g('classId')||'-1'};
        """ % (_safe_id(c.id), _safe_id(c.cpi)))
        if not isinstance(r, dict) or r.get("base") != "https://mooc1.chaoxing.com/import-export-ans" or not r.get("importEnc"):
            raise XxtError("试卷库页缺少导入导出凭据。")
        return r

    def import_paper_file(self, course: str, file_path: str, sha: str, title: str = "", parallel_id: str = "") -> dict:
        """Ti/Word 模板导入: multipart POST {file, crc:''} to import-export-ans/import/paperlibrary-word|ti?courseId&classId=-1&pid=0&cpi&enc
        (+ &paperid=<parallel paper> to import a sub-paper).  The new paper is named after the file; `title` renames it."""
        import shutil
        import time
        from pathlib import Path
        if title:
            check_title(title)
        c = self.ctx(course)
        v = self._paper_page_vals(c)
        kind = "ti" if Path(file_path).suffix.lower() == ".ti" else "word"
        before = {x["paper_id"] for x in self.papers(c.id)}
        subs_before = {s["sub_id"] for s in self.parallel_subs(c.id, parallel_id)} if parallel_id else set()
        tmp, snap, meta = self._snapshot(file_path, sha)
        try:
            self.b.navigate(f"https://mooc2-ans.chaoxing.com/mooc2-ans/exam/paperlist?clazzid=-1&courseid={_safe_id(c.id)}&ut=t&cpi={_safe_id(c.cpi)}&topicid=0",
                            settle=1.0, readiness=False)
            self._stage(snap, meta)
            extra = f"&paperid={_safe_id(parallel_id)}" if parallel_id else ""
            r = self.here("""
                const f=document.getElementById('mcp-file').files[0]; if(!f) return {stage:'file'};
                const fd=new FormData(); fd.append('file',f,f.name); fd.append('crc','');
                const u=%s+'/import/paperlibrary-%s?courseId=%s&classId=%s&pid=0&cpi=%s&enc=%s'+%s;
                const r=await fetch(u,{method:'POST',body:fd,credentials:'include'}); let j=null; try{j=await r.json()}catch(e){}
                return {stage:'done',http:r.status,j};
            """ % (json.dumps(v["base"]), kind, _safe_id(c.id), _safe_id(v["classId"]), _safe_id(c.cpi), _safe_id(v["importEnc"]),
                   json.dumps(extra)), retry_safe=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        j = (r or {}).get("j") if isinstance(r, dict) else None
        if not isinstance(r, dict) or r.get("stage") != "done" or not isinstance(j, dict):
            return {"ok": False, "write_outcome": "unknown", "error": "导入请求没有得到回应；请在试卷库核查。"}
        if j.get("status") is not True:
            return {"ok": False, "write_outcome": "not_written", "error": f"平台拒绝导入：{str(j.get('msg') or '')[:80]}（Word 必须用平台的 Word 模板）。"}
        if parallel_id:
            for _ in range(15):
                st = self.on(M2, "return await J('/mooc2-ans/exam/choose-paper-status?%s');" % self._pq(c, parallel_id))
                if not (isinstance(st, dict) and st.get("taskStatus") == "running"):
                    break
                time.sleep(2)
            new_subs = [s for s in self.parallel_subs(c.id, parallel_id) if s["sub_id"] not in subs_before]
            ok = len(new_subs) == 1
            if ok and title:
                ok = self._set_title(c, new_subs[0]["sub_id"], check_title(title), False).get("status") is True
                new_subs = [s for s in self.parallel_subs(c.id, parallel_id) if s["sub_id"] == new_subs[0]["sub_id"]] or new_subs
            return {"ok": ok, "parallel_paper": parallel_id, "sub_paper": new_subs[0] if new_subs else None,
                    "note": "导入的子卷要和其他子卷结构一致，平行试卷才能完成创建；可用 update_parallel_paper 核对。",
                    **({} if ok else {"write_outcome": "unknown", "error": "导入后在平行试卷里没核对到新子卷。"})}
        pid = str(j.get("paperid") or "")
        if title and pid.isdigit():
            self._set_title(c, pid, check_title(title), False)
        hit = [x for x in self.papers(c.id) if x["paper_id"] == pid and pid not in before]
        ok = len(hit) == 1 and (not title or hit[0]["title"] == title.strip())
        return {"ok": ok, "paper": hit[0] if hit else None,
                **({} if ok else {"write_outcome": "unknown", "error": "导入后在试卷库里没核对到新试卷。"})}

    def export_papers(self, course: str, paper_ids: list[str], fmt: str, with_answers: bool = True) -> dict:
        """export-paperlibrary?courseId&classId=-1&paperIds&exportType&exportAll=false&cpi&enc=<#importExportEnc>&version (+includeAnswer/
        includeParser=false); one ordinary paper comes back at once (several or random papers go to the download center, not handled)."""
        import base64
        from pathlib import Path
        from .xxt import M1
        if fmt not in PAPER_EXPORT:
            raise XxtError(f"导出格式只能是：{'、'.join(PAPER_EXPORT)}。")
        etype, ext, magics = PAPER_EXPORT[fmt]
        c = self.ctx(course)
        v = self._paper_page_vals(c)
        lib = {x["paper_id"]: x for x in self.papers(c.id)}
        out_dir = Path(self.cfg.download_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for pid in paper_ids:
            if pid not in lib or lib[pid].get("parallel") is not None:
                raise XxtError(f"试卷 {pid} 不在试卷库或是平行试卷（平行试卷要逐个导出子卷）。")
            q = (f"/import-export-ans/export-paperlibrary?courseId={_safe_id(c.id)}&classId={_safe_id(v['classId'])}&paperIds={_safe_id(pid)}"
                 f"&exportType={etype}&exportAll=false&cpi={_safe_id(c.cpi)}&enc={_safe_id(v['exportEnc'])}&version={_safe_id(v['version'])}"
                 + ("" if with_answers else "&includeAnswer=false&includeParser=false"))
            r = self.on(M1, """const r=await fetch(%s,{credentials:'include'}); const b=new Uint8Array(await r.arrayBuffer());
                if(b.length>30*1024*1024) return {big:true}; let s=''; for(let i=0;i<b.length;i+=8192) s+=String.fromCharCode.apply(null,b.subarray(i,i+8192));
                return {http:r.status,b64:btoa(s)};""" % json.dumps(q), timeout=120)
            data = base64.b64decode((r or {}).get("b64") or "") if isinstance(r, dict) else b""
            if not data or not any(data.startswith(m) for m in magics):
                raise XxtError(f"试卷「{lib[pid]['title']}」导出失败：{data[:120].decode('utf-8', 'ignore')[:80] or '没有内容'}。")
            name = re.sub(r'[\\/:*?"<>|\s]+', "_", f"{c.name}-{lib[pid]['title']}{'' if with_answers else '-无答案'}.{ext}")
            path = out_dir / name
            path.write_bytes(data)
            files.append({"paper": lib[pid]["title"], "file": str(path), "size": len(data)})
        return {"ok": True, "format": fmt, "with_answers": with_answers, "files": files}


# format -> (exportType, file extension, accepted leading bytes)
PAPER_EXPORT = {"Word": ("word", "docx", (b"PK",)), "PDF": ("pdf", "pdf", (b"%PDF",)), "Excel": ("excel", "xls", (b"\xd0\xcf\x11\xe0", b"PK")),
                "Ti": ("ti", "ti", (b'{"type"', b'{"time"'))}
