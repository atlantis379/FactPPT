from tools.local_chapter_revision import selected_pages


def test_revision_selection_uses_exact_page_ids_and_all_nonentailed_targets():
    review = {"sections": [
        {"section_id": "S03:p1", "summary_verdict": "ENTAILED", "key_points": [{"verdict": "ENTAILED"}]},
        {"section_id": "S03:p2", "summary_verdict": "PARTIAL", "key_points": []}],
        "issues": [{"ref": "digest:S03:p11:key1", "severity": "BLOCKER", "problem": "Test issue"},
                   {"ref": "overall_summary", "severity": "BLOCKER", "problem": "S03:p1 in global context"}]}
    assert selected_pages(review) == {"S03:p2", "S03:p11"}
