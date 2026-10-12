from factdeck.content_obligations import build_obligations, validate_deck


def _base(*, main_quote="主事实；仅条件甲时适用", main_display="主事实",
          unit_text="主事实；仅条件甲时适用", condition_quote="仅条件甲时适用",
          facts_extra=None, context_responses=None):
    units = [{"id": "u-main", "text": unit_text}, {"id": "u-foot", "text": "脚注：仅适用于条件甲"}]
    claim = {"id": "p1#c1", "unit_ids": ["u-main"],
             "spans": [{"unit_id": "u-main", "quote": unit_text}],
             "scope": {"population": "", "condition": "仅条件甲时适用"}}
    facts = {
        "main": {"id": "main", "unit": "u-main", "quote": main_quote, "display": main_display,
                 "status": "ACCEPTED", "needs_confirmation": False},
        "condition": {"id": "condition", "unit": "u-main", "quote": condition_quote, "display": condition_quote,
                      "status": "ACCEPTED", "needs_confirmation": False},
        "foot": {"id": "foot", "unit": "u-foot", "quote": "脚注：仅适用于条件甲", "display": "脚注：仅适用于条件甲",
                 "status": "ACCEPTED", "needs_confirmation": False},
    }
    facts.update(facts_extra or {})
    w = {"sources": [{"id": "s1", "units": units, "claims": {"items": [claim]}}],
         "summary": {"sections": []}, "facts": {"result": {"facts": list(facts.values())}},
         "semantic_bundles": [], "deck": None}
    page = {"id": "p1", "layout": "bullets", "items": [{"fact": "main"}],
            "design": {"fact": "condition"}, "notes": [{"fact": "foot"}]}
    responses = context_responses or []
    return w, {"pages": [page], "context_responses": responses}, {"facts": facts}, {"pages": [{"id": "p1", "facts": ["main"]}]}


def _show(deck, chk, *facts):
    deck["pages"][0]["items"].extend({"fact": f} for f in facts)
    chk["pages"][0]["facts"].extend(facts)


def test_missing_condition_is_blocking_and_visible_fact_clears_it():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    got = validate_deck(w, deck, verified, chk)
    assert any("condition" in e and "主事实" in e for e in got["errors"])
    _show(deck, chk, "condition")
    assert not validate_deck(w, deck, verified, chk)["errors"]


def test_unselected_claim_condition_does_not_create_pending():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    chk["pages"][0]["facts"] = []
    result = validate_deck(w, deck, verified, chk)
    assert result["pending"] == []
    assert not any("claim:" in p for p in result["pending"])


def test_multispan_claim_does_not_use_any_fragment_as_primary():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    w["sources"][0]["claims"]["items"][0]["spans"].append({"unit_id": "u-foot", "quote": "脚注：仅适用于条件甲"})
    w["sources"][0]["claims"]["items"][0]["unit_ids"].append("u-foot")
    built = build_obligations(w, deck, verified)
    assert built["obligations"][0]["primary_fact_refs"] == []
    result = validate_deck(w, deck, verified, chk)
    assert not any("claim:" in e for e in result["errors"])
    assert any("unique primary fact" in x or "唯一主事实" in x for x in result["warnings"])


def test_explicit_footnote_bundle_requires_source_backed_display():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    w["semantic_bundles"] = [{"id": "b-foot", "role": "footnote", "source_unit_refs": ["u-foot"],
                              "primary_fact_refs": ["main"], "dependent_fact_refs": ["foot"],
                              "relationship_status": "SUPPORTED", "relationship_evidence": "u-foot"}]
    got = validate_deck(w, deck, verified, chk)
    assert any("footnote" in e for e in got["errors"])
    _show(deck, chk, "foot", "condition")
    assert not validate_deck(w, deck, verified, chk)["errors"]


def test_design_and_notes_are_not_coverage():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    deck["pages"][0]["design"]["fact"] = "condition"
    deck["pages"][0]["notes"] = [{"fact": "condition"}]
    assert any("未同页显示" in e for e in validate_deck(w, deck, verified, chk)["errors"])


def test_focus_only_does_not_count_as_visible_coverage():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    deck["pages"][0]["focus"] = {"fact": "condition"}
    assert any("未同页显示" in e for e in validate_deck(w, deck, verified, chk)["errors"])


def test_quote_contains_scope_but_display_hides_it():
    extra = {"condition-hidden": {"id": "condition-hidden", "unit": "u-main",
             "quote": "仅条件甲时适用", "display": "适用", "status": "ACCEPTED"}}
    w, deck, verified, chk = _base(facts_extra=extra)
    w["facts"]["result"]["facts"] = [f for f in w["facts"]["result"]["facts"] if f["id"] != "condition"]
    verified["facts"].pop("condition")
    _resolve_signals_as_human(w, deck)
    got = validate_deck(w, deck, verified, chk)
    assert any("没有显示含原文限定" in e for e in got["errors"])


def test_multiple_dependent_facts_all_required():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    w["semantic_bundles"] = [{"id": "all-deps", "role": "context", "source_unit_refs": ["u-foot"],
                              "primary_fact_refs": ["main"], "dependent_fact_refs": ["foot", "condition"],
                              "relationship_status": "SUPPORTED", "relationship_evidence": "u-foot"}]
    _show(deck, chk, "foot")
    assert any("context" in e for e in validate_deck(w, deck, verified, chk)["errors"])


def test_carved_fact_with_scope_quote_cannot_bypass_binding():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    carved = {"id": "cut-main", "unit": "u-main", "quote": "主事实；仅条件甲时适用",
              "display": "主事实", "status": "ACCEPTED"}
    deck["facts"] = [carved]
    verified["facts"]["cut-main"] = carved
    _show(deck, chk, "cut-main")
    assert any("限定" in e for e in validate_deck(w, deck, verified, chk)["errors"])


def test_unknown_fact_reference_in_bundle_is_rejected():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    w["semantic_bundles"] = [{"id": "bad", "role": "limit", "source_unit_refs": ["u-foot"],
                              "primary_fact_refs": ["does-not-exist"], "dependent_fact_refs": ["foot"],
                              "relationship_status": "SUPPORTED", "relationship_evidence": "u-foot"}]
    assert any("不存在的事实" in e for e in validate_deck(w, deck, verified, chk)["errors"])


def test_unknown_relationship_is_retained_for_human_without_guessing():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    w["semantic_bundles"] = [{"id": "unclear", "role": "context", "source_unit_refs": ["u-foot"],
                              "primary_fact_refs": ["main"], "dependent_fact_refs": ["foot"],
                              "relationship_status": "UNKNOWN", "relationship_evidence": "u-foot"}]
    result = validate_deck(w, deck, verified, chk)
    assert any("尚未确认" in p for p in result["pending"])
    assert not any("context" in e for e in result["errors"])


def test_summary_limit_role_binds_core_fact_to_limiting_fact():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    w["summary"]["sections"] = [{"id": "s1", "message": {"core": {"claim_id": "p1#c1"},
                                             "roles": {"point-limit": "limit"}},
                                  "point_coverage": [{"point_id": "point-limit", "unit_ids": ["u-foot"]}]}]
    result = validate_deck(w, deck, verified, chk)
    assert any("limit" in e and "main" in e for e in result["errors"])
    _show(deck, chk, "foot")
    assert not any("limit" in e for e in validate_deck(w, deck, verified, chk)["errors"])


def test_unconfirmed_transcription_is_pending_for_formal_render_gate():
    extra = {"transcribed": {"id": "transcribed", "unit": "u-foot", "quote": "转录数字", "display": "转录数字",
                             "status": "ACCEPTED", "needs_confirmation": True}}
    w, deck, verified, chk = _base(facts_extra=extra)
    _resolve_signals_as_human(w, deck)
    _show(deck, chk, "transcribed")
    assert any("待确认转录事实 transcribed" in p for p in validate_deck(w, deck, verified, chk)["pending"])


def test_page_notes_are_visible_but_speaker_notes_are_not():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    w["semantic_bundles"] = [{"id": "foot", "role": "footnote", "source_unit_refs": ["u-foot"],
                              "primary_fact_refs": ["main"], "dependent_fact_refs": ["foot"],
                              "relationship_status": "SUPPORTED", "relationship_evidence": "u-foot"}]
    chk["pages"][0]["facts"].extend(["foot", "condition"])  # checker includes rendered page note and condition item
    assert not validate_deck(w, deck, verified, chk)["errors"]
    deck["pages"][0]["speaker_notes"] = [{"fact": "foot"}]
    chk["pages"][0]["facts"] = ["main"]
    assert any("footnote" in e for e in validate_deck(w, deck, verified, chk)["errors"])


def test_source_transcriptions_and_human_confirmation_are_resolved():
    w, deck, verified, chk = _base()
    w["sources"][0]["transcriptions"] = [{"id": "u-trans", "text": "原转录", "second_read": {"agree": False}}]
    w["confirmations"] = {"transcriptions": {"u-trans": {"decision": "CONFIRM", "text": "确认文本"}}}
    built = build_obligations(w)
    assert built["context_signals"] == {}
    # The registry includes transcribed units as valid source anchors.
    w["semantic_bundles"] = [{"id": "trans-bound", "role": "context", "source_unit_refs": ["u-trans"],
                              "primary_fact_refs": ["main"], "dependent_fact_refs": ["foot"],
                              "relationship_status": "SUPPORTED", "relationship_evidence": "u-trans"}]
    result = validate_deck(w, deck, verified, chk)
    assert not any("有效来源单元" in e for e in result["errors"])


def test_separate_transcription_proposal_is_a_pending_source_unit():
    w, deck, verified, chk = _base()
    _resolve_signals_as_human(w, deck)
    w["transcription_proposals"] = [{"id": "correction:S01:p1", "source_id": "S01", "page_id": "S01:p1",
                                     "text": "人工更正待核对", "needs_confirmation": True}]
    f = {"id": "proposal-fact", "unit": "correction:S01:p1", "quote": "人工更正待核对",
         "display": "人工更正待核对", "status": "ACCEPTED", "needs_confirmation": True}
    verified["facts"][f["id"]] = f
    w["semantic_bundles"] = [{"id": "proposal", "role": "context", "source_unit_refs": ["correction:S01:p1"],
                              "primary_fact_refs": ["main"], "dependent_fact_refs": ["proposal-fact"],
                              "relationship_status": "SUPPORTED", "relationship_evidence": "correction:S01:p1"}]
    _show(deck, chk, "condition", "proposal-fact")
    result = validate_deck(w, deck, verified, chk)
    assert not any("有效来源单元" in e for e in result["errors"])
    assert any("proposal-fact" in p for p in result["pending"])


def test_context_signal_requires_response_and_excerpt_marker():
    w, deck, verified, chk = _base(main_quote="但是主事实", main_display="但是主事实", unit_text="前句；但是主事实")
    w["sources"][0]["claims"]["items"][0]["scope"]["condition"] = ""
    w["facts"]["result"]["facts"] = [verified["facts"]["main"]]
    result = validate_deck(w, deck, verified, chk)
    assert any("context_responses" in e for e in result["errors"])
    deck["context_responses"] = [{"signal_id": sig, "state": "EXCERPT", "reason": "只呈现本段", "marker": "节选",
                                  "evidence_refs": ["p1"]}
                                 for sig in build_obligations(w, deck, verified)["context_signals"]]
    deck["pages"][0]["subtitle"] = {"text": "节选"}
    assert not validate_deck(w, deck, verified, chk)["errors"]


def test_irrelevant_page_fact_cannot_cover_context_signal():
    w, deck, verified, chk = _base(main_quote="但是主事实", main_display="但是主事实", unit_text="前句；但是主事实")
    w["sources"][0]["claims"]["items"][0]["scope"]["condition"] = ""
    w["facts"]["result"]["facts"] = [verified["facts"]["main"]]
    sig = next(iter(build_obligations(w, deck, verified)["context_signals"]))
    deck["pages"].append({"id": "p2", "items": [{"fact": "foot"}]})
    chk["pages"].append({"id": "p2", "facts": ["foot"]})
    deck["context_responses"] = [{"signal_id": sig, "state": "COVERED", "reason": "有引用", "evidence_refs": ["foot"]}]
    assert any("依赖事实" in e for e in validate_deck(w, deck, verified, chk)["errors"])


def _resolve_signals_as_human(w, deck):
    deck["context_responses"] = [{"signal_id": sid, "state": "NEEDS_HUMAN", "reason": "测试中保留待人工判断",
                                  "evidence_refs": ["u-main"]}
                                 for sid in build_obligations(w)["context_signals"]]


def test_old_project_without_obligations_remains_compatible():
    w = {"sources": [], "summary": {"sections": []}, "facts": {"result": {"facts": []}}}
    result = validate_deck(w, {"pages": [{"id": "p1", "items": [{"text": "旧项目"}]}]}, {"facts": {}}, {"pages": []})
    assert result == {"errors": [], "pending": [], "warnings": []}
