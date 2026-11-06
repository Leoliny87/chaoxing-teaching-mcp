"""File uploads: course materials and chapter files (chains verified on the test course, 2026-11-07).

Both chains stage the file in the page through a visible <input type=file> that
this module injects (bsk upload), then post it with the page's own fetch:

Materials:  POST {uploadDomain}/upload/uploadNew?t&enc2&userId  (multipart file, source=1;
            t/enc2/userId are in the course-data page script)
            -> POST /mooc2-ans/coursedata/adddata jsonData=[{courseId, rootId, dataName, source:'1',
               dataSize, dataType, objectId, courseName, isOpen:'0', dataRealType}]
Chapter:    from a mooc1 page: GET /mooc-ans/edit/get-course-info (uploadParam, userInfo, courseInfo), GET /ananas/getTk (data.tk, may be '')
            -> POST /ananas/generate-sign {params: JSON(m), enc, t}  (uploadParam)
            -> POST pan-yz.chaoxing.com/upload/v2/uploadfile  multipart m + file + sign fields
            -> documents: GET /ananas/status/<objectid> for pagenum; then the module is
               appended to the card like any other insert.

What is uploaded is a private snapshot copy whose SHA-256 must equal the one bound
at preview time, and the page re-hashes the staged bytes before posting.
"""
from __future__ import annotations

import hashlib
import os
import random
import shutil
import tempfile
import time
from pathlib import Path

from .ops_write import _jobid, _mid, _ms
from .xxt import M1, XxtBase, XxtError, _safe_id

KINDS = {  # kind -> (module, allowed suffixes; None = any)
    "文档": ("insertdoc", {"doc", "docx", "ppt", "pptx", "pdf", "xls", "xlsx"}),
    "音频": ("insertaudio", {"aac", "ac3", "aif", "aiff", "amr", "ape", "asf", "flac", "m4a", "mp3", "ogg", "wav", "wma"}),
    "视频": ("insertvideo", {"rmvb", "3gp", "mpg", "mpeg", "mov", "wmv", "avi", "mkv", "mp4", "flv", "vob", "f4v"}),
    "图片": ("insertimage", {"gif", "jpeg", "jpg", "png", "svg", "bmp", "tif", "tiff"}),
    "附件": ("downloadfile", None),
}
MAX_BYTES = 1024 ** 3
_BAD_NAME = set('`~!@#$%^&*+<>?:"{},\\;[]/|')


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def hsize(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit, k in (("KB", 1), ("MB", 2), ("GB", 3)):
        if n < 1024 ** (k + 1) or unit == "GB":
            return f"{n / 1024 ** k:.2f} {unit}"
    return f"{n} B"


def safe_name(name: str) -> str:
    return "".join("-" if ch in _BAD_NAME else ch for ch in name).strip() or "file"


_INJECT = ("let i=document.getElementById('mcp-file');if(!i){i=document.createElement('input');i.type='file';i.id='mcp-file';"
           "document.body.appendChild(i)}i.style.cssText='position:fixed;left:8px;top:8px;z-index:2147483647;width:240px;"
           "height:40px;opacity:1;display:block;background:#fff';i.value='';return true;")
_STAGED = ("const i=document.getElementById('mcp-file');const f=i&&i.files&&i.files[0];if(!f)return null;"
           "const d=await crypto.subtle.digest('SHA-256',await f.arrayBuffer());"
           "return {name:f.name,size:f.size,sha256:[...new Uint8Array(d)].map(b=>b.toString(16).padStart(2,'0')).join('')};")


class UploadOps(XxtBase):
    def _snapshot(self, file_path: str, expected_sha256: str) -> tuple[Path, Path, dict]:
        src = Path(file_path)
        st = src.stat()
        if not src.is_file() or st.st_size <= 0 or st.st_size > MAX_BYTES:
            raise XxtError("文件不存在、为空或超过 1GB；没有上传。")
        tmp = Path(tempfile.mkdtemp(prefix="xxt-up-"))
        os.chmod(tmp, 0o700)
        snap = tmp / safe_name(src.name)
        shutil.copyfile(src, snap)
        digest = sha256_file(snap)
        if not expected_sha256 or digest != expected_sha256:
            shutil.rmtree(tmp, ignore_errors=True)
            raise XxtError("文件内容与预演时不一致（哈希不同）；请重新预演后再确认。没有上传。")
        return tmp, snap, {"name": snap.name, "size": snap.stat().st_size, "sha256": digest}

    def _stage(self, snap: Path, meta: dict) -> None:
        self.here(_INJECT)
        self.b.upload_selector("#mcp-file", str(snap))
        got = self.here(_STAGED)
        if not isinstance(got, dict) or got.get("sha256") != meta["sha256"] or int(got.get("size") or -1) != meta["size"]:
            raise XxtError("页面里暂存的文件与本机快照不一致；没有上传。")

    # ================================================================ course materials
    def upload_material_v3(self, course: str, file_path: str, expected_sha256: str) -> dict:
        c = self.ctx(course)
        tmp, snap, meta = self._snapshot(file_path, expected_sha256)
        try:
            before = {m["material_id"] for m in self.materials(c.id)}
            self.b.navigate(f"https://mooc2-ans.chaoxing.com/mooc2-ans/coursedata?{self.q(c)}&v=6", settle=1.0, readiness=False)
            self._stage(snap, meta)
            r = self.here(r"""
                const g=k=>(document.querySelector('#'+k)||{}).value;
                const inl=[...document.scripts].filter(s=>!s.src).map(s=>s.textContent).join('\n');
                const m=inl.match(/upload\/uploadNew\?t=(\d+)&enc2=([0-9a-f]+)&userId=(\d+)/);
                if(!m||!window.ServerHost||!g('courseid')) return {stage:'page'};
                const f=document.getElementById('mcp-file').files[0];
                const fd=new FormData(); fd.append('source','1'); fd.append('file',f,f.name);
                const u=await fetch(ServerHost.uploadDomain+'/upload/uploadNew?t='+m[1]+'&enc2='+m[2]+'&userId='+m[3],{method:'POST',body:fd,credentials:'include'});
                let d=null; try{d=await u.json()}catch(e){}
                if(!d||d.state!=='SUCCESS'||!/^[0-9a-f]{32}$/.test(d.url||'')) return {stage:'upload',http:u.status};
                const arr=[{courseId:g('courseid'),rootId:g('dataId')||'0',dataName:f.name,source:'1',dataSize:d.fileSize,dataType:d.fileType,
                  objectId:d.url,courseName:g('courseName'),isOpen:'0',dataRealType:d.fileRealType}];
                const a=await fetch('/mooc2-ans/coursedata/adddata',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'},
                  body:new URLSearchParams({jsonData:JSON.stringify(arr),courseid:g('courseid'),cpi:g('cpi'),microTopicId:g('microTopicId')||'0'})});
                let j=null; try{j=await a.json()}catch(e){}
                return {stage:'done',status:!!(j&&j.status),object_id:d.url};
            """, retry_safe=False)
            if not isinstance(r, dict) or r.get("stage") != "done":
                raise XxtError(f"上传在「{(r or {}).get('stage', '未知')}」阶段失败；资料库没有新增。")
            new = []
            for _ in range(5):
                new = [m for m in self.materials(c.id) if m["material_id"] not in before and m.get("title") == meta["name"]]
                if new:
                    break
                time.sleep(2)
            ok = bool(r.get("status")) and len(new) == 1
            return {"ok": ok, "material": new[0] if new else None, "file": meta["name"], "size": meta["size"],
                    **({} if ok else {"write_outcome": "unknown", "error": "文件已上传但资料列表核对不一致；请用 list_materials 查看，不要重复上传。"})}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ================================================================ chapter files
    def insert_chapter_file(self, course: str, chapter_id: str, card_id: str, file_path: str, kind: str,
                            expected_sha256: str) -> dict:
        if kind not in KINDS:
            raise XxtError(f"插入类型只能是：{'、'.join(KINDS)}。")
        module, allowed = KINDS[kind]
        suffix = Path(file_path).suffix.lower().lstrip(".")
        if allowed is not None and suffix not in allowed:
            raise XxtError(f"「{kind}」只支持：{'、'.join(sorted(allowed))}。")
        c = self.ctx(course)
        nid = _safe_id(chapter_id)
        tmp, snap, meta = self._snapshot(file_path, expected_sha256)
        try:
            # Run from the plain mooc1 base page: the chapter editor app blocks leaving the
            # page (beforeunload), and get-course-info returns the same window.info it uses.
            self.on(M1, "return true;")
            self._stage(snap, meta)
            r = self.here(r"""
                let info={}; try{info=(await (await fetch('/mooc-ans/edit/get-course-info?courseId=%s&clazzId=%s',{credentials:'include'})).json()).data||{}}catch(e){}
                const up=info.uploadParam||{}, ui=info.userInfo||{}, CLOUD='https://pan-yz.chaoxing.com';
                if(!up.uploadEnc) return {stage:'page'};
                const f=document.getElementById('mcp-file').files[0];
                let tk=''; try{const t=await (await fetch('/ananas/getTk',{credentials:'include'})).json(); tk=(t.data&&t.data.tk)||''}catch(e){}
                const m={_token:tk,d:'/Upload-Files/',puid:ui.uid||up.uploadUid,hqsd:1,
                  destPathArr:JSON.stringify(['课程',(info.courseInfo||{}).courseName||'','章节']),name:f.name,type:f.type,
                  lastModifiedDate:new Date(f.lastModified).toISOString(),size:f.size};
                let sg=null; try{sg=await (await fetch('/ananas/generate-sign',{method:'POST',credentials:'include',
                  headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'},
                  body:new URLSearchParams({params:JSON.stringify(m),enc:up.uploadEnc,t:up.uploadTimeStamp})})).json()}catch(e){}
                if(!sg||!sg.signature) return {stage:'sign'};
                if(sg.lastModifiedDate) m.lastModifiedDate=sg.lastModifiedDate;
                const v=new FormData(); Object.keys(m).forEach(k=>v.append(k,m[k])); v.append('file',f,f.name);
                ['appid','timestamp','nonce','signature','_from'].forEach(k=>{if(sg[k]!=null)v.append(k,sg[k])});
                let d=null; try{d=await (await fetch(CLOUD+'/upload/v2/uploadfile',{method:'POST',body:v,credentials:'include'})).json()}catch(e){}
                if(!d||d.result!==true||!d.data||!/^[0-9a-f]{32}$/.test(d.data.objectId||'')) return {stage:'upload'};
                return {stage:'done',objectid:d.data.objectId,size:d.data.size,suffix:d.data.suffix||''};
            """ % (_safe_id(c.id), _safe_id(c.clazz_id)), retry_safe=False)
            if not isinstance(r, dict) or r.get("stage") != "done":
                raise XxtError(f"上传在「{(r or {}).get('stage', '未知')}」阶段失败；章节没有修改。")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        oid, size, name = r["objectid"], int(r.get("size") or meta["size"]), meta["name"]
        ext = "." + (suffix or str(r.get("suffix") or ""))
        job = _jobid()
        if module == "insertimage":
            mid, jb = _mid(), f"{_ms()}{random.randint(100000, 999999)}"   # image _jobid: ms + 6 digits
            src = f"https://p.cldisk.com/star4/{oid}/origin{ext}"
            html = (f'<p><img class="img_pic" src="{src}" data-original="{src}" mid="{mid}" _jobid="{jb}" modifyimg="1"></p>')
            att = {"module": "insertimage", "name": None, "mid": mid, "_jobid": jb, "objectid": oid}
            out = self.insert_chapter_module(course, chapter_id, card_id, module, {}, inline_html=html, inline_attachment=att)
            return {**out, "object_id": oid, "file": name}
        data = {"objectid": oid, "name": name, "type": ext, "size": size, "hsize": hsize(size), "title": name, "mid": _mid()}
        if module == "downloadfile":
            u = f"https://p.ananas.chaoxing.com/star3/origin/{oid}{ext}"
            data.update(src=u, _src=u)
        else:
            data.update(_jobid=job, jobid=job)
        if module == "insertvideo":
            data.update(fastforward="true", doublespeed=1)
        if module == "insertdoc":
            pages = None
            for _ in range(10):
                s = self._call(M1, f"/ananas/status/{oid}")
                j = s.get("json") if isinstance(s, dict) else None
                if isinstance(j, dict) and j.get("status") == "success" and j.get("pagenum"):
                    pages = j["pagenum"]
                    break
                time.sleep(3)
            data["pagenum"] = str(pages or 1)
        out = self.insert_chapter_module(course, chapter_id, card_id, module, data)
        return {**out, "object_id": oid, "file": name, **({"job_id": job} if module != "downloadfile" else {})}
