"""Use the portal's course-bound native hall setup wizard."""

import json
import re
import shutil
from urllib.parse import urlsplit

from .ops_exhibit import fingerprint, portal_editor, VR
from .xxt import XxtError


FIELDS = {
    "courseScript": "参考示例：",
    "knowledgeGoal": "知识目标讲解词",
    "abilityGoal": "能力目标讲解词",
    "literacyGoal": "素养目标讲解词",
    "teachingGoal": "最终教学目标讲解词",
    "highlightSummary": "请撰写优势亮点讲解词",
    "teacherSummary": "请填写师资建设讲解词",
    "achievementSummary": "请填写课程成果讲解词",
}
SLOTS = {"unitLogo": 0, "courseCover": 1, "courseVideo": 2}
READ_FORM = """
const ref=performance.getEntriesByType('resource').find(e=>{const u=new URL(e.name);
 return u.origin===location.origin&&u.pathname==='/api/datasource-form/getFormDataByCourseId'&&u.searchParams.get('courseId')===cid});
if(!ref)throw Error('展厅表单未加载');
const data=(await J(ref.name,{cache:'no-store'})).result;
if(!data||String(data.courseId)!==cid)throw Error('展厅表单归属不符');
const {uid,formUserId,...form}=data;
"""
TEMPLATES = """const options=[...document.querySelectorAll('.template-item-container')].map(e=>({
 id:String(e.querySelector('input[type=radio]')?.value||''),name:e.querySelector('label')?.textContent.trim()||e.innerText.replace('查看详情','').trim(),
 selected:e.classList.contains('selected')}));"""
BUTTON = """const button=(txt,root=document)=>{const items=[...root.querySelectorAll('button')].filter(e=>e.offsetWidth&&!e.disabled&&e.innerText.trim()===txt);
if(items.length!==1)throw Error('找不到唯一按钮 '+txt);return items[0];};"""


def open_form(cl, c):
    portal_editor(cl, c)
    cl.here("showVirtualDiv();return true;")
    url = cl.wait_for(
        "return document.querySelector('#visualShowRoomFormEditUrl')?.value;"
    )
    if not url:
        raise XxtError("没有展厅表单入口。")
    target = urlsplit(url)
    if (
        target.scheme != "https"
        or target.netloc != VR
        or target.path not in ("", "/")
        or target.fragment.partition("?")[0] != "/newForm"
    ):
        raise XxtError("展厅表单地址无效。")
    cl.b.navigate(url, readiness=False)
    if not cl.wait_for(
        "return !!document.querySelector('.template-item-container')&&performance.getEntriesByType('resource').some(r=>new URL(r.name).pathname==='/api/datasource-form/getFormDataByCourseId')"
    ):
        raise XxtError("展厅表单没有加载。")
    return "const cid=" + json.dumps(c.id) + ";" + READ_FORM


def validate_edits(fields):
    if not isinstance(fields, dict) or set(fields) - set(FIELDS) - {"highlights"}:
        raise XxtError("展厅表单不支持这些字段。")
    for k, v in fields.items():
        if k == "highlights":
            if (
                not isinstance(v, list)
                or len(v) != 3
                or any(
                    not isinstance(row, dict) or set(row) != {"title", "content"}
                    for row in v
                )
            ):
                raise XxtError("亮点须为三组标题和正文。")
            for row in v:
                for value in row.values():
                    if (
                        not isinstance(value, str)
                        or not value.strip()
                        or len(value) > 3000
                        or re.search(r"[<>\x00]", value)
                    ):
                        raise XxtError("亮点文字无效。")
        elif (
            not isinstance(v, str)
            or not v.strip()
            or len(v) > 6000
            or re.search(r"[<>\x00]", v)
        ):
            raise XxtError("请使用纯文本讲解词。")


def to_details(cl, template=""):
    if template:
        cl.here(
            "const name="
            + json.dumps(template)
            + """;const choices=[...document.querySelectorAll('.template-item-container')].filter(e=>(e.querySelector('label')?.textContent.trim()||e.innerText.replace('查看详情','').trim())===name);
           if(choices.length!==1)throw Error('模板不唯一');choices[0].querySelector('.template-image-wrapper').click();return true;"""
        )
    cl.here(
        BUTTON
        + "if(![...document.querySelectorAll('button')].some(e=>e.offsetWidth&&e.innerText.trim()==='提交'))button('下一步').click();return true;"
    )
    if not cl.wait_for(
        "return [...document.querySelectorAll('button')].some(e=>e.offsetWidth&&e.innerText.trim()==='提交')"
    ):
        raise XxtError("未进入展厅完整信息页。")


def verified(old, new, fields, template_id, media_slot):
    ignore = {"autoSendData"}
    if template_id:
        if str(new.get("spaceTemplate")) != template_id:
            return False
        ignore.add("spaceTemplate")
    if media_slot:
        if not new.get(media_slot) or new.get(media_slot) == old.get(media_slot):
            return False
        ignore.add(media_slot)
    for k, v in fields.items():
        if k == "highlights":
            desired = [dict(a, **b) for a, b in zip(old.get(k, []), v, strict=True)]
            if new.get(k) != desired:
                return False
        elif new.get(k) != v:
            return False
        ignore.add(k)
    return {k: v for k, v in old.items() if k not in ignore} == {
        k: v for k, v in new.items() if k not in ignore
    }


def register_exhibit_form(tool, client, check_write, dry, check_path, digest):
    @tool("read", "列出本课程已保存的展厅表单、可用空间模板及当前模板。")
    def get_exhibit_form(course: str):
        cl = client()
        script = open_form(cl, cl.course(course))
        data = cl.here(script + TEMPLATES + "return {form,options};")
        return dict(data, revision=fingerprint(data["form"]))

    @tool(
        "write",
        "暂存展厅模板、讲解词、三项亮点或本地媒体文件。媒体支持 unitLogo、courseCover、courseVideo。",
    )
    def save_exhibit_form(
        course: str,
        revision: str,
        fields: dict,
        template: str = "",
        media_slot: str = "",
        file_path: str = "",
        file_sha256: str = "",
        confirm: bool = False,
    ):
        validate_edits(fields)
        if (
            bool(media_slot) != bool(file_path)
            or (media_slot and media_slot not in SLOTS)
            or not (template or fields or media_slot)
        ):
            raise XxtError("请指定表单变更，文件需同时指定媒体位置。")
        p = check_path(file_path) if file_path else None
        if p and p.suffix.lower() not in (
            {".mp4"} if media_slot == "courseVideo" else {".png", ".jpg", ".jpeg"}
        ):
            raise XxtError("媒体文件类型与表单位置不符。")
        cl, c = client(), check_write(course)
        script = open_form(cl, c)
        data = cl.here(script + TEMPLATES + "return {form,options};")
        old = data["form"]
        if fingerprint(old) != revision:
            raise XxtError("展厅表单已变化。")
        found = [
            x
            for x in data["options"]
            if x["name"] == template and re.fullmatch(r"[1-9][0-9]*", x["id"])
        ]
        if template and len(found) != 1:
            raise XxtError("找不到相应的空间模板。")
        tid = found[0]["id"] if template else ""
        if not confirm:
            return dry(
                c,
                "暂存展厅设置",
                fields=fields,
                template=template,
                media_slot=media_slot,
                file=p.name if p else "",
                bind={"file_sha256": digest(p)["sha256"]} if p else {},
            )
        to_details(cl, template)
        cl.here(
            "const labels="
            + json.dumps(FIELDS)
            + ",patch="
            + json.dumps(fields)
            + """;
          const inputs=[...document.querySelectorAll('input,textarea')].filter(x=>!x.closest('.el-dialog'));
          const fill=(e,v)=>{e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));};
          for(const [k,v] of Object.entries(patch)){if(k==='highlights'){
             for(const [j,s] of [['title','亮点标题'],['content','亮点正文']]){const f=inputs.filter(e=>e.placeholder===s);
               if(f.length!==3)throw Error('亮点表单数量不符');f.forEach((e,i)=>fill(e,v[i][j]));}
          }else{const f=inputs.filter(e=>e.placeholder?.startsWith(labels[k]));if(f.length!==1)throw Error('表单位置不唯一');fill(f[0],v);}}
          return true;"""
        )
        if p:
            temp, snap, meta = cl._snapshot(str(p), file_sha256)
            try:
                field = (
                    "const f=[...document.querySelectorAll('input[type=file]')].filter(e=>!e.closest('.el-dialog'))["
                    + str(SLOTS[media_slot])
                    + "];if(!f)throw Error('文件控件未就绪');const box=f.closest('.el-form-item');"
                )
                cl.here(
                    field
                    + "box.querySelector('.el-upload-list__item .el-icon--close')?.click();return true;"
                )
                if not cl.wait_for(
                    field + "return !box.querySelector('.el-upload-list__item')"
                ):
                    raise XxtError("媒体控件已有未完成的编辑。")
                selector = cl.here(
                    field
                    + """const a=[];let n=f;while(n&&n!==document.body){a.unshift(n.tagName.toLowerCase()+':nth-child('+([...n.parentElement.children].indexOf(n)+1)+')');n=n.parentElement;}return 'body>'+a.join('>');"""
                )
                cl.b.upload_selector(selector, str(snap))
                if not cl.wait_for(
                    field
                    + "return !!box.querySelector('.el-upload-list__item')&&box.innerText.includes("
                    + json.dumps(meta["name"])
                    + ")&&!box.innerText.includes('上传中')",
                    timeout=100,
                ):
                    raise XxtError("媒体上传未完成。")
            finally:
                shutil.rmtree(temp, ignore_errors=True)
        if fingerprint(cl.here(script + "return form;")) != revision:
            raise XxtError("表单在编辑期间发生变化。")
        cl.here(BUTTON + "button('暂存').click();return true;", retry_safe=False)
        before = json.dumps(old, ensure_ascii=True)
        after = (
            cl.wait_for(
                script
                + "const before="
                + before
                + ";return form.autoSendData==0&&JSON.stringify(before)!==JSON.stringify(form)&&form;",
                timeout=25,
            )
            if (fields or tid or p)
            else None
        )
        if not after:
            after = cl.here(script + "return form;")
        if after.get("autoSendData") != 0:
            return {"ok": False, "write_outcome": "unknown"}
        if not after or not verified(old, after, fields, tid, media_slot):
            return {
                "ok": False,
                "write_outcome": "unknown",
                "hint": "请重新读取展厅表单核对。",
            }
        return {
            "ok": True,
            "revision": fingerprint(after),
            "template_id": str(after["spaceTemplate"]),
        }

    @tool(
        "destructive",
        "提交已暂存的展厅表单并请求重新生成。平台会覆盖手工布置的展板，仅在明确需要重建时使用。",
    )
    def publish_exhibit_form(course: str, revision: str, confirm: bool = False):
        cl, c = client(), check_write(course)
        script = open_form(cl, c)
        old = cl.here(script + "return form;")
        if fingerprint(old) != revision or old.get("autoSendData") != 0:
            raise XxtError("需要本课程已暂存、尚未提交的展厅设置。")
        if not confirm:
            return dry(
                c,
                "重新生成展厅，现有手工展板会被覆盖",
                template=old.get("spaceTemplate"),
                revision=revision,
            )
        to_details(cl)
        cl.here(BUTTON + "button('提交').click();return true;")
        if not cl.wait_for(
            "return [...document.querySelectorAll('.el-message-box')].some(e=>e.offsetWidth&&e.innerText.includes('重新生成展厅'))"
        ):
            raise XxtError("平台没有展示重新生成确认框。")
        if fingerprint(cl.here(script + "return form;")) != revision:
            raise XxtError("提交前表单发生变化。")
        cl.here(
            BUTTON
            + "const box=[...document.querySelectorAll('.el-message-box')].find(e=>e.offsetWidth&&e.innerText.includes('重新生成展厅'));button('确认提交',box).click();return true;",
            retry_safe=False,
        )
        back = cl.wait_for(script + "return form.autoSendData==1&&form;", timeout=35)
        return {
            "ok": bool(back and verified(old, back, {}, "", "")),
            "stage": "submitted" if back else "unverified",
        }
