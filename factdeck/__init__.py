"""Teaching-deck layouts: relation selector, HTML templates, measured native PPTX."""

__all__ = ["select_layout"]


def select_layout(*args, **kwargs):
    from factdeck.layout_selector import select_layout as _select_layout

    return _select_layout(*args, **kwargs)
