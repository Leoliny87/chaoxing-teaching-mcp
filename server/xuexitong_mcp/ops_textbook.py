"""个人首页「数字教材」(digital textbook / teach material) CRUD.

Endpoints captured live from the cv-p.chaoxing.com SPA on 2026-11-13 (network
capture of the real UI requests, not guessed):

  enc exchange : GET  /personalSpace/checkWfwfid?enc=<portal enc>  -> {enc:<space enc>}
  list         : GET  /personalSpace/teachMaterialList?enc=<space enc>
  cover upload : POST /personalSpace/uploadFile   (multipart 'file') -> {objectid}
  create       : POST /personalSpace/addTeachMaterial  (form-urlencoded, enc in body)
  delete       : GET  /personalSpace/deleteTeachMaterial?courseId=&id=&enc=<delEnc>
  detail       : GET  /personalSpace/getCourseDetail?enc=<detailEnc>&code=<id>&courseId=

The portal enc is read from the personal-home left-menu 「数字教材」 link
(i.mooc.chaoxing.com). The cover URL is the platform's own canonical CDN address
built from the uploaded objectid: https://p.ananas.chaoxing.com/star3/origin/<objectid>.
All API calls run same-origin on cv-p.chaoxing.com via a stable static base page.
"""
from __future__ import annotations

import base64
import json
import os
import re

from .xxt import BASE_PAGE, M1, M2, XxtBase, XxtError

CV = "cv-p.chaoxing.com"
# A version-stable static file on the cv-p origin (no UI to re-render), so
# same-origin fetch evaluates stay reliable (same trick as the other hosts).
BASE_PAGE.setdefault(CV, "https://cv-p.chaoxing.com/tm/static/jquery-3.3.1.min.js")

PORTAL = "https://i.mooc.chaoxing.com/space/index"
COVER_CDN = "https://p.ananas.chaoxing.com/star3/origin/"


class TextbookOps(XxtBase):
    # ------------------------------------------------------------ enc plumbing
    def _tb_portal_enc(self) -> str:
        """Read the digital-textbook menu link enc from the personal home."""
        self.b.navigate(PORTAL, settle=1.0, readiness=False)
        js = (
            "const as=[...document.querySelectorAll('a')];"
            "for(const a of as){if((a.textContent||'').trim()==='数字教材'){"
            "const h=a.getAttribute('href')||'';const m=h.match(/enc=([a-f0-9]+)/);"
            "if(m)return m[1];}}"
            "return null;"
        )
        enc = self.b.eval(js, retry_safe=True)
        if not enc:
            raise XxtError("门户未找到「数字教材」菜单链接或其 enc；请确认已登录个人首页。")
        return enc

    def _tb_enc(self) -> str:
        """Exchange the portal enc for the personalSpace enc (checkWfwfid)."""
        portal = self._tb_portal_enc()
        r = self.on(CV, "return await J('/personalSpace/checkWfwfid?enc=' + encodeURIComponent(%s));" % json.dumps(portal))
        if not isinstance(r, dict) or not r.get("enc"):
            raise XxtError("checkWfwfid 未返回 personalSpace enc：%s" % json.dumps(r, ensure_ascii=False)[:120])
        return r["enc"]

    # ------------------------------------------------------------ read
    def textbook_list(self) -> list:
        enc = self._tb_enc()
        r = self.on(CV, "return await J('/personalSpace/teachMaterialList?enc=' + encodeURIComponent(%s));" % json.dumps(enc))
        if not isinstance(r, dict) or r.get("code") != 200:
            raise XxtError("教材列表读取失败：%s" % json.dumps(r, ensure_ascii=False)[:160])
        out = []
        for m in r.get("data") or []:
            out.append({
                "id": m.get("id"), "courseId": m.get("courseId"),
                "name": m.get("courseName"), "author": m.get("courseAuthor"),
                "unit": m.get("courseUnitName"), "cover": m.get("coursePic"),
                "fid": m.get("fid"), "type": m.get("type"),
            })
        return out

    def textbook_detail(self, id: str) -> dict:
        """Best-effort detail read. Locates the item's detailEnc from the list."""
        enc = self._tb_enc()
        lst = self.on(CV, "return await J('/personalSpace/teachMaterialList?enc=' + encodeURIComponent(%s));" % json.dumps(enc))
        item = next((m for m in (lst.get("data") or []) if str(m.get("id")) == str(id)), None)
        if not item:
            raise XxtError("未找到 id=%s 的教材。" % id)
        de = item.get("detailEnc")
        r = self.on(CV, "return await J('/personalSpace/getCourseDetail?enc=' + encodeURIComponent(%s) + '&code=' + %s + '&courseId=' + %s);"
                    % (json.dumps(de), json.dumps(str(id)), json.dumps(str(item.get("courseId")))))
        out = {"item": {k: item.get(k) for k in ("id", "courseId", "courseName", "courseAuthor", "coursePic", "courseUnitName")},
               "detail": r}
        if not (isinstance(r, dict) and r.get("status") is not False):
            out["limitation"] = ("列表级信息已返回；getCourseDetail 未返回完整详情（status:false）。"
                                 "完整章节/内容详情需平台 textbookDetail 页的独立加载流程，尚未接入。")
        return out

    # ------------------------------------------------------------ write
    def _tb_upload_cover(self, cover_path: str) -> str:
        p = os.path.expanduser(cover_path)
        if not os.path.isfile(p):
            raise XxtError("封面文件不存在：%s" % cover_path)
        data = open(p, "rb").read()
        if len(data) > 1024 * 1024:
            raise XxtError("封面超过 1M 限制。")
        b64 = base64.b64encode(data).decode()
        ext = os.path.splitext(p)[1].lower().lstrip(".") or "png"
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif"}.get(ext)
        if not mime:
            raise XxtError("封面仅支持 PNG/JPG/GIF。")
        js = (
            "const b=atob(%s);const a=new Uint8Array(b.length);"
            "for(let i=0;i<b.length;i++)a[i]=b.charCodeAt(i);"
            "const fd=new FormData();fd.append('file',new Blob([a],{type:%s}),'cover.%s');"
            "const r=await fetch('/personalSpace/uploadFile',{method:'POST',credentials:'include',body:fd});"
            "return await r.json();" % (json.dumps(b64), json.dumps(mime), ext)
        )
        r = self.on(CV, js)
        if not isinstance(r, dict) or not r.get("objectid"):
            raise XxtError("封面上传失败：%s" % json.dumps(r, ensure_ascii=False)[:160])
        return COVER_CDN + r["objectid"]

    def textbook_create(self, name: str, author: str, cover_path: str, desc: str = "",
                        deputy: str = "", participate: str = "", unit: str = "") -> dict:
        if not name or not author:
            raise XxtError("教材名称与主编必填。")
        enc = self._tb_enc()
        pic = self._tb_upload_cover(cover_path)
        form = {
            "deptName": "", "courseName": name, "courseAuthor": author,
            "deputyChiefEditor": deputy, "participateEditor": participate,
            "courseUnitName": unit, "coursePic": pic, "courseDesc": desc,
            "courseFid": "", "deptId": "", "enc": enc,
        }
        r = self.on(CV, "return await J('/personalSpace/addTeachMaterial', POST(%s));" % json.dumps(form, ensure_ascii=False))
        if not isinstance(r, dict) or r.get("code") != 200:
            raise XxtError("教材创建失败：%s" % json.dumps(r, ensure_ascii=False)[:200])
        return {"ok": True, "name": name, "cover": pic, "response": r}

    def textbook_delete(self, id: str) -> dict:
        enc = self._tb_enc()
        lst = self.on(CV, "return await J('/personalSpace/teachMaterialList?enc=' + encodeURIComponent(%s));" % json.dumps(enc))
        item = next((m for m in (lst.get("data") or []) if str(m.get("id")) == str(id)), None)
        if not item:
            raise XxtError("未找到 id=%s 的教材。" % id)
        r = self.on(CV, "return await J('/personalSpace/deleteTeachMaterial?courseId=' + %s + '&id=' + %s + '&enc=' + encodeURIComponent(%s));"
                    % (json.dumps(str(item.get("courseId"))), json.dumps(str(id)), json.dumps(item.get("delEnc"))))
        if not isinstance(r, dict) or r.get("code") != 200:
            raise XxtError("教材删除失败：%s" % json.dumps(r, ensure_ascii=False)[:200])
        return {"ok": True, "id": id, "name": item.get("courseName"), "response": r}

    # ---------------------------------------------- knowledge graph (same backend as course graph)
    # The textbook 知识图谱 tab opens mooc2-ans.chaoxing.com/topic-ans/knowgraph with the textbook's
    # courseId; its data/edit APIs are the very same /mooc2-ans/coursetopic/ and /mooc2-ans/questionBankTopic/
    # endpoints the course-graph tools use (verified live 2026-11-13). clazzid=0 reads the course-level
    # graph structure (class only affects per-class stats). cpi is the user's curPersonId.
    _TB_KINDS = {"未设置": 0, "事实性": 1, "概念性": 2, "程序性": 3, "元认知": 4}

    def _tb_cpi(self) -> str:
        if self.cfg.cpi:
            return str(self.cfg.cpi)
        cs = self.courses()
        if cs and getattr(cs[0], "cpi", ""):
            return str(cs[0].cpi)
        raise XxtError("无法解析 cpi；请在配置中设置 cpi 后重试。")

    def _tb_graph_ctx(self, id: str) -> dict:
        enc = self._tb_enc()
        lst = self.on(CV, "return await J('/personalSpace/teachMaterialList?enc=' + encodeURIComponent(%s));" % json.dumps(enc))
        item = next((m for m in (lst.get("data") or []) if str(m.get("id")) == str(id)), None)
        if not item:
            raise XxtError("未找到 id=%s 的教材。" % id)
        return {"courseid": str(item.get("courseId")), "clazzid": "0", "cpi": self._tb_cpi(), "ut": "t",
                "_name": item.get("courseName")}

    def _gget(self, url: str, params: dict):
        return self.on(M2, "const r=await fetch(%s+'?'+new URLSearchParams(%s),{credentials:'include'}); let j=null; try{j=await r.json()}catch(e){} return j;"
                       % (json.dumps(url), json.dumps(params, ensure_ascii=False)))

    def _gpost(self, url: str, params: dict):
        return self.on(M2, """const r=await fetch(%s,{method:'POST',credentials:'include',headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'},
            body:new URLSearchParams(%s)}); let j=null; try{j=await r.json()}catch(e){} return j;""" % (json.dumps(url), json.dumps(params, ensure_ascii=False)),
                       retry_safe=False)

    def textbook_graph(self, id: str, page: int = 1, size: int = 50) -> dict:
        ctx = self._tb_graph_ctx(id)
        p = {k: ctx[k] for k in ("courseid", "clazzid", "cpi", "ut")}
        j = self._gget("/mooc2-ans/coursetopic/gettopicwoodsdata",
                       {**p, "page": int(page), "limit": int(size), "orderType": 0, "orderText": "", "query": "", "lableIds": ""})
        d = (j or {}).get("data") if isinstance(j, dict) else None
        if not isinstance(d, dict) or not isinstance(d.get("topicWoodsData"), list):
            raise XxtError("教材知识图谱读取失败：%s" % json.dumps(j, ensure_ascii=False)[:150])
        items = [{"point_id": str(x.get("topicId")), "name": x.get("name"),
                  "labels": [l.get("name") for l in x.get("topicLabelArray") or []],
                  "cite_count": x.get("citeCount"), "description": x.get("topicDesc")} for x in d["topicWoodsData"]]
        st = self._gget("/mooc2-ans/coursetopic/gettopicsetting", {**p, "topicModelId": 0})
        tabs = [t.get("name") for t in ((st or {}).get("data") or {}).get("topicModelData") or []] if isinstance(st, dict) else []
        return {"textbook": ctx["_name"], "courseId": ctx["courseid"], "total": d.get("totalCount"),
                "page": int(page), "items": items, "graph_tabs": tabs}

    def textbook_graph_add_point(self, id: str, name: str, kind: str = "未设置", description: str = "") -> dict:
        ctx = self._tb_graph_ctx(id)
        if kind not in self._TB_KINDS:
            raise XxtError("kind 必须是 %s 之一。" % "/".join(self._TB_KINDS))
        r = self._gget("/mooc2-ans/coursetopic/woodsaddtopic",
                       {"courseid": ctx["courseid"], "cpi": ctx["cpi"], "topic": name,
                        "classify": self._TB_KINDS[kind], "topicLabelIds": "", "topicDesc": description})
        pid = str(((r or {}).get("data") or {}).get("topicId") or "") if isinstance(r, dict) else ""
        if not (isinstance(r, dict) and r.get("status") is True and pid.isdigit()):
            return {"ok": False, "write_outcome": "not_written", "error": "平台没有添加（%s）。" % str((r or {}).get("msg") or "")[:60]}
        return {"ok": True, "point_id": pid, "name": name, "note": "加在教材图谱最外层；知识列表索引可能晚几秒更新。"}

    def textbook_graph_point(self, id: str, point_id: str) -> dict:
        ctx = self._tb_graph_ctx(id)
        j = self._gget("/mooc2-ans/questionBankTopic/edittopicproperty",
                       {"courseid": ctx["courseid"], "cpi": ctx["cpi"], "topicModelId": 0, "topicId": str(point_id)})
        if not isinstance(j, dict) or j.get("status") is not True:
            raise XxtError("知识点属性读取失败。")
        kinds = {v: k for k, v in self._TB_KINDS.items()}
        return {"point_id": str(point_id), "name": j.get("topicName"), "kind": kinds.get(int(j.get("classify") or 0)),
                "description": j.get("topicDesc"), "labels": [x.get("name") for x in j.get("topiclabelList") or []],
                "teaching_target": j.get("teachTarget") or "", "study_hours": j.get("studyHours") or ""}

    def textbook_graph_set_point(self, id: str, point_id: str, kind: str | None = None, description: str | None = None,
                                 teaching_target: str | None = None, study_hours: str | None = None) -> dict:
        ctx = self._tb_graph_ctx(id)
        cur = self.textbook_graph_point(id, point_id)
        want_kind = cur["kind"] if kind is None else kind
        if want_kind not in self._TB_KINDS:
            raise XxtError("kind 必须是 %s 之一。" % "/".join(self._TB_KINDS))
        r = self._gpost("/mooc2-ans/questionBankTopic/savepropertyedit",
                        {"courseid": ctx["courseid"], "cpi": ctx["cpi"], "topicIds": str(point_id),
                         "classify": self._TB_KINDS[want_kind], "cognize": -1, "topicLabelIds": "",
                         "topicDesc": cur["description"] if description is None else description,
                         "teachTargert": cur["teaching_target"] if teaching_target is None else teaching_target,
                         "studyHours": cur["study_hours"] if study_hours is None else str(study_hours)})
        back = self.textbook_graph_point(id, point_id)
        ok = isinstance(r, dict) and r.get("status") is True and back["kind"] == want_kind
        return {"ok": ok, "properties": back,
                **({} if ok else {"write_outcome": "unknown", "error": "保存后核对不一致；请用 textbook_graph_point 查看，不要重复提交。"})}

    def textbook_graph_delete_point(self, id: str, point_id: str) -> dict:
        ctx = self._tb_graph_ctx(id)
        r = self._gpost("/mooc2-ans/questionBankTopic/deleteTopic",
                        {"courseid": ctx["courseid"], "cpi": ctx["cpi"], "topicId": str(point_id), "asyn": 1})
        if not (isinstance(r, dict) and r.get("status") is True):
            return {"ok": False, "write_outcome": "not_written", "error": "平台没有删除（%s）。" % str((r or {}).get("msg") or "")[:60]}
        return {"ok": True, "point_id": str(point_id), "note": "已删除（含子节点）；可在平台图谱回收站恢复。"}

    # ---------------------------------------------- chapters / 目录 (same backend as course chapters)
    # The textbook 目录 tab embeds mooc2-ans/mycourse/tchcourse; its chapter tree read/write uses the very
    # same /mooc-ans/edit/ endpoints (M1) as the course-chapter tools (verified live 2026-11-13:
    # get-knowledge-list with the textbook courseId returns the real chapter tree).
    def textbook_chapters(self, id: str) -> dict:
        ctx = self._tb_graph_ctx(id)
        j = self.on(M1, "return await J('/mooc-ans/edit/get-knowledge-list?courseId=%s&cpi=%s');" % (ctx["courseid"], ctx["cpi"]))
        if not isinstance(j, dict) or not isinstance(j.get("data"), list) or j.get("success") is False or j.get("result") is False:
            raise XxtError("教材章节列表返回无效或服务端报错；不能视为空列表，请稍后核查。")
        out: list[dict] = []
        seen: set[str] = set()

        def walk(nodes, prefix, parent):
            if nodes is None:
                return
            if not isinstance(nodes, list):
                raise XxtError("章节树子节点格式异常；未返回不完整列表。")
            for i, n in enumerate(nodes, 1):
                if (not isinstance(n, dict) or n.get("id") is None or isinstance(n.get("id"), bool)
                        or not str(n.get("id")).strip() or not isinstance(n.get("title"), str) or not n["title"].strip()):
                    raise XxtError("章节树节点缺少有效 ID 或标题；未返回不完整列表。")
                cid = str(n["id"])
                if cid in seen:
                    raise XxtError("章节树中存在重复 ID；未返回不完整列表。")
                seen.add(cid)
                num = f"{prefix}{i}"
                out.append({"chapter_id": cid, "number": num, "title": n.get("title"), "layer": n.get("layer"), "parent_id": parent})
                walk(n.get("children"), num + ".", cid)

        walk(j["data"], "", "0")
        return {"textbook": ctx["_name"], "courseId": ctx["courseid"], "count": len(out), "chapters": out}

    def _tb_find_chapter(self, id: str, chapter: str) -> dict:
        chs = self.textbook_chapters(id)["chapters"]
        ch = next((x for x in chs if x["chapter_id"] == str(chapter) or x["number"] == str(chapter)), None)
        if not ch:
            raise XxtError("未找到章节 %s；请用 textbook_chapters 核对。" % chapter)
        return ch

    def textbook_create_chapter(self, id: str, title: str, parent: str = "") -> dict:
        ctx = self._tb_graph_ctx(id)
        if not title or not title.strip():
            raise XxtError("章节标题不能为空。")
        if parent:
            p = self._tb_find_chapter(id, parent)
            pid, layer = p["chapter_id"], int(p["layer"]) + 1
        else:
            pid, layer = "0", 1
        if layer > 7:
            raise XxtError("章节不能超过7层。")
        r = self.on(M1, "const f=new FormData(); f.append('courseid','%s'); f.append('name',%s); f.append('parentid','%s'); f.append('layer','%s'); f.append('mooc2','1'); return await J('/mooc-ans/edit/createchapter',{method:'POST',body:f});"
                    % (ctx["courseid"], json.dumps(title), pid, layer), retry_safe=False)
        nid = str((r or {}).get("id", ""))
        hit = [x for x in self.textbook_chapters(id)["chapters"] if x["chapter_id"] == nid]
        return {"ok": bool(hit), "chapter": hit[0] if hit else None, "server": r,
                **({} if hit else {"write_outcome": "unknown", "error": "创建后未在章节树看到；请用 textbook_chapters 核查，不要重复创建。"})}

    def textbook_rename_chapter(self, id: str, chapter_id: str, new_name: str) -> dict:
        ctx = self._tb_graph_ctx(id)
        if not new_name or len(new_name) > 100:
            raise XxtError("章节名称需为 1–100 字。")
        self._tb_find_chapter(id, chapter_id)
        r = self.on(M1, "const r=await fetch('/mooc-ans/edit/changename',{method:'POST',credentials:'include',headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'},body:new URLSearchParams(%s)}); let j=null; try{j=await r.json()}catch(e){} return j;"
                    % json.dumps({"courseid": ctx["courseid"], "nodeid": str(chapter_id), "name": new_name, "cpi": ctx["cpi"]}, ensure_ascii=False), retry_safe=False)
        after = [x for x in self.textbook_chapters(id)["chapters"] if x["chapter_id"] == str(chapter_id)]
        ok = isinstance(r, dict) and len(after) == 1 and after[0]["title"] == new_name
        return {"ok": ok, "chapter": after[0] if after else None,
                **({} if ok else {"write_outcome": "unknown", "error": "改名后核对不一致；请用 textbook_chapters 查看，不要重复提交。"})}

    def textbook_delete_chapter(self, id: str, chapter_id: str) -> dict:
        ctx = self._tb_graph_ctx(id)
        chs = self.textbook_chapters(id)["chapters"]
        ch = next((x for x in chs if x["chapter_id"] == str(chapter_id) or x["number"] == str(chapter_id)), None)
        if not ch:
            raise XxtError("未找到章节 %s；请用 textbook_chapters 核对。" % chapter_id)
        kids = [x for x in chs if x["number"].startswith(ch["number"] + ".")]
        r = self.on(M1, "const f=new FormData(); f.append('courseid','%s'); f.append('nodeid','%s'); return await J('/mooc-ans/edit/deletechapter',{method:'POST',body:f});"
                    % (ctx["courseid"], ch["chapter_id"]), retry_safe=False)
        ok = not [x for x in self.textbook_chapters(id)["chapters"] if x["chapter_id"] == ch["chapter_id"]]
        return {"ok": ok, "deleted": f"{ch['number']} {ch['title']}", "also_deleted_children": len(kids), "server": r,
                **({} if ok else {"write_outcome": "unknown", "error": "删除后核对不一致；请用 textbook_chapters 核查。"})}
