# Reliable PPT v0.3 Agent Governance Pack

Start here:
1. Read `AGENTS.md`.
2. Read `docs/specs/DEVELOPMENT_CONTRACT.md`.
3. Read `docs/specs/SYSTEM_SPEC_v0.3.md`.
4. Follow the active M0 contract in `docs/milestones/CURRENT.md`.
5. Run `python -m unittest discover -s tests/governance -v` and `python tools/governance/check.py --changed-file <path>` for local checks.
6. Complete independent audit and CI before marking M0 frozen. Future v0.2 schemas require an explicit frozen-manifest entry and a later milestone.

## Teaching-layout deck

This package has no HTTP `/api/deck`. The default generation entry is `factdeck.deck.build_deck`. `python -m factdeck.render` measures those pages; it does not fill slides on a second path.

`build_deck` slims a SUMMARY, selects a teaching layout, and renders it with `factdeck.html_templates.render_html`. Fact text on the page is whatever the display fact gate admits. A rejected or unreviewed fill is left out of the HTML. Chapter limits are `max_sections`, `max_pages`, and `bullets_per_section` on that call (`factdeck.summary.ChapterLimits`). A deck-wide card-wall check is not part of this entry. Cover, section, and comparison have no body template here.
