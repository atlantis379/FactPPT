from tools.codex_worker import asset_url_allowed


def test_locked_template_endpoint_is_allowed_only_for_its_project_and_role():
    assert asset_url_allowed('deck_a', 'academic_template', '/api/deck/workflows/deck_a/visual-template')
    assert asset_url_allowed('deck_a', 'design', '/api/deck/workflows/deck_a/generation/assets/g/cover/design')
    assert not asset_url_allowed('deck_a', 'academic_template', '/api/deck/workflows/deck_b/visual-template')
    assert not asset_url_allowed('deck_a', 'design', '/api/deck/workflows/deck_a/visual-template')
    assert not asset_url_allowed('deck_a', 'academic_template', 'https://external.example/image.png')
