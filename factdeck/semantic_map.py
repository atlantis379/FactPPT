"""SEMANTIC_MAP (``semantic_map.v1``) and claim attachment in front of SUMMARY.

Order in this package:

    INGEST → UNITS → SEMANTIC_MAP → CLAIMS → SUMMARY → SUMMARY_REVIEW
        → FACTS → SLOTS → PPT

``parse_semantic_map`` checks the map artifact. ``attach_claims`` requires
``semantic_node_id`` once that map exists and puts a claim with no usable
node in the ``unassigned`` bucket. ``summary_from_semantic_map`` builds a
SUMMARY whose chapters follow the map: mainline nodes first, then the
other nodes, keeping relative order inside each group. A key point that
cites a claim from another node is flagged by ``classify_key_points`` and
rejected by ``summary_from_semantic_map``. The display fact gate,
half-sentence check, and slot pairing stay where they are.

INGEST, UNITS, claim extraction, and SUMMARY_REVIEW are not in this
repository. See the pipeline section of ``README.md``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from factdeck.summary import summary_from_outline

SCHEMA_VERSION = "semantic_map.v1"
STAGE = "SEMANTIC_MAP"
UNASSIGNED_NODE_ID = "unassigned"

# Factdeck order. Frozen SYSTEM_SPEC §17.1 names are not renamed.
PIPELINE_ORDER = (
    "INGEST",
    "UNITS",
    "SEMANTIC_MAP",
    "CLAIMS",
    "SUMMARY",
    "SUMMARY_REVIEW",
    "FACTS",
    "SLOTS",
    "PPT",
)

# Entry point in this repository. None is a FactPPTv2 residual.
STAGE_ENTRY = {
    "INGEST": None,
    "UNITS": None,
    "SEMANTIC_MAP": "factdeck.semantic_map.parse_semantic_map",
    "CLAIMS": "factdeck.semantic_map.attach_claims",
    "SUMMARY": "factdeck.semantic_map.summary_from_semantic_map",
    "SUMMARY_REVIEW": None,
    "FACTS": "factdeck.facts.gate_display",
    "SLOTS": "factdeck.slots.trace_slide",
    "PPT": "factdeck.deck.build_deck",
}

NODE_ROLES = frozenset({
    "definition",
    "burden",
    "assessment",
    "pathway",
    "indication",
    "table",
    "followup",
    "other",
})
EDGE_RELATIONS = frozenset({"sequence", "contrast", "condition", "evidence"})

MAP_FIELDS = frozenset({"schema_version", "one_liner", "nodes", "edges"})
NODE_FIELDS = frozenset({"id", "title", "role", "thesis", "unit_hints", "mainline"})
EDGE_FIELDS = frozenset({"from", "to", "relation"})
CLAIM_FIELDS = frozenset({
    "claim_id",
    "text",
    "source_text",
    "source_span_ids",
    "semantic_node_id",
    "unit_id",
})
KEY_POINT_FIELDS = frozenset({"id", "key_point_id", "semantic_node_id", "claim_ids", "text"})

SEMANTIC_MAP_SCHEMA = {
    "$id": SCHEMA_VERSION,
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "one_liner", "nodes"],
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "one_liner": {"type": "string", "maxSentences": 1, "digits": False},
        "nodes": {
            "type": "array",
            "minItems": 1,
            "required": ["id", "title", "role", "thesis", "unit_hints", "mainline"],
        },
        "edges": {"type": "array"},
    },
    "node_roles": sorted(NODE_ROLES),
    "edge_relations": sorted(EDGE_RELATIONS),
    "unassigned": UNASSIGNED_NODE_ID,
}

_DIGITS = re.compile(r"[0-9０-９]")
_SENTENCE_BREAK = re.compile(r"[。！？.!?]")


class SemanticMapError(ValueError):
    """Invalid map, claim attachment, or summary alignment."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class SemanticNode:
    id: str
    title: str
    role: str
    thesis: str
    unit_hints: tuple[str, ...]
    mainline: bool

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "role": self.role,
            "thesis": self.thesis,
            "unit_hints": list(self.unit_hints),
            "mainline": self.mainline,
        }


@dataclass(frozen=True)
class SemanticEdge:
    source: str
    target: str
    relation: str

    def to_dict(self) -> dict:
        return {"from": self.source, "to": self.target, "relation": self.relation}


@dataclass(frozen=True)
class SemanticMap:
    """Ordered semantic sections. Edges are stored and are not a sort key."""

    one_liner: str
    nodes: tuple[SemanticNode, ...]
    edges: tuple[SemanticEdge, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def teaching_ids(self) -> tuple[str, ...]:
        """Mainline nodes in map order, then the other nodes in map order."""

        mainline = [node.id for node in self.nodes if node.mainline]
        branch = [node.id for node in self.nodes if not node.mainline]
        return tuple([*mainline, *branch])

    def to_dict(self) -> dict:
        payload = {
            "schema_version": self.schema_version,
            "one_liner": self.one_liner,
            "nodes": [node.to_dict() for node in self.nodes],
        }
        if self.edges:
            payload["edges"] = [edge.to_dict() for edge in self.edges]
        return payload


@dataclass(frozen=True)
class ClaimRef:
    claim_id: str
    text: str
    source_text: str
    source_span_ids: tuple[str, ...]
    semantic_node_id: str | None
    unit_id: str | None = None


@dataclass(frozen=True)
class ClaimViolation:
    claim_id: str
    code: str
    message: str


@dataclass(frozen=True)
class AttachedClaims:
    """Claims grouped by map node. Orphans are only in ``unassigned``."""

    by_node: Mapping[str, tuple[ClaimRef, ...]]
    unassigned: tuple[ClaimRef, ...]
    violations: tuple[ClaimViolation, ...]


@dataclass(frozen=True)
class KeyPointFlag:
    key_point_id: str
    semantic_node_id: str
    claim_ids: tuple[str, ...]
    text: str | None
    code: str
    message: str
    claim_id: str | None = None
    claim_node_id: str | None = None


def parse_semantic_map(artifact: Mapping | str | bytes) -> SemanticMap:
    """Validate a ``semantic_map.v1`` object or JSON document."""

    payload = _load_artifact(artifact)
    _reject_unknown(payload, MAP_FIELDS, "semantic map")
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise SemanticMapError("SCHEMA_VERSION", f"schema_version must be {SCHEMA_VERSION}")
    one_liner = _prose(payload, "one_liner", one_sentence=True)
    nodes = _nodes(_as_list(payload.get("nodes"), "nodes"))
    edges = _edges(payload.get("edges"), {node.id for node in nodes})
    return SemanticMap(one_liner, nodes, edges)


def attach_claims(
    claims: Sequence[Mapping],
    semantic_map: SemanticMap | Mapping | str | bytes,
    *,
    units: Mapping[str, str] | None = None,
) -> AttachedClaims:
    """Bucket claims under map nodes.

    A claim with no ``semantic_node_id``, an unknown id, or the reserved
    ``unassigned`` id stays in ``unassigned``. It is not copied onto another
    node. ``source_text`` is the original span; ``text`` must be an exact
    substring of that span.
    """

    parsed = semantic_map if isinstance(semantic_map, SemanticMap) else parse_semantic_map(semantic_map)
    grouped = {node.id: [] for node in parsed.nodes}
    unassigned: list[ClaimRef] = []
    violations: list[ClaimViolation] = []
    seen: set[str] = set()
    known = set(grouped)
    for index, raw in enumerate(_as_list(claims, "claims"), start=1):
        claim = _parse_claim(raw, index, seen, units)
        node_id = claim.semantic_node_id
        if node_id in known:
            grouped[node_id].append(claim)
            continue
        if node_id in {None, ""}:
            code = "MISSING_NODE"
            detail = "missing semantic_node_id"
        elif node_id == UNASSIGNED_NODE_ID:
            code = "UNASSIGNED"
            detail = "semantic_node_id is unassigned"
        else:
            code = "UNKNOWN_NODE"
            detail = f"semantic_node_id {node_id} is not on the map"
        unassigned.append(claim)
        violations.append(ClaimViolation(
            claim.claim_id,
            code,
            f"claim {claim.claim_id} {detail}",
        ))
    frozen = {node_id: tuple(items) for node_id, items in grouped.items()}
    return AttachedClaims(MappingProxyType(frozen), tuple(unassigned), tuple(violations))


def classify_key_points(
    semantic_map: SemanticMap | Mapping | str | bytes,
    key_points: Sequence[Mapping],
    claims: Sequence[Mapping] | AttachedClaims,
    *,
    units: Mapping[str, str] | None = None,
) -> tuple[KeyPointFlag, ...]:
    """Flag key points whose claims belong to a different node.

    ``WRONG_NODE``, ``UNKNOWN_NODE``, ``UNKNOWN_CLAIM``, and ``MISSING_NODE``
    are flags. A key point string that is not an exact slice of one cited
    claim raises ``NON_VERBATIM`` or ``AMBIGUOUS_SPAN``.
    """

    parsed = semantic_map if isinstance(semantic_map, SemanticMap) else parse_semantic_map(semantic_map)
    attached = claims if isinstance(claims, AttachedClaims) else attach_claims(claims, parsed, units=units)
    return _flag_key_points(parsed, key_points, attached)


def summary_from_semantic_map(
    semantic_map: SemanticMap | Mapping | str | bytes,
    key_points: Sequence[Mapping],
    claims: Sequence[Mapping],
    *,
    units: Mapping[str, str] | None = None,
):
    """SUMMARY chapters in teaching order.

    Unassigned claims raise. A key point flagged by ``classify_key_points``
    raises with that flag's code. Bullet text is copied. ``prepare_deck``
    still applies the fact gate and the half-sentence rule.
    """

    parsed = semantic_map if isinstance(semantic_map, SemanticMap) else parse_semantic_map(semantic_map)
    attached = attach_claims(claims, parsed, units=units)
    if attached.violations:
        violation = attached.violations[0]
        raise SemanticMapError(violation.code, violation.message)
    flags = _flag_key_points(parsed, key_points, attached)
    bad = next((flag for flag in flags if flag.code != "OK"), None)
    if bad is not None:
        raise SemanticMapError(bad.code, bad.message)
    return summary_from_outline(_outline(parsed, flags, attached))


def _load_artifact(artifact: Mapping | str | bytes) -> Mapping:
    if isinstance(artifact, (str, bytes)):
        try:
            artifact = json.loads(artifact)
        except json.JSONDecodeError as exc:
            raise SemanticMapError("SCHEMA", "semantic map artifact is not JSON") from exc
    if not isinstance(artifact, Mapping):
        raise SemanticMapError("TYPE", "semantic map must be a mapping")
    return artifact


def _nodes(items: Sequence) -> tuple[SemanticNode, ...]:
    if not items:
        raise SemanticMapError("EMPTY", "nodes must contain a section")
    nodes = []
    seen: set[str] = set()
    for index, raw in enumerate(items, start=1):
        node = _node(raw, index)
        if node.id == UNASSIGNED_NODE_ID:
            raise SemanticMapError("RESERVED_ID", "unassigned is reserved for orphan claims")
        if node.id in seen:
            raise SemanticMapError("DUPLICATE_ID", f"duplicate node id {node.id}")
        seen.add(node.id)
        nodes.append(node)
    return tuple(nodes)


def _node(raw: object, index: int) -> SemanticNode:
    if not isinstance(raw, Mapping):
        raise SemanticMapError("TYPE", f"node {index} must be a mapping")
    _reject_unknown(raw, NODE_FIELDS, f"node {index}")
    node_id = _token(raw, "id", f"node {index}")
    title = _line(raw, "title", f"node {index}")
    role = raw.get("role")
    if role not in NODE_ROLES:
        raise SemanticMapError("ROLE", f"node {node_id} role is not a semantic map role")
    thesis = _prose(raw, "thesis", one_sentence=True, label=f"node {node_id}")
    hints = _hints(raw.get("unit_hints"), node_id)
    mainline = raw.get("mainline")
    if not isinstance(mainline, bool):
        raise SemanticMapError("TYPE", f"node {node_id} mainline must be a bool")
    return SemanticNode(node_id, title, str(role), thesis, hints, mainline)


def _edges(raw: object, node_ids: set[str]) -> tuple[SemanticEdge, ...]:
    if raw is None:
        return ()
    edges = []
    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(_as_list(raw, "edges"), start=1):
        if not isinstance(item, Mapping):
            raise SemanticMapError("TYPE", f"edge {index} must be a mapping")
        _reject_unknown(item, EDGE_FIELDS, f"edge {index}")
        source = _token(item, "from", f"edge {index}")
        target = _token(item, "to", f"edge {index}")
        relation = item.get("relation")
        if relation not in EDGE_RELATIONS:
            raise SemanticMapError("RELATION", f"edge {index} relation is not a semantic map relation")
        if source == target:
            raise SemanticMapError("SELF_EDGE", f"edge {index} links a node to itself")
        if source not in node_ids or target not in node_ids:
            raise SemanticMapError("EDGE_ENDPOINT", f"edge {index} endpoint is not on the map")
        key = (source, target, str(relation))
        if key in seen:
            raise SemanticMapError("DUPLICATE_ID", f"duplicate edge {source} → {target}")
        seen.add(key)
        edges.append(SemanticEdge(source, target, str(relation)))
    return tuple(edges)


def _parse_claim(
    raw: object,
    index: int,
    seen: set[str],
    units: Mapping[str, str] | None,
) -> ClaimRef:
    if not isinstance(raw, Mapping):
        raise SemanticMapError("TYPE", f"claim {index} must be a mapping")
    _reject_unknown(raw, CLAIM_FIELDS, f"claim {index}")
    claim_id = _token(raw, "claim_id", f"claim {index}")
    if claim_id in seen:
        raise SemanticMapError("DUPLICATE_ID", f"duplicate claim id {claim_id}")
    seen.add(claim_id)
    text = _required_text(raw, "text", claim_id)
    if "source_text" not in raw:
        raise SemanticMapError("MISSING_FIELD", f"claim {claim_id} requires source_text")
    source_text = raw.get("source_text")
    if not isinstance(source_text, str) or not source_text:
        raise SemanticMapError("MISSING_FIELD", f"claim {claim_id} requires source_text")
    if text not in source_text:
        raise SemanticMapError("NON_VERBATIM", f"claim {claim_id} text is not a span of source_text")
    spans = _spans(raw.get("source_span_ids"), claim_id)
    unit_id = _optional_token(raw, "unit_id", claim_id)
    if unit_id is not None and units is not None:
        if unit_id not in units:
            raise SemanticMapError("UNKNOWN_UNIT", f"claim {claim_id} unit_id is not in units")
        unit_text = units[unit_id]
        if not isinstance(unit_text, str) or text not in unit_text:
            raise SemanticMapError("NON_VERBATIM", f"claim {claim_id} text is not a span of unit {unit_id}")
    node_id = _optional_node(raw, claim_id)
    return ClaimRef(claim_id, text, source_text, spans, node_id, unit_id)


def _flag_key_points(
    parsed: SemanticMap,
    key_points: Sequence[Mapping],
    attached: AttachedClaims,
) -> tuple[KeyPointFlag, ...]:
    known = {node.id for node in parsed.nodes}
    located = _claim_index(attached)
    flags = []
    seen: set[str] = set()
    for index, raw in enumerate(_as_list(key_points, "key_points"), start=1):
        point_id, node_id, claim_ids, text = _key_point_shape(raw, index, seen)
        if node_id is None:
            flags.append(_point_flag(
                point_id, "", claim_ids, text, "MISSING_NODE",
                f"key point {point_id} requires semantic_node_id",
            ))
            continue
        if node_id not in known:
            flags.append(_point_flag(
                point_id, node_id, claim_ids, text, "UNKNOWN_NODE",
                f"key point {point_id} semantic_node_id {node_id} is not on the map",
            ))
            continue
        claims = []
        missing = None
        for claim_id in claim_ids:
            claim = located.get(claim_id)
            if claim is None:
                missing = claim_id
                break
            claims.append(claim)
        if missing is not None:
            flags.append(_point_flag(
                point_id, node_id, claim_ids, text, "UNKNOWN_CLAIM",
                f"key point {point_id} cites unknown claim {missing}",
                claim_id=missing,
            ))
            continue
        mismatched = next((claim for claim in claims if _resolved_node(claim, attached) != node_id), None)
        if mismatched is not None:
            claim_node = _resolved_node(mismatched, attached) or UNASSIGNED_NODE_ID
            flags.append(_point_flag(
                point_id, node_id, claim_ids, text, "WRONG_NODE",
                f"key point {point_id} cites {mismatched.claim_id} from node {claim_node}, not {node_id}",
                claim_id=mismatched.claim_id,
                claim_node_id=claim_node,
            ))
            continue
        if text is not None:
            _require_one_span(point_id, text, claims)
        flags.append(_point_flag(point_id, node_id, claim_ids, text, "OK", "ok"))
    return tuple(flags)


def _outline(parsed: SemanticMap, flags: Sequence[KeyPointFlag], attached: AttachedClaims) -> dict:
    grouped: dict[str, list[KeyPointFlag]] = {node_id: [] for node_id in parsed.teaching_ids()}
    for flag in flags:
        grouped[flag.semantic_node_id].append(flag)
    titles = {node.id: node.title for node in parsed.nodes}
    located = _claim_index(attached)
    sections = []
    for node_id in parsed.teaching_ids():
        bullets = []
        for flag in grouped[node_id]:
            bullets.extend(_bullets(flag, located))
        sections.append({
            "id": node_id,
            "title": titles[node_id],
            "role": "body",
            "bullets": bullets,
        })
    return {"sections": sections}


def _bullets(flag: KeyPointFlag, located: Mapping[str, ClaimRef]) -> list[dict]:
    claims = [located[claim_id] for claim_id in flag.claim_ids]
    if flag.text is None:
        return [_bullet(flag, claim, claim.text) for claim in claims]
    matched = next(claim for claim in claims if flag.text in claim.text)
    bullets = [_bullet(flag, matched, flag.text)]
    for claim in claims:
        if claim.claim_id != matched.claim_id:
            bullets.append(_bullet(flag, claim, claim.text))
    return bullets


def _bullet(flag: KeyPointFlag, claim: ClaimRef, text: str) -> dict:
    return {
        "id": f"{flag.key_point_id}:{claim.claim_id}",
        "text": text,
        "source_text": claim.source_text,
        "source_id": claim.source_span_ids[0],
        "source_field": "body",
    }


def _require_one_span(point_id: str, text: str, claims: Sequence[ClaimRef]) -> None:
    matches = [claim for claim in claims if text in claim.text]
    if not matches:
        raise SemanticMapError("NON_VERBATIM", f"key point {point_id} text is not a span of its claims")
    if len(matches) > 1:
        raise SemanticMapError("AMBIGUOUS_SPAN", f"key point {point_id} text matches more than one claim")


def _key_point_shape(raw: object, index: int, seen: set[str]) -> tuple[str, str | None, tuple[str, ...], str | None]:
    if not isinstance(raw, Mapping):
        raise SemanticMapError("TYPE", f"key point {index} must be a mapping")
    _reject_unknown(raw, KEY_POINT_FIELDS, f"key point {index}")
    point_id = _point_id(raw, index)
    if point_id in seen:
        raise SemanticMapError("DUPLICATE_ID", f"duplicate key point id {point_id}")
    seen.add(point_id)
    if "semantic_node_id" not in raw or raw.get("semantic_node_id") in {None, ""}:
        node_id = None
    else:
        node_id = raw.get("semantic_node_id")
    if not _is_token(node_id):
        raise SemanticMapError("TYPE", f"key point {point_id} semantic_node_id must be a token")
    claim_ids = _claim_ids(raw.get("claim_ids"), point_id)
    text = None
    if "text" in raw and raw.get("text") is not None:
        value = raw.get("text")
        if not isinstance(value, str) or not value.strip():
            raise SemanticMapError("EMPTY", f"key point {point_id} text is empty")
        text = value
    return point_id, node_id, claim_ids, text


def _point_id(raw: Mapping, index: int) -> str:
    primary = raw.get("id")
    alias = raw.get("key_point_id")
    if primary is None and alias is None:
        raise SemanticMapError("MISSING_FIELD", f"key point {index} requires id")
    chosen = primary if primary is not None else alias
    if not _is_token(chosen):
        raise SemanticMapError("TYPE", f"key point {index} id must be a token")
    if primary is not None and alias is not None and primary != alias:
        raise SemanticMapError("DUPLICATE_ID", f"key point {index} id and key_point_id differ")
    return chosen


def _claim_ids(raw: object, point_id: str) -> tuple[str, ...]:
    items = _as_list(raw, f"key point {point_id} claim_ids")
    if not items:
        raise SemanticMapError("EMPTY", f"key point {point_id} cites no claims")
    found = []
    seen: set[str] = set()
    for item in items:
        if not _is_token(item):
            raise SemanticMapError("TYPE", f"key point {point_id} claim_ids must be tokens")
        if item in seen:
            raise SemanticMapError("DUPLICATE_ID", f"key point {point_id} repeats claim {item}")
        seen.add(item)
        found.append(item)
    return tuple(found)


def _claim_index(attached: AttachedClaims) -> dict[str, ClaimRef]:
    found = {}
    for group in attached.by_node.values():
        for claim in group:
            found[claim.claim_id] = claim
    for claim in attached.unassigned:
        found[claim.claim_id] = claim
    return found


def _resolved_node(claim: ClaimRef, attached: AttachedClaims) -> str | None:
    group = attached.by_node.get(claim.semantic_node_id or "")
    if group is not None and any(item.claim_id == claim.claim_id for item in group):
        return claim.semantic_node_id
    return None


def _point_flag(
    point_id: str,
    node_id: str,
    claim_ids: tuple[str, ...],
    text: str | None,
    code: str,
    message: str,
    *,
    claim_id: str | None = None,
    claim_node_id: str | None = None,
) -> KeyPointFlag:
    return KeyPointFlag(point_id, node_id, claim_ids, text, code, message, claim_id, claim_node_id)


def _prose(raw: Mapping, field: str, *, one_sentence: bool, label: str | None = None) -> str:
    if field not in raw:
        raise SemanticMapError("MISSING_FIELD", f"{label or 'semantic map'} requires {field}")
    value = raw.get(field)
    owner = label or "semantic map"
    if not isinstance(value, str) or not value.strip():
        raise SemanticMapError("EMPTY", f"{owner} {field} is empty")
    if _DIGITS.search(value):
        raise SemanticMapError("DIGITS", f"{owner} {field} must not add clinical numbers")
    if "\n" in value or "\r" in value or (one_sentence and len(_SENTENCE_BREAK.findall(value)) > 1):
        raise SemanticMapError("MULTI_SENTENCE", f"{owner} {field} must be one sentence")
    return value


def _line(raw: Mapping, field: str, label: str) -> str:
    if field not in raw:
        raise SemanticMapError("MISSING_FIELD", f"{label} requires {field}")
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SemanticMapError("EMPTY", f"{label} {field} is empty")
    if "\n" in value or "\r" in value:
        raise SemanticMapError("TYPE", f"{label} {field} must be one line")
    return value


def _hints(raw: object, node_id: str) -> tuple[str, ...]:
    if raw is None:
        raise SemanticMapError("MISSING_FIELD", f"node {node_id} requires unit_hints")
    found = []
    seen: set[str] = set()
    for item in _as_list(raw, f"node {node_id} unit_hints"):
        if not _is_token(item):
            raise SemanticMapError("TYPE", f"node {node_id} unit_hints must be tokens")
        if item in seen:
            raise SemanticMapError("DUPLICATE_ID", f"node {node_id} repeats unit hint {item}")
        seen.add(item)
        found.append(item)
    return tuple(found)


def _spans(raw: object, claim_id: str) -> tuple[str, ...]:
    items = _as_list(raw, f"claim {claim_id} source_span_ids")
    if not items:
        raise SemanticMapError("MISSING_SPAN", f"claim {claim_id} requires source_span_ids")
    found = []
    seen: set[str] = set()
    for item in items:
        if not _is_token(item):
            raise SemanticMapError("TYPE", f"claim {claim_id} source_span_ids must be tokens")
        if item in seen:
            raise SemanticMapError("DUPLICATE_ID", f"claim {claim_id} repeats source span {item}")
        seen.add(item)
        found.append(item)
    return tuple(found)


def _optional_node(raw: Mapping, claim_id: str) -> str | None:
    if "semantic_node_id" not in raw or raw.get("semantic_node_id") is None:
        return None
    value = raw.get("semantic_node_id")
    if value == "":
        return None
    if not _is_token(value):
        raise SemanticMapError("TYPE", f"claim {claim_id} semantic_node_id must be a token")
    return str(value)


def _optional_token(raw: Mapping, field: str, claim_id: str) -> str | None:
    if field not in raw or raw.get(field) is None:
        return None
    value = raw.get(field)
    if not _is_token(value):
        raise SemanticMapError("TYPE", f"claim {claim_id} {field} must be a token")
    return str(value)


def _is_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not any(character.isspace() for character in value)
    )


def _token(raw: Mapping, field: str, label: str) -> str:
    if field not in raw:
        raise SemanticMapError("MISSING_FIELD", f"{label} requires {field}")
    value = raw.get(field)
    if not _is_token(value):
        raise SemanticMapError("TYPE", f"{label} {field} must be a token")
    return str(value)


def _required_text(raw: Mapping, field: str, claim_id: str) -> str:
    if field not in raw:
        raise SemanticMapError("MISSING_FIELD", f"claim {claim_id} requires {field}")
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SemanticMapError("EMPTY", f"claim {claim_id} {field} is empty")
    return value


def _reject_unknown(raw: Mapping, allowed: frozenset[str], label: str) -> None:
    extra = sorted(set(raw) - allowed)
    if extra:
        raise SemanticMapError("UNKNOWN_FIELD", f"{label} has unknown field {extra[0]}")


def _as_list(value: object, label: str) -> list:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise SemanticMapError("TYPE", f"{label} must be a list")
    return list(value)
