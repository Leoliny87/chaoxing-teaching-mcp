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

from .xxt import BASE_PAGE, XxtBase, XxtError

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
