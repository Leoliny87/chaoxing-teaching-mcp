"""Course management images, portal media, and existing portal articles."""

import json
import re
import shutil
from urllib.parse import urlencode, urlsplit

from .ops_exhibit import fingerprint, portal_editor
from .ops_write import sanitize_html
from .xxt import M1, M2, XxtError, _safe_id


def save_management_image(cl, c, slot, snap, meta, old):
    """Upload a finished composition using the course management form's native save operation."""
    if slot not in ("cover", "logo") or meta["size"] > 5 * 1024 * 1024:
        raise XxtError("课程封面和标志限 5 MiB 以内。")
    endpoint = "/mooc2-ans/tcm/getcoursesetting?" + urlencode(
        {"courseId": c.id, "courseid": c.id, "cpi": c.cpi}
    )
    cl.on(M2, "return true;")
    cl._stage(snap, meta)
    args = {"cid": c.id, "cpi": c.cpi, "slot": slot, "old": old, "endpoint": endpoint}
    return cl.here(
        "const args="
        + json.dumps(args)
        + r""";
      if(location.host!=='mooc2-ans.chaoxing.com')throw Error('课程管理域不符');
      const form=async()=>{const d=D(await F(args.endpoint,{cache:'no-store'}));
        if(d.querySelector('#curCourseLogo')?.getAttribute('src')!==args.old.cover||
           d.querySelector('#curCourseHeaderLogo')?.getAttribute('src')!==args.old.logo)throw Error('课程素材已变化');
        return d;};
      const d=await form(),value=k=>d.getElementById(k)?.value;
      const params=new URLSearchParams({uid:value('uploadUid'),enc2:value('uploadEnc'),t:value('currentTime')});
      if(!['uploadUid','uploadEnc','currentTime'].every(value))throw Error('上传组件未就绪');
      const file=document.querySelector('#mcp-file')?.files[0];if(!file)throw Error('未选定文件');
      const data=new FormData(),cover=args.slot==='cover';
      let body=file,ext=file.name.split('.').pop().toLowerCase();
      if(cover){
        const img=await createImageBitmap(file);try{const canvas=document.createElement('canvas');
          canvas.width=img.width;canvas.height=img.height;canvas.getContext('2d').drawImage(img,0,0);
          body=await new Promise((resolve,reject)=>canvas.toBlob(v=>v?resolve(v):reject(Error('图片转换失败')),'image/png'));
          ext='png';}finally{img.close();}}
      const name=cover?file.name.replace(/\.[^.]+$/,'.png'):file.name;
      data.append('filePart',body,name);data.append('fileType',ext);data.append('name',name);
      const upload=await fetch('https://mooc1.chaoxing.com/upload-ans/edit/uploadBase64?'+params,{method:'POST',credentials:'include',body:data});
      if(!upload.ok)throw Error('图片上传失败');
      const receipt=await upload.json();if(!receipt.status||!receipt.url)throw Error('图片上传回执不完整');
      const fresh=await form();const payload={courseId:args.cid,cpi:args.cpi};
      if(cover)payload.imageData=receipt.url;else{payload.imageUrl=receipt.url;payload.v=fresh.querySelector('#corusesetv')?.value||'0';}
      const saved=await J('/mooc2-ans/tcm/'+(cover?'updatecourselogo':'updatecourseheaderlogo'),POST(payload));
      if(!saved?.status)throw Error('课程图片保存回执不明确');return saved.imgUrl||receipt.url;""",
        retry_safe=False,
    )


def read_management_images(cl, c):
    c = cl.ctx(c.id)
    endpoint = "/mooc2-ans/tcm/getcoursesetting?" + urlencode(
        {"courseid": c.id, "courseId": c.id, "cpi": c.cpi}
    )
    assets = cl.on(
        M2,
        "const d=D(await F("
        + json.dumps(endpoint)
        + "));"
        + "const src=id=>d.querySelector(id)?.getAttribute('src')??null;"
        + "return {cover:src('#curCourseLogo'),logo:src('#curCourseHeaderLogo')};",
    )
    if None in assets.values():
        raise XxtError("缺少课程封面或标志控件。")
    return assets


def media_dialog(cl):
    cl.here("""if(!document.querySelector('.courseShowPop')?.offsetWidth){
        const link=document.querySelector('[onclick*="courseShow("]');if(!link)throw Error('没有课程展示编辑入口');link.click();}
        return true;""")
    if not cl.wait_for(
        "return !!document.querySelector('.courseShowPop')?.offsetWidth && !!document.querySelector('#updatecoursevideo')"
    ):
        raise XxtError("门户媒体设置没有加载。")
    return cl.here("""const attr=(id,k)=>document.querySelector(id)?.getAttribute(k)||'';
        return {background:attr('#updatecoursebg','data'),trailer:attr('#updatecoursevideo','data'),
                article:document.querySelector('#backgroundArticleId')?.value,
                bg_auto:!!document.querySelector('#courseBgAutoplay')?.checked,
                video_auto:!!document.querySelector('#coursePartAutoplay')?.checked};""")


def public_portal(cl, c, url):
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc != M1
        or not re.fullmatch(
            r"/course-ans/courseportal/portal/[A-Za-z0-9=_-]+", parts.path
        )
    ):
        raise XxtError("请输入本课在超星的门户首页链接。")
    cl.b.navigate(f"https://{M1}" + parts.path, readiness=False)
    wait = """const d=document.querySelector('iframe')?.contentDocument;
      const res=d?.defaultView?.performance.getEntriesByType('resource').find(x=>new URL(x.name).origin===location.origin && new URL(x.name).pathname.endsWith('/portal-basic-info'));"""
    if not cl.wait_for(wait + "return !!res;"):
        raise XxtError("门户未返回课程信息。")
    return cl.here(
        wait
        + """
      const info=(await J(res.name,{cache:'no-store'})).dataInfo;
      if(!info?.editButtonUrl || new URL(info.editButtonUrl,location.href).searchParams.get('courseId')!=="""
        + json.dumps(c.id)
        + """)throw Error('课程门户不匹配');
      return (info.articleStyleInfo||[]).map(a=>({id:String(a.id),title:a.title||a.name||'',parent:a.parentArticleTitle||'',
        content:a.content||'',children:a.subArray?.length||0}));"""
    )


def register_portal(tool, client, check_write, dry, check_path, digest):
    @tool("read", "读取课程管理的课程封面与标志，以及课程门户的背景和片花对象标识。")
    def get_course_branding(course: str):
        cl = client()
        c = cl.course(course)
        assets = read_management_images(cl, c)
        if None in assets.values():
            raise XxtError("缺少课程封面或标志控件。")
        portal_editor(cl, c)
        return {"management": assets, "portal": media_dialog(cl)}

    @tool(
        "write",
        "从本机文件更新本课封面、标志、门户背景图或课程片花。在对应编辑器核验前后状态。",
    )
    def set_course_branding_file(
        course: str,
        slot: str,
        file_path: str,
        confirm: bool = False,
        file_sha256: str = "",
        previous_revision: str = "",
    ):
        types = {
            "cover": {".jpg", ".jpeg", ".png", ".gif"},
            "logo": {".jpg", ".jpeg", ".png"},
            "background": {".jpg", ".jpeg", ".png"},
            "trailer": {".mp4"},
        }
        c, cl = check_write(course), client()
        p = check_path(file_path)
        if slot not in types or p.suffix.lower() not in types[slot]:
            raise XxtError(
                "请使用 cover、logo、background 对应的图片，或 trailer 对应的 MP4。"
            )

        def read_state():
            if slot in ("cover", "logo"):
                result = read_management_images(cl, c)
                if None in result.values():
                    raise XxtError("缺少图片控件。")
                return result
            portal_editor(cl, c)
            return media_dialog(cl)

        old = read_state()
        if not confirm:
            file_digest = digest(p)["sha256"]
            return dry(
                c,
                "更新课程展示素材",
                slot=slot,
                file=p.name,
                sha256=file_digest,
                previous=old[slot],
                bind={
                    "file_sha256": file_digest,
                    "previous_revision": fingerprint(old),
                },
            )
        if fingerprint(old) != previous_revision:
            raise XxtError("课程展示素材已变化，请刷新。")
        tmp, snap, meta = cl._snapshot(str(p), file_sha256)
        try:
            if slot in ("cover", "logo"):
                new_id = save_management_image(cl, c, slot, snap, meta, old)
            else:
                selector = "#BgUploader" if slot == "background" else "#TrailerUploader"
                field = (
                    "#updatecoursebg" if slot == "background" else "#updatecoursevideo"
                )
                cl.b.upload_selector(selector, str(snap))
                new_id = cl.wait_for(
                    "const v=document.querySelector("
                    + json.dumps(field)
                    + ")?.getAttribute('data');return /^[0-9a-f]{32}$/.test(v)&&v!=="
                    + json.dumps(old[slot])
                    + "&&v",
                    timeout=100,
                )
                if not new_id:
                    raise XxtError("未取得新媒体的对象标识。")
                if slot == "trailer":
                    cl.here(
                        """const v=document.querySelector('#updatecoursevideo');
                        const r=await saveCoursePartVideo(v.getAttribute('data'),v.getAttribute('src'),Number(document.querySelector('#coursePartAutoplay').checked));
                        if(!r?.status)throw Error('片花保存回执不明确');return true;""",
                        retry_safe=False,
                    )
                else:
                    cl.here(
                        """const btn=document.querySelector('.courseShowPop .saveCoverVideoBtn');
                        if(!btn?.offsetWidth)throw Error('保存控件不可用');btn.click();return true;""",
                        retry_safe=False,
                    )
                cl.wait_for(
                    "return !document.querySelector('.courseShowPop')?.offsetWidth"
                )
            after = read_state()
            return {
                "ok": bool(new_id)
                and after[slot] == new_id
                and all(old[k] == after[k] for k in old if k != slot),
                "slot": slot,
                "file": meta["name"],
                "sha256": meta["sha256"],
                "saved": after[slot],
            }
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @tool("read", "读取指定课程门户的栏目 ID、标题和修订摘要；指定栏目 ID 时读取正文。")
    def get_portal_articles(course: str, portal_url: str, article_id: str = ""):
        cl = client()
        rows = public_portal(cl, cl.course(course), portal_url)
        if article_id:
            found = [r for r in rows if r["id"] == _safe_id(article_id)]
            if len(found) != 1:
                raise XxtError("栏目不存在或不唯一。")
            row = found[0]
            return dict(row, revision=fingerprint(row))
        return {
            "articles": [
                {k: r[k] for k in ("id", "title", "children")}
                | {"revision": fingerprint(r)}
                for r in rows
            ]
        }

    @tool(
        "write",
        "修改本课程门户已有叶子栏目的正文。可追加安全 HTML、替换一处文字或替换整篇。",
    )
    def edit_portal_article(
        course: str,
        portal_url: str,
        article_id: str,
        revision: str,
        content: str,
        mode: str = "append",
        find: str = "",
        confirm: bool = False,
    ):
        c, cl = check_write(course), client()

        def current():
            matches = [
                r
                for r in public_portal(cl, c, portal_url)
                if r["id"] == _safe_id(article_id)
            ]
            if len(matches) != 1:
                raise XxtError("栏目不存在或不唯一。")
            return matches[0]

        row = current()
        if fingerprint(row) != revision or row["children"]:
            raise XxtError("栏目已变更或含子栏目。")
        html = sanitize_html(content)
        if mode == "append":
            body = row["content"] + html
        elif mode == "replace":
            body = html
        elif mode == "resource_url":
            from .ops_course_patches import patch_card

            body = patch_card(row["content"], mode, content, find)
        elif (
            mode == "text"
            and find
            and not re.search(r'[<>&"]', find + content)
            and row["content"].count(find) == 1
        ):
            from .ops_course_patches import replace_visible_text

            body = replace_visible_text(row["content"], find, content)
        else:
            raise XxtError(
                "请选择 append、replace、resource_url 或匹配唯一正文文字的 text。"
            )
        if not confirm:
            return dry(
                c, "修改门户栏目", article=row["title"], mode=mode, new_content=content
            )
        portal_editor(cl, c)
        payload = {
            "articleId": article_id,
            "courseId": c.id,
            "cpi": c.cpi,
            "content": body,
            "title": row["title"],
            "parentArticleTitle": row["parent"],
            "subsetArticles": "",
            "deleteArticleIds": "",
        }
        cl.here(
            "const v="
            + json.dumps(payload)
            + """;const form=D(await F('/course-ans/courseportal/editcoursearticlevm?'+new URLSearchParams({courseId:v.courseId,cpi:v.cpi,articleId:v.articleId})));
           if(!form.querySelector('#articleTitleEnglish'))throw Error('栏目编辑表单不完整');
           v.titleEnglish=form.querySelector('#articleTitleEnglish').value||'';
           const res=await J('/course-ans/courseportal/editcoursearticle',POST(v));if(!res?.status)throw Error('栏目保存回执不明确');return true;""",
            retry_safe=False,
        )
        return {"ok": current()["content"] == body, "article_id": article_id}
