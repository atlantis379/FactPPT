"""Text a slide states as true.  There are exactly two ways onto a slide, and neither is a check of written prose.

A first version let the model write assertions and headlines freely, then tested them against the cited sentence:
is the digit in there, is the modality word in there.  A test over a bag of tokens has no idea where a token sits,
so 「不建议使用」→「建议使用」, 「超过70%」→「不足70%」and a swapped 70/30 all passed — and a word list cannot be
finished, because the failure is the method.  So stating something is no longer writing it:

  excerpt     ``{"fact": id}`` or ``{"fact": id, "show": "..."}``: the sentence, or an in-order piece of it, through
              the same gate as the fact store (``facts.verify``): dropping a negation, qualifier or number is refused.
  derivation  ``{"derived": "...", "from": [ids]}``: a synthesis across sentences.  It is not judged here at all.  It
              stays pending until a person confirms this exact text over these exact sentences (``digest``), and a
              pending line cannot be drawn.  Changing a word, or the source, voids the confirmation.

Nothing here reports text as verified.  Code can refuse; only a person passes a derivation.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping

from .lexicon import critical_tokens, dropped_blockers, extractive


class ShownError(ValueError):
    """The text cannot go on a slide."""


def digest(text: str, evidence: list[str], facts: Mapping[str, dict]) -> str:
    """What a person confirms: these words over these sentences, so neither can change afterwards."""
    body = json.dumps([text, [[f, facts[f]["quote"]] for f in evidence]], ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def resolve(ref, facts: Mapping[str, dict], where: str, confirmed: Collection[str] = (),
            error: type[ShownError] = ShownError) -> dict:
    """A reference → the text it puts on the slide.  A bare string is refused: nothing states by being written."""
    if not isinstance(ref, Mapping):
        raise error(f"{where} 须为引用 {{\"fact\": id}}（可加 \"show\" 取原句节选）或 {{\"derived\": 综合句, \"from\": [id]}}："
                    f"断言不能直接写成文字，主题名放 section")
    if "derived" in ref:
        return _derived(ref, facts, where, confirmed, error)
    fid = ref.get("fact")
    if not isinstance(fid, str) or fid not in facts:
        raise error(f"{where} 引用了不存在的句子：{fid}")
    quote = facts[fid]["quote"]
    show = ref.get("show")
    if show is None:
        return {"kind": "excerpt", "text": quote, "facts": [fid], "pending": False}
    if not isinstance(show, str) or not show.strip() or "\n" in show:
        raise error(f"{where} 的 show 须为一行文字")
    show = show.strip()
    ok, dropped = extractive(show, quote)
    if not ok:
        raise error(f"{where} 的 show「{show}」不是这句的按序节选：改写要走 derived，由人确认")
    lost = dropped_blockers(dropped)
    if lost:
        raise error(f"{where} 的 show 删掉了「{'、'.join(lost)}」，这些词会改变原句的意思：保留它们，或换一句")
    extra = critical_tokens(show) - critical_tokens(quote)
    if extra:
        raise error(f"{where} 的 show 含原句没有的关键项：{'、'.join(sorted(extra))}")
    return {"kind": "excerpt", "text": show, "facts": [fid], "pending": False}


def _derived(ref, facts, where, confirmed, error) -> dict:
    text, ids = ref.get("derived"), ref.get("from")
    if not isinstance(text, str) or not text.strip() or "\n" in text:
        raise error(f"{where} 的 derived 须为一行文字")
    if not isinstance(ids, list) or not ids:
        raise error(f"{where} 须用 from 列出它综合的句子")
    for fid in ids:
        if not isinstance(fid, str) or fid not in facts:
            raise error(f"{where} 引用了不存在的句子：{fid}")
    text = text.strip()
    d = digest(text, ids, facts)
    return {"kind": "derivation", "text": text, "facts": list(ids), "digest": d, "pending": d not in confirmed}
