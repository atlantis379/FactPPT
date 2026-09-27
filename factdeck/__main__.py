"""python -m factdeck <project_dir> <sources_dir> <out_dir>

1. load sources → units          2. verify facts → facts_report.md
3. check deck spec               4. render HTML/PNG/PDF/PPTX and verify
"""
import json
import sys
from pathlib import Path

from .cli_facts import main as facts_main
from .deck import main as deck_main
from .render import run as render_run


def main(argv):
    project, sources, out = map(Path, argv[:3])
    F, D, C = facts_main(project, sources)
    rej = [f for f in F if f.status == "REJECTED"]
    print(f"事实：{len(F)} 条，拒绝 {len(rej)}；冲突 {len(C)}；推导待确认 {sum(not d.confirmed for d in D)}")
    chk = deck_main(project)
    if chk["errors"]:
        print(f"页面规格错误 {chk['errors']} 处，见 {project / 'deck_check.json'}")
        return 1
    rep = render_run(project, out)
    print(json.dumps(rep["summary"], ensure_ascii=False))
    s = rep["summary"]
    hard = s["untracked_text"] + s["fact_text_mismatch"] + s["overflow"] + s["out_of_bounds"] + s["authored_lint"] + s["pptx_missing_facts"]
    blocked = s["pending_confirmation"] > 0 or any(not c.resolution for c in C)
    print("结果：" + ("有排版/一致性错误" if hard else ("审核稿（存在待确认项，不可作为终稿交付）" if blocked else "可交付")))
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
