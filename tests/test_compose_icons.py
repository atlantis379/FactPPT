from factdeck import compose

FIGURE = {"figure": "图标把基因这一项和文字对上"}


def page(icon_for, design=FIGURE):
    p = {"layout": "composed", "blocks": [
        {"kind": "text", "id": "g", "role": "head", "refs": [{"fact": "gene"}], "x": 80, "y": 0, "w": 200, "h": 24},
        {"kind": "icon", "icon": "dna", "for": icon_for, "x": 0, "y": 0, "w": 64, "h": 64}]}
    if design is not None:
        p["design"] = design
    return p


def test_icon_stands_for_a_fact_shown_on_the_page():
    assert compose.structure_errors(page("gene")) == []


def test_icon_for_a_fact_not_on_the_page_is_refused():
    errors = compose.structure_errors(page("smoking"))
    assert any("图标需以 for 指明" in e for e in errors)


def test_icon_needs_a_file_id():
    p = page("gene")
    del p["blocks"][1]["icon"]
    assert any("图标需以 icon 指明" in e for e in compose.structure_errors(p))


def test_a_page_that_draws_states_its_figure_layer():
    errors = compose.structure_errors(page("gene", design=None))
    assert any("design.figure" in e for e in errors)
    errors = compose.structure_errors(page("gene", design={"figure": "  "}))
    assert any("design.figure" in e for e in errors)


def test_a_text_only_page_needs_no_figure_layer():
    p = page("gene", design=None)
    p["blocks"] = p["blocks"][:1]
    assert compose.structure_errors(p) == []


def line_page(**line):
    return {"layout": "composed", "design": {"figure": "曲线在 1 秒处标出 FEV1"}, "blocks": [
        {"kind": "text", "id": "v", "role": "note", "refs": [{"fact": "fev1"}], "x": 0, "y": 0, "w": 100, "h": 24},
        {"kind": "line", "points": [[0, 100], [200, 40]], **line}]}


def test_a_line_names_the_facts_it_draws_or_is_an_axis():
    assert any("encodes" in e for e in compose.structure_errors(line_page()))
    assert compose.structure_errors(line_page(encodes=["fev1"])) == []
    assert compose.structure_errors(line_page(axis=True)) == []


def test_a_headline_page_takes_its_title_from_a_fact_and_has_no_lead():
    from factdeck.deck import _structure
    p = page("gene")
    p.update(title={"fact": "gene"}, headline=True)
    assert not any("headline" in e for e in _structure(p))
    p["title"] = {"text": "主题"}
    assert any("headline" in e for e in _structure(p))
    p.update(title={"fact": "gene"}, lead={"fact": "gene"})
    assert any("headline" in e for e in _structure(p))
