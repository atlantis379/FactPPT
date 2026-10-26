"""Display fact gate for one original span.

Admission compares on-screen numbers, doses, and drug names to slices of the
original span. ``canon`` may fold whitespace between a digit and a unit. It
does not delete whitespace between digits, so ``10 0 mg`` cannot become
``100 mg``.

Dropping a comparison, population, time window, or quantifier is not
ACCEPTED unless the caller names every dropped class and supplies a human
gate that covers those same classes. Display ACCEPTED is not graph APPROVED.

Slot pairing calls this gate from ``factdeck.slots``. Summary slimming
calls it from ``factdeck.summary`` and does not rewrite a string the gate
rejects. ``dangling_half_sentence`` is the display check for a clip that
is not a full admitted slice. Card-wall geometry lives on the deck mainline.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from factdeck.lexicon import (
    CONTRAST_PHRASES,
    DERIVATION_BY_KIND,
    DERIVATIONS,
    DOSE_UNIT_ALTERNATION,
    DRUGS,
    ISSUE_BY_DERIVATION,
    POPULATION_PHRASES,
    QUANTIFIER_PHRASES,
    TIME_PATTERNS,
)

_FOLD = str.maketrans(
    {
        "０": "0",
        "１": "1",
        "２": "2",
        "３": "3",
        "４": "4",
        "５": "5",
        "６": "6",
        "７": "7",
        "８": "8",
        "９": "9",
        "％": "%",
        "µ": "μ",
        "\u3000": " ",
        "．": ".",
        "＞": ">",
        "＜": "<",
    }
)

_DOSE_RE = re.compile(
    r"(?<![0-9０-９.．])"
    r"(?P<comp>[<>≤≥＞＜])?\s*"
    r"(?P<sign>[-−－])?\s*"
    r"(?P<num>[0-9０-９]+(?:\.[0-9０-９]+)?)"
    r"(?:(?P<range_sep>\s*[-–—~～－−]\s*)"
    r"(?P<range_comp>[<>≤≥＞＜]?\s*)"
    r"(?P<range_num>[0-9０-９]+(?:\.[0-9０-９]+)?))?"
    rf"(?P<unit>\s*(?:{DOSE_UNIT_ALTERNATION})?)",
    re.IGNORECASE,
)

_DRUG_RE = re.compile(
    "|".join(re.escape(name) for name in sorted(DRUGS, key=len, reverse=True)),
    re.IGNORECASE,
)

_QUALIFIER_RES = (
    ("contrast", re.compile("|".join(re.escape(phrase) for phrase in sorted(CONTRAST_PHRASES, key=len, reverse=True)))),
    ("contrast", re.compile(r"从(?=\s*[0-9０-９])")),
    ("contrast", re.compile(r"\bversus\b|\bvs\.?(?!\w)", re.IGNORECASE)),
    ("population", re.compile("|".join(re.escape(phrase) for phrase in sorted(POPULATION_PHRASES, key=len, reverse=True)))),
    ("quantifier", re.compile("|".join(re.escape(phrase) for phrase in sorted(QUANTIFIER_PHRASES, key=len, reverse=True)))),
    ("quantifier", re.compile(r"(?<![大])约(?!定|束)")),
    ("quantifier", re.compile(r"[<>≤≥＞＜]")),
    ("quantifier", re.compile(r"[0-9０-９]+\s*次")),
    *(("time_window", re.compile(pattern)) for pattern in TIME_PATTERNS),
)

_ISSUE_ORDER = (
    "ADDED_CONTENT",
    "CONTRAST_DROPPED",
    "POPULATION_CHANGED",
    "TIME_WINDOW_CHANGED",
    "MISSING_QUALIFIER",
)

_REJECTION_PRIORITY = {
    "NUMERIC_STITCH": 0,
    "NUMERIC_BOUNDARY": 1,
    "NUMERIC_UNIT_MISMATCH": 2,
    "ADDED_CONTENT": 3,
    "VACUOUS_DISPLAY": 4,
    "EMPTY_DISPLAY": 5,
}


@dataclass(frozen=True)
class UnitSlice:
    """One original slice. Offsets index the string passed to the gate."""

    kind: str
    text: str
    start: int
    end: int
    token: str | None = None
    unit: str | None = None
    audit_value: Decimal | None = None
    audit_low: Decimal | None = None
    audit_high: Decimal | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "token": self.token,
            "unit": self.unit,
            "audit_value": _decimal_string(self.audit_value),
            "audit_low": _decimal_string(self.audit_low),
            "audit_high": _decimal_string(self.audit_high),
        }


@dataclass(frozen=True)
class FactGateResult:
    status: str
    reason_code: str
    reason: str
    issues: tuple[str, ...]
    omissions: tuple[str, ...]
    omitted_texts: tuple[str, ...]
    added_texts: tuple[str, ...]
    evidence_slices: tuple[UnitSlice, ...]
    display_slices: tuple[UnitSlice, ...]

    @property
    def gate(self) -> str:
        return "FACT_GATE"

    @property
    def admits_to_approved_graph(self) -> bool:
        """Display admission never writes an Approved Semantic Graph object."""

        return False

    def to_dict(self) -> dict:
        return {
            "gate": self.gate,
            "status": self.status,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "issues": list(self.issues),
            "omissions": list(self.omissions),
            "omitted_texts": list(self.omitted_texts),
            "added_texts": list(self.added_texts),
            "admits_to_approved_graph": self.admits_to_approved_graph,
            "evidence_slices": [item.to_dict() for item in self.evidence_slices],
            "display_slices": [item.to_dict() for item in self.display_slices],
        }


def canon(text: str) -> str:
    """Fold compatible characters and whitespace that is not between digits.

    ``canon("10 0 mg")`` stays ``"10 0mg"``. ``canon("100 mg")`` is
    ``"100mg"``. Containment on this string is not admission.
    """

    normalized = _fold_compatible(text or "")
    # U+E000 is not whitespace. A control sentinel would be deleted by \\s.
    held = re.sub(r"(?<=\d)\s+(?=\d)", "\ue000", normalized)
    folded = re.sub(r"\s+", "", held).replace("\ue000", " ")
    return folded.casefold()


def extract_unit_slices(text: str) -> tuple[UnitSlice, ...]:
    """Return drug, dose, and qualifier slices with original offsets."""

    raw = text or ""
    drugs = _drug_slices(raw)
    drug_spans = [(item.start, item.end) for item in drugs]
    doses = _dose_slices(raw, drug_spans)
    qualifiers = _qualifier_slices(raw)
    slices = [*drugs, *doses, *qualifiers]
    slices.sort(key=lambda item: (item.start, item.end, item.kind))
    return tuple(slices)


def gate_display(
    source_text: str | None,
    display_text: str | None,
    *,
    derivation: str | Sequence[str] | None = None,
    human_gate: Mapping[str, object] | None = None,
) -> FactGateResult:
    """Admit display text only when it is the original slices or a gated omission.

    ``source_text`` must be the original span, including its original
    whitespace. A string that was already whitespace-folded can hide a stitch.
    """

    source = "" if source_text is None else str(source_text)
    display = "" if display_text is None else str(display_text)
    evidence = extract_unit_slices(source)
    if not display.strip():
        return _make("REJECTED", "EMPTY_DISPLAY", set(), (), (), evidence, ())

    shown = extract_unit_slices(display)
    source_doses = [item for item in evidence if item.kind == "dose"]
    reasons = [
        reason
        for dose in shown
        if dose.kind == "dose"
        for reason in (_classify_dose(dose, source_doses, source),)
        if reason
    ]
    extra_drugs = _extra_drugs(evidence, shown)
    if extra_drugs:
        reasons.append("ADDED_CONTENT")
    omitted, added = _qualifier_delta(evidence, shown)
    if added:
        reasons.append("ADDED_CONTENT")

    rejection = _first_rejection(reasons)
    omissions = {DERIVATION_BY_KIND[item.kind] for item in omitted}
    omitted_texts = tuple(dict.fromkeys(item.text for item in omitted))
    added_texts = tuple(dict.fromkeys([* (item.text for item in extra_drugs), *(item.text for item in added)]))
    if rejection:
        return _make("REJECTED", rejection, omissions, omitted_texts, added_texts, evidence, shown)

    if _source_has_facts(evidence) and not _source_has_facts(shown):
        return _make("REJECTED", "VACUOUS_DISPLAY", omissions, omitted_texts, added_texts, evidence, shown)

    if omissions and not _human_covers(omissions, derivation, human_gate):
        return _make("NEEDS_REVIEW", "OMISSION", omissions, omitted_texts, added_texts, evidence, shown)
    if omissions:
        return _make("ACCEPTED", "HUMAN_GATE_OMISSION", omissions, omitted_texts, added_texts, evidence, shown)
    return _make("ACCEPTED", "EXTRACTIVE_FAITHFUL", set(), (), (), evidence, shown)


_SENTENCE_END = re.compile(r"[。！？；\n]")
_SLICE_GAP = re.compile(r"[\s，。、；：:,.．·（）()【】\[\]《》\-—–~～/]*")


def dangling_half_sentence(
    source_text: str | None,
    display_text: str | None,
    gate: FactGateResult | None = None,
) -> bool:
    """True when display is a clipped phrase, not a full admitted slice.

    The whole source span is not a clip. A complete sentence of that span
    is not a clip. A shortening the gate accepts is not a clip when the
    display is exactly the admitted slices and the characters between
    those slices are punctuation. Any other shortening is a half-sentence:
    the caller omits the bullet or the slot instead of showing the fragment.
    """

    display = "" if display_text is None else str(display_text)
    source = "" if source_text is None else str(source_text)
    if not display.strip():
        return False
    folded_display = canon(display)
    folded_source = canon(source)
    if not folded_display or folded_display == folded_source:
        return False
    if folded_display not in folded_source:
        return False
    if _covers_whole_sentences(source, display):
        return False
    decided = gate if gate is not None else gate_display(source, display)
    if decided.status == "ACCEPTED" and _display_is_admitted_slices(display, decided.display_slices):
        return False
    return True


def _covers_whole_sentences(source: str, display: str) -> bool:
    sentences = _sentences(source)
    folded = canon(display)
    if any(folded == canon(sentence) for sentence in sentences):
        return True
    for start in range(len(sentences)):
        joined = ""
        for sentence in sentences[start:]:
            joined += sentence
            if canon(joined) == folded:
                return True
    return False


def _sentences(source: str) -> list[str]:
    sentences = []
    start = 0
    for match in _SENTENCE_END.finditer(source):
        piece = source[start : match.end()].strip()
        if piece:
            sentences.append(piece)
        start = match.end()
    tail = source[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _display_is_admitted_slices(display: str, slices: tuple[UnitSlice, ...]) -> bool:
    if not slices:
        return False
    covered = [False] * len(display)
    for item in slices:
        for index in range(max(0, item.start), min(len(display), item.end)):
            covered[index] = True
    gap = "".join(char for char, done in zip(display, covered) if not done)
    return bool(_SLICE_GAP.fullmatch(gap))


def _make(
    status: str,
    reason_code: str,
    omissions: set[str],
    omitted_texts: tuple[str, ...],
    added_texts: tuple[str, ...],
    evidence: tuple[UnitSlice, ...] | list[UnitSlice],
    shown: tuple[UnitSlice, ...] | list[UnitSlice],
) -> FactGateResult:
    ordered = tuple(sorted(omissions))
    return FactGateResult(
        status=status,
        reason_code=reason_code,
        reason=_reason(reason_code, ordered),
        issues=_issues(reason_code, ordered),
        omissions=ordered,
        omitted_texts=omitted_texts,
        added_texts=added_texts,
        evidence_slices=tuple(evidence),
        display_slices=tuple(shown),
    )


def _reason(reason_code: str, omissions: tuple[str, ...]) -> str:
    listed = "、".join(omissions)
    if reason_code == "EXTRACTIVE_FAITHFUL":
        return "屏上数字、剂量和药名都对应原文字切片，对照、人群、时间和量词仍在屏上。"
    if reason_code == "HUMAN_GATE_OMISSION":
        return f"屏上删除了{listed}，具名派生和人工闸门已覆盖这些删除类。"
    if reason_code == "NUMERIC_STITCH":
        return "空白把分开的数字拼到了一起，屏上的数不是原文字切片。"
    if reason_code == "NUMERIC_BOUNDARY":
        return "屏上的数只是原文字数字的前缀、后缀或区间端点。"
    if reason_code == "NUMERIC_UNIT_MISMATCH":
        return "屏上单位和原文字切片不一致。"
    if reason_code == "EMPTY_DISPLAY":
        return "屏上没有可核对的文字。"
    if reason_code == "VACUOUS_DISPLAY":
        return "屏上没有原文字中的数字、药名或限定语。"
    if reason_code == "ADDED_CONTENT":
        return "屏上出现了原文字切片里没有的数字、药名或限定语。"
    if reason_code == "OMISSION":
        return f"屏上删除了{listed}，没有同时给出覆盖这些类的具名派生和人工闸门。"
    return reason_code


def _issues(reason_code: str, omissions: tuple[str, ...]) -> tuple[str, ...]:
    found = set(ISSUE_BY_DERIVATION[name] for name in omissions)
    if reason_code in {"NUMERIC_STITCH", "NUMERIC_BOUNDARY", "NUMERIC_UNIT_MISMATCH", "ADDED_CONTENT"}:
        found.add("ADDED_CONTENT")
    return tuple(item for item in _ISSUE_ORDER if item in found)


def _first_rejection(reasons: list[str]) -> str | None:
    if not reasons:
        return None
    return min(reasons, key=lambda item: _REJECTION_PRIORITY.get(item, 99))


def _fold_compatible(text: str) -> str:
    return text.translate(_FOLD)


def _ascii_digits(number: str) -> str:
    return number.translate(_FOLD)


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _norm_unit(unit: str | None) -> str:
    text = re.sub(r"\s+", "", unit or "")
    if not text:
        return ""
    text = text.replace("％", "%").replace("µ", "μ")
    folded = text.casefold()
    if folded.startswith("个细胞/"):
        return "个细胞/μl"
    if folded.startswith("个/"):
        return "个/μl"
    aliases = {
        "ug": "μg",
        "μg": "μg",
        "mg": "mg",
        "mg/kg": "mg/kg",
        "ml": "ml",
        "iu": "iu",
        "%": "%",
    }
    return aliases.get(folded, text)


def _drug_slices(text: str) -> list[UnitSlice]:
    return [
        UnitSlice("drug", match.group(0), match.start(), match.end())
        for match in _DRUG_RE.finditer(text)
    ]


def _dose_slices(text: str, blocked: list[tuple[int, int]]) -> list[UnitSlice]:
    slices = []
    for match in _DOSE_RE.finditer(text):
        raw = match.group(0)
        lead = len(raw) - len(raw.lstrip())
        trail = len(raw) - len(raw.rstrip())
        start = match.start() + lead
        end = match.end() - trail
        snippet = raw.strip()
        if not snippet or _overlaps(start, end, blocked):
            continue
        number = _ascii_digits(match.group("num"))
        range_number = match.group("range_num")
        range_ascii = _ascii_digits(range_number) if range_number else None
        sign = bool(match.group("sign"))
        token = f"{number}-{range_ascii}" if range_ascii else number
        if sign:
            token = f"-{token}"
        unit = _norm_unit(match.group("unit"))
        audit_value = None
        audit_low = None
        audit_high = None
        if range_ascii:
            audit_low = Decimal(number)
            audit_high = Decimal(range_ascii)
            if sign:
                audit_low = -audit_low
        else:
            audit_value = Decimal(number)
            if sign:
                audit_value = -audit_value
        slices.append(
            UnitSlice(
                "dose",
                snippet,
                start,
                end,
                token=token,
                unit=unit,
                audit_value=audit_value,
                audit_low=audit_low,
                audit_high=audit_high,
            )
        )
    return slices


def _qualifier_slices(text: str) -> list[UnitSlice]:
    candidates = []
    for kind, pattern in _QUALIFIER_RES:
        for match in pattern.finditer(text):
            if match.start() == match.end():
                continue
            candidates.append(UnitSlice(kind, match.group(0), match.start(), match.end()))
    ranked = sorted(candidates, key=lambda item: (-(item.end - item.start), item.start, item.kind))
    chosen: list[UnitSlice] = []
    for item in ranked:
        if any(item.start < other.end and other.start < item.end for other in chosen):
            continue
        chosen.append(item)
    chosen.sort(key=lambda item: (item.start, item.end))
    return chosen


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < stop and end > begin for begin, stop in spans)


def _classify_dose(dose: UnitSlice, source_doses: list[UnitSlice], source_text: str) -> str | None:
    if any(dose.token == item.token and dose.unit == item.unit for item in source_doses):
        return None
    if any(dose.token == item.token for item in source_doses):
        return "NUMERIC_UNIT_MISMATCH"
    if _whitespace_stitches(source_text, dose.token or ""):
        return "NUMERIC_STITCH"
    if any(_is_boundary(dose.token or "", item.token or "") for item in source_doses):
        return "NUMERIC_BOUNDARY"
    return "ADDED_CONTENT"


def _whitespace_stitches(source_text: str, token: str) -> bool:
    number = token[1:] if token.startswith("-") and len(token) > 1 and token[1].isdigit() else token
    if len(number) < 2 or any(char.isspace() for char in number):
        return False
    pattern = r"\s*".join(re.escape(char) for char in number)
    folded = _fold_compatible(source_text)
    return any(re.search(r"\s", match.group(0)) for match in re.finditer(pattern, folded))


def _is_boundary(display_token: str, source_token: str) -> bool:
    if not display_token or not source_token or display_token == source_token:
        return False
    if source_token.startswith(display_token) or source_token.endswith(display_token):
        return True
    return "-" in source_token and display_token in source_token.split("-")


def _extra_drugs(source_slices: list[UnitSlice] | tuple[UnitSlice, ...], display_slices: list[UnitSlice] | tuple[UnitSlice, ...]) -> list[UnitSlice]:
    pool = [item for item in source_slices if item.kind == "drug"]
    extra = []
    for drug in display_slices:
        if drug.kind != "drug":
            continue
        index = next((i for i, item in enumerate(pool) if canon(item.text) == canon(drug.text)), None)
        if index is None:
            extra.append(drug)
        else:
            pool.pop(index)
    return extra


def _qualifier_delta(
    source_slices: list[UnitSlice] | tuple[UnitSlice, ...],
    display_slices: list[UnitSlice] | tuple[UnitSlice, ...],
) -> tuple[list[UnitSlice], list[UnitSlice]]:
    source_q = [item for item in source_slices if item.kind in DERIVATION_BY_KIND]
    display_q = [item for item in display_slices if item.kind in DERIVATION_BY_KIND]
    pool = list(source_q)
    added = []
    for item in display_q:
        key = canon(item.text)
        index = next((i for i, src in enumerate(pool) if src.kind == item.kind and canon(src.text) == key), None)
        if index is not None:
            pool.pop(index)
            continue
        if any(src.kind == item.kind and key in canon(src.text) for src in source_q):
            continue
        added.append(item)
    return pool, added


def _source_has_facts(slices: list[UnitSlice] | tuple[UnitSlice, ...]) -> bool:
    return any(item.kind in {"dose", "drug"} or item.kind in DERIVATION_BY_KIND for item in slices)


def _names(value: str | Sequence[str] | None) -> set[str]:
    if value is None:
        return set()
    items = [value] if isinstance(value, str) else list(value)
    return {item for item in items if isinstance(item, str) and item in DERIVATIONS}


def _human_covers(
    omissions: set[str],
    derivation: str | Sequence[str] | None,
    human_gate: Mapping[str, object] | None,
) -> bool:
    if not omissions <= _names(derivation):
        return False
    if not isinstance(human_gate, Mapping):
        return False
    decision = human_gate.get("decision")
    if not isinstance(decision, str) or decision.strip() != "ALLOW_OMISSION":
        return False
    reviewer = human_gate.get("reviewer_id")
    if not isinstance(reviewer, str) or not reviewer.strip():
        return False
    return omissions <= _names(human_gate.get("covers"))
