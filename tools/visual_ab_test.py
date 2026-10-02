"""Isolated six-page full-design-reference / native-PPT visual experiment.

Uses the frozen exported deck, not mutable workflow state. Never writes workflow DBs.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "output" / "visual_ab_test"
SAMPLES = [1, 4, 17, 22, 30, 47]
TITLES = ["封面", "国内外指南定义", "炎症表型指标", "生物制剂选择路径", "研究中的缓解定义与结果", "规格、用法与价格"]
STYLE = {"paper": "#F6F4EF", "ink": "#151B24", "accent": "#2458D3", "muted": "#5B6473", "line": "#D7D9DD"}


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    from lxml import html as lh
    from pptx import Presentation
    start = time.perf_counter()
    src = ROOT / "output" / "deck_full"
    frozen = OUT / "frozen"
    frozen.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in ("deck.html", "deck.pptx", "render_report.json"):
        target = frozen / name
        if target.exists() and sha(target) != sha(src / name):
            raise ValueError("Frozen input differs from current source; use a different output directory")
        shutil.copy2(src / name, target)
        hashes[name] = sha(target)
    tree = lh.fromstring((frozen / "deck.html").read_text(encoding="utf-8"))
    slides = tree.xpath("//section[contains(concat(' ',normalize-space(@class),' '),' slide ')]")
    prs = Presentation(frozen / "deck.pptx")
    assert len(slides) == len(prs.slides) == 52
    pages = []
    for i, (n, name) in enumerate(zip(SAMPLES, TITLES), 1):
        slide = slides[n - 1]
        facts = {x.get("data-fact"): x.text_content() for x in slide.xpath('.//*[@data-fact]')}
        def text(cls):
            got = slide.xpath(".//*[contains(concat(' ',normalize-space(@class),' '),' " + cls + " ')]")
            return got[0].text_content().strip() if got else ""
        cells = [[{"facts": c.xpath('.//*[@data-fact]/@data-fact'), "text": c.text_content().strip()}
                  for c in row.xpath('./th|./td')] for row in slide.xpath('.//table//tr')]
        authors = [x.text_content() for x in slide.xpath('.//*[@data-authored]')]
        chrome = [x.text_content().strip() for x in slide.xpath('.//*[@data-chrome]')]
        page = {"sample": i, "original_page": n, "id": slide.get("id"), "kind": name,
                "title": text("title"), "section": text("section"), "lead": text("lead"),
                "facts": facts, "authored": authors, "chrome": chrome, "table": cells,
                "notes": prs.slides[n - 1].notes_slide.notes_text_frame.text,
                "pending_markers": len(slide.xpath('.//*[@data-mark="pending"]')),
                "original_html": lh.tostring(slide, encoding="unicode")}
        pages.append(page)
        shutil.copy2(src / f"slide{n:02d}.png", frozen / f"sample{i:02d}.png")
    manifest = {"schema": "visual-ab-test.v1", "source_hashes": hashes, "source": str(src),
                "style": STYLE, "pages": pages, "preparation_seconds": round(time.perf_counter()-start, 3)}
    dump(OUT / "content_lock.json", manifest)
    print(json.dumps([{k:p[k] for k in ('sample','id','title','pending_markers')} for p in pages], ensure_ascii=False))


def prompts():
    m = json.loads((OUT / "content_lock.json").read_text(encoding="utf-8"))
    direction = [
        "A striking editorial COVER: enormous left-aligned Chinese title spanning two to three balanced lines, small course label above, subtitle below. On the right a sophisticated flat-vector conceptual lung silhouette made from branching cobalt lines and geometric organic curves. It is a decorative topic illustration, not a clinical diagram. One strong cobalt composition with subtle grain; exceptionally confident typography and ample whitespace.",
        "A professional two-source textual comparison. Present both guideline names equally and compare their two clauses on aligned horizontal levels. Large source-name typography, cobalt rules, open canvas instead of rounded cards. Keep source references and abbreviation expansion in a distinct quiet lower zone. The eye should see the paired guideline structure instantly.",
        "A typography-led four-metric editorial page. Three huge cobalt threshold numbers and one prominent short clinical feature; small labels above. No dashboard cards. Strong but equal treatment of four peers. Put the full qualifying lead above and the alternate-source 2.5% statement in a separate quiet reference strip below, never mix it with the 2% main metric.",
        "A carefully structured branching decision diagram. Parent population above, three threshold branches below. Low group leads to its existing selection instruction, middle group to its existing drug-target list, high group to its exclusion instruction and its own target list. Preserve these associations; no new clinical paths. Confident cobalt connectors, minimal open containers, quiet shared context above. Make reading order unmistakable.",
        "An editorial clinical research result page: giant 41.6% as a typographic focal point with its 4-component label. Distinct left-hand study-context and population area, below it clearly distinguish the three-component and four-component definitions. No invented chart, no invented comparator. Data and definition must be visible together.",
        "A professionally art-directed dense 6-drug by 6-column TABLE page. Full original cell text remains. Clear column widths, larger drug names, aligned numeric price column, alternating very subtle warm ivory bands, cobalt header and careful rules. Prioritize legibility, no decorative illustration consuming table space. Preserve every row, unit, qualifier and 中国 scope label. Native reconstruction will use editable table cells."
    ]
    base = """Generate ONE complete professionally designed 16:9 Chinese PowerPoint slide INCLUDING ALL LOCKED TEXT. This is a visual design reference to be reconstructed later as editable native PowerPoint; take responsibility for the entire graphic design, composition, typography, figures and information hierarchy. Aim for a high-end medical journal editorial style: warm ivory #F6F4EF, carbon #151B24, saturated cobalt #2458D3, restrained subtle paper grain. Bold Chinese sans-serif headings, clean readable body, crisp source footnotes. Avoid generic business templates, repeated UI cards, pills, unnecessary rounded boxes, fake 3D and heavy shadows. Clean flat scientific editorial visual language. Strong first focal point, meaningful reading order, impeccable alignment and professional whitespace. Use 16:9 full slide, no screen/mockup or surrounding scene. ALL substantive words/numbers/qualifiers must be exactly the locked text below. Line wrapping and visual emphasis may change, wording must not. Do not add any extra claim, number, comparison, drug, axis, clinical relation or logo. Small source footnotes are required. No lorem ipsum or filler text. Design the complete slide, not an empty background.\n"""
    records = []
    for i,p in enumerate(m['pages']):
        content = {"authored_labels": p['authored'], "facts":p['facts'], "footer":p['chrome']}
        if p['table']: content['table']=p['table']
        prompt = base + "\nPAGE ART DIRECTION:\n" + direction[i] + "\n\nLOCKED CONTENT:\n" + json.dumps(content, ensure_ascii=False,indent=2)
        file = OUT / "prompts" / f"sample{i+1:02d}-full-design.txt"
        file.parent.mkdir(exist_ok=True)
        file.write_text(prompt,encoding='utf-8')
        records.append({"sample":i+1,"page_id":p['id'],"prompt_file":str(file.relative_to(OUT)),"prompt_sha256":sha(file),"art_direction":direction[i]})
    dump(OUT/'design_inputs.json',{"stage":"complete-design-reference","records":records})
    print('Prepared six complete-design prompts')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "prompts", "build", "office", "deliver"])
    args = parser.parse_args()
    if args.command in ("prepare", "prompts"):
        {"prepare":prepare,"prompts":prompts}[args.command]()
    else:
        from tools.visual_ab_native import build, office, deliver
        {"build":build,"office":office,"deliver":deliver}[args.command]()
