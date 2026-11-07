"""Question model shared by assignment, exam-paper and question-bank creation.

Every request shape here was captured from the real editors on the test
course on 2026-11-07: the work editor (module/work/js/createWork.js), the
paper editor (module/exam/js/examAction.js) and the bank editor
(js/questionbank/addQuestion.js).  The three surfaces store the same answer
JSON; they differ only in endpoint and in a few form fields.

Callers give plain text.  It is escaped and wrapped in <p> here, so no caller
HTML reaches the server.
"""
from __future__ import annotations

import html as _h
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from .xxt import XxtError

TYPES = {"单选": 0, "多选": 1, "填空": 2, "判断": 3, "简答": 4, "名词解释": 5, "论述": 6, "计算": 7, "其它": 8,
         "分录": 9, "连线": 11, "排序": 13, "完型填空": 14, "阅读理解": 15, "程序": 17, "口语": 18, "听力": 19,
         "共用选项": 20, "测评": 21, "口语测评": 22, "钟表": 23, "选词填空": 24, "选做": 25, "写作": 26}
LABEL = {0: "单选题", 1: "多选题", 2: "填空题", 3: "判断题", 4: "简答题", 5: "名词解释", 6: "论述题", 7: "计算题",
         8: "其它", 9: "分录题", 11: "连线题", 13: "排序题", 14: "完型填空", 15: "阅读理解", 17: "程序题", 18: "口语题",
         19: "听力题", 20: "共用选项题", 21: "测评题", 22: "口语测评题", 23: "钟表题", 24: "选词填空", 25: "选做题",
         26: "写作题"}
_ALIASES = {"其他": "其它", "完形填空": "完型填空", "共用选项题": "共用选项", "选做题": "选做"}
# Which editor offers which type (from each editor's type menu).
SURFACES = {"work": set(TYPES.values()) - {25}, "exam": set(TYPES.values()) - {22, 23}, "bank": set(TYPES.values()),
            "quiz": {0, 1, 2, 3, 4}}   # 随堂练习 editor: 单选 多选 填空 判断 简答
SUBJECTIVE = {4, 5, 6, 7, 8, 18}
BLANKS = {2, 9}
COMPOSITE = {14, 15, 19, 25}
CHILD_TYPES = {0, 1, 2, 3, 4}

LANGS = {"C": 1, "C#": 2, "Java": 3, "VB.NET": 4, "Python2": 5, "Golang": 6, "PHP": 8, "Bash": 11,
         "Python3.6.9": 16, "C++": 17, "JavaScript": 19, "R": 20, "HTML": 21, "Python3.12.12": 22, "Octave": 26}
_LANG_ALIASES = {"python": "Python3.12.12", "python3": "Python3.12.12", "py": "Python3.12.12", "python3.12": "Python3.12.12",
                 "python3.6": "Python3.6.9", "python2": "Python2", "c": "C", "cpp": "C++", "c++": "C++", "java": "Java",
                 "js": "JavaScript", "javascript": "JavaScript", "go": "Golang", "golang": "Golang", "bash": "Bash",
                 "shell": "Bash", "php": "PHP", "r": "R", "html": "HTML", "c#": "C#", "csharp": "C#", "octave": "Octave",
                 "vb": "VB.NET", "vb.net": "VB.NET"}
ORAL_LANGS = {"英语": "en", "汉语": "cn", "普通话": "cn", "法语": "fr", "日语": "jp", "西班牙语": "sp", "韩语": "kr",
              "德语": "de", "俄语": "ru"}
CLOCK_MODES = {"认读": ("0", "选择钟面表示的时刻"), "拨针": ("1", "根据所表示的时刻，通过拨动分针，将时间拨动到正确位置")}
_BLANK_MARK = re.compile(r"##(\d+)##")
_UNDERLINE = '<span style="text-decoration: underline;">&nbsp;&nbsp;&nbsp;\\1&nbsp;&nbsp;&nbsp;</span>'


def jdump(v: Any) -> str:
    """JSON the way the pages' JSON.stringify writes it."""
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def p(text: Any) -> str:
    """Plain text -> editor paragraphs; empty text stays empty."""
    s = str(text if text is not None else "").strip()
    return "".join(f"<p>{_h.escape(line)}</p>" for line in s.split("\n") if line.strip()) if s else ""


def num(x: float) -> int | float:
    return int(x) if float(x).is_integer() else float(x)


def letters(n: int) -> list[str]:
    return [chr(65 + i) for i in range(n)]


def type_id(name: Any) -> int:
    s = str(name or "").strip()
    s = _ALIASES.get(s, s)
    if s not in TYPES and s.endswith("题"):
        s = _ALIASES.get(s[:-1], s[:-1])
    if s not in TYPES:
        raise XxtError(f"未知题型「{name}」。可用：{'、'.join(TYPES)}")
    return TYPES[s]


@dataclass
class Q:
    t: int
    stem: str                       # stem as given (plain text; may contain ##n## marks)
    score: float
    analysis: str = ""
    options: list[str] = field(default_factory=list)   # html per option
    answer: Any = None              # normalized per type
    children: list["Q"] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return LABEL[self.t]

    @property
    def stem_html(self) -> str:
        h = p(self.stem)
        return _BLANK_MARK.sub(_UNDERLINE, h) if self.t in (14, 24) else h


def _score(v: Any, where: str) -> float:
    s = float(5 if v in (None, "") else v)   # an explicit 0 must be rejected, not defaulted
    if not 0 < s <= 100:
        raise XxtError(f"{where}分值必须在 0–100 之间。")
    return s


def _opts(q: dict, where: str, lo: int = 2, hi: int = 26, key: str = "options") -> list[str]:
    o = q.get(key) or []
    if not isinstance(o, list) or not lo <= len(o) <= hi or any(not str(x).strip() for x in o):
        raise XxtError(f"{where}需要 {lo}–{hi} 个非空选项（{key}）。")
    if len({str(x).strip() for x in o}) != len(o):
        raise XxtError(f"{where}选项不能相同。")
    return [str(x).strip() for x in o]


def _letter_list(v: Any, n: int, where: str, count: int | None = None, unique: bool = False) -> list[str]:
    seq = list(v) if isinstance(v, (list, tuple)) else list(str(v or "").replace(",", "").replace(" ", ""))
    seq = [str(x).strip().upper() for x in seq]
    ok = set(letters(n))
    if not seq or any(x not in ok for x in seq):
        raise XxtError(f"{where}答案必须是 {letters(n)[0]}–{letters(n)[-1]} 中的字母。")
    if count is not None and len(seq) != count:
        raise XxtError(f"{where}答案需要 {count} 个字母，实际 {len(seq)} 个。")
    if unique and len(set(seq)) != len(seq):
        raise XxtError(f"{where}答案字母不能重复。")
    return seq


def _tf(v: Any, where: str) -> bool:
    if v in ("对", "正确", "true", "True", True, "√"):
        return True
    if v in ("错", "错误", "false", "False", False, "×"):
        return False
    raise XxtError(f"{where}判断答案必须是 对 或 错。")


def _marks(stem: str, where: str) -> int:
    nums = [int(m) for m in _BLANK_MARK.findall(stem)]
    if not nums or sorted(nums) != list(range(1, len(nums) + 1)):
        raise XxtError(f"{where}题干要用 ##1##、##2##… 依次标出空位。")
    return len(nums)


def normalize(raw: dict, surface: str, where: str = "", child_of: int | None = None) -> Q:
    q = dict(raw or {})
    t = type_id(q.get("type"))
    if child_of is not None:
        allowed = {0} if child_of == 14 else CHILD_TYPES
        if t not in allowed:
            raise XxtError(f"{where}小题只能是：{'、'.join(LABEL[x] for x in sorted(allowed))}。")
    elif t not in SURFACES[surface]:
        raise XxtError(f"{where}「{LABEL[t]}」在{ {'work': '作业', 'exam': '试卷', 'bank': '题库', 'quiz': '随堂练习'}[surface] }编辑器里不可用。")
    stem = str(q.get("stem") or "").strip()
    if not stem and t != 23 and not (child_of == 14):
        raise XxtError(f"{where}题干为空。")
    out = Q(t=t, stem=stem, score=_score(q.get("score"), where), analysis=str(q.get("analysis") or ""))
    if t in (0, 1):
        o = _opts(q, where)
        out.options = [p(x) for x in o]
        ans = _letter_list(q.get("answer"), len(o), where, unique=True)
        if t == 0 and len(ans) != 1:
            raise XxtError(f"{where}单选题只能有一个答案。")
        if t == 1 and len(ans) < 2:
            raise XxtError(f"{where}多选题至少两个正确答案。")
        out.answer = sorted(ans)
    elif t in BLANKS:
        a = q.get("answer")
        blanks = a if isinstance(a, list) else [a]
        if not blanks or any(not str(x or "").strip() for x in blanks) or len(blanks) > 50:
            raise XxtError(f"{where}填空答案为空（answer 可以是字符串或每空一项的列表，最多 50 空）。")
        out.answer = [p(x) for x in blanks]
    elif t == 3:
        out.answer = _tf(q.get("answer"), where)
    elif t in SUBJECTIVE:
        out.answer = p(q.get("answer"))
    elif t == 11:
        left, right = _opts(q, where, 1, 26, "left"), _opts(q, where, 1, 26, "right")
        out.extra = {"left": [p(x) for x in left], "right": [p(x) for x in right]}
        out.answer = _letter_list(q.get("answer"), len(right), where, count=len(left))
    elif t == 13:
        o = _opts(q, where)
        out.options = [p(x) for x in o]
        out.answer = "".join(_letter_list(q.get("answer"), len(o), where, count=len(o), unique=True))
    elif t in COMPOSITE:
        kids = q.get("children") or []
        if not isinstance(kids, list) or not 1 <= len(kids) <= 50:
            raise XxtError(f"{where}需要 1–50 道小题（children）。")
        out.children = [normalize(k, surface, f"{where}第 {j} 小题：", child_of=t) for j, k in enumerate(kids, 1)]
        if t == 14:
            if _marks(stem, where) != len(kids):
                raise XxtError(f"{where}题干中空的数量必须等于小题数量。")
        if t == 25:
            n = int(q.get("optional_num") or 0)
            if not 1 <= n <= len(kids):
                raise XxtError(f"{where}选做题需要 optional_num（任选几题），范围 1–{len(kids)}。")
            out.extra["optional_num"] = n
            for k in out.children:          # the editors give every optional child the full score
                k.score = out.score
        else:
            out.score = sum(k.score for k in out.children)
    elif t == 17:
        lang = str(q.get("language") or "").strip()
        lang = _LANG_ALIASES.get(lang.lower(), lang)
        if lang not in LANGS:
            raise XxtError(f"{where}程序语言必须是：{'、'.join(LANGS)}。")
        code = str(q.get("answer") or q.get("code") or "")
        if not code.strip():
            raise XxtError(f"{where}程序题需要参考代码（answer）。")
        review = {"手动": "1", "教师手动批阅": "1", "自动": "0", "系统自动批阅": "0"}.get(str(q.get("review") or "手动"))
        if review is None:
            raise XxtError(f"{where}批阅方式只能是 手动 或 自动。")
        cases = q.get("cases") or []
        if lang != "HTML":
            if not isinstance(cases, list) or not cases or any(not isinstance(c, dict) for c in cases):
                raise XxtError(f"{where}程序题需要测试用例 cases：[{{input, output}}]。")
            if review == "0" and any(not str(c.get("output") or "") for c in cases):
                raise XxtError(f"{where}自动批阅时每个用例都要有输出。")
        out.extra = {"lang": lang, "code": code, "review": review, "template": str(q.get("template") or ""),
                     "cases": [(str(c.get("input") or ""), str(c.get("output") or "")) for c in cases]}
    elif t == 20:
        o = _opts(q, where)
        items = _opts(q, where, 1, 50, "items")
        out.options = [p(x) for x in o]
        out.extra["items"] = [p(x) for x in items]
        out.answer = _letter_list(q.get("answer"), len(o), where, count=len(items))
    elif t == 21:
        o = _opts(q, where)
        sc = q.get("option_scores") or []
        if not isinstance(sc, list) or len(sc) != len(o):
            raise XxtError(f"{where}测评题需要与选项一一对应的 option_scores。")
        sel = int(q.get("select_num") or 1)
        if not 1 <= sel <= len(o):
            raise XxtError(f"{where}select_num 必须在 1–{len(o)} 之间。")
        out.options = [p(x) for x in o]
        out.extra = {"scores": [num(float(x)) for x in sc], "select_num": sel}
    elif t == 22:
        text = str(q.get("read_text") or q.get("answer") or "").strip()
        lang = ORAL_LANGS.get(str(q.get("language") or "英语"), str(q.get("language") or ""))
        if not text or lang not in ORAL_LANGS.values():
            raise XxtError(f"{where}口语测评需要 read_text（朗读文本）和语言（{'、'.join(ORAL_LANGS)}）。")
        out.extra = {"read_text": text, "lang": lang, "auto": "1" if q.get("auto_mark", True) else "",
                     "hide": "1" if q.get("hide_read_text") else ""}
    elif t == 23:
        mode = CLOCK_MODES.get(str(q.get("mode") or "认读"))
        clocks = q.get("clocks") or []
        if mode is None:
            raise XxtError(f"{where}钟表题 mode 只能是 认读 或 拨针。")
        if not isinstance(clocks, list) or not 1 <= len(clocks) <= 20:
            raise XxtError(f"{where}钟表题需要 clocks：[{{period:上午|下午, hour, minute}}]。")
        data = []
        for c in clocks:
            per, h, m = str(c.get("period") or ""), int(c.get("hour", -1)), int(c.get("minute", -1))
            if per not in ("上午", "下午") or not 1 <= h <= 12 or not 0 <= m <= 59:
                raise XxtError(f"{where}钟表时刻无效：时段 上午/下午，时 1–12，分 0–59。")
            data.append({"period": per, "hour": str(h), "minute": str(m)})
        out.extra = {"mode": mode, "clocks": data}
    elif t == 24:
        words = _opts(q, where, 2, 26)
        n = _marks(stem, where)
        out.options = words                  # the page stores the words as plain text
        out.answer = _letter_list(q.get("answer"), len(words), where, count=n)
    elif t == 26:
        essay = str(q.get("answer") or q.get("model_essay") or "")
        mn = int(q.get("min_words") or 0)
        if mn < 0 or mn > 15000:
            raise XxtError(f"{where}min_words 范围 0–15000。")
        out.extra = {"essay": essay.strip(), "min_words": mn}
    return out


def normalize_list(questions: list[dict], surface: str) -> list[Q]:
    if not questions:
        raise XxtError("至少需要一道题。")
    if len(questions) > 200:
        raise XxtError("一次最多 200 道题。")
    return [normalize(q, surface, f"第 {i} 题：") for i, q in enumerate(questions, 1)]


def summary(q: Q) -> dict:
    """Dry-run view: what will be created, without echoing reference answers back as data to act on."""
    d = {"type": q.label, "stem": q.stem[:200], "score": num(q.score)}
    if q.options:
        d["options"] = len(q.options)
    if q.children:
        d["children"] = [summary(k) for k in q.children]
    return d


# ---------------------------------------------------------------- answer JSON
def _choice_answer(q: Q) -> list[dict]:
    out = []
    for L, o in zip(letters(len(q.options)), q.options):
        out.append({"content": o, "isanswer": True, "name": L} if L in q.answer else {"content": o, "name": L})
    return out


def _child(q: Q, parent: int) -> dict:
    s = num(q.score)
    if q.t in (0, 1):
        data: dict = {"score": s, "content": q.stem_html, "answer": _choice_answer(q)}
        if parent == 14:
            data = {"score": s, "answer": _choice_answer(q)}
    elif q.t == 2:
        data = {"score": s, "content": q.stem_html,
                "answer": [{"content": b, "name": str(i)} for i, b in enumerate(q.answer, 1)], "isMutex": 0, "isSubject": 0}
    elif q.t == 3:
        data = {"score": s, "content": q.stem_html, "answer": jdump([{"answer": q.answer}])}
    else:
        data = {"score": s, "content": q.stem_html, "answer": jdump([{"answer": q.answer}])}
    item: dict = {"id": str(uuid.uuid4()), "type": q.t}
    if parent != 14:
        item["typeId"] = 0
    item.update({"name": q.label, "topicIds": [], "targetData": "", "data": data})
    return item


def _wrap_code(code: str) -> str:
    return ('<pre class="line-numbers hover newProcedure"><code class="language-plain" lang="Plain Text">'
            f"{_h.escape(code, quote=False)}</code></pre>")


def answer_json(q: Q) -> str | None:
    t = q.t
    if t == 11:
        L, R = q.extra["left"], q.extra["right"]
        return jdump([[{"name": i, "content": x} for i, x in enumerate(L, 1)],
                      [{"name": n, "content": x} for n, x in zip(letters(len(R)), R)],
                      [{"name": i, "content": a} for i, a in enumerate(q.answer, 1)]])
    if t == 13:
        return jdump([[{"name": n, "content": x} for n, x in zip(letters(len(q.options)), q.options)], {"answer": q.answer}])
    if t in COMPOSITE:
        return jdump([_child(k, t) for k in q.children])
    if t == 17:
        e = q.extra
        cases = e["cases"]
        ex = ([{"stdin": "", "stdout": "", "memory": 65536, "time": 10000, "answer": ""}] if e["lang"] == "HTML"
              else [{"stdin": i, "stdout": o, "memory": 65536, "time": 10000} for i, o in cases])
        ins, outs = "---".join(i for i, _ in cases), "---".join(o for _, o in cases)
        return jdump([{"answerInput": ins, "answerInputText": ins, "answer": outs, "answerText": outs,
                       "answerCode": _wrap_code(e["code"]), "languageName": e["lang"], "languageIndex": str(LANGS[e["lang"]]),
                       "exampleArr": ex, "procedureReviewMode": e["review"],
                       "preparedCode": [{"codeNum": str(LANGS[e["lang"]]), "codeName": e["lang"], "code": e["template"]}]}])
    if t == 20:
        items = q.extra["items"]
        return jdump([{"title": f"(1)-({len(items)}) 题共用备选答案：", "frontDescribe": q.stem_html},
                      [{"name": n, "content": x} for n, x in zip(letters(len(q.options)), q.options)],
                      [{"name": i, "content": x} for i, x in enumerate(items, 1)],
                      [{"name": i, "content": a} for i, a in enumerate(q.answer, 1)]])
    if t == 21:
        return jdump([{"selectNum": q.extra["select_num"]},
                      [{"name": n, "content": x, "score": s}
                       for n, x, s in zip(letters(len(q.options)), q.options, q.extra["scores"])]])
    if t == 22:
        e = q.extra
        return jdump([{"readText": e["read_text"], "language": e["lang"], "slack": "2", "autoMark": e["auto"],
                       "hideReadText": e["hide"]}])
    if t == 23:
        return jdump([{"type": q.extra["mode"][0], "data": q.extra["clocks"]}])
    if t == 24:
        return jdump([[{"name": n, "content": x} for n, x in zip(letters(len(q.options)), q.options)],
                      [{"name": i, "content": a} for i, a in enumerate(q.answer, 1)]])
    if t == 26:
        mn = q.extra["min_words"]
        return jdump([{"answer": q.extra["essay"], "grade": "cet4", "wordMinNum": str(mn) if mn else 0, "wordnum": "15000"}])
    return None


def content_html(q: Q) -> str:
    return q.extra["mode"][1] if q.t == 23 else q.stem_html


# ---------------------------------------------------------------- per-surface type fields
def type_fields(q: Q, surface: str) -> list[tuple[str, Any]]:
    """Type-specific form fields for work/toEditWorkQuestion and qbank/add_question."""
    t, f = q.t, []
    if t == 0:
        f += [("defAnswer", q.answer[0])] + list(zip(letters(len(q.options)), q.options))
    elif t == 1:
        f += [("defAnswer", a) for a in q.answer] + list(zip(letters(len(q.options)), q.options))
    elif t in BLANKS:
        joined = "★".join(q.answer)
        f += [(str(i), b) for i, b in enumerate(q.answer, 1)] + [("isMutex", 0)]
        f += [("wrapAnswer", joined), ("blankSubject", 0)] if surface == "work" else [("answer", joined), ("blankSubject", "")]
    elif t == 3:
        f += [("answerForTF", "true" if q.answer else "false")]
    elif t in SUBJECTIVE:
        f += [("answer", q.answer), ("saveScorePoints", "")] + ([("wordMinNum", ""), ("wordnum", "")] if surface == "work" else [])
    elif t == 11:
        f += [(str(i), x) for i, x in enumerate(q.extra["left"], 1)] + list(zip(letters(len(q.extra["right"])), q.extra["right"]))
    elif t in (13, 21, 24):
        f += list(zip(letters(len(q.options)), q.options))
        if t == 21:
            f += [("selectMaxNum", len(q.options))]
    elif t == 17:
        f += [("runProcedureFlag", "true"), ("isCheckSave", 0), ("autoScore", 0), ("timeLimit", 2000), ("memoryLimit", 262144)]
    elif t == 20:
        f += list(zip(letters(len(q.options)), q.options)) + [(str(i), x) for i, x in enumerate(q.extra["items"], 1)]
    elif t == 22:
        f += [("readText", q.extra["read_text"])]
    elif t == 23:
        f += [("clockType", q.extra["mode"][0])]
    elif t == 26:
        f += [("subject", 0), ("publishSource", 2), ("wordMinNum", q.extra["min_words"] or ""), ("wordnum", "")]
    elif t in COMPOSITE and surface == "bank":
        f += [("typeField", t), ("score", num(q.score))] + ([("optionalNum", q.extra["optional_num"])] if t == 25 else [])
    a = answer_json(q)
    if a is not None:
        f.append(("answer", a))
    return f


EXAM_ENDPOINT = {0: "editPaperSingleChoiceV2", 1: "editPaperMultipleChoiceV2", 2: "editPaperBlankFillingV2",
                 9: "editPaperBlankFillingV2", 3: "editPaperTrueFalseV2", 11: "editPaperConnectionLine",
                 13: "editPaperSortQues", 17: "editPaperProcedure", 20: "editBType", 21: "editEvaluation",
                 24: "editFillinBlanks", 26: "editPaperAnswerV2",
                 **{t: "editPaperAnswerV2" for t in SUBJECTIVE}, **{t: "editReadComPrehensionClozeText" for t in COMPOSITE}}


def exam_fields(q: Q) -> list[tuple[str, Any]]:
    """Type-specific fields for the paper editor's per-type save endpoint."""
    t, f = q.t, []
    if t in (0, 1):
        opts = dict(zip(letters(len(q.options)), q.options))
        f += [("defAnswer", ",".join(q.answer))] + [(L, opts.get(L, "")) for L in letters(26)]
    elif t in BLANKS:
        f += [("answer", "★".join(q.answer)), ("isMutex", 0), ("blankSubject", 0), ("standardId", 0)]
    elif t == 3:
        f += [("answer", "true" if q.answer else "false")]
    elif t in SUBJECTIVE:
        f += [("answer", q.answer), ("standardId", 0), ("wordMinNum", 0), ("wordnum", 0), ("scorePoints", ""),
              ("useAi", 0), ("autoScore", 0), ("promptId", -1)]
    elif t in COMPOSITE:
        f += [("optionalNum", q.extra.get("optional_num", 0)), ("standardId", 0), ("questionNumberMode", 0)]
    elif t in (11, 20, 24):
        f += [("questionNumberMode", 0)]
    elif t in (17, 26):
        f += [("standardId", 0)]
    a = answer_json(q)
    if a is not None:
        f.append(("answer", a))
    return f
