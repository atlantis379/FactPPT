"""Teaching-deck layouts, a display fact gate, and per-slot provenance.

``select_layout`` chooses a teaching layout. ``gate_display`` checks one
original span. ``trace_slide`` binds each measured slot to a source slice
and admits it only through that gate. ``factdeck.deck.build_deck`` is the
default deck entry: template pages only, with no HTTP ``/api/deck``.
It slims a SUMMARY before layout selection, omits a dangling half-sentence,
and refuses an equal card wall that admitted facts do not differentiate.
"""

__all__ = [
    "select_layout",
    "gate_display",
    "canon",
    "extract_unit_slices",
    "trace_slide",
    "bind_layout",
    "gate_keeps_display",
    "prepare_deck",
    "summary_from_slides",
    "summary_from_outline",
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


def prepare_deck(*args, **kwargs):
    from factdeck.summary import prepare_deck as _prepare_deck

    return _prepare_deck(*args, **kwargs)


def summary_from_slides(*args, **kwargs):
    from factdeck.summary import summary_from_slides as _summary_from_slides

    return _summary_from_slides(*args, **kwargs)


def summary_from_outline(*args, **kwargs):
    from factdeck.summary import summary_from_outline as _summary_from_outline

    return _summary_from_outline(*args, **kwargs)
