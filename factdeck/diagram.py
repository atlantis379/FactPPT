"""Arrows in native slide diagrams, recovered by code from the original's geometry.

A slide flowchart is text boxes joined by connectors or block-arrow shapes. The
connectors carry no text, so without this step a diagram reaches the fact store as
loose boxes and every arrow drawn later would rest on the author's reading alone.

Input is plain geometry (EMU, slide coordinates):

* boxes: {key: (x, y, w, h)} text shapes that can be ends of an arrow;
* lines: connectors as (path, head0, head1, glued0, glued1): the drawn path (elbows
  included), whether an arrowhead sits at the first/last point, and the box key the
  connector is glued to at each end (None if not glued);
* blocks: block arrows (x, y, w, h, direction) with direction in "right/left/up/down".

Each end of a line is, in this order: the box it is glued to; a box it touches; a
point on another line (a trunk splitting into branches, a branch joining a bar); or
a box close by. Lines joined at such points form one network. In a network, boxes
at plain ends are sources and boxes at arrowhead ends are targets; each
source→target pair is an arrow. A network without both says nothing about direction
and is skipped. A short text box lying on a network's line is the label of the arrow
whose arrowhead is nearest to it.
"""
from __future__ import annotations

import math

TOL = 0.012            # share of slide width: how close an end must be to a line or box to join it
TOUCH = 0.003          # share of slide width: an end this close to a box touches it
LABEL_MAX = 4          # characters; longer text beside a line is content, not a label


def _dist_point_rect(p, r) -> float:
    x, y, w, h = r
    return math.hypot(max(x - p[0], 0, p[0] - (x + w)), max(y - p[1], 0, p[1] - (y + h)))


def _dist_point_seg(p, a, b) -> float:
    (ax, ay), (bx, by) = a, b
    L = (bx - ax) ** 2 + (by - ay) ** 2
    t = 0 if L == 0 else max(0, min(1, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / L))
    return math.hypot(p[0] - ax - t * (bx - ax), p[1] - ay - t * (by - ay))


def _dist_point_path(p, path) -> float:
    return min(_dist_point_seg(p, a, b) for a, b in zip(path, path[1:]))


def _dist_rect_path(r, path) -> float:
    best = 1e18
    for a, b in zip(path, path[1:]):
        for i in range(25):
            q = (a[0] + (b[0] - a[0]) * i / 24, a[1] + (b[1] - a[1]) * i / 24)
            best = min(best, _dist_point_rect(q, r))
    return best


def arrows(boxes: dict, lines: list, blocks: list, labels: dict, slide_width: float) -> list[dict]:
    """[{from, to, label, method}] — `labels` maps the keys of plain text boxes (no fill, no outline) to their text;
    only those can be arrow labels."""
    tol, touch = TOL * slide_width, TOUCH * slide_width
    short = {k for k, t in labels.items() if 0 < len(t.strip()) <= LABEL_MAX}
    out: list[dict] = []

    def near_box(p, limit, allow_short):
        cand = [(d, k) for k, r in boxes.items() if (d := _dist_point_rect(p, r)) <= limit and (allow_short or k not in short)]
        return min(cand)[1] if cand else None

    # ---- connector networks
    ends = []                  # per line, per end: (box or None, has_head, glued, joins another line)
    for i, (path, h0, h1, g0, g1) in enumerate(lines):
        row = []
        for p, h, g in ((path[0], h0, g0), (path[-1], h1, g1)):
            if g in boxes:
                row.append((g, h, True, False))
                continue
            box = near_box(p, touch, allow_short=False)
            on_line = any(j != i and _dist_point_path(p, lines[j][0]) <= tol for j in range(len(lines)))
            if box is None and not on_line:
                box = near_box(p, tol, allow_short=False)
            row.append((box, h, False, box is None and on_line))
        ends.append(row)
    parent = list(range(len(lines)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, (path, *_rest) in enumerate(lines):
        for k, p in enumerate((path[0], path[-1])):
            if ends[i][k][3]:
                for j in range(len(lines)):
                    if j != i and _dist_point_path(p, lines[j][0]) <= tol:
                        parent[find(i)] = find(j)
    nets: dict[int, list[int]] = {}
    for i in range(len(lines)):
        nets.setdefault(find(i), []).append(i)
    for members in nets.values():
        at = [(ends[i][k], lines[i][0][0 if k == 0 else -1]) for i in members for k in (0, 1)]
        src = sorted({e[0] for e, _ in at if e[0] and not e[1]})
        heads = [(e[0], p) for e, p in at if e[0] and e[1]]
        dst = sorted({b for b, _ in heads})
        found = [{"from": s, "to": t, "label": None,
                  "method": "connector" if len(members) == 1 and all(e[2] for e, _ in at) else "connector_geometry"}
                 for s in src for t in dst if s != t]
        if not found:
            continue
        attached = {e[0] for e, _ in at}
        claims = {}                                   # target → (distance, label): the closest label wins
        for lk in sorted(short - attached):
            m = min(members, key=lambda i: _dist_rect_path(boxes[lk], lines[i][0]))
            dist = _dist_rect_path(boxes[lk], lines[m][0])
            if dist > tol:
                continue
            x, y, w, h = boxes[lk]
            c = (x + w / 2, y + h / 2)
            own = [(e[0], lines[m][0][0 if k == 0 else -1]) for k, e in enumerate(ends[m]) if e[0] and e[1]]
            if own:                      # the line it sits on ends in an arrowhead at a box
                target = min(own, key=lambda hp: math.hypot(hp[1][0] - c[0], hp[1][1] - c[1]))[0]
            else:                        # otherwise only an unambiguous network can take it
                target = found[0]["to"] if len(found) == 1 else None
            if target and sum(g["to"] == target for g in found) == 1 and (target not in claims or dist < claims[target][0]):
                claims[target] = (dist, lk)
        for f in found:
            if f["to"] in claims:
                f["label"] = claims[f["to"]][1]
        out += found
    # ---- block arrows: the nearest boxes behind the tail and ahead of the head, overlapping its width
    for x, y, w, h, d in blocks:
        vertical = d in ("up", "down")
        lo, hi = (x, x + w) if vertical else (y, y + h)
        reach = max(h if vertical else w, 3 * tol)
        before, after = [], []
        for k, r in boxes.items():
            a, b = (r[0], r[0] + r[2]) if vertical else (r[1], r[1] + r[3])
            if k in short or min(b, hi) - max(a, lo) <= 0:
                continue
            gb, ga = (y - (r[1] + r[3]), r[1] - (y + h)) if vertical else (x - (r[0] + r[2]), r[0] - (x + w))
            area = r[2] * r[3]          # equally near: the smaller, more specific box
            if -tol <= gb <= reach:
                before.append((round(gb / touch), area, k))
            if -tol <= ga <= reach:
                after.append((round(ga / touch), area, k))
        if before and after:
            a, b = min(before)[2], min(after)[2]
            s, t = (a, b) if d in ("down", "right") else (b, a)
            if s != t:
                out.append({"from": s, "to": t, "label": None, "method": "block_arrow"})
    seen, unique = set(), []
    for a in out:
        if (a["from"], a["to"]) not in seen:
            seen.add((a["from"], a["to"]))
            unique.append(a)
    return unique
