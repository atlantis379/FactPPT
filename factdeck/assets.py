"""Generated pictures (``figure.v1`` + the asset manifest): a picture is a claim nobody can verify by reading its code.

A generator draws well and has no idea whether what it drew is right, and no check over pixels can tell.  So a
picture goes through the same order of proof as a sentence, in generic steps that know nothing about any subject:

  spec        what the picture must show, every element a word of a sentence and every relation stated by one
  generate    candidates from a prompt built by code from the spec and the deck's style pack, never freehand
  style       one anchor picture fixes the deck's look; others are measured against it
  review      a reader from a *different* provider describes the picture blind, then answers the spec item by item
  sign-off    the presenter, who owns the claim, sees the picture beside what to check.  The hash is signed: a new
              picture is a new, unsigned one

Code never says a picture is correct.  ``status`` says how far it got, and the top of that ladder is "signed", not
"verified".  What a picture shows beyond its sources is listed by the reviewer and shown to the signer: a drawing
always holds more than the sentence it came from.
"""
from __future__ import annotations

import colorsys
import hashlib
import json
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .lexicon import canon

SCHEMA = "figure.v1"
ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "config" / "style_packs.json"
RELATIONS = {"contains", "surrounds", "above", "below", "beside", "connects", "leads_to"}
MODES = {"realistic", "schematic"}
ROLES = {"backdrop", "icon", "illustration"}
MAX_ELEMENTS = 8
# steps of the ladder; only "signed" may ship an illustration, a backdrop or icon needs "reviewed"
GENERATED, REVIEWED, SIGNED, REJECTED = "generated", "reviewed", "signed", "rejected"
STYLE_TOLERANCE = {"saturation": 0.18, "brightness": 0.18, "warmth": 0.18}


class AssetError(ValueError):
    """The picture, or the spec for it, cannot be accepted."""


def _need(cond, msg: str) -> None:
    if not cond:
        raise AssetError(msg)


def _plain(text: str) -> str:
    return re.sub(r"\s+", "", canon(text or ""))


def styles() -> dict:
    return {k: v for k, v in json.loads(STYLES.read_text(encoding="utf-8")).items() if not k.startswith("_")}


# ------------------------------------------------------------------------------------------------ the spec

def check_spec(spec: Mapping, facts: Mapping[str, dict]) -> dict:
    """A picture may only be asked to show what sentences state.  Every name is a word of its sentence, and every
    relation is carried by one sentence naming both ends, so a spec cannot invent an anatomy of its own."""
    _need(spec.get("schema_version") == SCHEMA, f"schema_version 须为 {SCHEMA}")
    _need(spec.get("mode") in MODES, f"mode 须为 {' / '.join(sorted(MODES))}")
    elements = spec.get("elements")
    _need(isinstance(elements, list) and 1 <= len(elements) <= MAX_ELEMENTS, f"elements 须为 1–{MAX_ELEMENTS} 项：再多读者看不完")
    names: dict[str, dict] = {}
    for k, e in enumerate(elements):
        name, fid = e.get("name"), e.get("fact")
        _need(fid in facts, f"elements[{k}] 引用了不存在的句子：{fid}")
        _need(isinstance(name, str) and name.strip() and _plain(name) in _plain(facts[fid]["quote"]),
              f"elements[{k}] 的「{name}」不是这句里的词：图里画什么，要由原文说出来")
        _need(name not in names, f"elements 重复：{name}")
        names[name] = e
    relations = spec.get("relations") or []
    for k, r in enumerate(relations):
        _need(r.get("kind") in RELATIONS, f"relations[{k}] 的 kind 须为 {' / '.join(sorted(RELATIONS))}")
        a, b, fid = r.get("from"), r.get("to"), r.get("fact")
        _need(a in names and b in names, f"relations[{k}] 的两端须是 elements 里的名字")
        _need(fid in facts, f"relations[{k}] 引用了不存在的句子：{fid}")
        q = _plain(facts[fid]["quote"])
        _need(_plain(a) in q and _plain(b) in q,
              f"relations[{k}]「{a}」—「{b}」没有在同一句里说到：这个关系原文没有")
    anchors = spec.get("anchors") or {}
    for key, a in anchors.items():
        _need(a.get("name") in names, f"anchors[{key}] 须是 elements 里的名字")
        _need(all(isinstance(a.get(k), (int, float)) and 0 <= a[k] <= 1 for k in "xy"), f"anchors[{key}] 的 x、y 须在 0–1 之间")
    return {"schema_version": SCHEMA, "id": spec.get("id"), "mode": spec["mode"], "elements": list(elements),
            "relations": list(relations), "anchors": dict(anchors), "exclude": list(spec.get("exclude") or [])}


def prompt_for(spec: Mapping, style: Mapping) -> str:
    """The prompt is built, not written: the same spec and pack give the same words, so a deck stays one deck."""
    img = style["image"]
    parts = [f"A single {'photorealistic' if spec['mode'] == 'realistic' else 'schematic'} illustration.",
             "Show exactly: " + "; ".join(e["name"] for e in spec["elements"]) + "."]
    if spec["relations"]:
        parts.append("Arrangement: " + "; ".join(f'{r["from"]} {r["kind"].replace("_", " ")} {r["to"]}' for r in spec["relations"]) + ".")
    parts += [f"Rendering: {img['rendering']}.", f"Camera: {img['camera']}.", f"Background: {img['background']}.",
              f"Palette: {', '.join(img['palette'])}.", "Do not draw any: " + ", ".join(img["forbid"] + spec["exclude"]) + "."]
    return " ".join(parts)


# --------------------------------------------------------------------------------------------- providers

@dataclass
class Picture:
    data: bytes
    provider: str
    model: str


class Provider(Protocol):
    """One vendor.  Generation and reading are both here, so a review can be sent to a vendor that did not draw."""
    name: str

    def generate(self, prompt: str, *, size: tuple[int, int], references: list[Path]) -> Picture: ...

    def read(self, image: Path, prompt: str) -> dict: ...


# --------------------------------------------------------------------------------------------- the style

def measure(path: Path | str) -> dict:
    """The few numbers that make two pictures look like one hand: how saturated, how bright, how warm."""
    from PIL import Image
    im = Image.open(path).convert("RGBA").resize((64, 64))
    raw = im.tobytes()
    px = [p for p in (tuple(raw[i:i + 4]) for i in range(0, len(raw), 4)) if p[3] > 128]
    _need(px, f"{path} 是全透明的")
    hls = [colorsys.rgb_to_hls(r / 255, g / 255, b / 255) for r, g, b, _ in px]
    n = len(px)
    return {"saturation": round(sum(x[2] for x in hls) / n, 3), "brightness": round(sum(x[1] for x in hls) / n, 3),
            "warmth": round(sum((r - b) / 255 for r, _, b, _ in px) / n, 3)}


def style_drift(metrics: Mapping, anchor: Mapping) -> list[str]:
    """What sets this picture apart from the deck's anchor, if anything."""
    return [f"{k} {metrics[k]} 与锚图 {anchor[k]} 相差超过 {t}" for k, t in STYLE_TOLERANCE.items()
            if abs(metrics[k] - anchor[k]) > t]


def normalize(src: Path, dst: Path, size: tuple[int, int], key_background: bool = False) -> None:
    """Fit a picture to its slot's proportions, and clear a plain background so it sits on the page, not in a box."""
    from PIL import Image, ImageDraw, ImageOps
    im = Image.open(src).convert("RGBA")
    if key_background:
        w, h = im.size
        for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            if im.getpixel(corner)[3] > 0:
                ImageDraw.floodfill(im, corner, (0, 0, 0, 0), thresh=24)
    ImageOps.fit(im, size, method=Image.LANCZOS).save(dst)


# --------------------------------------------------------------------------------------------- the review

BLIND_PROMPT = ("You are shown one picture and nothing else. Describe only what you can see. Reply as JSON: "
                '{"has_text": true/false, "objects": [names of the things drawn], "layout": "how they are arranged"}.')


def checklist(spec: Mapping) -> list[dict]:
    """The spec as questions a reader can answer from the picture alone.  Questions, because a reader told what it
    should see will see it: the blind description comes first, and these only follow."""
    items = [{"id": f'e:{e["name"]}', "ask": f'Is "{e["name"]}" clearly shown?'} for e in spec["elements"]]
    items += [{"id": f'r:{r["from"]}|{r["to"]}', "ask": f'Is "{r["from"]}" {r["kind"].replace("_", " ")} "{r["to"]}"?'}
              for r in spec["relations"]]
    items += [{"id": f'a:{k}', "ask": f'Is the point at x={a["x"]}, y={a["y"]} (0-1 of the picture) on "{a["name"]}"?'}
              for k, a in (spec.get("anchors") or {}).items()]
    return items


def checklist_prompt(spec: Mapping) -> str:
    return ("Answer each question from the picture alone. Reply as JSON: "
            '{"answers": [{"id": "...", "answer": "yes|no|unsure"}], '
            '"beyond": ["anything drawn that the questions did not mention"]}. Questions: '
            + json.dumps(checklist(spec), ensure_ascii=False))


def judge(spec: Mapping, blind: Mapping, answers: Mapping) -> dict:
    """What the reviews add up to.  A "no" or a word in the picture refuses it; "unsure" goes to the person."""
    want = {c["id"] for c in checklist(spec)}
    got = {a.get("id"): a.get("answer") for a in answers.get("answers") or []}
    failed = sorted(i for i in want if got.get(i) == "no")
    missing = sorted(want - set(got))
    unsure = sorted(i for i in want if got.get(i) not in ("yes", "no"))
    reasons = ([ "图里有文字：文字只能由原生文本框显示"] if blind.get("has_text") else []) + [f"核对未过：{i}" for i in failed]
    return {"passed": not reasons and not missing, "reasons": reasons + [f"未回答：{i}" for i in missing],
            "unsure": [i for i in unsure if i not in missing], "beyond": list(answers.get("beyond") or []),
            "seen": list(blind.get("objects") or [])}


# ------------------------------------------------------------------------------------------- the manifest

def sha256(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Manifest:
    """One deck's pictures: what each is for, where it came from, how far it got.  Kept beside the deck."""

    def __init__(self, folder: Path | str):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "assets.json"
        self.items: dict[str, dict] = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")

    def add(self, aid: str, role: str, picture: Picture, *, spec: Mapping | None, prompt: str, style: str) -> dict:
        _need(role in ROLES, f"role 须为 {' / '.join(sorted(ROLES))}")
        _need(role != "illustration" or spec, "插图须有图意规格：说不出要画什么就不画")
        file = self.folder / f"{aid}.png"
        file.write_bytes(picture.data)
        self.items[aid] = {"id": aid, "role": role, "file": str(file), "sha256": sha256(file), "provider": picture.provider,
                           "model": picture.model, "prompt": prompt, "style": style, "spec": spec, "status": GENERATED}
        self.save()
        return self.items[aid]

    def adopt(self, aid: str, role: str, source: Path | str, *, licence: str) -> dict:
        """A figure from the source document, or one the user made: no generator, so no generator to cross-check."""
        _need(licence, "素材须写明来源与授权")
        file = self.folder / f"{aid}.png"
        shutil.copyfile(source, file)
        self.items[aid] = {"id": aid, "role": role, "file": str(file), "sha256": sha256(file), "provider": "adopted",
                           "model": "", "prompt": "", "style": "", "spec": None, "licence": licence, "status": GENERATED}
        self.save()
        return self.items[aid]

    def set_anchor(self, aid: str) -> dict:
        """The picture the deck's look is measured against.  Later pictures take it as their reference."""
        for e in self.items.values():
            e.pop("anchor", None)
        self.items[aid]["anchor"] = measure(self.items[aid]["file"])
        self.save()
        return self.items[aid]

    def style_issues(self, aid: str) -> list[str]:
        base = next((e for e in self.items.values() if e.get("anchor")), None)
        return style_drift(measure(self.items[aid]["file"]), base["anchor"]) if base and base["id"] != aid else []

    def review(self, aid: str, reader: str, blind: Mapping, answers: Mapping) -> dict:
        e = self.items[aid]
        _need(reader != e["provider"], f"{aid} 由 {reader} 生成，须由另一家核对：同一家的模型会犯同样的错")
        _need(e["sha256"] == sha256(e["file"]), f"{aid} 的文件已被改动")
        result = judge(e["spec"] or {"elements": [], "relations": []}, blind, answers)
        result["reader"] = reader
        e["review"] = result
        e["status"] = REVIEWED if result["passed"] else REJECTED
        self.save()
        return e

    def sign(self, aid: str, by: str) -> dict:
        """The presenter takes responsibility for the picture: this file, nothing else."""
        e = self.items[aid]
        _need(by, "须写明确认人")
        _need(e["status"] == REVIEWED or e["provider"] == "adopted", f"{aid} 还没有通过核对（{e['status']}）")
        e["status"], e["signed"] = SIGNED, {"by": by, "sha256": sha256(e["file"])}
        self.save()
        return e

    def blockers(self, aid: str) -> list[str]:
        """Why this picture may not ship yet.  An illustration needs a signature; anything else a passed review."""
        e = self.items.get(aid)
        if not e:
            return [f"素材 {aid} 不在清单里"]
        if sha256(e["file"]) != e["sha256"]:
            return [f"素材 {aid} 的文件已被改动"]
        if e["status"] == REJECTED:
            return [f"素材 {aid} 未通过核对：{'；'.join(e['review']['reasons'])}"]
        if e["role"] == "illustration":
            s = e.get("signed")
            if not s or s["sha256"] != e["sha256"]:
                return [f"插图 {aid} 等待主讲人确认"]
        elif e["status"] == GENERATED and e["provider"] != "adopted":
            return [f"素材 {aid} 还没有核对"]
        return []
