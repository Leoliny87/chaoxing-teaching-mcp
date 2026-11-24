"""List and upload personal teaching models via the course's native 3D resource picker."""

import json
import shutil
import struct
from urllib.parse import urlencode, urlsplit

from .ops_course_graph_authoring import numeric
from .ops_teaching_model import HOST
from .ops_upload import safe_name
from .xxt import M1, XxtError

ORIGIN = "https://" + HOST
ROOT = ORIGIN + "/"
UPSTREAM = "vr.chaoxing.com"
MAX_GLB = 100 * 1024 * 1024
_LIBRARY = """if(location.origin!==%s || location.pathname!=='/')return null;
 const pages=performance.getEntriesByType('resource').map(e=>new URL(e.name)).filter(u=>
    u.origin===location.origin && u.pathname==='/api/model-editor/config/page');
 const page=[...new Set(pages.map(u=>u.href))].at(-1);
 if(!page)return null;
 const r=await fetch(page,{credentials:'include',redirect:'error',cache:'no-store'});
 if(!r.ok)return null;const j=await r.json(),data=j?.result;
 if(!j.success||!Array.isArray(data?.records))return null;
 const items=data.records.map(row=>{let cfg=row.configJSON;
    try{if(typeof cfg==='string')cfg=JSON.parse(cfg)}catch{return null}
    const name=cfg?.modelSettings?.name||row.name, id=String(row.id);
    if(!name || !/^[1-9][0-9]*$/.test(id))return null;return {id,name};});
 if(items.some(x=>!x))return null;
 const labels=[...document.images].map(i=>i.alt);
 if(items.some(x=>!labels.includes(x.name)))return null;
 const total=Number(data.total), current=Number(data.current),size=Number(data.size);
 if(!Number.isSafeInteger(total)||total<0||!Number.isSafeInteger(current)||current<1||!Number.isSafeInteger(size)||size<1)return null;
 return {current,size,total,items,more:current*size<total};""" % json.dumps(ORIGIN)


def verified_page(url, host, path):
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.netloc == host and parsed.path == path


def glb_file(path):
    if path.suffix.lower() != ".glb" or not 20 <= path.stat().st_size <= MAX_GLB:
        raise XxtError("请选择平台支持的 GLB 文件（不超过 100 MiB）。")
    with path.open("rb") as file:
        header = file.read(20)
    if len(header) != 20:
        raise XxtError("GLB 文件头不完整。")
    magic, version, length, chunk, typ = struct.unpack("<4sIIII", header)
    if (
        magic != b"glTF"
        or version != 2
        or length != path.stat().st_size
        or typ != 0x4E4F534A
        or not 0 < chunk <= length - 20
    ):
        raise XxtError("GLB 2.0 文件头或文件长度无效。")


class ModelLibrary:
    def __init__(self, api, c, chapter):
        self.api, self.c, self.chapter = api, c, chapter

    def open(self):
        chapter = numeric(self.chapter)
        if chapter not in {str(x["chapter_id"]) for x in self.api.chapters(self.c.id)}:
            raise XxtError("入口章节未在当前课程中找到。")
        cid = numeric(self.c.id)
        query = urlencode(
            {
                "classId": numeric(self.c.clazz_id),
                "cpi": numeric(self.c.cpi),
                "newMooc": "true",
                "mooc2": "1",
            }
        )
        self.api.b.navigate(
            f"https://{M1}/mooc-ans/edit/chapters/{cid}/{chapter}?{query}"
        )
        toolbar = (
            "if(location.origin!=="
            + json.dumps("https://" + M1)
            + " || !location.pathname.endsWith("
            + json.dumps("/edit/chapters/" + cid + "/" + chapter)
            + "))return false;const tools=[...document.querySelectorAll('*')].filter(e=>e.offsetWidth&&!e.childElementCount&&e.innerText?.trim()==='3D资源');"
        )
        if not self.api.wait_for(toolbar + "return tools.length===1;"):
            raise XxtError("章节编辑器未显示唯一的「3D资源」控件。")
        if not self.api.here(
            toolbar + "if(tools.length!==1)return false;tools[0].click();return true;",
            retry_safe=False,
        ):
            raise XxtError("进入原生 3D 资源选择器失败。")
        link = self.api.wait_for(
            toolbar
            + """const frames=[...document.querySelectorAll('iframe')].filter(f=>{
          const u=new URL(f.src||'about:blank');return f.offsetWidth&&u.origin==='https://vr.chaoxing.com'&&u.pathname==='/out-api/redirect';});
          return frames.length===1&&frames[0].src;"""
        )
        if not verified_page(link, UPSTREAM, "/out-api/redirect"):
            raise XxtError("未收到选定课程提供的 3D 资源入口。")
        self.api.b.navigate(link)
        if not self.api.wait_for(
            "return location.origin==="
            + json.dumps(ORIGIN)
            + " && location.pathname==='/course_pop'"
            " && [...document.querySelectorAll('button')].some(b=>b.offsetWidth&&b.innerText.trim()==='完整功能');"
        ):
            raise XxtError("超星课程入口未打开模型教学编辑器。")
        # The verified course picker offers the root studio as “完整功能”. Use our own tab.
        self.api.b.navigate(ROOT)
        pre = (
            "if(location.origin!=="
            + json.dumps(ORIGIN)
            + "||location.pathname!=='/')return false;"
        )
        mine = "const a=[...document.querySelectorAll('button')].filter(b=>b.offsetWidth&&b.innerText.trim()==='我的模型');"
        if not self.api.wait_for(pre + mine + "return a.length===1;"):
            raise XxtError("模型工作室未显示当前账号的「我的模型」。")
        if not self.api.here(
            pre + mine + "if(a.length!==1)return false;a[0].click();return true;",
            retry_safe=False,
        ):
            raise XxtError("无法选择当前账号的模型。")
        first = self.api.wait_for(_LIBRARY)
        if not isinstance(first, dict) or first.get("current") != 1:
            raise XxtError("当前账号的模型列表未能从第一页读取。")

    def page(self, index=1, find=None):
        if type(index) is not int or index < 1:
            raise XxtError("页码应为正整数。")
        visited = set()
        while True:
            data = self.api.here(_LIBRARY)
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("items"), list)
                or data.get("current") in visited
            ):
                raise XxtError("模型列表分页无效。")
            visited.add(data["current"])
            if find is not None:
                match = [a for a in data["items"] if find(a)]
                if len(match) > 1:
                    raise XxtError("有多个同名模型，无法唯一识别。")
                if match:
                    return match[0]
            elif data["current"] == index:
                return data
            if not data["more"]:
                if find is not None:
                    return None
                raise XxtError("模型库中没有该页。")
            target = data["current"] + 1
            if not self.api.here(
                "if(location.origin!=="
                + json.dumps(ORIGIN)
                + """||location.pathname!=='/')return false;
              const b=document.querySelector('.ant-pagination-next:not(.ant-pagination-disabled) button');
              if(!b||b.disabled)return false;b.click();return true;""",
                retry_safe=False,
            ):
                raise XxtError("无法使用原生翻页控件。")
            if not self.api.wait_for(
                "const data=await(async()=>{"
                + _LIBRARY
                + "})();return data?.current==="
                + str(target)
                + ";"
            ):
                raise XxtError("未能核对模型库下一页。")

    def preview(self, row):
        url = ORIGIN + "/preview/" + numeric(row["id"])
        self.api.b.navigate(url)
        receipt = self.api.wait_for(
            "const id="
            + json.dumps(row["id"])
            + ",name="
            + json.dumps(row["name"])
            + ",origin="
            + json.dumps(ORIGIN)
            + """;
          if(location.origin!==origin||location.pathname!=='/preview/'+id)return false;
          const native=performance.getEntriesByType('resource').map(r=>new URL(r.name))
            .find(u=>u.origin===origin && u.pathname==='/api/model-editor/config/get');
          if(!native)return false;
          const res=await fetch(native,{credentials:'include',redirect:'error',cache:'no-store'});if(!res.ok)return false;
          const j=await res.json(),m=j.result;
          const c=m&&typeof m.configJSON==='string'?JSON.parse(m.configJSON):m?.configJSON;
          return !!j.success && String(m?.id)===id && c?.modelSettings?.name===name
            && [...document.querySelectorAll('canvas')].some(e=>e.width>0&&e.height>0);""",
            timeout=35,
        )
        if not receipt:
            raise XxtError("模型预览未读回对应 ID、名称及画布。")
        return {"model_id": row["id"], "name": row["name"], "preview_url": url}

    def upload(self, snap, name):
        pre = (
            "if(location.origin!=="
            + json.dumps(ORIGIN)
            + "||location.pathname!=='/')return false;"
        )
        base = """const dlg=document.querySelector('[role=dialog]');const get=(scope,text)=>
           [...(scope?.querySelectorAll('button')||[])].find(b=>b.offsetWidth&&b.innerText.trim()===text);"""
        if not self.api.here(
            pre
            + base
            + "const b=get(document,'上传模型');if(!b||dlg)return false;b.click();return true;",
            retry_safe=False,
        ):
            raise XxtError("未打开上传模型窗口。")
        if not self.api.wait_for(
            pre
            + base
            + "return !!dlg?.querySelector('#materialName') && !!get(dlg,'选择模型文件');"
        ):
            raise XxtError("模型上传表单未就绪。")
        self.api.b.fill_selector("[role=dialog] #materialName", name)
        selector = "[role=dialog] .flex.flex-wrap button:first-child"
        if not self.api.here(
            pre
            + base
            + "return document.querySelector("
            + json.dumps(selector)
            + ")===get(dlg,'选择模型文件');"
        ):
            raise XxtError("无法唯一定位选择模型文件按钮。")
        self.api.b.upload_selector(selector, str(snap))
        expected = (
            pre
            + base
            + "const save=get(dlg,'确定');return !!save && !save.disabled && dlg.innerText.includes("
            + json.dumps(snap.name)
            + ") && dlg.querySelector('#materialName')?.value==="
            + json.dumps(name)
            + ";"
        )
        if not self.api.wait_for(expected, timeout=90):
            raise XxtError("模型文件未就绪，请核对上传界面。")
        if not self.api.here(
            expected.replace("return !!save", "const ok=!!save")
            + "if(!ok)return false;save.click();return true;",
            retry_safe=False,
        ):
            raise XxtError("模型或文件名发生变化。")
        if not self.api.wait_for(
            pre
            + base
            + "return !dlg&&[...document.images].some(i=>i.alt==="
            + json.dumps(name)
            + ");",
            timeout=120,
        ):
            raise XxtError("已提交模型，平台尚未回读。请先查模型库再尝试上传。")


def register_model_library(
    tool, client, check_write, dry, check_upload_path, upload_preview_digest
):
    def library(course, chapter, write=False):
        api = client()
        c = api.ctx(check_write(course).id if write else course)
        studio = ModelLibrary(api, c, chapter)
        studio.open()
        return studio

    @tool(
        "read",
        "从选定课程章节的 3D 资源入口打开「我的模型」，按页读取当前账号模型库的名称与原生 ID。",
    )
    def list_teaching_model_library(
        course: str, chapter_id: str, page: int = 1
    ) -> dict:
        return library(course, chapter_id).page(page)

    @tool(
        "read",
        "从模型库按原生 ID 核实模型，再打开并核对可用于章节或门户的公开预览链接。",
    )
    def get_teaching_model_preview(course: str, chapter_id: str, model_id: str) -> dict:
        numeric(model_id)
        studio = library(course, chapter_id)
        row = studio.page(find=lambda r: r["id"] == model_id)
        if not row:
            raise XxtError("个人模型库中未找到指定模型。")
        return studio.preview(row)

    @tool(
        "write",
        "通过课程章节的原生入口上传 GLB 到当前账号的「我的模型」，保持原文件，校验预演哈希并回读模型与公开预览链接。",
    )
    def upload_teaching_model(
        course: str,
        chapter_id: str,
        name: str,
        file_path: str,
        confirm: bool = False,
        file_sha256: str = "",
    ) -> dict:
        if (
            not name.strip()
            or len(name.encode("utf-16-le")) // 2 > 20
            or any(ord(c) < 32 for c in name)
        ):
            raise XxtError("模型名称应为 1 至 20 字。")
        path = check_upload_path(file_path)
        glb_file(path)
        studio = library(course, chapter_id, True)
        if studio.page(find=lambda r: r["name"] == name):
            raise XxtError("我的模型中已有同名条目。")
        if not confirm:
            fingerprint = upload_preview_digest(path)
            return dry(
                studio.c,
                "上传模型至当前账号的「我的模型」",
                bind={"file_path": str(path), "file_sha256": fingerprint["sha256"]},
                name=name,
                file=safe_name(path.name),
                **fingerprint,
            )
        tmp, snap, _ = studio.api._snapshot(str(path), file_sha256)
        try:
            glb_file(snap)
            studio.upload(snap, name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        studio.open()
        new = studio.page(find=lambda r: r["name"] == name)
        if not new:
            raise XxtError("提交后未能在当前账号的模型库核对新模型。")
        return {"ok": True, "sha256": file_sha256, **studio.preview(new)}
