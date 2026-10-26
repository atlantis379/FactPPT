"""Teaching-deck layouts, plus a display fact gate.

``select_layout`` chooses a teaching layout. ``gate_display`` checks one
original span against text that would go on a slide. Templates do not call
the gate.
"""

__all__ = ["select_layout", "gate_display", "canon", "extract_unit_slices"]


def select_layout(*args, **kwargs):
    from factdeck.layout_selector import select_layout as _select_layout

    return _select_layout(*args, **kwargs)


def gate_display(*args, **kwargs):
    from factdeck.facts import gate_display as _gate_display

    return _gate_display(*args, **kwargs)


def canon(*args, **kwargs):
    from factdeck.facts import canon as _canon

    return _canon(*args, **kwargs)


def extract_unit_slices(*args, **kwargs):
    from factdeck.facts import extract_unit_slices as _extract_unit_slices

    return _extract_unit_slices(*args, **kwargs)
