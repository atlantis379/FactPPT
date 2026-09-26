"""Parse a textbook's own heading hierarchy out of OCR'd paragraph text.

The problem
-----------
The line merger glues headings into the paragraph that follows them:

    第二节细菌性肺炎一、肺炎链球菌肺炎肺炎链球菌肺炎（Streptococcal...）是由...

so the structure the book actually declares has to be recovered by splitting those
markers back out. Ordering is preserved exactly: this module never sorts, samples
or reorders -- a teaching deck must follow the book.

Heading vocabulary observed in the scanned textbook
---------------------------------------------------
    第X章 / 第X节            structural
    一、二、三、              numbered sub-section
    （一）（二）              numbered item
    1. 2. 3.                 enumerated item
    【主题】                  inline topic marker (流行病学 / 病因和发病机制 / 治疗 ...)

The safest markers are used to define structure; the noisier ones (``1.``) are only
recognised as headings when they follow a structural marker, because decimals and
dosages otherwise look identical.
"""
from __future__ import annotations

import re

#: 第X节 / 第X章 -- emitted as their own node
_CHAPTER = re.compile(r"第[一二三四五六七八九十百]+章")
_SECTION = re.compile(r"第[一二三四五六七八九十百]+节")
#: 一、二、三、 -- only at the start of a block, or right after a section marker
_CN_NUM = re.compile(r"(?<![一二三四五六七八九十])[一二三四五六七八九十]{1,3}、")
#: （一）（二）
_PAREN_NUM = re.compile(r"[（(][一二三四五六七八九十]{1,3}[）)]")
#: 【主题】
_TOPIC = re.compile(r"【([^】]{1,24})】")

#: characters that end a heading name
_NAME_STOP = "（(，。；：、,;:）)0123456789【】"

LEVELS = {"chapter": 0, "section": 1, "topic": 2, "cn": 3, "paren": 4, "item": 5}


def _leading_name(remainder: str, max_len: int = 24) -> tuple[str, str]:
    """Split a heading name from the body that follows it.

    Three shapes occur in this textbook, all handled here:

    * the heading is repeated as the first words of its body
      ("一、肺炎链球菌肺炎肺炎链球菌肺炎（...") -> a doubled prefix identifies the
      name exactly;
    * the body's first word repeats the TAIL of the heading
      ("第一节肺炎概述肺炎（pneumonia）...") -> "肺炎概述肺炎" truncates to
      "肺炎概述" because "肺炎" both ends the name and starts it;
    * neither -> the name ends at the first strong delimiter.
    """
    remainder = _LEAD_NOISE.sub("", remainder or "")
    limit = min(max_len, len(remainder) // 2)
    for length in range(limit, 1, -1):
        if remainder[:length] == remainder[length:2 * length]:
            return remainder[:length], remainder[2 * length:]
    match = re.match(r"^([^%s]{2,20})" % re.escape(_NAME_STOP), remainder)
    if match:
        name = match.group(1)
        rest = remainder[len(name):]
        for cut in range(2, len(name) - 1):
            tail = name[cut:]
            if len(tail) >= 2 and name.startswith(tail):
                name = name[:cut]
                rest = remainder[len(name):]
                break
        return name, rest
    return "", remainder


#: leading Chinese numerals, optional enumeration punctuation, and OCR border junk
_LEAD_NOISE = re.compile(r"^[|｜丨\-—_=~\s]*[一二三四五六七八九十]{0,3}[、.．]?\s*")


def _markers(text: str) -> list[tuple[int, int, str, str]]:
    """(start, end, kind, marker) for every STRUCTURAL marker in the text.

    Two guards keep prose from being mistaken for structure:

    * ``一、`` is accepted at the start of a block, or close after a section
      marker (the textbook writes "第二节细菌性肺炎一、肺炎链球菌肺炎"),
      but not deep inside a paragraph where "一、二两组" occurs naturally;
    * ``第X章`` preceded by a digit is a running head glued to a page number
      ("59第六章肺部感染性疾病"), not a new chapter.
    """
    found: list[tuple[int, int, str, str]] = []
    section_spans = [(m.start(), m.end()) for m in _SECTION.finditer(text)]
    section_ends = {end for _s, end in section_spans}
    section_horizon = (max(section_ends) + 12) if section_ends else -1
    for match in _CHAPTER.finditer(text):
        if match.start() > 0 and text[match.start() - 1].isdigit():
            continue          # running head glued to a page number
        found.append((match.start(), match.end(), "chapter", match.group(0)))
    for match in _SECTION.finditer(text):
        found.append((match.start(), match.end(), "section", match.group(0)))
    for match in _TOPIC.finditer(text):
        found.append((match.start(), match.end(), "topic", match.group(0)))
    for match in _CN_NUM.finditer(text):
        if match.start() == 0 or match.start() in section_ends or \
                match.start() <= section_horizon:
            found.append((match.start(), match.end(), "cn", match.group(0)))
    for match in _PAREN_NUM.finditer(text):
        found.append((match.start(), match.end(), "paren", match.group(0)))
    found.sort()
    cleaned: list[tuple[int, int, str, str]] = []
    for item in found:
        if cleaned and item[0] < cleaned[-1][1]:
            continue
        cleaned.append(item)
    return cleaned


def parse(blocks: list[dict]) -> dict:
    """Build the ordered outline from OCR blocks.

    Returns ``{"nodes": [...], "counts": {...}}``; each node is::

        {"level": int, "kind": str, "title": str, "marker": str,
         "paragraphs": [str], "page": int, "order": int}

    Document order is preserved: nodes are appended as encountered.
    """
    nodes: list[dict] = []
    counts: dict[str, int] = {}
    current: dict | None = None

    def open_node(kind: str, marker: str, title: str, page) -> dict:
        nonlocal current
        node = {"level": LEVELS[kind], "kind": kind, "title": title or marker,
                "marker": marker, "paragraphs": [], "page": page, "order": len(nodes)}
        nodes.append(node)
        counts[kind] = counts.get(kind, 0) + 1
        current = node
        return node

    def add_text(text: str, page) -> None:
        nonlocal current
        if not text:
            return
        if current is None:
            open_node("chapter", "", "（未标注章节）", page)
        current["paragraphs"].append(text)

    for block in blocks:
        text = (block.get("text") or "").strip()
        page = block.get("page")
        if not text:
            continue
        marks = _markers(text)
        if not marks:
            add_text(text, page)
            continue
        if marks[0][0] > 0:
            add_text(text[:marks[0][0]].strip(), page)
        for index, (_start, end, kind, marker) in enumerate(marks):
            segment_end = marks[index + 1][0] if index + 1 < len(marks) else len(text)
            segment = text[end:segment_end].strip()
            if kind == "topic":
                # 【主题】 introduces its content inline: the segment IS the content
                node = open_node("topic", marker, marker[1:-1], page)
                if segment:
                    node["paragraphs"].append(segment)
                continue
            name, rest = _leading_name(segment)
            node = open_node(kind, marker, name or marker, page)
            if rest.strip():
                node["paragraphs"].append(rest.strip())
    return {"nodes": nodes, "counts": counts}


def outline_markdown(outline: dict) -> str:
    lines = []
    for node in outline["nodes"]:
        indent = "  " * node["level"]
        lines.append("{}- [{}] {}  (p{})".format(indent, node["kind"], node["title"], node["page"]))
    return "\n".join(lines)


def section_tree(outline: dict) -> list[dict]:
    """Group the flat node list into sections with their topics and items."""
    sections: list[dict] = []
    stack: dict[int, dict] = {}

    def attach(node: dict) -> dict:
        entry = {"kind": node["kind"], "title": node["title"], "page": node["page"],
                 "paragraphs": list(node["paragraphs"]), "children": [],
                 "level": node["level"]}
        depth = node["level"]
        for higher in range(depth - 1, -1, -1):
            if higher in stack:
                stack[higher]["children"].append(entry)
                break
        else:
            sections.append(entry)
        stack[depth] = entry
        for deeper in [d for d in stack if d > depth]:
            del stack[deeper]
        return entry

    for node in outline["nodes"]:
        attach(node)
    return sections
