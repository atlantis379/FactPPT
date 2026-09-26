from app.visual_quality import issues


def test_severe_density_returns_to_content_instead_of_trying_another_box():
    plan = {"pages": [
        {"page_id": "p1", "selected_archetype": "EDITORIAL_STATEMENT",
         "elements": [{"name": "claim:c1", "text": "临床长段落" * 30,
                       "style": {"fontSize": 27}}]},
        {"page_id": "p2", "selected_archetype": "COMPARISON_COLUMNS",
         "elements": [{"name": "claim:c2", "text": "证据长段落" * 36,
                       "style": {"fontSize": 16}}]},
    ]}
    result = issues(plan)
    assert [(item["page_id"], item["code"], item["route"]) for item in result] == [
        ("p1", "FULL_PARAGRAPH_HERO", "UPSTREAM_CONTENT"),
        ("p2", "DENSE_SMALL_TYPE", "UPSTREAM_CONTENT")]
