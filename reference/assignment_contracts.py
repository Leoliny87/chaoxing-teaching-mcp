"""Pure, offline assignment-contract prototypes; not installed or imported by MCP.

Adapted from project-owned undeployed research. No browser, network, credentials,
filesystem operations, tool registration or publication actions are included.
"""
import hashlib
import json
import re

def request_digest(course, class_id, title, question):
    value = json.dumps([course, class_id, title, question], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(value.encode()).hexdigest()

def validate_empty_editor(initial, course, class_id):
    # Actual page evidence: workid is empty until the first question is added.
    # A pre-existing nonempty ID must never be treated as a pristine new editor.
    if (initial.get("path") != "/mooc2-ans/work/goToWorkEditor" or initial.get("url_work_id") != ""
            or initial.get("course") != course or initial.get("class_id") != class_id
            or initial.get("work_id") != "" or not re.fullmatch(r"新建作业\d{14}", initial.get("title") or "")
            or initial.get("editors") != 0 or not re.search(r"题量\s*0\s*，\s*总分\s*0(?:\.0+)?(?:\s|$)", initial.get("text", ""))):
        raise ValueError("新编辑器、课程、题量或空对象标识不符合已验证范围；停止。")

def native_text_expectation(target, label):
    """Bind the reviewed label to BSK's exact textContent fact, not innerText.

    The current BSK implementation compares field=text with raw textContent.
    Only surrounding whitespace may differ from the requested visible label;
    hidden text, a different label or an incomplete snapshot stops before click.
    This helper does not retry a failed action or change the target selector.
    """
    if (not isinstance(target, dict) or not isinstance(label, str) or not label
            or not isinstance(target.get("selector"), str) or not target["selector"]
            or not isinstance(target.get("raw_text"), str) or len(target["raw_text"]) > 16384
            or not isinstance(target.get("visible_text"), str)
            or target["visible_text"].strip() != label or target["raw_text"].strip() != label):
        raise ValueError("原生控件的可见文字与完整文字不一致；未点击。")
    return {"target": target["selector"], "field": "text", "equals": target["raw_text"]}

