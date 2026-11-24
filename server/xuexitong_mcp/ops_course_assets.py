"""Reuse a chapter editor's cloud upload and verify attached hall media in the visitor view."""

import json
import re
import shutil

from .ops_exhibit import open_hall, state, one
from .xxt import XxtError


def register_course_assets(tool, client, check_write, dry, check_path, digest):
    @tool(
        "write",
        "将已预览的本机文件上传至本课章节素材云盘，返回原生文件 ID，供展厅、模型和网页引用。",
    )
    def upload_course_asset(
        course: str, file_path: str, confirm: bool = False, file_sha256: str = ""
    ):
        cl, c = client(), check_write(course)
        p = check_path(file_path)
        if not confirm:
            meta = digest(p)
            return dry(
                c,
                "上传课程素材到云盘",
                file=p.name,
                bytes=p.stat().st_size,
                sha256=meta["sha256"],
                bind={"file_sha256": meta["sha256"]},
            )
        tmp, snap, meta = cl._snapshot(str(p), file_sha256)
        try:
            result = cl._cloud_upload(cl.ctx(c.id), snap, meta)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        oid = result.get("objectid")
        if not isinstance(oid, str) or not re.fullmatch("[0-9a-f]{32}", oid):
            raise XxtError("原生上传回执没有有效的文件 ID。")
        return {
            "ok": True,
            "object_id": oid,
            "name": meta["name"],
            "sha256": meta["sha256"],
            "size": meta["size"],
        }

    @tool(
        "read",
        "从本课展厅参观端核验某一展板的音视频或图片，返回实际下载字节数、SHA-256 和可解码的媒体信息。",
    )
    def verify_exhibit_media(
        course: str, prop_id: str, slot: str, expected_sha256: str = ""
    ):
        kinds = {"audioFileId": "audio", "videoFileId": "video", "imgFileId": "image"}
        if slot not in kinds or (
            expected_sha256 and not re.fullmatch("[a-fA-F0-9]{64}", expected_sha256)
        ):
            raise XxtError("请提供媒体字段及有效的 SHA-256。")
        cl = client()
        hid = open_hall(cl, cl.course(course), public=True)
        oid = one(state(cl, hid)["props"], prop_id)["hallPropAttr"].get(slot)
        if not isinstance(oid, str) or not re.fullmatch("[0-9a-f]{32}", oid):
            raise XxtError("展板未配置该媒体。")
        js = "const oid=" + json.dumps(oid) + ",type=" + json.dumps(kinds[slot]) + ";"
        result = cl.here(
            js
            + """
          const r=await fetch('/api/upload-file/remoteFile/'+oid,{cache:'no-store'}),limit=192*1024*1024;
          if(!r.ok||!r.body||Number(r.headers.get('content-length'))>limit)throw Error('资源不可用或超过 192 MiB');
          const reader=r.body.getReader(),parts=[];let count=0;
          try{while(true){const {value,done}=await reader.read();if(done)break;count+=value.length;
              if(count>limit){await reader.cancel();throw Error('资源过大');} parts.push(value);}}finally{reader.releaseLock();}
          const blob=new Blob(parts,{type:r.headers.get('content-type')||''}),sha=await crypto.subtle.digest('SHA-256',await blob.arrayBuffer());
          const result={bytes:count,sha256:[...new Uint8Array(sha)].map(n=>n.toString(16).padStart(2,'0')).join('')};
          if(type==='image'){const img=await createImageBitmap(blob);result.width=img.width;result.height=img.height;img.close();}
          else{const m=document.createElement(type),url=URL.createObjectURL(blob);try{
              await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('读取媒体元数据超时')),8000);
                m.onloadedmetadata=()=>{clearTimeout(timer);resolve()};m.onerror=()=>{clearTimeout(timer);reject(Error('媒体解码失败'))};m.src=url;m.load();});
              result.duration=m.duration;if(type==='video'){result.width=m.videoWidth;result.height=m.videoHeight;}
            }finally{URL.revokeObjectURL(url);}}
          return result;"""
        )
        return dict(
            result,
            ok=not expected_sha256 or result["sha256"] == expected_sha256.lower(),
            object_id=oid,
        )
