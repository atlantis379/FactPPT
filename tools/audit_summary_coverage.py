"""Read-only audit/scaffold. Never accepts a summary or advances a workflow."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from factdeck.source_coverage import audit, scaffold


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--summary', required=True, type=Path, help='完整总结JSON，不是展示片段包')
    p.add_argument('--units', required=True, type=Path, help='单元列表或含pages[].units的来源缓存')
    p.add_argument('--claims', type=Path, help='论断清单{claim_id: claim}；v2登记据此拒绝把论断原文归为非论断')
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--scaffold', type=Path, help='另存未判断的登记骨架；不自动标记覆盖')
    args = p.parse_args()
    s = json.loads(args.summary.read_text(encoding='utf-8'))
    raw = json.loads(args.units.read_text(encoding='utf-8'))
    if isinstance(raw, list):
        units = raw
    else:
        units = [dict(u, id=u.get('id') or u['unit_id'], page_id=page['page_id'])
                 for page in raw['pages'] for u in page['units']]
    claims = json.loads(args.claims.read_text(encoding='utf-8')) if args.claims else None
    report = audit(s, units, claims)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.scaffold:
        args.scaffold.parent.mkdir(parents=True, exist_ok=True)
        args.scaffold.write_text(json.dumps(scaffold(s, units), ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['structural_status'], 'issues': len(report['issues']),
                      'pending': len(report['pending']), 'warnings': len(report['warnings']), 'report': str(args.out)}, ensure_ascii=False))
    return 2 if report['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
