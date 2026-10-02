"""The exported PPTX is structured, not flat: titles in title placeholders, theme colours and fonts, grouped items.

Content is invented test data.
"""
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from factdeck.render import THEMES, build_pptx, readback


def run(text, size=17, hexv="0E1B2C"):
    return {"text": text, "size": size, "bold": False, "color": {"hex": hexv.lower(), "a": 1}}


def box(x, y, w, h, paras, role="", group=""):
    return {"x": x, "y": y, "w": w, "h": h, "align": "left", "anchor": "top", "lineHeight": 26, "nowrap": False,
            "paras": paras, "role": role, "group": group}


def shape(x, y, w, h, hexv, group=""):
    return {"x": x, "y": y, "w": w, "h": h, "fill": {"hex": hexv.lower(), "a": 1}, "radius": 0, "line": None, "accents": [], "group": group}


def model(texts, shapes=()):
    return {"background": {"hex": "ffffff", "a": 1}, "rasters": [], "shapes": list(shapes), "lines": [], "figures": [], "tables": [], "texts": texts}


def test_titles_theme_and_groups(tmp_path):
    tokens = THEMES["navy-teal"]
    primary = tokens["primary"].lstrip("#")
    m1 = model([box(64, 60, 800, 46, [[run("页面标题", 34, primary)]], role="title"),
                box(100, 200, 300, 30, [[run("甲通路环节")]], group="p1:lane0"),
                box(100, 300, 300, 30, [[run("乙通路环节")]], group="p1:lane1")],
               [shape(80, 190, 500, 60, tokens["sky"].lstrip("#"), group="p1:lane0"),
                shape(80, 290, 500, 60, tokens["sky"].lstrip("#"), group="p1:lane1")])
    m2 = model([box(100, 200, 300, 30, [[run("没有标题的页")]])])
    out = tmp_path / "deck.pptx"
    build_pptx([m1, m2], {}, ["", ""], out, "测试", {}, "Microsoft YaHei", tokens)
    prs = Presentation(str(out))
    s1, s2 = prs.slides
    assert s1.shapes.title is not None and s1.shapes.title.text_frame.text == "页面标题"
    assert s2.shapes.title is None                                   # no empty placeholder left behind
    groups = [sh for sh in s1.shapes if sh.shape_type == MSO_SHAPE_TYPE.GROUP]
    assert len(groups) == 2 and all(len(g.shapes) == 2 for g in groups)
    xml = s1._element.xml
    assert 'schemeClr val="accent1"' in xml                           # the title colour refers to the theme
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    theme = prs.slide_master.part.part_related_by(RT.THEME).blob.decode("utf-8")
    assert 'typeface="Microsoft YaHei"' in theme and primary.upper() in theme
    fview = {"a": {"text": "甲通路环节"}, "b": {"text": "乙通路环节"}, "t": {"text": "页面标题"}}
    rb = readback(out, [["a", "b", "t"], []], fview)
    assert rb[0]["missing"] == []                                    # text inside groups and the placeholder is found
