"""Deletes with recycle-bin verification, recycle bins, discussion moderation, material folders/permissions,
targeted reminders (endpoints read from the pages' own scripts and verified on the test course, 2026-11-07).

Recycle bins (all mooc2-ans):
  作业  delete  GET /mooc2-ans/work/delete?courseid&classid=0&id=<work record>&recycle=1&cpi   (recycle=0 restores)
        bin     /mooc2-ans/work/list?courseid&selectClassid=0&recycle=1&cpi&v=0&topicid=0     (li[id^=work])
  考试  delete  GET /mooc2-ans/exam/test/delete-test?id&courseid&clazzid&ut=t&cpi&recyle=1     (recyle=0 restores)
        bin     /mooc2-ans/exam/test?courseid&ut=&cpi&clazzid&recyle=1&topicid=0
  试卷  delete  POST /mooc2-ans/exam/deletepaper?…&status=2 {paperids}  (status 0 restores, 1 purges from the bin)
        bin     /mooc2-ans/exam/paperlist?clazzid=-1&courseid&ut=t&cpi&type=1                    (ul.dataBody_td[data])
  资料  delete  POST /mooc2-ans/coursedata/batchDelete?dataId&courseId
        bin     GET /mooc2-ans/coursedata/recycle-data-list?courseid&pagenum&cpi&pagesize           (ul.recycle_div[kid])
        restore GET /mooc2-ans/coursedata/recycle-data {dataIds, courseid, cpi}; purge delete-recycle-data
A delete counts as done only when the item left the list, every other item of that list is still there, and the
item is in the bin.  Topics: GET groupweb /pc/topic/{bbsid}/{uuid}/deleteTopic; top/essence
/pc/topic/{uuid}/{set|cancel}/{top|choice}.  Urge: GET /mooc2-ans/work/urge {courseid, clazzid, cpi, workid,
studentIds} (per student, the mark page's 督促) -- recipients are bound at preview.
Materials: add-folder (GET), update-isDownload (POST {courseId, dataId, isDownload, cpi}), move (POST {dataId:"id--",
folderId, courseid, cpi}); a folder's content is /mooc2-ans/coursedata?…&dataId=<folder>.
"""
from __future__ import annotations

import json
import re
import time
import uuid as _uuid

from .xxt import GROUP, M1, M2, STAT, XxtBase, XxtError, _best, _safe_id

BIN_KINDS = ("作业", "考试", "试卷", "资料")
PURGE_KINDS = ("试卷", "资料")


def outline_levels(outline: str) -> list[tuple[int, str]]:
    """Outline text -> [(level from 0, title)]; a tab or two spaces is one level; levels may only go one deeper at a time."""
    out: list[tuple[int, str]] = []
    for raw in (outline or "").replace("\r", "").split("\n"):
        if not raw.strip():
            continue
        lead = raw[:len(raw) - len(raw.lstrip())]
        lv = lead.count("\t") + (len(lead.replace("\t", "")) + 1) // 2
        prev = out[-1][0] if out else -1
        if lv > prev + 1 or lv > 6:
            raise XxtError(f"「{raw.strip()[:30]}」的缩进跳级了（每深一级多缩进两个空格，最多 7 层）。")
        t = raw.strip()
        if len(t) > 100:
            raise XxtError("每个目录名最多 100 字。")
        out.append((lv, t))
    if not out or len(out) > 100:
        raise XxtError("outline 每行一个目录，1–100 行；下一级在行首多缩进两个空格。")
    return out


def moved_check(before: list[str], after: list[str], binned: list[str] | None, target: str) -> tuple[bool, str]:
    """True when `target` left the list, nothing else did, and (if a bin was read) it is in the bin."""
    b, a = set(map(str, before)), set(map(str, after))
    if target in a:
        return False, "还在列表里"
    lost = (b - {target}) - a
    if lost:
        return False, f"列表里另有 {len(lost)} 项也不见了（列表可能没读全）"
    if binned is not None and target not in set(map(str, binned)):
        return False, "回收站里没有找到它"
    return True, ""


class ManageOps(XxtBase):
    # ------------------------------------------------------------------ list readers (raise on an unreadable page)
    def _rows(self, kind: str, c, binned: bool = False, folder: str = "0") -> list[dict]:
        cid, cpi, clz = _safe_id(c.id), _safe_id(c.cpi), _safe_id(c.clazz_id)
        if kind == "作业":
            u = (f"/mooc2-ans/work/list?courseid={cid}&selectClassid=0&recycle=1&cpi={cpi}&v=0&topicid=0&from=" if binned
                 else f"/mooc2-ans/work/list?{self.q(c)}")
            js = """const d=D(await F(%s)); if(!d.querySelector('#recycle')) return null;
                return [...d.querySelectorAll('.taskList li[id^=work]')].map(li=>({id:li.id.replace('work',''),title:T(li.querySelector('.list_li_tit')),class:T(li.querySelector('.list_class'))}));"""
        elif kind == "考试":
            u = (f"/mooc2-ans/exam/test?courseid={cid}&ut=&cpi={cpi}&clazzid={clz}&recyle=1&topicid=0" if binned
                 else f"/mooc2-ans/exam/test?{self.q(c)}")
            js = """const d=D(await F(%s)); if(!d.querySelector('#recyle')) return null;
                return [...d.querySelectorAll('li[data]')].filter(l=>l.querySelector('.list_li_tit')).map(l=>({id:l.getAttribute('data'),
                  title:T(l.querySelector('.list_li_tit')),paper_id:(l.querySelector('.list_li_content')||{getAttribute:()=>null}).getAttribute('data'),class:T(l.querySelector('.list_class'))}));"""
        elif kind == "试卷":
            u = f"/mooc2-ans/exam/paperlist?clazzid=-1&courseid={cid}&ut=t&cpi={cpi}&topicid=0" + ("&type=1" if binned else "")
            js = """const d=D(await F(%s)); if(!d.querySelector('#courseId')) return null;
                return [...d.querySelectorAll('ul.dataBody_td[data]')].filter(u=>u.getAttribute('type')=='1').map(u=>({id:u.getAttribute('data'),
                  title:T(u.querySelector('.rename_title'))||T(u.querySelector('li:nth-child(2)')),
                  purgeable:__BIN__?!!u.querySelector('.removeBtn'):undefined}));""".replace("__BIN__", "true" if binned else "false")
        elif kind == "资料":
            if binned:
                u = f"/mooc2-ans/coursedata/recycle-data-list?courseid={cid}&pagenum=1&cpi={cpi}&pagesize=200"
                js = """const r=await fetch(%s,{credentials:'include'}); if(!r.ok) return null; const d=D(await r.text());
                    return [...d.querySelectorAll('ul.recycle_div[kid]')].map(u=>({id:u.getAttribute('kid'),title:T(u.querySelector('.ul_text'))}));"""
            else:
                u = f"/mooc2-ans/coursedata?{self.q(c)}&v=6" + (f"&dataId={_safe_id(folder)}" if folder and folder != "0" else "")
                js = """const d=D(await F(%s)); if(!d.querySelector('#dataId')) return null;
                    return [...d.querySelectorAll('ul.dataBody_td[id]')].map(u=>({id:u.id,title:u.getAttribute('dataname'),folder:u.getAttribute('type')==='afolder',
                      download:u.getAttribute('isdown')==='1',open:u.getAttribute('isopen')}));"""
        else:
            raise XxtError(f"只支持：{'、'.join(BIN_KINDS)}。")
        r = self.on(M2, js % json.dumps(u))
        if not isinstance(r, list):
            raise XxtError(f"{kind}{'回收站' if binned else '列表'}读取失败或结构不完整；没有继续。")
        return r

    def recycle_bin(self, course: str, kind: str) -> dict:
        c = self.ctx(course)
        return {"kind": kind, "items": self._rows(kind, c, binned=True)}

    def _bin_request(self, kind: str, c, item_id: str, action: str) -> str:
        """JS for delete (to the bin) / restore / purge of one item."""
        cid, cpi, clz, i = _safe_id(c.id), _safe_id(c.cpi), _safe_id(c.clazz_id), _safe_id(item_id)
        if kind == "作业":
            flag = {"delete": 1, "restore": 0}[action]
            return f"return await J('/mooc2-ans/work/delete?courseid={cid}&classid=0&id={i}&recycle={flag}&cpi={cpi}');"
        if kind == "考试":
            flag = {"delete": 1, "restore": 0}[action]
            return f"return await J('/mooc2-ans/exam/test/delete-test?id={i}&courseid={cid}&clazzid={clz}&ut=t&cpi={cpi}&recyle={flag}');"
        if kind == "试卷":
            st = {"delete": 2, "restore": 0, "purge": 1}[action]
            return (f"return await J('/mooc2-ans/exam/deletepaper?courseid={cid}&clazzid={clz}&cpi={cpi}&ut=t&status={st}',"
                    f"POST({{courseid:'{cid}',clazzid:'{clz}',cpi:'{cpi}',ut:'t',status:'{st}',paperids:'{i}'}}));")
        if kind == "资料":
            if action == "delete":
                return f"return await J('/mooc2-ans/coursedata/batchDelete?dataId={i}&courseId={cid}',{{method:'POST'}});"
            ep = {"restore": "recycle-data", "purge": "delete-recycle-data"}[action]
            return f"return await J('/mooc2-ans/coursedata/{ep}?dataIds={i}&courseid={cid}&cpi={cpi}');"
        raise XxtError(f"只支持：{'、'.join(BIN_KINDS)}。")

    def find_binnable(self, course: str, kind: str, target: str, binned: bool = False) -> dict:
        c = self.ctx(course)
        return _best(self._rows(kind, c, binned=binned), target, key="title", id_keys=("id",))

    def delete_to_bin(self, course: str, kind: str, target_id: str) -> dict:
        c = self.ctx(course)
        before = self._rows(kind, c)
        t = _best(before, target_id, key="title", id_keys=("id",))
        r = self.on(M2, self._bin_request(kind, c, t["id"], "delete"), retry_safe=False)
        after, binned = self._rows(kind, c), self._rows(kind, c, binned=True)
        ok, why = moved_check([x["id"] for x in before], [x["id"] for x in after], [x["id"] for x in binned], str(t["id"]))
        refused = isinstance(r, dict) and r.get("status") is False and any(x["id"] == t["id"] for x in after)
        out = {"ok": ok, "kind": kind, "deleted": t["title"], "id": t["id"], "in_recycle_bin": ok, "note": "可用 restore_deleted 从回收站还原"}
        if not ok:
            out.update(write_outcome="not_written" if refused else "unknown",
                       error=(f"服务端拒绝：{str(r.get('msg') or '')[:80]}" if refused else f"删除后核对不通过：{why}；请用 list_recycle_bin 核查，不要重复删除。"))
        return out

    def bin_action(self, course: str, kind: str, target_id: str, action: str) -> dict:
        """restore (back to the list) or purge (gone from the bin for good) one item of the recycle bin."""
        if action == "purge" and kind not in PURGE_KINDS:
            raise XxtError(f"只有 {'、'.join(PURGE_KINDS)} 支持从回收站彻底删除。")
        c = self.ctx(course)
        before_bin = self._rows(kind, c, binned=True)
        t = _best(before_bin, target_id, key="title", id_keys=("id",))
        if action == "purge" and t.get("purgeable") is False:
            raise XxtError("这份试卷还被考试引用（包括回收站里的考试），平台不允许彻底删除；没有删除。")
        r = self.on(M2, self._bin_request(kind, c, t["id"], action), retry_safe=False)
        after_bin, listed = self._rows(kind, c, binned=True), self._rows(kind, c)
        ids_bin = [x["id"] for x in after_bin]
        if action == "restore":
            ok = t["id"] not in ids_bin and any(x["id"] == t["id"] for x in listed)
        else:
            ok, _ = moved_check([x["id"] for x in before_bin], ids_bin, None, str(t["id"]))
            ok = ok and not any(x["id"] == t["id"] for x in listed)
        out = {"ok": ok, "kind": kind, "action": {"restore": "还原", "purge": "彻底删除"}[action], "title": t["title"], "id": t["id"]}
        if not ok:
            out.update(write_outcome="unknown", error="操作后核对不通过；请用 list_recycle_bin 核查，不要重复操作。",
                       server=r if isinstance(r, dict) else None)
        return out

    # ------------------------------------------------------------------ discussions
    def _topic_state(self, c, bbs: str) -> dict:
        r = self.on(GROUP, """
            const base='folder_uuid=&courseId=%(c)s&isSetTop=&selectedStartTime=&selectedEndTime=&selectedType=0&learnSilverStartTime=&learnSilverEndTime=&lastAuxValue=';
            const j=await J('/course/topic/%(b)s/getTopicList?page=1&pageSize=200&kw=&'+base);
            let top=null; try{const t=await J('/course/topic/%(b)s/getTopTopicList?'+base); top=(t&&t.datas||[]).map(x=>x.uuid)}catch(e){}
            if(j&&j.status===true&&j.datas===undefined&&Array.isArray(j.folder_list)) return {items:[],top:top||[]};
            if(!j||!Array.isArray(j.datas)) return null;
            return {items:j.datas.map(x=>({topic_id:x.uuid,title:x.title,choice:x.choice==1,top:x.isTop==1||x.top==1,replies:x.reply_count})),top};
        """ % {"c": _safe_id(c.id), "b": bbs})
        if not isinstance(r, dict) or not isinstance(r.get("items"), list):
            raise XxtError("讨论列表读取失败；没有继续。")
        tops = set(r.get("top") or [])
        allx = {x["topic_id"]: x for x in r["items"]}
        for u in tops:
            allx.setdefault(u, {"topic_id": u, "title": None, "choice": None, "replies": None})
        for x in allx.values():
            x["top"] = x["topic_id"] in tops or bool(x.get("top"))
        return allx

    def delete_topic_verified(self, course: str, topic_id: str) -> dict:
        c = self.ctx(course)
        bbs = self._bbsid(c)
        before = self._topic_state(c, bbs)
        if topic_id not in before:
            raise XxtError("讨论列表里没有这个话题。")
        r = self.on(GROUP, f"return await J('/pc/topic/{bbs}/{_safe_id(topic_id)}/deleteTopic?_t='+Date.now());", retry_safe=False)
        after = self._topic_state(c, bbs)
        ok, why = moved_check(list(before), list(after), None, topic_id)
        out = {"ok": ok, "deleted": before[topic_id]["title"], "topic_id": topic_id}
        if not ok:
            out.update(write_outcome="unknown", error=f"删除后核对不通过：{why}", server=r if isinstance(r, dict) else None)
        return out

    def moderate_topic(self, course: str, topic_id: str, action: str) -> dict:
        acts = {"置顶": ("set", "top"), "取消置顶": ("cancel", "top"), "加精": ("set", "choice"), "取消加精": ("cancel", "choice")}
        if action not in acts:
            raise XxtError(f"action 只能是：{'、'.join(acts)}。")
        op, what = acts[action]
        c = self.ctx(course)
        bbs = self._bbsid(c)
        before = self._topic_state(c, bbs)
        if topic_id not in before:
            raise XxtError("讨论列表里没有这个话题。")
        r = self.on(GROUP, f"return await J('/pc/topic/{_safe_id(topic_id)}/{op}/{what}?_t='+Date.now());", retry_safe=False)
        after = self._topic_state(c, bbs).get(topic_id) or {}
        want = op == "set"
        got = after.get(what)
        ok = isinstance(r, dict) and r.get("status") is not False and got == want
        out = {"ok": ok, "topic": before[topic_id]["title"], "action": action, what: got}
        if not ok:
            out.update(write_outcome="not_written" if isinstance(r, dict) and r.get("status") is False else "unknown",
                       error=f"操作后核对不通过（{str((r or {}).get('msg') or '') if isinstance(r, dict) else ''}）。")
        return out

    def teacher_reply(self, course: str, topic_id: str, content: str) -> dict:
        from .ops_write import _uri
        if not content.strip() or len(content) > 5000:
            raise XxtError("回复内容 1–5000 字。")
        c = self.ctx(course)
        bbs = self._bbsid(c)
        before = self._topic_state(c, bbs)
        if topic_id not in before:
            raise XxtError("讨论列表里没有这个话题。")
        # The reply page re-renders (BrowserSkill refuses an evaluate there): read its urlToken from the page HTML
        # fetched on the static base page, then post from there.
        page = (f"/course/topic/v3/bbs/{bbs}/{_safe_id(topic_id)}/replysList?courseId={_safe_id(c.id)}"
                f"&classId={_safe_id(c.clazz_id)}&cpi={_safe_id(c.cpi)}&ut=t")
        form = {"courseId": c.id, "classId": c.clazz_id, "replyId": "", "uuid": str(_uuid.uuid4()),
                "topic_content": _uri(content), "anonymous": "0", "bbsid": bbs}
        r = self.on(GROUP, """
            const h=await F(%s); const m=h.match(/urlToken\\s*:\\s*['"]([0-9a-fA-F]{16,64})['"]/);
            if(!m) return {stage:'token'};
            const f=%s; f.urlToken=m[1];
            const r=await fetch('/pc/invitation/%s/addReplys',{method:'POST',credentials:'include',
              headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest'},
              body:new URLSearchParams(f).toString()});
            let j=null; try{j=await r.json()}catch(e){}
            const rep=j&&j.datas&&j.datas.reply;
            return {http:r.status,status:!!(j&&j.status),msg:j&&j.msg?String(j.msg).slice(0,80):'',content:rep?rep.content:null,reply_id:rep?rep.uuid:null};
        """ % (json.dumps(page), json.dumps(form, ensure_ascii=False), _safe_id(topic_id)), retry_safe=False)
        if isinstance(r, dict) and r.get("stage") == "token":
            raise XxtError("话题页缺少回复凭据；没有回复。")
        # The topic's reply_count catches up a few seconds later; the server echoes the stored reply at once.
        stored = isinstance(r, dict) and r.get("content") == content
        after = {}
        for _ in range(4):
            after = self._topic_state(c, bbs).get(topic_id) or {}
            if int(after.get("replies") or 0) > int(before[topic_id].get("replies") or 0):
                break
            time.sleep(2)
        grew = int(after.get("replies") or 0) > int(before[topic_id].get("replies") or 0)
        ok = stored or (isinstance(r, dict) and bool(r.get("status")) and grew)
        out = {"ok": ok, "topic": before[topic_id]["title"], "stored_reply": r.get("content") if isinstance(r, dict) else None,
               "replies_before": before[topic_id].get("replies"), "replies_after": after.get("replies")}
        if not ok:
            out.update(write_outcome="unknown", error="回复后没有核实到；请打开话题核查，不要重复回复。")
        return out

    # ------------------------------------------------------------------ chapters
    def delete_chapter_bound(self, course: str, chapter_id: str, bound_children: list[str]) -> dict:
        c = self.course(course)
        chs = self.chapters(c.id)
        ch = next((x for x in chs if x["chapter_id"] == chapter_id), None)
        if not ch:
            raise XxtError("章节已不存在；没有删除。")
        kids = sorted(x["chapter_id"] for x in chs if x["number"].startswith(ch["number"] + "."))
        if kids != sorted(map(str, bound_children)):
            raise XxtError("预演后子章节有变化；没有删除，请重新预演。")
        r = self.on(M1, f"const f=new FormData(); f.append('courseid','{_safe_id(c.id)}'); f.append('nodeid','{_safe_id(chapter_id)}');"
                        "return await J('/mooc-ans/edit/deletechapter',{method:'POST',body:f});", retry_safe=False)
        after = [x["chapter_id"] for x in self.chapters(c.id)]
        gone = {chapter_id, *kids}
        lost = ({x["chapter_id"] for x in chs} - gone) - set(after)
        ok = not (gone & set(after)) and not lost
        out = {"ok": ok, "deleted": f"{ch['number']} {ch['title']}", "children_deleted": len(kids)}
        if not ok:
            out.update(write_outcome="unknown", error="删除后核对不通过（章节还在，或别的章节也不见了）；请用 list_chapters 核查。",
                       server=r if isinstance(r, dict) else None)
        return out

    def _chapter_post(self, path: str, form: dict) -> dict:
        r = self.on(M1, "const f=new FormData(); for(const [k,v] of Object.entries(%s)) f.append(k,v); return await J(%s,{method:'POST',body:f});"
                    % (json.dumps(form, ensure_ascii=False), json.dumps(path)), retry_safe=False)
        return r if isinstance(r, dict) else {}

    def move_chapter(self, course: str, chapter: str, parent: str) -> dict:
        """移动到: the chapter (with its children) becomes the last child of `parent`."""
        c = self.course(course)
        chs = self.chapters(c.id)
        ch = _best(chs, chapter, id_keys=("chapter_id", "number"))
        p = _best(chs, parent, id_keys=("chapter_id", "number"))
        if p["chapter_id"] == ch["chapter_id"] or p["number"].startswith(ch["number"] + "."):
            raise XxtError("不能移到它自己或它的子章节下面。")
        depth = max([x["number"].count(".") for x in chs if x["number"] == ch["number"] or x["number"].startswith(ch["number"] + ".")])
        if p["number"].count(".") + 1 + (depth - ch["number"].count(".")) + 1 > 7:
            raise XxtError("移动后会超过 7 层目录。")
        r = self._chapter_post("/mooc-ans/edit/chaptermove", {"courseid": c.id, "nodeid": ch["chapter_id"], "pnodeid": p["chapter_id"]})
        now = {x["chapter_id"]: x for x in self.chapters(c.id)}
        ok = r.get("status") is True and now.get(ch["chapter_id"], {}).get("parent_id") == p["chapter_id"]
        out = {"ok": ok, "chapter": ch["title"], "parent": p["title"], "number_now": now.get(ch["chapter_id"], {}).get("number")}
        if not ok:
            out.update(write_outcome="unknown", error="移动后读回的上级章节不对；请用 list_chapters 核查。", server=r)
        return out

    def reorder_chapter(self, course: str, chapter: str, target: str, position: str) -> dict:
        """排序: put the chapter right before / after a sibling-level target (the editor's drag)."""
        if position not in ("before", "after"):
            raise XxtError("position 只能是 before 或 after。")
        c = self.course(course)
        chs = self.chapters(c.id)
        ch = _best(chs, chapter, id_keys=("chapter_id", "number"))
        t = _best(chs, target, id_keys=("chapter_id", "number"))
        if ch["chapter_id"] == t["chapter_id"] or t["number"].startswith(ch["number"] + "."):
            raise XxtError("目标不能是它自己或它的子章节。")
        if ch["layer"] != 1 and t["layer"] == 1:
            raise XxtError("非一级目录不能成为一级目录。")
        r = self._chapter_post("/mooc-ans/edit/movechapter/drag", {"courseid": c.id, "nodeid": ch["chapter_id"], "destid": t["chapter_id"], "position": position})
        now = self.chapters(c.id)
        sib = [x["chapter_id"] for x in now if x["parent_id"] == t["parent_id"]]
        ok = r.get("status") is True and ch["chapter_id"] in sib and t["chapter_id"] in sib and \
            sib.index(ch["chapter_id"]) == sib.index(t["chapter_id"]) + (1 if position == "after" else -1)
        num = next((x["number"] for x in now if x["chapter_id"] == ch["chapter_id"]), None)
        out = {"ok": ok, "chapter": ch["title"], "position": position, "target": t["title"], "number_now": num}
        if not ok:
            out.update(write_outcome="unknown", error="排序后读回的位置不对；请用 list_chapters 核查。", server=r)
        return out

    def import_chapters(self, course: str, outline: str) -> dict:
        """快速导入目录: each line one chapter; the editor's format indents each level by two spaces.  Appended to the course."""
        rows = outline_levels(outline)
        c = self.course(course)
        before = {x["chapter_id"] for x in self.chapters(c.id)}
        text = "".join("  " * lv + t + "\n" for lv, t in rows)
        r = self._chapter_post("/mooc-ans/edit/importdirForText", {"courseId": c.id, "text": text})
        now = self.chapters(c.id)
        new = [x for x in now if x["chapter_id"] not in before]
        ok = (r.get("success") is True or r.get("status") is True) and \
            [(int(x["layer"]) - 1, x["title"]) for x in new] == [(lv, t) for lv, t in rows]
        out = {"ok": ok, "created": [{"number": x["number"], "title": x["title"], "layer": x["layer"]} for x in new]}
        if not ok:
            out.update(write_outcome="unknown" if new or not r.get("msg") else "not_written",
                       error=f"导入后的目录和大纲不一致（{str(r.get('msg') or '')[:60]}）；请用 list_chapters 核查。")
        return out

    # ------------------------------------------------------------------ materials
    def create_material_folder(self, course: str, name: str) -> dict:
        n = re.sub(r"[`~!@#$%^&*+<>?:\"{},\\/;\[\]|]", "", name or "").strip()
        if not 2 <= len(n) <= 100:
            raise XxtError("文件夹名 2–100 字，且不能含特殊字符。")
        c = self.ctx(course)
        before = self._rows("资料", c)
        if any(x["folder"] and x["title"] == n for x in before):
            raise XxtError("根目录已有同名文件夹；没有新建。")
        q = {"dataName": n, "courseId": c.id, "classId": c.clazz_id, "courseName": c.name, "rootId": "0", "dataType": "afolder",
             "source": "1", "isOpen": "0", "parent": "", "cpi": c.cpi, "move": "true"}
        r = self.on(M2, "return await F('/mooc2-ans/coursedata/add-folder?'+new URLSearchParams(%s));" % json.dumps(q, ensure_ascii=False),
                    retry_safe=False)
        hit = [x for x in self._rows("资料", c) if x["folder"] and x["title"] == n]
        out = {"ok": len(hit) == 1, "folder": n, "folder_id": hit[0]["id"] if hit else None}
        if not hit:
            out.update(write_outcome="not_written" if str(r).strip() == "-1" else "unknown",
                       error="文件夹层级超出限制" if str(r).strip() == "-1" else "新建后资料列表里没有这个文件夹；请用 list_materials 核查。")
        return out

    def set_material_download(self, course: str, material_id: str, allow: bool) -> dict:
        c = self.ctx(course)
        m = _best(self._rows("资料", c), material_id, key="title", id_keys=("id",))
        if m["folder"]:
            raise XxtError("文件夹没有单独的下载开关；请对文件设置。")
        r = self.on(M2, "return await J('/mooc2-ans/coursedata/update-isDownload',POST(%s));"
                    % json.dumps({"courseId": c.id, "dataId": m["id"], "isDownload": 1 if allow else 0, "cpi": c.cpi}), retry_safe=False)
        now = next((x for x in self._rows("资料", c) if x["id"] == m["id"]), {})
        ok = now.get("download") is allow
        out = {"ok": ok, "material": m["title"], "download_before": m["download"], "download_after": now.get("download")}
        if not ok:
            out.update(write_outcome="unknown", error="设置后读回不一致。", server=r if isinstance(r, dict) else None)
        return out

    def move_material(self, course: str, material_id: str, folder_id: str) -> dict:
        c = self.ctx(course)
        root = self._rows("资料", c)
        m = _best(root, material_id, key="title", id_keys=("id",))
        f = _best([x for x in root if x["folder"]], folder_id, key="title", id_keys=("id",))
        if m["id"] == f["id"]:
            raise XxtError("不能把文件夹移到它自己里面。")
        inside_before = self._rows("资料", c, folder=f["id"])
        r = self.on(M2, "return await F('/mooc2-ans/coursedata/move',POST(%s));"
                    % json.dumps({"dataId": m["id"] + "--", "folderId": f["id"], "courseid": c.id, "cpi": c.cpi}), retry_safe=False)
        root_after, inside = self._rows("资料", c), self._rows("资料", c, folder=f["id"])
        ok = not any(x["id"] == m["id"] for x in root_after) and any(x["id"] == m["id"] for x in inside) \
            and {x["id"] for x in inside_before} <= {x["id"] for x in inside}
        out = {"ok": ok, "material": m["title"], "folder": f["title"]}
        if not ok:
            out.update(write_outcome="unknown", error="移动后核对不通过；请用 list_materials 核查。")
        return out

    def folder_materials(self, course: str, folder: str = "0") -> list[dict]:
        c = self.ctx(course)
        if folder and folder != "0":
            folder = _best([x for x in self._rows("资料", c) if x["folder"]], folder, key="title", id_keys=("id",))["id"]
        return self._rows("资料", c, folder=folder)

    # ------------------------------------------------------------------ grade export
    def export_grades_verified(self, course: str, cls: str) -> dict:
        """学情统计 → 成绩 → 导出: getEnc, then the page's own form POST to fystat-ans /api/export (a file download)."""
        from pathlib import Path
        c = self.ctx(course)
        clz = _safe_id(self.resolve_class(c, cls))
        e = self.on(STAT, "return await J('/stat2/score-data/getEnc',POST({clazzid:'%s',courseid:'%s',cpi:'%s',ut:'t'}));"
                    % (clz, _safe_id(c.id), _safe_id(c.cpi)))
        enc = (e or {}).get("exportEnc") if isinstance(e, dict) else None
        if not isinstance(enc, str) or not re.fullmatch(r"[0-9a-fA-F]{16,64}", enc):
            raise XxtError("没有拿到导出凭据；没有导出。")
        if int((e or {}).get("studentCount") or 0) > 2000:
            raise XxtError("班级超过 2000 人，平台改走下载中心异步导出；请在学习通里导出。")
        d = self.cfg.download_dir
        d.mkdir(parents=True, exist_ok=True)
        out = Path(d) / re.sub(r'[\\/:*?"<>|\s]+', "_", f"{c.name}-{clz}-成绩.xlsx")
        self.here("""
            let f=document.getElementById('__xxt_exp_form'); if(f) f.remove();
            f=document.createElement('form'); f.id='__xxt_exp_form'; f.method='post'; f.action='https://fystat-ans.chaoxing.com/api/export';
            for(const [k,v] of Object.entries(%s)){const i=document.createElement('input'); i.type='hidden'; i.name=k; i.value=v; f.appendChild(i);}
            const b=document.createElement('button'); b.type='submit'; b.id='__xxt_exp'; b.textContent='export';
            b.style.cssText='position:fixed;top:10px;left:10px;z-index:99999;font-size:24px'; f.appendChild(b); document.body.appendChild(f); return true;
        """ % json.dumps({"courseId": c.id, "classId": clz, "exportEnc": enc, "createId": c.cpi, "seltables": "6"}))
        self.b.download_selector("#__xxt_exp", str(out))
        ok = out.is_file() and out.stat().st_size > 0 and out.read_bytes()[:2] == b"PK"
        res = {"ok": ok, "file": str(out), "size": out.stat().st_size if out.is_file() else 0, "students": (e or {}).get("studentCount")}
        if not ok:
            res.update(write_outcome="unknown", error="下载的文件不是 Excel 或为空；请在 学情统计 → 成绩 里导出。")
        return res

    # ------------------------------------------------------------------ reminders
    def urge_students(self, course: str, assignment: str, person_ids: list[str]) -> dict:
        c = self.ctx(course)
        a = self._find_assignment(c, assignment)
        s = self.submissions(c.id, a["id"])
        pending = {str(x["person_id"]) for x in s["unsubmitted"]}
        ids = [_safe_id(x) for x in person_ids]
        if not ids or not set(ids) <= pending:
            raise XxtError("要督促的学生必须都在当前未交名单里；名单已变化，没有发送。请重新预演。")
        clz = _safe_id(a.get("clazz_id") or c.clazz_id)
        r = self.on(M2, f"return await J('/mooc2-ans/work/urge?courseid={_safe_id(c.id)}&clazzid={clz}&cpi={_safe_id(c.cpi)}"
                        f"&workid={_safe_id(a['relation_id'])}&studentIds={','.join(ids)}');", retry_safe=False)
        ok = isinstance(r, dict) and r.get("status") is True
        out = {"ok": ok, "assignment": a["title"], "sent_to": len(ids)}
        if not ok:
            out.update(write_outcome="not_written" if isinstance(r, dict) and r.get("status") is False else "unknown",
                       error=f"服务端没有确认：{str((r or {}).get('msg') or '') if isinstance(r, dict) else '无结果'}")
        return out
