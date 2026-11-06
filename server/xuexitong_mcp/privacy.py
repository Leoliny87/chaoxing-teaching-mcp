"""Minimise secrets in MCP output and application logs, not page inputs."""
from __future__ import annotations

import re

_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_URL_SUFFIX = re.compile(r"\?|#|%3f|%23", re.IGNORECASE)
_SECRET_PARAM = re.compile(
    r"\b(rbtoken|access_token|refresh_token|token|openc|penc|enc|signature|sign|ticket|cpi|personid|uid)"
    r"(=|%3d)([^&\s\"'<>]+)", re.IGNORECASE,
)
_SECRET_KEY = re.compile(r"^(rbtoken|access_token|refresh_token|token|openc|penc|enc|signature|sign|ticket|cookie|authorization)$", re.IGNORECASE)
_SECRET_JSON = re.compile(
    r"([\"']?(?:rbtoken|access_token|refresh_token|token|openc|penc|enc|signature|sign|ticket|cookie|authorization)[\"']?\s*:\s*[\"'])([^\"']+)",
    re.IGNORECASE,
)


def redact_text(text: str) -> str:
    def clean_url(match: re.Match) -> str:
        url = match.group(0)
        suffix = _URL_SUFFIX.search(url)
        return url[:suffix.start()] + "?[参数已隐藏]" if suffix else url

    text = _SECRET_JSON.sub(lambda m: m.group(1) + "<redacted>", _URL.sub(clean_url, text))
    return _SECRET_PARAM.sub(lambda m: m.group(1) + m.group(2) + "<redacted>", text)


def redact_result(value, *, preserve_details: bool = False):
    if isinstance(value, dict):
        return {key: (item if preserve_details and key == "details" else
                      "<redacted>" if _SECRET_KEY.fullmatch(str(key)) else redact_result(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact_result(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


_CJK = re.compile(r"[一-鿿]")
_LONG_DIGITS = re.compile(r"\d{5,}")
_SAFE_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")


def _safe_code(error) -> str:
    code = str(getattr(error, "code", "") or "")
    return code if _SAFE_CODE.fullmatch(code) else "error"


def safe_error_text(error) -> str:
    """User-facing text for an exception without relaying unstructured evidence.

    * Local BskError / XxtError / ValueError messages are written by this package.
    * BskError from the bsk process (origin="cli") may echo page data, inputs or
      handles: only its code is shown; structured labels go via safe_browser_error_details().
    * Page-script errors (JsError) keep only messages that look like this package's own
      Chinese `throw Error(...)` texts; anything else (TypeError text, page strings) is dropped.
    * Every other exception is reduced to its type name.
    """
    name = type(error).__name__
    if name == "BskError":
        if getattr(error, "origin", "cli") == "local":
            return redact_text(f"{_safe_code(error)}: {getattr(error, 'message', '')}")
        return f"{_safe_code(error)}（BrowserSkill 返回，原始内容已隐藏）"
    if name == "JsError":
        msg = str(error)
        if _CJK.search(msg) and not _LONG_DIGITS.search(msg) and len(msg) <= 120:
            return redact_text(msg)
        return "页面脚本异常（原始内容已隐藏）"
    if name in ("XxtError", "NeedsHuman", "ValueError"):
        return redact_text(str(error))
    return name


def safe_exception_log(error) -> str:
    """Exception type plus code locations only; never the exception message or locals."""
    import traceback
    frames = traceback.extract_tb(error.__traceback__)[-8:]
    where = " <- ".join(f"{f.filename.replace(chr(92), '/').rsplit('/', 1)[-1]}:{f.lineno}({f.name})" for f in reversed(frames))
    return f"{type(error).__name__} at {where or '?'}"


def safe_browser_error_details(error, *, health_step: str | None = None) -> dict:
    """Keep bounded diagnostic labels, never raw page evidence or error payloads."""
    data = getattr(error, "data", None)
    data = data if isinstance(data, dict) else {}
    details = {"code": _safe_code(error)} if type(error).__name__ == "BskError" else {}
    for key in ("reason", "phase", "effect_state"):
        value = data.get(key)
        if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value):
            details[key] = value
    stage = getattr(error, "xxt_stage", None)
    operation = getattr(error, "xxt_operation", None)
    if stage in ("sync", "dispatch"):
        details["stage"] = stage
    if stage == "dispatch" and operation in ("navigate", "evaluate", "click", "press", "fill", "other"):
        details["operation"] = operation
    if health_step in ("doctor", "session", "login", "guard_navigation", "guard_read", "courses", "language_read"):
        details["health_step"] = health_step
    diagnostic = safe_semantic_diff(data.get("semantic_diff"))
    if diagnostic is not None:
        details["semantic_diff"] = diagnostic
    return details


def safe_semantic_diff(value):
    """Accept diagnostic labels only; never relay arbitrary browser evidence."""
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
        return None
    available = value.get("available")
    if type(available) is not bool:
        return None
    out = {"version": 1, "available": available}
    if not available:
        reason = value.get("reason")
        if not isinstance(reason, str) or reason not in {"capture_missing", "size_limit", "signature_missing", "schema_mismatch", "ambiguous_rows", "diagnostic_error"}:
            return None
        return {**out, "reason": reason}
    if (value.get("comparison") != "whole_page_signature" or type(value.get("same_signature")) is not bool
            or type(value.get("truncated")) is not bool or not isinstance(value.get("changes"), list)):
        return None
    out.update(comparison="whole_page_signature", same_signature=value["same_signature"],
               truncated=value["truncated"] or len(value["changes"]) > 16, changes=[])
    fields = {"frame", "node", "role", "tag", "name", "text", "value", "in_form", "checked", "state",
              "disabled", "inert", "modal", "visible", "pointer_events", "attributes", "identity", "order", "extra"}
    for item in value["changes"][:16]:
        if (not isinstance(item, dict) or not isinstance(item.get("bucket"), str)
                or item["bucket"] not in {"scope", "nodes", "values", "modals", "media"}
                or not isinstance(item.get("kind"), str) or item["kind"] not in {"changed", "added", "removed"}
                or not isinstance(item.get("fields"), list) or not 1 <= len(item["fields"]) <= 20
                or any(not isinstance(f, str) or f not in fields for f in item["fields"])):
            return None
        safe = {"bucket": item["bucket"], "kind": item["kind"], "fields": list(dict.fromkeys(item["fields"]))}
        if "frame" in item:
            if not isinstance(item["frame"], str) or not re.fullmatch(r"frame_[1-9][0-9]{0,4}", item["frame"]):
                return None
            safe["frame"] = item["frame"]
        if "row" in item:
            if type(item["row"]) is not int or not 1 <= item["row"] <= 5000:
                return None
            safe["row"] = item["row"]
        out["changes"].append(safe)
    return out
