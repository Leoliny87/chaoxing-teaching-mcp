"""Verify the bytes and decoded dimensions served by the native panorama viewer."""

import json
import re

from .ops_chapter2 import PANORAMA_HOST
from .xxt import XxtError

_MAX_PANORAMA_BYTES = 96 * 1024 * 1024


def register_panorama_authoring(tool, client):
    @tool(
        "read",
        "读取已上传的全景图片在超星查看器中实际提供的文件 SHA-256 与像素尺寸，可与原图哈希核对。",
    )
    def verify_panorama_image(
        course: str, panorama_id: str, expected_sha256: str = ""
    ) -> dict:
        api = client()
        api.ctx(course)
        if not re.fullmatch(r"[1-9][0-9]{0,31}", panorama_id):
            raise XxtError("需要有效的全景资源数字 ID。")
        if expected_sha256 and not re.fullmatch("[a-fA-F0-9]{64}", expected_sha256):
            raise XxtError("SHA-256 应为 64 个十六进制字符。")
        row = api.find_panorama(panorama_id)
        if row.get("panorama_id") != panorama_id or row.get("type") != "image":
            raise XxtError("资源未在当前账号的全景图片列表中找到。")
        js = """const origin=%s, id=%s, limit=%s;
          if(location.origin!==origin)return null;
          const path='/fyportal/threedresourse/panorama/down/'+id;
          const r=await fetch(path,{credentials:'include',cache:'no-store',redirect:'error'});
          if(!r.ok || Number(r.headers.get('content-length')||0)>limit || !r.body)return null;
          const reader=r.body.getReader(), chunks=[];let size=0;
          try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;
              if(size>limit){await reader.cancel();return null;}chunks.push(value);}}
          finally{reader.releaseLock();}
          const blob=new Blob(chunks,{type:r.headers.get('content-type')||'application/octet-stream'});
          const image=await createImageBitmap(blob);
          try{const hash=await crypto.subtle.digest('SHA-256',await blob.arrayBuffer());
              return {width:image.width,height:image.height,bytes:size,
                sha256:[...new Uint8Array(hash)].map(b=>b.toString(16).padStart(2,'0')).join('')};}
          finally{image.close();}
        """ % (json.dumps(PANORAMA_HOST), json.dumps(panorama_id), _MAX_PANORAMA_BYTES)
        # find_panorama opened the trusted picker on the same origin as its viewer.
        result = api.here(js)
        if (
            not isinstance(result, dict)
            or not re.fullmatch("[0-9a-f]{64}", str(result.get("sha256", "")))
            or not all(
                isinstance(result.get(k), int) and result[k] > 0
                for k in ("width", "height", "bytes")
            )
        ):
            raise XxtError("未能读取或解码查看器的全景图片（单图上限 96 MiB）。")
        return {
            "ok": not expected_sha256 or expected_sha256.lower() == result["sha256"],
            "panorama_id": panorama_id,
            "title": row.get("title"),
            **result,
        }
