"""Teaching-deck layouts, a display fact gate, and per-slot provenance.

``select_layout`` chooses a teaching layout. ``gate_display`` checks one
original span. ``trace_slide`` binds each measured slot to a source slice
and admits it only through that gate.
"""

__all__ = [
    "select_layout",
    "gate_display",
    "canon",
    "extract_unit_slices",
    "trace_slide",
    "bind_layout",
    "gate_keeps_display",
]


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


def trace_slide(*args, **kwargs):
    from factdeck.slots import trace_slide as _trace_slide

    return _trace_slide(*args, **kwargs)


def bind_layout(*args, **kwargs):
    from factdeck.slots import bind_layout as _bind_layout

    return _bind_layout(*args, **kwargs)


def gate_keeps_display(*args, **kwargs):
    from factdeck.slots import gate_keeps_display as _gate_keeps_display

    return _gate_keeps_display(*args, **kwargs)
