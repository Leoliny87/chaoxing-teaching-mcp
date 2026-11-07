"""More chapter inserts (from the chapter editor bundle ananas2/assets/Home-*.js, verified on the test course, 2026-11-08).

All read endpoints are on mooc1 (the editor's own origin) unless noted:
  速课     GET /suke/sukeList?lastId&pageSize -> data.list[{id, title, url, cover, insertTime}]
           module insertmicroCourse {url, title, cover, mid, _jobid, jobid}                       (task point)
  图书     GET /ananas/book/query/<keyword>/<page> -> result[{dxid, bookname, author, publisher, publishdate,
           readurl, pdgurl, coverurl, size, isshidu}], pageInfo.hitcount
           module insertbook {readurl, pdgurl, coverurl, bookname, author, publisher, publishdate, size(试读=1),
           mid, _jobid, jobid, ywbf:"1", start:1}                                                   (task point)
  图书内页 GET /ananas/chapter/query/<keyword>/<page> -> result[{title, bookname, size(page), author, publishdate,
           readurl, content}]; inserted as the inline mark chapterLink:
           <a id class="chapterLink" type="text" linktype="0" href=readurl _href address title target desc data tips>
  全景     mobile3 GET /fyportal/threedresourse/panorama/list -> [{id, filename, resourcetype, uploadtime}]
           module resourceQj {previewUrl: https://mobile3.chaoxing.com/fyportal/threedresourse/panorama/review/<id>,
           title, mid}
  投票问卷 mobilelearn POST /v2/apis/chapterquestion/publish (the #formId of page/questionnaire/addOrUpdateQues4Chapter)
           -> data.message[0].att_chat_course {id, title, subTitle}; module insertvote {id, title, description=subTitle,
           mid, _jobid}
  文档导入 upload to the cloud disk (as other chapter files) -> POST /sqp/api/upload-from-yp {objectId, fileName,
           isParseLatexFormula} (404 until the cloud object is ready; retry) -> crc -> GET /sqp/api/parseToHtml?file=<crc>
           -> {html}; the html is appended to the card body.
  AI 排版  POST /ai-ans/ai/chapter/format JSON {userId, formatText, styleList, t, enc} (t/enc = get-course-info
           aiInfo.aiWriting.aiTime / aiFormatEnc) -> text = JSON [{styleName, content}]; the page wraps each item in
           <styleName style=… class=…> using the chosen template (通用模板1 / 通用模板2 / 科技蓝) and puts images,
           tables and links back at their "[图片n]" placeholders.
"""
from __future__ import annotations

import hashlib
import html as _h
import json
import re
import shutil
import time
import uuid as _uuid
from pathlib import Path

from .ops_write import _jobid, _mid, card_attachments
from .xxt import M1, ML, XxtBase, XxtError, _safe_id  # noqa: F401

PANORAMA_HOST = "https://mobile3.chaoxing.com"
SEARCH_KINDS = ("速课", "图书", "图书内页", "全景")

# the editor's three AI-format templates (AiFormat component)
AI_TEMPLATES = {
    "通用模板1": {"styleName": '["h1","h2","h1","normal","h3"]', "style": {
        "normal": ("font-weight: normal;font-family: inherit;font-size: 10.5pt;text-align: justify;font-style: normal;", ""),
        "h1": ("font-weight: bold;font-family: inherit;font-size: 22pt;text-align: justify;font-style: normal;line-height: 1;", ""),
        "h2": ("font-weight: bold;font-family: 'Hei';font-size: 16pt;text-align: justify;font-style: normal;line-height: 1;", ""),
        "h3": ("font-weight: bold;font-family: inherit;font-size: 16pt;text-align: justify;font-style: normal;line-height: 1;", "")}},
    "通用模板2": {"styleName": '["h1","normal","toc 1","hyperlink"]', "style": {
        "normal": ("font-size: 10.5pt;color: #161616;text-align: justify;", ""),
        "toc 1": ("font-size: 10.5pt;color: #161616;text-align: justify;", ""),
        "hyperlink": ("text-decoration: underline;color: #0563C1;", ""),
        "h1": ("font-weight: bold;font-family: 微软雅黑;font-size: 15pt;color: #161616;text-align: left;line-height: 1;", "")}},
    "科技蓝": {"styleName": '["h1","h2","h3","h4","normal"]', "style": {
        "h1": ("width: fit-content;padding: 0 40px 0 60px;color: #131B26;font-size: 30px;text-align: center;margin: 20px auto;"
               "font-family: 'FZLanTingHeiS-B-GB';display: flex;align-items: center;justify-content: center;position: relative;", "ai-format-h1"),
        "h2": ("font-size: 24px;color: #131B26;padding: 0 0 0 22px;font-family: 'FZLanTingHeiS-B-GB';text-align: left;position: relative;margin: 10px 0;", "ai-format-h2"),
        "h3": ("font-size: 24px;color: #131B26;padding: 0 0 0 22px;font-family: 'FZLanTingHeiS-B-GB';text-align: left;position: relative;margin: 10px 0;", "ai-format-h3"),
        "h4": ("font-size: 24px;color: #131B26;padding: 0 0 0 22px;font-family: 'FZLanTingHeiS-B-GB';text-align: left;position: relative;margin: 10px 0;", "ai-format-h3"),
        "normal": ("", "ai-format-normal")}},
}
_TAG = re.compile(r"^(h[0-6]|p|normal|toc 1|hyperlink)$")


def ai_format_html(items: list, template: str) -> str:
    """The AiFormat page's rendering: <tag style class>content</tag> per item ("normal"/"toc 1"/"hyperlink" -> p, h0 -> h1).
    The content is the AI's text, so it is escaped here."""
    t = AI_TEMPLATES[template]["style"]
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("styleName") or "normal")
        tag = "h1" if name == "h0" else ("p" if name in ("normal", "toc 1", "hyperlink") or not re.fullmatch(r"h[1-6]", name) else name)
        css, cls = t.get(name, ("", ""))
        attrs = (f' style="{_h.escape(css, quote=True)}"' if css else "") + (f' class="{cls}"' if cls else "")
        out.append(f"<{tag}{attrs}>{_h.escape(str(it.get('content') or ''))}</{tag}>")
    return "".join(out)


def html_text(s: str) -> str:
    return re.sub(r"\s+", "", _h.unescape(re.sub(r"<[^>]+>", "", s or "")))


def split_for_format(desc: str) -> tuple[str, list[tuple[str, str]]]:
    """Card body -> (plain text with "[图片n]"/"[表格n]"/"[链接n]" placeholders, [(placeholder, original html)]), as the page
    does before sending text to the AI.  Paragraph and heading ends become new lines."""
    keep: list[tuple[str, str]] = []

    def hold(kind: str):
        def f(m):
            keep.append((f"[{kind}{sum(1 for k, _ in keep if k.startswith('[' + kind)) + 1}]", m.group(0)))
            return keep[-1][0] + ("" if kind == "链接" else "\n")     # tables and images stand on their own line
        return f
    s = re.sub(r"<table\b.*?</table>", hold("表格"), desc or "", flags=re.S | re.I)
    s = re.sub(r"<img\b[^>]*>", hold("图片"), s, flags=re.I)
    s = re.sub(r"<a\b.*?</a>", hold("链接"), s, flags=re.S | re.I)
    s = re.sub(r"</(p|h[1-6]|div|li)>|<br\s*/?>", "\n", s, flags=re.I)
    text = _h.unescape(re.sub(r"<[^>]+>", "", s))
    text = "\n".join(x.strip() for x in text.split("\n") if x.strip())
    return text, keep


def put_back(html: str, keep: list[tuple[str, str]]) -> str:
    for name, orig in keep:
        piece = orig if name.startswith("[链接") else f"<p>{orig}</p>"
        html = html.replace(_h.escape(name), piece, 1) if _h.escape(name) in html else html + piece
    return html


def vote_form(course_id: str, title: str, questions: list[dict], minutes: float | None, show_result: bool, anonymous: bool) -> list:
    """The #formId of mobilelearn page/questionnaire/addOrUpdateQues4Chapter (投票问卷 in a chapter)."""
    from .ops_active import QN_TYPE
    from .questions import letters
    t = (title or "").strip()
    if not t or len(t) > 100:
        raise XxtError("投票问卷标题 1–100 字。")
    if not isinstance(questions, list) or not 1 <= len(questions) <= 50:
        raise XxtError("投票问卷需要 1–50 道题。")
    tl = -1 if not minutes else int(float(minutes) * 60000)
    if minutes and not 0 < float(minutes) <= 60 * 24 * 30:
        raise XxtError("活动时长 0–30 天；留空 = 手动结束。")
    f: list[tuple[str, object]] = [("content", t), ("activeId", ""), ("courseId", course_id), ("testPaperId", ""),
                                   ("questioncount", len(questions)), ("timelong", tl), ("planId", "")]
    for i, q in enumerate(questions, 1):
        where = f"第 {i} 题："
        if not isinstance(q, dict):
            raise XxtError(f"{where}格式应为对象。")
        qt = QN_TYPE.get(str(q.get("type") or "").strip().removesuffix("题"))
        if qt is None:
            raise XxtError(f"{where}题型只能是：{'、'.join(QN_TYPE)}。")
        stem = str(q.get("stem") or "").strip()
        if not stem or len(stem) > 2000:
            raise XxtError(f"{where}题干 1–2000 字。")
        f += [(f"question_type_{i}", qt), ("questionId", 0), (f"question_content_{i}", stem)]
        if qt in (0, 1):
            opts = q.get("options") or []
            if not isinstance(opts, list) or not 2 <= len(opts) <= 26 or any(not str(o or "").strip() for o in opts):
                raise XxtError(f"{where}单选/多选需要 2–26 个非空选项。")
            for j, (L, o) in enumerate(zip(letters(len(opts)), opts)):
                f += [(f"question_options_{i}", L), (f"question_option_{i}_{j}", str(o).strip())]
        elif qt == 16:
            f += [(f"question_options_{i}", "1"), (f"question_option_{i}_0", "对"), (f"question_options_{i}", "2"), (f"question_option_{i}_1", "错")]
        f.append((f"question_ismust_{i}", 1 if q.get("required") else 0))
    f += [("isscanresult", 1 if show_result else 0), ("isanony", 1 if anonymous else 0), ("isUsed", "on")]
    return [(k, str(v)) for k, v in f]


class ChapterInsertOps(XxtBase):
    # ------------------------------------------------------------------ sources (read)
    def chapter_resources(self, course: str, kind: str, keyword: str = "", page: int = 1) -> dict:
        if kind not in SEARCH_KINDS:
            raise XxtError(f"kind 只能是：{'、'.join(SEARCH_KINDS)}。")
        page = max(1, min(int(page or 1), 50))
        if kind == "速课":
            items = self._suke_all()
            k = str(keyword or "").strip()
            items = [x for x in items if not k or k in x["title"]]
            return {"kind": kind, "total": len(items), "items": items[(page - 1) * 50:page * 50]}
        if kind == "全景":
            items = self._panoramas()
            k = str(keyword or "").strip()
            return {"kind": kind, "items": [x for x in items if not k or k in x["title"]]}
        kw = str(keyword or "").strip()
        if not kw or len(kw) > 50:
            raise XxtError("请给出 1–50 字的搜索词（书名、作者或内容）。")
        if kind == "图书":
            return {"kind": kind, **self._books(kw, page)}
        return {"kind": kind, **self._book_pages(kw, page)}

    def _suke_all(self) -> list[dict]:
        r = self.on(M1, """
            const out=[]; let last='';
            for(let i=0;i<50;i++){ const j=await J('/suke/sukeList?lastId='+last+'&pageSize=20');
              const l=j&&j.data&&j.data.list; if(!Array.isArray(l)) return out.length?out:{err:JSON.stringify(j).slice(0,120)}; out.push(...l);
              if(l.length<20) break; last=l[l.length-1].id; }
            return out.map(x=>({suke_id:String(x.id),title:x.title,url:x.url,cover:x.cover,created:x.insertTime}));""")
        if not isinstance(r, list):
            raise XxtError(f"速课列表读取失败（{(r or {}).get('err') if isinstance(r, dict) else ''}）。")
        for x in r:
            x["created"] = time.strftime("%Y-%m-%d", time.localtime(x["created"] / 1000)) if isinstance(x.get("created"), (int, float)) else None
        return r

    def _books(self, kw: str, page: int) -> dict:
        r = self.on(M1, "return await J('/ananas/book/query/'+encodeURIComponent(%s)+'/%d');" % (json.dumps(kw, ensure_ascii=False), page))
        if not isinstance(r, dict) or not isinstance(r.get("result"), list):
            raise XxtError("图书搜索失败。")
        keys = ("dxid", "bookname", "author", "publisher", "publishdate", "size", "isshidu", "readurl", "pdgurl", "coverurl")
        items = [{k: x.get(k) for k in keys} for x in r["result"] if isinstance(x, dict)]
        return {"total": (r.get("pageInfo") or {}).get("hitcount"), "page": page, "items": items}

    def _book_pages(self, kw: str, page: int) -> dict:
        r = self.on(M1, "return await J('/ananas/chapter/query/'+encodeURIComponent(%s)+'/%d');" % (json.dumps(kw, ensure_ascii=False), page))
        if not isinstance(r, dict) or not isinstance(r.get("result"), list):
            raise XxtError("图书内页搜索失败。")
        items = [{"no": i, "title": x.get("title"), "bookname": x.get("bookname"), "page": x.get("size"), "author": x.get("author"),
                  "publishdate": x.get("publishdate"), "readurl": x.get("readurl"),
                  "excerpt": html_text(str(x.get("content") or ""))[:120]} for i, x in enumerate(r["result"], 1) if isinstance(x, dict)]
        return {"total": (r.get("pageInfo") or {}).get("hitcount"), "page": page, "items": items}

    def _panoramas(self) -> list[dict]:
        # the list is same-origin only (the editor shows the picker as a mobile3 iframe), so read it from that page
        self.b.navigate(PANORAMA_HOST + "/threedresourse/panorama/toselect", settle=0.5, readiness=False)
        r = self.here("const r=await fetch('/fyportal/threedresourse/panorama/list',{credentials:'include'}); return r.ok?await r.json():null;")
        if not isinstance(r, list):
            raise XxtError("全景资源列表读取失败。")
        return [{"panorama_id": str(x.get("id")), "title": x.get("filename") or x.get("resourcename"), "type": x.get("resourcetype"),
                 "uploaded": time.strftime("%Y-%m-%d", time.localtime(int((x.get("uploadtime") or {}).get("time") or 0) / 1000))}
                for x in r if isinstance(x, dict) and str(x.get("id") or "").isdigit()]

    # ------------------------------------------------------------------ inserts
    def find_suke(self, suke: str) -> dict:
        items = self._suke_all()
        hit = [x for x in items if x["suke_id"] == str(suke)] or [x for x in items if x["title"] == str(suke)]
        if len(hit) != 1:
            raise XxtError(f"没有唯一的速课「{str(suke)[:40]}」（按速课ID或完整标题）；可先用 search_chapter_resources(kind=速课) 查。")
        return hit[0]

    def insert_chapter_suke(self, course: str, chapter_id: str, card_id: str, suke_id: str) -> dict:
        s = self.find_suke(suke_id)
        if not str(s.get("url") or "").startswith("https://"):
            raise XxtError("这个速课没有有效的链接。")
        job = _jobid()
        data = {"url": s["url"], "title": s["title"], "cover": s.get("cover") or "", "mid": _mid(), "_jobid": job, "jobid": job}
        return {**self.insert_chapter_module(course, chapter_id, card_id, "insertmicroCourse", data), "suke": s["title"], "job_id": job}

    def find_book(self, keyword: str, dxid: str) -> dict:
        for page in (1, 2, 3):
            hit = [x for x in self._books(keyword, page)["items"] if str(x.get("dxid")) == str(dxid)]
            if hit:
                return hit[0]
        raise XxtError(f"用「{keyword[:30]}」搜索的前 3 页里没有这本书（dxid {dxid}）。")

    def insert_chapter_book(self, course: str, chapter_id: str, card_id: str, keyword: str, dxid: str) -> dict:
        b = self.find_book(keyword, dxid)
        if not str(b.get("readurl") or "").startswith("http"):
            raise XxtError("这本书没有阅读链接。")
        job = _jobid()
        data = {"readurl": b["readurl"], "pdgurl": b.get("pdgurl") or "", "coverurl": b.get("coverurl") or "", "bookname": b.get("bookname") or "",
                "author": b.get("author") or "", "publisher": b.get("publisher") or "", "publishdate": b.get("publishdate") or "",
                "size": 1 if b.get("isshidu") else b.get("size"), "mid": _mid(), "_jobid": job, "jobid": job, "ywbf": "1", "start": 1}
        return {**self.insert_chapter_module(course, chapter_id, card_id, "insertbook", data), "book": b.get("bookname"), "job_id": job}

    def find_book_page(self, keyword: str, no: int, title: str) -> dict:
        items = self._book_pages(keyword, 1)["items"]
        hit = [x for x in items if x["no"] == int(no)]
        if not hit or (title and hit[0]["title"] != title):
            raise XxtError("搜索结果已变化（第 %s 条不是预演时的那一页）；没有插入，请重新预演。" % no)
        return hit[0]

    def insert_chapter_book_page(self, course: str, chapter_id: str, card_id: str, keyword: str, no: int, title: str) -> dict:
        x = self.find_book_page(keyword, no, title)
        url = str(x.get("readurl") or "")
        if not url.startswith("http"):
            raise XxtError("这一页没有阅读链接。")
        aid = f"mcp{_uuid.uuid4().hex[:16]}"
        t, u = _h.escape(str(x["title"] or ""), quote=True), _h.escape(url, quote=True)
        mark = (f'<p><a id="{aid}" class="chapterLink" type="text" linktype="0" href="{u}" _href="{u}" title="{t}" target="_blank" '
                f'address="{u}" desc="" data="" tips="no" style="text-decoration: underline; text-align: center; color: rgb(58, 139, 255);">'
                f'{_h.escape(str(x["title"] or ""))}</a></p>')
        out = self.insert_chapter_module(course, chapter_id, card_id, "chapterLink", {}, inline_html=mark, inline_marker=aid)
        return {**out, "book_page": f"《{x.get('bookname')}》第 {x.get('page')} 页：{x.get('title')}"}

    def find_panorama(self, panorama: str) -> dict:
        items = self._panoramas()
        hit = [x for x in items if x["panorama_id"] == str(panorama)] or [x for x in items if x["title"] == str(panorama)]
        if len(hit) != 1:
            raise XxtError(f"没有唯一的全景资源「{str(panorama)[:40]}」（按ID或文件名）；可先用 search_chapter_resources(kind=全景) 查。")
        return hit[0]

    def insert_chapter_panorama(self, course: str, chapter_id: str, card_id: str, panorama_id: str) -> dict:
        p = self.find_panorama(panorama_id)
        data = {"previewUrl": f"{PANORAMA_HOST}/fyportal/threedresourse/panorama/review/{_safe_id(p['panorama_id'])}", "title": p["title"], "mid": _mid()}
        return {**self.insert_chapter_module(course, chapter_id, card_id, "resourceQj", data), "panorama": p["title"]}

    def insert_chapter_vote(self, course: str, chapter_id: str, card_id: str, title: str, questions: list[dict],
                            minutes: float | None = None, show_result: bool = False, anonymous: bool = False) -> dict:
        c = self.course(course)
        form = vote_form(_safe_id(c.id), title, questions, minutes, show_result, anonymous)
        r = self.on(ML, """
            const f=new URLSearchParams(); for(const [k,v] of %s) f.append(k,v);
            return await J('/v2/apis/chapterquestion/publish?DB_STRATEGY=COURSEID&STRATEGY_PARA=courseId',
              {method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest'},body:f.toString()});
        """ % json.dumps(form, ensure_ascii=False), retry_safe=False)
        msg = (((r or {}).get("data") or {}).get("message") or [{}]) if isinstance(r, dict) else [{}]
        att = (msg[0] or {}).get("att_chat_course") if isinstance(msg, list) and msg else None
        if not isinstance(r, dict) or r.get("result") != 1 or not isinstance(att, dict) or not str(att.get("id") or "").isdigit():
            return {"ok": False, "write_outcome": "unknown" if isinstance(r, dict) and r.get("result") == 1 else "not_written",
                    "error": f"投票问卷没有建成（{str((r or {}).get('errorMsg') or '')[:60]}）；章节没有修改。"}
        data = {"id": att["id"], "title": att.get("title") or title, "description": att.get("subTitle") or "", "mid": _mid(), "_jobid": _jobid()}
        out = self.insert_chapter_module(course, chapter_id, card_id, "insertvote", data)
        return {**out, "vote_id": str(att["id"]), "title": data["title"],
                **({} if out.get("ok") else {"note": f"投票问卷 {att['id']} 已建好，但没能插进章节；请核查后再插入，不要重复新建。"})}

    # ------------------------------------------------------------------ body-level: 文档导入, AI 排版
    def _append_html(self, course: str, chapter_id: str, card_id: str, html: str, replace: bool = False) -> dict:
        c = self.course(course)
        cur = self._read_card(c, chapter_id, card_id)
        if cur is None:
            raise XxtError("指定的章节卡片不存在；没有修改。")
        desc = cur.get("description") or ""
        atts = card_attachments(desc)
        new_desc = html if replace else desc + html
        r = self._save_card(c, chapter_id, card_id, cur.get("title") or "", new_desc, atts)
        back = self._read_card(c, chapter_id, card_id)
        body = (back or {}).get("description") or ""
        want = html_text(html)
        ok = r.get("http") == 200 and back is not None and bool(want) and want[:200] in html_text(body) and \
            len(card_attachments(body)) == len(atts)
        return {"ok": ok, "card_id": card_id, "chars": len(html), "inserts_kept": len(atts),
                **({} if ok else {"write_outcome": "unknown", "error": "保存后读回不一致；请用 read_chapter_content 核查，不要重复提交。"})}

    def import_chapter_document(self, course: str, chapter_id: str, card_id: str, file_path: str, expected_sha256: str) -> dict:
        c = self.ctx(course)
        tmp, snap, meta = self._snapshot(file_path, expected_sha256)
        try:
            up = self._cloud_upload(c, snap, meta)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        r = self.here("""
            let crc=null, last='';
            for(let i=0;i<8&&!crc;i++){ const fd=new FormData(); fd.append('objectId',%s); fd.append('fileName',%s); fd.append('isParseLatexFormula','true');
              try{const j=await (await fetch('/sqp/api/upload-from-yp',{method:'POST',body:fd,credentials:'include'})).json(); last=JSON.stringify(j).slice(0,80); if(j.status&&j.crc) crc=j.crc}catch(e){}
              if(!crc) await new Promise(r=>setTimeout(r,4000)); }
            if(!crc) return {stage:'convert',last};
            const j=await (await fetch('/sqp/api/parseToHtml?file='+crc,{credentials:'include'})).json();
            return j&&j.status?{stage:'done',html:j.html}:{stage:'html'};
        """ % (json.dumps(up["objectid"]), json.dumps(meta["name"], ensure_ascii=False)), retry_safe=False)
        if not isinstance(r, dict) or r.get("stage") != "done" or not str(r.get("html") or "").strip():
            return {"ok": False, "write_outcome": "not_written", "object_id": up["objectid"],
                    "error": f"平台没能把文档转成网页内容（{(r or {}).get('stage')}）；文件已在云盘，章节没有修改。"}
        html = str(r["html"]) + "<p></p>"
        out = self._append_html(course, chapter_id, card_id, html)
        return {**out, "file": meta["name"], "object_id": up["objectid"], "imported_text": html_text(html)[:200]}

    def ai_format_preview(self, course: str, chapter_id: str, card_id: str, template: str) -> dict:
        """Ask the platform AI to lay out one card with one of the editor's templates.  Returns the new body; nothing is saved."""
        if template not in AI_TEMPLATES:
            raise XxtError(f"模板只能是：{'、'.join(AI_TEMPLATES)}。")
        c = self.ctx(course)
        cur = self._read_card(c, chapter_id, card_id)
        if cur is None:
            raise XxtError("指定的章节卡片不存在。")
        desc = cur.get("description") or ""
        if card_attachments(desc) or "taskIframeWrap" in desc:
            raise XxtError("这个卡片里有插入的资料或任务点，AI 排版会重写整页正文，为避免丢失，不处理；请把正文放在单独的卡片里再排版。")
        src, keep = split_for_format(desc)
        if len(src) > 20000:
            raise XxtError("正文超过 2 万字，请拆成几张卡片再排版。")
        if not src:
            raise XxtError("没有可排版的文字。")
        r = self.on(M1, """
            const ci=(await J('/mooc-ans/edit/get-course-info?courseId=%s&clazzId=%s')).data||{};
            const w=(ci.aiInfo||{}).aiWriting||{}; if(!w.aiFormatEnc) return {stage:'enc'};
            const body={userId:String((ci.userInfo||{}).uid||''),formatText:%s,styleList:%s,t:String(w.aiTime),enc:w.aiFormatEnc};
            const r=await fetch('/ai-ans/ai/chapter/format',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
            let j=null; try{j=await r.json()}catch(e){}
            return {stage:'done',http:r.status,j};
        """ % (_safe_id(c.id), _safe_id(c.clazz_id), json.dumps(src, ensure_ascii=False), json.dumps(AI_TEMPLATES[template]["styleName"])),
            timeout=200)
        j = (r or {}).get("j") if isinstance(r, dict) else None
        if not isinstance(j, dict) or j.get("status") is not True:
            raise XxtError(f"AI 排版没有返回结果（{(r or {}).get('stage')} {str((j or {}).get('msg') or '')[:60]}）。")
        try:
            items = json.loads(j.get("text") or "")
        except ValueError:
            raise XxtError("AI 排版的结果不是预期的格式。") from None
        html = put_back(ai_format_html(items, template), keep)
        return {"html": html, "digest": hashlib.sha256(html.encode("utf-8")).hexdigest(), "paragraphs": len(items),
                "kept": [k for k, _ in keep], "source_chars": len(src)}

    def ai_format_apply(self, course: str, chapter_id: str, card_id: str, html: str) -> dict:
        c = self.course(course)
        cur = self._read_card(c, chapter_id, card_id)
        if cur is None:
            raise XxtError("指定的章节卡片不存在；没有修改。")
        if card_attachments(cur.get("description") or "") or "taskIframeWrap" in (cur.get("description") or ""):
            return {"ok": False, "write_outcome": "not_written", "error": "卡片里现在有插入项了；没有覆盖。"}
        return self._append_html(course, chapter_id, card_id, html, replace=True)

    def insert_chapter_graph(self, course: str, chapter_id: str, card_id: str, point_ids: list[str]) -> dict:
        """课程图谱 insert: POST mooc1 /mooc-ans/knowledge-topic-relation/save-knowledge-graph {courseid, mid, topicIds:"a,b,",
        knowledgeid=<chapter>} -> data = knowledgeGraphId; module knowledgeGraph {mid, knowledgeGraphId}."""
        c = self.course(course)
        mid = _mid()
        r = self.on(M1, """
            const fd=new FormData(); fd.append('courseid',%s); fd.append('mid',%s); fd.append('topicIds',%s); fd.append('knowledgeid',%s);
            return await J('/mooc-ans/knowledge-topic-relation/save-knowledge-graph',{method:'POST',body:fd});
        """ % (json.dumps(str(c.id)), json.dumps(mid), json.dumps("".join(f"{_safe_id(x)}," for x in point_ids)), json.dumps(str(chapter_id))),
            retry_safe=False)
        gid = str((r or {}).get("data") or "") if isinstance(r, dict) else ""
        if not isinstance(r, dict) or r.get("status") is not True or not gid:
            return {"ok": False, "write_outcome": "not_written", "error": f"图谱没有建成（{str((r or {}).get('msg') or '')[:60]}）；章节没有修改。"}
        out = self.insert_chapter_module(course, chapter_id, card_id, "knowledgeGraph", {"mid": mid, "knowledgeGraphId": gid})
        return {**out, "graph_id": gid, "points": len(point_ids)}
