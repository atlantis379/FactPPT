from pathlib import Path

from app.main import Claim, ClaimBindingPatch, ClaimRevisionRequest, ClaimSupersessionRequest, ContextContractRequest, ExternalFindingRequest, ExternalSource, GeneratedVisualVerificationRequest, GenerationCapabilityChangeRequest, GenerationExecutionRequest, HumanOverrideRequest, IssueRouteRequest, MedicalVisualAssetRequest, NumericFact, PageOrderRequest, PageSpec, Project, Relationship, ReviewDecisionRequest, RetryBudgetRequest, SourcePriorityPolicyRequest, SourceRef, SyntheticCaseRequest, TriageOverrideRequest, VisualBindingRequest, apply_source_priority_policy, architect, authorize_agent_write, canonicalize_claims, capability_gate, classify_cross_source_conflict, compliance, compile_prompt_briefs, compile_visual_contracts, configure_retry_budget, create_claim_revision, create_external_finding, create_human_override, create_synthetic_case, delivery_manifest, duration_assessment, enforce_policy_gate, immutable_snapshot_digest, invalidate_generation_capability, medical_review_sheet, override_triage_decision, persist_verification_issue_lifecycle, policy_gate, qualify_external_source, record_generation_execution, record_verification, register_claim_supersession, register_context_contract, register_medical_visual_asset, register_visual_binding, reorder_pages, review_object, route_verification_issue, rule_registry, select_generation_route, select_visual_strategy, semantic_deck, source_extractor, source_version_relation, triage_claims, update_claim_binding, validate, verifier, verify_generated_visual_contract, visual_router
from app.packager import build_pptx, verify_pptx
from app.model_adapter import record_run


def documented(text: str, *, doc_id: str = "d", page: int = 1) -> list[dict]:
    """``documents=[...]`` whose page text contains ``text``.

    P0-2 requires a SOURCE claim's source_ref to resolve to an uploaded document
    page and to contain both the ref quote and the claim's source_quote, so a
    bare ``document_id`` is no longer accepted as provenance. Fixtures must carry
    real chunks.
    """
    return [{"id": doc_id, "chunks": [{"page": page, "text": text}]}]


def record_current_route_components(project: Project, contract: dict) -> None:
    plan = next(plan for plan in project.visual_plans if plan["page_id"] == contract["page_id"])
    for position, component in enumerate(plan["effective_generation_route"]["component_routes"], start=1):
        component_id = component["component"]
        strategy = (
            "VERIFIED_MEDICAL_ASSET_RENDERER" if component_id.startswith("medical_visual_asset:") else
            "CONTROLLED_COMPOSITION" if component_id == "protected_semantic_layer" else
            "PROMPT_DRIVEN_IMAGE" if component_id == "editorial_background" else
            "FULL_IMAGE"
        )
        record_generation_execution(project, GenerationExecutionRequest(
            page_id=contract["page_id"], visual_generation_contract_id=contract["visual_generation_contract_id"], component=component_id, strategy=strategy,
            engine_id=component["engine_id"], engine_version=component["engine_version"], operation="RENDER",
            output_asset_id=f"asset-{position}", output_asset_version="1", deterministic_spec_ref=f"test:{component_id}",
        ))


def test_source_claim_requires_quote_and_reference():
    result = validate(Project(title="t", presentation_question="q", claims=[Claim(normalized_claim="x", provenance="SOURCE")]))
    assert result["status"] == "BLOCK"
    assert any(issue["rule"] == "CT-01" for issue in result["issues"])


def test_red_unbound_numeric_is_delivery_blocker():
    claim = Claim(normalized_claim="red number", provenance="SOURCE", source_quote="20", risk="RED", source_refs=[SourceRef(document_id="d", page=1, quote="20")], numeric_facts=[NumericFact(value="20", status="UNBOUND")])
    result = validate(Project(title="t", presentation_question="q", claims=[claim]))
    assert result["status"] == "BLOCK"
    assert any(issue["rule"] == "DB-01" for issue in result["issues"])


def test_red_synthesis_relationship_requires_human_review_not_silent_pass():
    a = Claim(id="a", normalized_claim="a", provenance="SUMMARY")
    b = Claim(id="b", normalized_claim="b", provenance="SUMMARY")
    rel = Relationship(from_claim_id="a", to_claim_id="b", relation_type="CAUSAL", provenance="SYNTHESIS", risk="RED")
    result = validate(Project(title="t", presentation_question="q", claims=[a, b], relationships=[rel]))
    assert result["status"] == "HUMAN_REVIEW_REQUIRED"
    assert any(issue["rule"] == "CR-13" for issue in result["issues"])


def test_human_approved_red_synthesis_relationship_can_reenter_verification_with_audit():
    first = Claim(id="a", normalized_claim="A", provenance="SUMMARY")
    second = Claim(id="b", normalized_claim="B", provenance="SUMMARY")
    relation = Relationship(id="r", from_claim_id="a", to_claim_id="b", relation_type="CLINICAL_PATHWAY", provenance="SYNTHESIS", risk="RED")
    project = Project(title="t", presentation_question="q", claims=[first, second], relationships=[relation])
    request = ReviewDecisionRequest(object_type="relationship", object_id="r", decision="APPROVE", reviewer="reviewer", rationale="Source spans and synthesis scope reviewed by medical reviewer.")
    event = review_object(project, request)
    assert event["decision"] == "APPROVE"
    assert relation.status == "SUPPORTED"
    assert relation.review_status == "APPROVED"
    assert validate(project)["status"] == "PASS"
    assert verifier(project)["status"] == "PASS"


def test_public_channel_blocks_unreviewed_red_claim():
    red = Claim(normalized_claim="risk", provenance="SUMMARY", risk="RED")
    result = validate(Project(title="t", presentation_question="q", output_channel="public_xiaohongshu", claims=[red]))
    assert result["status"] == "BLOCK"
    assert any(issue["rule"] == "CP-01" for issue in result["issues"])


def test_source_extractor_is_conservative_and_creates_no_relationships():
    project = Project(title="t", presentation_question="COPD 风险", documents=[{"id": "doc1", "chunks": [{"page": 2, "text": "过去一年≥1次中重度急性加重需要评估。无症状低风险人群不建议普遍筛查。"}]}])
    claims = source_extractor(project, "doc1")
    assert len(claims) == 2
    assert all(claim.provenance == "SOURCE" and claim.source_quote for claim in claims)
    assert all(claim.source_refs[0].page == 2 for claim in claims)


def test_source_extractor_atomizes_explicit_semicolon_propositions_without_losing_scope():
    project = Project(title="t", presentation_question="筛查范围", documents=[{"id": "doc1", "chunks": [{"page": 3, "text": "对于高危人群，应进行肺功能检查；无症状低风险人群不建议普遍筛查。"}]}])
    claims = source_extractor(project, "doc1")
    assert len(claims) == 2
    assert claims[0].source_quote == "对于高危人群，应进行肺功能检查；无症状低风险人群不建议普遍筛查。"
    assert "高危人群" in claims[0].conditions
    assert claims[0].normalized_claim != claims[1].normalized_claim
    assert project.relationships == []


def test_triage_preserves_conditions_and_architect_never_creates_edges():
    claim = Claim(id="c1", normalized_claim="COPD 风险分层需要保留时间窗", provenance="SOURCE", source_quote="COPD 风险分层需要保留时间窗", source_refs=[SourceRef(document_id="d", page=1, quote="COPD 风险分层需要保留时间窗")], conditions=["过去一年"])
    project = Project(title="t", presentation_question="COPD 风险分层", claims=[claim])
    decisions = triage_claims(project)
    plan, pages = architect(project)
    assert decisions[0].meaning_preserving_bundle == ["过去一年"]
    assert decisions[0].bucket == "MUST_INCLUDE"
    assert plan.narrative_spine == "COPD 风险分层"
    assert pages and project.relationships == []


def test_triage_requests_user_input_when_must_content_exceeds_duration_budget():
    claims = [
        Claim(id="c1", normalized_claim="COPD 风险分层需要保留时间窗", provenance="SOURCE", source_quote="COPD 风险分层需要保留时间窗", source_refs=[SourceRef(document_id="d", page=1, quote="x")], conditions=["过去一年"]),
        Claim(id="c2", normalized_claim="COPD 风险分层需要保留事件定义", provenance="SOURCE", source_quote="COPD 风险分层需要保留事件定义", source_refs=[SourceRef(document_id="d", page=1, quote="x")], conditions=["中重度事件"]),
    ]
    project = Project(title="t", presentation_question="COPD 风险分层", duration_minutes=1, claims=claims)
    assessment = duration_assessment(project, triage_claims(project))
    assert assessment["needs_user_input"] is True
    assert assessment["must_include_claim_ids"] == ["c1", "c2"]


def test_triage_audience_profile_changes_buckets_with_explainable_reasons():
    claims = [
        Claim(id="evidence", normalized_claim="COPD 研究证据需要比较结局和局限", provenance="SOURCE", source_quote="x", source_refs=[SourceRef(document_id="d", page=1, quote="x")]),
        Claim(id="pathway", normalized_claim="COPD 筛查诊断路径需要保留检查条件", provenance="SOURCE", source_quote="x", source_refs=[SourceRef(document_id="d", page=1, quote="x")]),
        Claim(id="concept", normalized_claim="COPD 疾病活动度概念需要区分控制", provenance="SOURCE", source_quote="x", source_refs=[SourceRef(document_id="d", page=1, quote="x")]),
    ]
    specialist = Project(title="t", presentation_question="COPD", audience="呼吸科专家", claims=[claim.model_copy(deep=True) for claim in claims])
    student = Project(title="t", presentation_question="COPD", audience="医学生", claims=[claim.model_copy(deep=True) for claim in claims])
    specialist_buckets = {item.claim_id: item.bucket for item in triage_claims(specialist)}
    student_buckets = {item.claim_id: item.bucket for item in triage_claims(student)}
    assert specialist_buckets != student_buckets
    assert specialist_buckets["evidence"] == "MUST_INCLUDE"
    assert student_buckets["concept"] == "MUST_INCLUDE"
    assert "audience_profile=specialist" in triage_claims(specialist)[0].reason


def test_architect_changes_sequence_for_audience_without_creating_edges():
    claims = [
        Claim(id="evidence", normalized_claim="COPD 研究证据需要比较结局和局限", provenance="SOURCE", source_quote="x", source_refs=[SourceRef(document_id="d", page=1, quote="x")], triage="MUST_INCLUDE"),
        Claim(id="pathway", normalized_claim="COPD 筛查诊断路径需要保留检查条件", provenance="SOURCE", source_quote="x", source_refs=[SourceRef(document_id="d", page=1, quote="x")], triage="MUST_INCLUDE"),
        Claim(id="concept", normalized_claim="COPD 疾病活动度概念需要区分控制", provenance="SOURCE", source_quote="x", source_refs=[SourceRef(document_id="d", page=1, quote="x")], triage="MUST_INCLUDE"),
    ]
    specialist = Project(title="t", presentation_question="COPD", audience="专科专家", claims=[claim.model_copy(deep=True) for claim in claims])
    student = Project(title="t", presentation_question="COPD", audience="医学生", claims=[claim.model_copy(deep=True) for claim in claims])
    specialist_plan, specialist_pages = architect(specialist)
    student_plan, student_pages = architect(student)
    assert specialist_pages[0].visual_type == "EVIDENCE_MAP"
    assert student_pages[0].visual_type == "CONCEPTUAL_FRAMEWORK"
    assert specialist_plan.audience_strategy.startswith("specialist")
    assert student.relationships == specialist.relationships == []


def test_architect_splits_over_capacity_page_without_omitting_selected_claims():
    claims = [
        Claim(id=f"c{index}", normalized_claim=f"COPD 研究证据 {index}", provenance="SOURCE", source_quote="x", source_refs=[SourceRef(document_id="d", page=1, quote="x")], triage="MUST_INCLUDE")
        for index in range(5)
    ]
    project = Project(title="t", presentation_question="COPD", claims=claims)
    _, pages = architect(project)
    assert len(pages) == 2
    assert all(len(page.claim_ids) <= 4 for page in pages)
    assert {claim_id for page in pages for claim_id in page.claim_ids} == {claim.id for claim in claims}


def test_page_order_override_is_auditable_and_invalidates_prior_verification():
    claim = Claim(id="c", normalized_claim="Sourced fact", provenance="SOURCE", source_quote="Sourced fact", source_refs=[SourceRef(document_id="d", page=1, quote="Sourced fact")])
    first = PageSpec(id="p1", title="Sourced fact", primary_message="Sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    second = PageSpec(id="p2", title="Sourced fact", primary_message="Sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="q", claims=[claim], pages=[first, second])
    project.verification_results = [verifier(project)]
    event = reorder_pages(project, PageOrderRequest(page_ids=["p2", "p1"], editor="editor", rationale="Teaching flow begins with the synthesis page."))
    assert event["before_page_ids"] == ["p1", "p2"]
    assert [page.id for page in project.pages] == ["p2", "p1"]
    assert event["invalidated_verification_results"] == 1
    assert project.verification_results[0]["stale"] is True


def test_validation_blocks_manual_page_that_exceeds_renderer_claim_capacity():
    claims = [Claim(id=f"c{index}", normalized_claim=f"Claim {index}", provenance="SUMMARY") for index in range(5)]
    page = PageSpec(id="p", title="Claim", primary_message="Claim", visual_type="EVIDENCE_MAP", claim_ids=[claim.id for claim in claims], provenance="SUMMARY", goal="teach")
    result = validate(Project(title="t", presentation_question="q", claims=claims, pages=[page]))
    assert any(issue["rule"] == "AR-04" and "four Claims" in issue["message"] for issue in result["issues"])


def test_verifier_and_router_protect_red_semantic_content():
    red = Claim(id="r", normalized_claim="RED threshold 20 %", provenance="SOURCE", source_quote="RED threshold 20 %", risk="RED", source_refs=[SourceRef(document_id="d", page=1, quote="RED threshold 20 %")], conditions=["population"], numeric_facts=[NumericFact(value="20", unit="%", metric="risk", population="adults", timeframe="12 months", outcome="adverse event", intervention="treatment", comparator="control", statistic_type="proportion")], triage="MUST_INCLUDE")
    # P0-1: the magnitude must actually appear in the source quote.
    project = Project(title="t", presentation_question="risk", claims=[red],
                      documents=documented("RED threshold 20 % in adults."))
    _, project.pages = architect(project)
    result = verifier(project)
    plans = visual_router(project)
    assert result["status"] in {"PASS", "HUMAN_REVIEW_REQUIRED"}
    assert plans[0]["generation_mode"] == "DETERMINISTIC_COMPOSITOR"
    assert plans[0]["protected_semantic_layer"][0]["claim_id"] == "r"


def test_human_review_cannot_approve_unbound_red_numeric():
    red = Claim(id="r", normalized_claim="threshold", provenance="SOURCE", source_quote="threshold", risk="RED", source_refs=[SourceRef(document_id="d", page=1, quote="threshold")], conditions=["population"], numeric_facts=[NumericFact(value="20", status="UNBOUND")])
    project = Project(title="t", presentation_question="risk", claims=[red])
    request = ReviewDecisionRequest(object_type="claim", object_id="r", decision="APPROVE", reviewer="reviewer", rationale="reviewed source")
    try:
        review_object(project, request)
    except Exception as error:
        assert "binding" in str(error).lower()
    else:
        raise AssertionError("unbound RED numeric was approved")


def test_semantic_deck_can_export_only_when_gates_pass():
    claim = Claim(id="c", normalized_claim="Low risk sourced fact", provenance="SOURCE", source_quote="Low risk sourced fact", risk="GREEN", source_refs=[SourceRef(document_id="d", page=1, quote="Low risk sourced fact")], conditions=["context"], review_status="APPROVED")
    page = PageSpec(id="p", title="Low risk sourced fact", primary_message="Low risk sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[claim],
                      pages=[page], documents=documented("Low risk sourced fact"))
    # the record must be PERSISTED and PASS before export is allowed
    assert record_verification(project)["status"] == "PASS"
    deck = semantic_deck(project)
    assert deck["export_type"] == "APPROVED_SEMANTIC_DECK_JSON"
    assert deck["pages"][0]["claims"][0]["id"] == "c"


def test_policy_engine_disallows_visual_routing_without_passed_gates():
    project = Project(title="t", presentation_question="q", workflow_state="COMPLIANCE_REVIEW")
    decision = policy_gate(project, "route_visuals")
    assert decision["status"] == "BLOCK"
    assert "verification" in decision["message"].lower()
    assert decision["evaluated_rule_ids"] == ["VG-07", "VG-09"]


def test_blocked_policy_gate_persists_structured_violation_record(monkeypatch):
    monkeypatch.setattr("app.main.save_projects", lambda projects: None)
    project = Project(title="t", presentation_question="q", workflow_state="COMPLIANCE_REVIEW")
    try:
        enforce_policy_gate([project], project, "route_visuals")
    except Exception as error:
        assert "verification" in str(error).lower()
    else:
        raise AssertionError("policy gate unexpectedly allowed routing")
    assert {record["rule_id"] for record in project.violation_records} == {"VG-07", "VG-09"}
    assert all(record["status"] == "OPEN" for record in project.violation_records)


def test_frozen_rule_registry_has_required_governance_fields_and_unique_ids():
    registry = rule_registry()
    assert registry["status"] == "PASS"
    assert registry["incomplete"] == []
    assert registry["duplicate_ids"] == []


def test_conflicting_multi_source_numeric_claims_are_grouped_not_merged():
    first = Claim(normalized_claim="风险阈值为 20%", provenance="SOURCE", source_quote="风险阈值为 20%", source_refs=[SourceRef(document_id="d1", page=1, quote="20%")], numeric_facts=[NumericFact(value="20%")])
    second = Claim(normalized_claim="风险阈值为 30%", provenance="SOURCE", source_quote="风险阈值为 30%", source_refs=[SourceRef(document_id="d2", page=1, quote="30%")], numeric_facts=[NumericFact(value="30%")])
    result = canonicalize_claims([first, second])
    assert result["conflict_groups"] == 1
    assert first.conflict_group_id == second.conflict_group_id
    assert first.numeric_facts[0].value != second.numeric_facts[0].value
    result = validate(Project(title="t", presentation_question="risk", claims=[first, second]))
    assert any(issue["rule"] == "CF-01" for issue in result["issues"])


def test_cross_source_context_difference_is_not_labeled_direct_contradiction():
    result = classify_cross_source_conflict({"population": "Population A", "value": "20%"}, {"population": "Population B", "value": "30%"})
    assert result["status"] == "CONTEXT_DIFFERENCE"
    assert result["conflict_type"] is None


def test_cross_source_recommendation_disagreement_has_a_typed_conflict():
    result = classify_cross_source_conflict({"population": "Adults", "condition": "COPD", "recommendation": "recommended"}, {"population": "Adults", "condition": "COPD", "recommendation": "not recommended"})
    assert result["status"] == "CONFLICT"
    assert result["conflict_type"] == "RECOMMENDATION_DIFFERENCE"


def test_publication_date_alone_does_not_create_supersession():
    assert source_version_relation({"id": "2026", "date": "2026"}, {"id": "2024", "date": "2024"}) == "UNKNOWN"


def test_external_verification_is_opt_in_qualified_and_isolated_from_user_claims():
    claim = Claim(id="c", normalized_claim="User source threshold", provenance="SOURCE", source_quote="threshold", source_refs=[SourceRef(document_id="user", page=1, quote="threshold")])
    project = Project(title="t", presentation_question="q", claims=[claim])
    source = ExternalSource(source_type="Guideline", organization="Medical Society", date_or_version="2026", primary_or_secondary="PRIMARY", official_or_regulatory_status="OFFICIAL", jurisdiction="CN", identifier="guideline-2026")
    request = ExternalFindingRequest(source=source, finding_text="External guideline reports a different threshold.", risk="RED", verified_as_of="2026-09-04", search_scope="User-supplied external guideline metadata", source_claim_ids=["c"])
    try:
        create_external_finding(project, request)
    except Exception as error:
        assert "disabled" in str(error).lower()
    else:
        raise AssertionError("external verification was accepted without explicit opt-in")
    project.external_medical_check = True
    project.verification_mode = "EXTERNAL_MEDICAL_CHECK"
    finding = create_external_finding(project, request)
    assert finding["provenance"] == "EXTERNAL_VERIFICATION"
    assert finding["source_pool"] == "EXTERNAL_VERIFICATION_POOL"
    assert finding["auto_update_user_source"] is False
    assert len(project.claims) == 1
    assert project.claims[0].provenance == "SOURCE"
    assert qualify_external_source(source)["status"] == "QUALIFIED"


def test_retracted_or_unqualified_external_source_cannot_support_red_finding():
    project = Project(title="t", presentation_question="q", verification_mode="EXTERNAL_MEDICAL_CHECK", external_medical_check=True)
    source = ExternalSource(source_type="Paper", retracted=True)
    request = ExternalFindingRequest(source=source, finding_text="Retracted report", risk="RED", verified_as_of="2026-09-04", search_scope="metadata review")
    try:
        create_external_finding(project, request)
    except Exception as error:
        assert "qualified" in str(error).lower() or "retracted" in str(error).lower()
    else:
        raise AssertionError("retracted external source supported RED content")


def test_external_provenance_cannot_be_inserted_into_user_claim_table():
    external_claim = Claim(id="ext", normalized_claim="External finding", provenance="EXTERNAL_VERIFICATION")
    result = validate(Project(title="t", presentation_question="q", claims=[external_claim]))
    assert result["status"] == "BLOCK"
    assert any("External Finding pool" in issue["message"] for issue in result["issues"])


def test_packager_emits_traceable_pptx_without_inferred_connectors():
    claim = Claim(id="c", normalized_claim="Sourced fact", provenance="SOURCE", source_quote="Sourced fact", source_refs=[SourceRef(document_id="d", page=2, quote="Sourced fact")], conditions=["context"], review_status="APPROVED")
    project = Project(title="t", presentation_question="fact", claims=[claim], documents=documented("Sourced fact", page=2), pages=[PageSpec(id="p", title="Sourced fact", primary_message="Sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")])
    record_verification(project)
    output = Path("data") / "test_semantic_deck.pptx"
    try:
        build_pptx(semantic_deck(project), output)
        assert verify_pptx(semantic_deck(project), output)["status"] == "PASS"
    finally:
        if output.exists():
            output.unlink()
        inspection = Path(str(output) + ".inspect.ndjson")
        if inspection.exists():
            inspection.unlink()


def test_packager_binds_visible_connector_to_exact_relationship_id():
    first = Claim(id="a", normalized_claim="First sourced fact", provenance="SOURCE", source_quote="First sourced fact", source_refs=[SourceRef(document_id="d", page=1, quote="First")], conditions=["context"])
    second = Claim(id="b", normalized_claim="Second sourced fact", provenance="SOURCE", source_quote="Second sourced fact", source_refs=[SourceRef(document_id="d", page=1, quote="Second")], conditions=["context"])
    relationship = Relationship(id="rel1", from_claim_id="a", to_claim_id="b", relation_type="ASSOCIATION", provenance="SOURCE", source_refs=[SourceRef(document_id="d", page=1, quote="relation")], status="SUPPORTED")
    page = PageSpec(id="p", title="First sourced fact", primary_message="First sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["a", "b"], relationship_ids=["rel1"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[first, second],
                      relationships=[relationship], pages=[page],
                      documents=documented("First sourced fact. Second sourced fact. relation."))
    record_verification(project)
    output = Path("data") / "test_relationship_deck.pptx"
    try:
        deck = semantic_deck(project)
        build_pptx(deck, output)
        assert verify_pptx(deck, output)["status"] == "PASS"
    finally:
        if output.exists():
            output.unlink()
        inspection = Path(str(output) + ".inspect.ndjson")
        if inspection.exists():
            inspection.unlink()


def test_visual_contract_locks_red_exact_text_and_object_ownership():
    red = Claim(id="r", normalized_claim="Threshold is 20%", provenance="SOURCE", source_quote="Threshold is 20%", risk="RED", source_refs=[SourceRef(document_id="d", page=1, quote="20%")], conditions=["population"], numeric_facts=[NumericFact(value="20%", metric="risk", population="adults", timeframe="12 months")], triage="MUST_INCLUDE")
    project = Project(title="t", presentation_question="risk", claims=[red])
    _, project.pages = architect(project)
    plans = visual_router(project)
    contracts = compile_visual_contracts(project, plans)
    assert contracts[0]["mandatory_object_ids"] == ["r"]
    assert "20%" in contracts[0]["exact_text_register"]
    assert contracts[0]["protected_semantic_layer"]


def test_prompt_brief_is_editorial_only_and_contract_keeps_locked_semantics():
    red = Claim(id="r", normalized_claim="Threshold is 20%", provenance="SOURCE", source_quote="Threshold is 20%", risk="RED", source_refs=[SourceRef(document_id="d", page=1, quote="20%")], conditions=["population"], numeric_facts=[NumericFact(value="20%", metric="risk", population="adults", timeframe="12 months")], triage="MUST_INCLUDE")
    project = Project(title="t", presentation_question="risk", audience="医学生", claims=[red])
    _, project.pages = architect(project)
    contracts = compile_visual_contracts(project, visual_router(project))
    brief = compile_prompt_briefs(project, contracts)[0]
    assert contracts[0]["page_goal"]["lock_level"] == "SEMANTIC_LOCK"
    assert contracts[0]["post_generation_verification"]["requirements"]["source_visibility"] == "REQUIRED"
    assert "20%" not in brief["allowed_editorial_prompt"]
    assert "exact numbers" in brief["excluded_from_prompt"]


def test_generation_router_hard_rejects_external_engine_without_egress_or_geometry_qualification():
    external_engine = {"engine_id": "cheap-image", "engine_version": "1", "qualification_status": "QUALIFIED", "qualification_basis": {"benchmark_suite": "test-render-suite", "tested_at": "2026-09-04", "evidence_refs": ["test-evidence"]}, "available": True, "external": True, "capabilities": {"exact_text_authority": True, "exact_data_geometry": False, "semantic_topology_lock": False, "post_generation_verification": True}}
    route = select_generation_route(visual_type="FOREST_PLOT", has_exact_text=True, has_exact_geometry=True, has_topology_lock=False, editorial_base_allowed=True, capabilities={"cheap": external_engine})
    assert route["status"] == "UNROUTABLE"
    assert route["rejected_candidates"][0]["reason"] == "DATA_EGRESS_DENIED"


def test_generation_router_uses_qualified_fallback_without_changing_visual_type():
    qualification_basis = {"benchmark_suite": "test-render-suite", "tested_at": "2026-09-04", "evidence_refs": ["test-evidence"]}
    unavailable = {"engine_id": "primary", "engine_version": "1", "qualification_status": "QUALIFIED", "qualification_basis": qualification_basis, "available": False, "external": False, "capabilities": {"exact_text_authority": True, "exact_data_geometry": True, "semantic_topology_lock": True, "post_generation_verification": True}}
    fallback = {"engine_id": "fallback", "engine_version": "1", "qualification_status": "QUALIFIED", "qualification_basis": qualification_basis, "available": True, "external": False, "capabilities": {"exact_text_authority": True, "exact_data_geometry": True, "semantic_topology_lock": True, "post_generation_verification": True}}
    route = select_generation_route(visual_type="FOREST_PLOT", has_exact_text=False, has_exact_geometry=True, has_topology_lock=False, editorial_base_allowed=False, capabilities={"primary": unavailable, "fallback": fallback})
    assert route["status"] == "ROUTABLE"
    assert route["visual_type"] == "FOREST_PLOT"
    assert route["effective_generation_route"]["component_routes"][0]["engine_id"] == "fallback"


def test_generation_execution_provenance_is_bound_to_qualified_route_and_egress_boundary():
    claim = Claim(id="c", normalized_claim="Threshold is 20%", provenance="SOURCE", source_quote="Threshold is 20%", risk="RED", source_refs=[SourceRef(document_id="d", page=1, quote="Threshold is 20%")], conditions=["adults"], numeric_facts=[NumericFact(value="20%", metric="risk", population="adults", timeframe="12 months")])
    page = PageSpec(id="p", title="Sourced fact", primary_message="Sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[claim], pages=[page])
    project.visual_plans = visual_router(project)
    project.visual_contracts = compile_visual_contracts(project, project.visual_plans)
    contract = project.visual_contracts[0]
    record = record_generation_execution(project, GenerationExecutionRequest(
        page_id="p", visual_generation_contract_id=contract["visual_generation_contract_id"], component="protected_semantic_layer", strategy="CONTROLLED_COMPOSITION", engine_id="local_deterministic_compositor", engine_version="mvp-1", operation="RENDER", output_asset_id="asset-local-1", output_asset_version="1", deterministic_spec_ref="deck:v1",
    ))
    assert record["input_contract_ref"] == f"{contract['visual_generation_contract_id']}:v0.1"
    assert record["execution_kind"] == "LOCAL_LIBRARY"
    try:
        record_generation_execution(project, GenerationExecutionRequest(
            page_id="p", visual_generation_contract_id=contract["visual_generation_contract_id"], component="protected_semantic_layer", strategy="CONTROLLED_COMPOSITION", engine_id="local_deterministic_compositor", engine_version="mvp-1", operation="RENDER", output_asset_id="asset-local-2", output_asset_version="1", external_egress_used=True,
        ))
    except Exception as error:
        assert "egress" in str(error).lower()
    else:
        raise AssertionError("local execution falsely declared external egress")


def test_material_generation_capability_change_invalidates_only_affected_visual_route():
    claim = Claim(id="c", normalized_claim="Threshold is 20%", provenance="SOURCE", source_quote="Threshold is 20%", risk="RED", source_refs=[SourceRef(document_id="d", page=1, quote="Threshold is 20%")], conditions=["adults"], numeric_facts=[NumericFact(value="20%", metric="risk", population="adults", timeframe="12 months")])
    page = PageSpec(id="p", title="Threshold is 20%", primary_message="Threshold is 20%", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[claim], pages=[page], workflow_state="COMPLIANCE_REVIEW")
    project.visual_plans = visual_router(project)
    project.visual_contracts = compile_visual_contracts(project, project.visual_plans)
    event = invalidate_generation_capability(project, GenerationCapabilityChangeRequest(
        engine_id="local_deterministic_compositor", from_version="mvp-1", to_version="mvp-2", possible_impacts=["data_geometry", "topology"], reported_by="render-ops", rationale="Renderer dependency changes geometry handling.",
    ))
    assert event["affected_page_ids"] == ["p"]
    assert project.visual_plans[0]["route_status"] == "STALE_CAPABILITY"
    assert project.visual_contracts[0]["stale"] is True
    rerouted = visual_router(project)[0]
    assert rerouted["allowed"] is False
    assert rerouted["route_status"] == "UNROUTABLE"


def test_medical_asset_is_a_separate_routable_component_not_a_local_compositor_assumption():
    claim = Claim(id="c", normalized_claim="Sourced fact", provenance="SOURCE", source_quote="Sourced fact", source_refs=[SourceRef(document_id="d", page=1, quote="Sourced fact")], conditions=["adults"])
    page = PageSpec(id="p", title="Sourced fact", primary_message="Sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", allow_external_generation=True, generation_data_egress_policy="CONTRACT_MINIMIZED", claims=[claim], pages=[page])
    register_medical_visual_asset(project, MedicalVisualAssetRequest(id="asset", page_id="p", origin="MEDICAL_REFERENCE_ASSET", semantic_role="anatomical_reference", medical_verified=True, copyright_status="LICENSED", license_reference="license-1"))
    external_asset_engine = {
        "engine_id": "licensed-asset-api", "engine_version": "2026.1", "execution_kind": "EXTERNAL_ASSET_LIBRARY", "qualification_status": "QUALIFIED", "available": True, "external": True,
        "qualification_basis": {"benchmark_suite": "medical-asset-suite", "tested_at": "2026-09-04", "evidence_refs": ["license-1", "test-evidence"]},
        "capabilities": {"exact_text_authority": False, "exact_data_geometry": False, "scale_axis_fidelity": False, "semantic_topology_lock": False, "medical_asset_pipeline": True, "post_generation_verification": True},
    }
    plan = visual_router(project, capabilities={"licensed-asset-api": external_asset_engine})[0]
    asset_component = next(component for component in plan["effective_generation_route"]["component_routes"] if component["component"] == "medical_visual_asset:asset")
    assert plan["allowed"] is True
    assert asset_component["engine_id"] == "licensed-asset-api"
    assert asset_component["generation_mode"] == "VERIFIED_MEDICAL_ASSET_RENDERER"
    project.visual_contracts = compile_visual_contracts(project, [plan])
    asset_qa = verify_generated_visual_contract(project, GeneratedVisualVerificationRequest(
        page_id="p", visual_generation_contract_id=project.visual_contracts[0]["visual_generation_contract_id"], rendered_mandatory_object_ids=["c"], rendered_exact_text=project.visual_contracts[0]["exact_text_register"], rendered_data_binding_ids=[], rendered_relationship_ids=[], rendered_medical_asset_ids=[], source_visible=True, visual_semantic_fidelity="PASS",
    ))
    assert any(issue["type"] == "MEDICAL_ASSET_FIDELITY" for issue in asset_qa["issues"])
    blocked = visual_router(Project(title="t", presentation_question="fact", claims=[claim], pages=[page], medical_visual_assets=project.medical_visual_assets))[0]
    assert blocked["allowed"] is False
    assert blocked["route_status"] == "UNROUTABLE"


def test_unqualified_marketing_claim_never_grants_capability():
    engine = {"engine_id": "new-model", "engine_version": "1", "qualification_status": "MARKETING_CLAIM", "available": True, "external": False, "capabilities": {"exact_text_authority": True, "post_generation_verification": True}}
    assert capability_gate(engine, {"exact_text_authority"}, external_egress_allowed=True)["reason"] == "ENGINE_NOT_QUALIFIED"


def test_qualified_label_without_auditable_benchmark_evidence_never_grants_capability():
    engine = {"engine_id": "unproven-model", "engine_version": "1", "qualification_status": "QUALIFIED", "available": True, "external": False, "capabilities": {"exact_text_authority": True, "post_generation_verification": True}}
    assert capability_gate(engine, {"exact_text_authority"}, external_egress_allowed=True)["reason"] == "MISSING_QUALIFICATION_EVIDENCE"


def test_external_model_adapter_is_denied_without_egress_decision():
    adapter = {"adapter_id": "external", "provider": "remote", "model_id": "x", "model_version": "1", "external": True}
    try:
        record_run("source_extractor", {"private": "source"}, {}, adapter=adapter)
    except ValueError as error:
        assert "egress" in str(error)
    else:
        raise AssertionError("external egress was permitted")


def test_semantic_deck_cannot_export_with_human_review_required_result():
    claim = Claim(id="c", normalized_claim="A fact", provenance="SOURCE", source_quote="A fact", source_refs=[SourceRef(document_id="d", page=1, quote="A fact")], conditions=["context"])
    page = PageSpec(id="p", title="Unsupported title", primary_message="A fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[claim],
                      pages=[page], documents=documented("Sourced fact"))
    # the verification must be RECORDED (not transient) before it is rejected
    recorded = record_verification(project)
    assert recorded["status"] != "PASS", "fixture must not accidentally pass"
    try:
        semantic_deck(project)
    except Exception as error:
        assert "PASS" in str(error)
    else:
        raise AssertionError("human-review semantic deck was exported")


def test_title_entailment_blocks_modality_upgrade_even_with_source_reference():
    claim = Claim(id="c", normalized_claim="该指标与未来风险升高相关，可考虑进一步评估。", provenance="SOURCE", source_quote="该指标与未来风险升高相关，可考虑进一步评估。", risk="RED", source_refs=[SourceRef(document_id="d", page=1, quote="相关，可考虑")], conditions=["特定高危人群"])
    page = PageSpec(id="p", title="该指标导致未来风险，推荐进一步治疗", primary_message="该指标导致未来风险", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    result = verifier(Project(title="t", presentation_question="risk", claims=[claim], pages=[page]))
    assert result["status"] == "BLOCK"
    entailment = result["title_entailments"][0]
    assert entailment["status"] == "UNSUPPORTED_STRENGTH_UPGRADE"


def test_title_entailment_blocks_unqualified_population_expansion():
    claim = Claim(id="c", normalized_claim="特定高危人群可考虑进一步评估。", provenance="SOURCE", source_quote="特定高危人群可考虑进一步评估。", source_refs=[SourceRef(document_id="d", page=1, quote="特定高危人群")], conditions=["特定高危人群"])
    page = PageSpec(id="p", title="所有患者均可进一步评估", primary_message="所有患者均可进一步评估", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    entailment = verifier(Project(title="t", presentation_question="risk", claims=[claim], pages=[page]))["title_entailments"][0]
    assert entailment["status"] == "UNSUPPORTED_SCOPE_EXPANSION"


def test_verifier_does_not_treat_source_ref_as_semantic_support():
    claim = Claim(id="c", normalized_claim="推荐立即升级治疗", provenance="SOURCE", source_quote="本研究报道了观察性结局。", source_refs=[SourceRef(document_id="d", page=1, quote="本研究报道了观察性结局。")])
    # the quote resolves to real uploaded text; the CLAIM still outruns it
    result = verifier(Project(title="t", presentation_question="q", claims=[claim],
                              documents=documented("本研究报道了观察性结局。")))
    assert result["status"] == "HUMAN_REVIEW_REQUIRED"
    assert result["source_span_support"][0]["status"] == "PARTIALLY_SUPPORTED"
    assert any(issue["type"] == "MINIMUM_SOURCE_SPAN" for issue in result["issues"])


def test_minimum_source_span_floor_survives_verbatim_reporting():
    """Reusing source_quote to restate a Claim the document never made must not be
    reported as a supported span. Verbatim is necessary but not sufficient: with no
    term overlap at all the span locates nothing, so it blocks rather than passing."""
    claim = Claim(id="c", normalized_claim="好", provenance="SOURCE", source_quote="好",
                  source_refs=[SourceRef(document_id="d", page=1, quote="好")])
    result = verifier(Project(title="t", presentation_question="q", claims=[claim],
                              documents=documented("好")))
    span = result["source_span_support"][0]
    assert span["status"] == "UNSUPPORTED_NO_OVERLAP", span
    assert span["coverage"] == 0.0
    assert result["verification_coverage"]["claim"] == "FAIL"
    assert any(issue["type"] == "MINIMUM_SOURCE_SPAN" and issue["severity"] == "BLOCK"
               for issue in result["issues"])


def test_verifier_requires_explicit_relationship_for_contextual_trigger():
    claim = Claim(id="c", normalized_claim="来源支持的事实", provenance="SOURCE", source_quote="来源支持的事实", source_refs=[SourceRef(document_id="d", page=1, quote="来源支持的事实")])
    page = PageSpec(id="p", title="因此应立即调整治疗", primary_message="因此应立即调整治疗", visual_type="CLINICAL_DECISION_MAP", claim_ids=["c"], provenance="SYNTHESIS", goal="teach")
    result = verifier(Project(title="t", presentation_question="q", claims=[claim], pages=[page]))
    assert any(issue["type"] == "CONTEXTUAL_IMPLICATION" for issue in result["issues"])
    assert result["verification_coverage"]["contextual_implication"] == "FAIL"


def test_human_binding_correction_is_audited_and_unblocks_reverification():
    red = Claim(id="r", normalized_claim="Threshold", provenance="SOURCE", source_quote="Threshold", risk="RED", source_refs=[SourceRef(document_id="d", page=1, quote="Threshold")], conditions=["old"], numeric_facts=[NumericFact(value="20%", status="UNBOUND")])
    project = Project(title="t", presentation_question="risk", claims=[red], workflow_state="BLOCKED")
    patch = ClaimBindingPatch(conditions=["adults", "12 months"], numeric_facts=[NumericFact(value="20%", unit="%", metric="risk", population="adults", timeframe="12 months", status="BOUND")], reviewer="reviewer", rationale="Bound to page-level source context")
    event = update_claim_binding(project, "r", patch)
    assert project.workflow_state == "ARCHITECTED"
    assert red.numeric_facts[0].status == "BOUND"
    assert event["before"]["numeric_facts"][0]["status"] == "UNBOUND"


def test_binding_change_invalidates_prior_verification_and_blocks_export_until_rerun():
    claim = Claim(id="c", normalized_claim="Sourced fact", provenance="SOURCE", source_quote="Sourced fact", source_refs=[SourceRef(document_id="d", page=1, quote="Sourced fact")], conditions=["old context"])
    page = PageSpec(id="p", title="Sourced fact", primary_message="Sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[claim],
                      pages=[page], documents=documented("Sourced fact"))
    project.verification_results = [verifier(project)]
    update_claim_binding(project, "c", ClaimBindingPatch(conditions=["new context"], reviewer="reviewer", rationale="Corrected the source-bound condition."))
    assert project.verification_results[0]["stale"] is True
    try:
        semantic_deck(project)
    except Exception as error:
        assert "stale" in str(error).lower()
    else:
        raise AssertionError("stale verification result was reused for export")


def test_compliance_blocks_patient_identifiers_in_source_or_presentation():
    project = Project(title="t", presentation_question="q", documents=[{"id": "d", "chunks": [{"page": 1, "text": "患者联系电话 13812345678"}]}])
    result = compliance(project)
    assert result["status"] == "BLOCK"
    assert result["issues"][0]["category"] == "PRIVACY"


def test_bound_red_numeric_without_semantic_context_is_still_blocked():
    claim = Claim(id="n", normalized_claim="Risk is 20%", provenance="SOURCE", source_quote="Risk is 20%", risk="RED", source_refs=[SourceRef(document_id="d", page=1, quote="20%")], conditions=["adults"], numeric_facts=[NumericFact(value="20%", status="BOUND")])
    result = validate(Project(title="t", presentation_question="risk", claims=[claim]))
    issue = next(item for item in result["issues"] if item["rule"] == "DB-01")
    assert "metric" in issue["message"]
    assert "population" in issue["message"]


def test_numeric_provenance_blocks_missing_as_zero_and_bound_figure_estimates():
    missing_as_zero = Claim(id="nr", normalized_claim="Result was not reported", provenance="SOURCE", source_quote="Outcome NR", source_refs=[SourceRef(document_id="d", page=1, quote="Outcome NR")], numeric_facts=[NumericFact(value="0", value_origin="SOURCE_EXACT")])
    figure_as_exact = Claim(id="fig", normalized_claim="Figure estimate", provenance="SOURCE", source_quote="Figure estimate", source_refs=[SourceRef(document_id="d", page=1, quote="Figure estimate")], numeric_facts=[NumericFact(value="42%", value_origin="ESTIMATED_FROM_FIGURE", status="BOUND")])
    result = validate(Project(title="t", presentation_question="q", claims=[missing_as_zero, figure_as_exact]))
    assert result["status"] == "BLOCK"
    assert sum(issue["rule"] == "DB-01" for issue in result["issues"]) == 2


def test_derived_numeric_requires_synthesis_formula_and_input_fact_ids():
    source_claim = Claim(id="bad", normalized_claim="Relative reduction is 20%", provenance="SOURCE", source_quote="A=10%, B=8%", source_refs=[SourceRef(document_id="d", page=1, quote="A=10%, B=8%")], numeric_facts=[NumericFact(value="20%", value_origin="DERIVED_CALCULATION", derivation_kind="RELATIVE_REDUCTION", derivation_formula="(A-B)/A", input_fact_ids=["a", "b"])])
    assert validate(Project(title="t", presentation_question="q", claims=[source_claim]))["status"] == "BLOCK"
    synthesis_claim = source_claim.model_copy(deep=True)
    synthesis_claim.provenance = "SYNTHESIS"
    assert validate(Project(title="t", presentation_question="q", claims=[synthesis_claim]))["status"] == "PASS"


def test_visual_router_prohibits_direct_comparison_for_not_comparable_data():
    claim = Claim(id="c", normalized_claim="Separate studies", provenance="SOURCE", source_quote="Separate studies", source_refs=[SourceRef(document_id="d", page=1, quote="Separate studies")], numeric_facts=[NumericFact(value="42%", comparability_status="NOT_COMPARABLE")])
    project = Project(title="t", presentation_question="q", claims=[claim], pages=[PageSpec(id="p", title="Separate studies", primary_message="Separate studies", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")])
    plan = visual_router(project)[0]
    assert "direct comparative chart/claim for NOT_COMPARABLE data" in plan["prohibited"]


def test_synthetic_case_requires_explicit_opt_in_and_stays_out_of_claim_table():
    claim = Claim(id="c", normalized_claim="Sourced fact", provenance="SOURCE", source_quote="Sourced fact", source_refs=[SourceRef(document_id="d", page=1, quote="Sourced fact")], conditions=["context"])
    project = Project(title="t", presentation_question="q", claims=[claim], synthetic_case=True)
    request = SyntheticCaseRequest(title="教学模拟病例", scenario_text="这是仅用于课堂讨论的模拟病例，不能视为原文病例。", explicitly_requested=True, source_claim_ids=["c"])
    case = create_synthetic_case(project, request)
    assert case["disclaimer"] == "AI生成模拟病例｜非原文病例｜仅用于教学演示"
    assert len(project.synthetic_cases) == 1
    assert len(project.claims) == 1


def test_synthetic_case_is_denied_without_project_opt_in():
    project = Project(title="t", presentation_question="q")
    request = SyntheticCaseRequest(title="教学模拟病例", scenario_text="这是仅用于课堂讨论的模拟病例，不能视为原文病例。", explicitly_requested=True)
    try:
        create_synthetic_case(project, request)
    except Exception as error:
        assert "disabled" in str(error).lower()
    else:
        raise AssertionError("synthetic case was created without opt-in")


def test_delivery_manifest_is_bound_to_immutable_semantic_snapshot_not_audit_time():
    claim = Claim(id="c", normalized_claim="Sourced fact", provenance="SOURCE", source_quote="Sourced fact", source_refs=[SourceRef(document_id="d", page=1, quote="Sourced fact")], conditions=["context"])
    page = PageSpec(id="p", title="Sourced fact", primary_message="Sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[claim],
                      pages=[page], documents=documented("Sourced fact"))
    project.verification_results = [verifier(project)]
    project.compliance_issues = [compliance(project)]
    deck = semantic_deck(project)
    first_hash = immutable_snapshot_digest(deck, project.documents)
    deck["exported_at"] = "a later time"
    deck["audit_log"].append({"action": "later event"})
    assert immutable_snapshot_digest(deck, project.documents) == first_hash
    manifest = delivery_manifest(project, deck, "pptx-hash", {"status": "PASS", "issues": []})
    assert manifest["snapshot_id"] == f"del_{first_hash[:16]}"
    assert manifest["post_generation_verification"]["status"] == "PASS"


def test_unverified_ai_medical_visual_blocks_validation_and_verifier():
    project = Project(title="t", presentation_question="q")
    register_medical_visual_asset(project, MedicalVisualAssetRequest(
        id="ai-medical",
        origin="AI_GENERATED_MEDICAL_VISUAL",
        semantic_role="anatomical_reference",
        ai_generation_allowed=True,
        medical_verified=False,
        copyright_status="USER_OWNED",
    ))
    validation = validate(project)
    verification = verifier(project)
    assert validation["status"] == "BLOCK"
    assert any(issue["rule"] == "VG-09" and issue["object"] == "ai-medical" for issue in validation["issues"])
    assert verification["verification_coverage"]["medical_visual"] == "FAIL"
    assert any(issue["type"] == "MEDICAL_VISUAL_QA" for issue in verification["issues"])


def test_client_delivery_blocks_unresolved_visual_asset_license():
    project = Project(title="t", presentation_question="q", output_channel="client_delivery")
    register_medical_visual_asset(project, MedicalVisualAssetRequest(
        id="third-party",
        origin="MEDICAL_REFERENCE_ASSET",
        semantic_role="medical_content",
        medical_verified=True,
        copyright_status="REQUIRES_LICENSE_RESOLUTION",
    ))
    validation = validate(project)
    assert validation["status"] == "BLOCK"
    assert any(issue["rule"] == "CP-01" and issue["object"] == "third-party" for issue in validation["issues"])


def test_public_delivery_also_blocks_unknown_visual_asset_license():
    project = Project(title="t", presentation_question="q", output_channel="public_xiaohongshu")
    register_medical_visual_asset(project, MedicalVisualAssetRequest(id="public-third-party", origin="MEDICAL_REFERENCE_ASSET", semantic_role="decorative_reference", medical_verified=True, copyright_status="UNKNOWN"))
    assert any(issue["rule"] == "CP-01" and issue["object"] == "public-third-party" for issue in validate(project)["issues"])


def test_verified_or_decorative_asset_has_auditable_pass_coverage():
    project = Project(title="t", presentation_question="q")
    event = register_medical_visual_asset(project, MedicalVisualAssetRequest(
        id="decorative",
        origin="AI_GENERATED_MEDICAL_VISUAL",
        semantic_role="decorative_reference",
        ai_generation_allowed=True,
        medical_verified=False,
        copyright_status="USER_OWNED",
    ))
    assert event["asset"]["id"] == "decorative"
    assert validate(project)["status"] == "PASS"
    assert verifier(project)["verification_coverage"]["medical_visual"] == "PASS"


def test_red_medical_visual_requires_complete_provenance_and_fidelity_qa():
    project = Project(title="t", presentation_question="q")
    register_medical_visual_asset(project, MedicalVisualAssetRequest(
        id="red-diagram",
        origin="REDRAWN_FROM_EVIDENCE",
        semantic_role="medical_content",
        risk_level="RED",
        medical_semantic_source_refs=["src-medical"],
        node_provenance_coverage=1.0,
        relationship_provenance_coverage=0.86,
        semantic_fidelity_status="NEEDS_HUMAN_REVIEW",
        copyright_status="USER_OWNED",
    ))
    issues = verifier(project)["issues"]
    assert any(issue["type"] == "MEDICAL_VISUAL_PROVENANCE" for issue in issues)
    assert any(issue["type"] == "MEDICAL_VISUAL_QA" for issue in issues)


def test_semantic_visual_binding_cannot_create_unlocked_or_unknown_relationship():
    claim = Claim(id="c", normalized_claim="Fact", provenance="SUMMARY")
    relation = Relationship(id="r", from_claim_id="c", to_claim_id="c", relation_type="CLINICAL_PATHWAY", provenance="SUMMARY")
    page = PageSpec(id="p", title="Fact", primary_message="Fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], relationship_ids=["r"], provenance="SUMMARY", goal="teach")
    project = Project(title="t", presentation_question="q", claims=[claim], relationships=[relation], pages=[page])
    register_visual_binding(project, VisualBindingRequest(id="vb", page_id="p", binding_type="connector_to_relationship", from_object_id="arrow", to_object_id="missing", semantic_value="causal", source_refs=[], locked=False))
    issues = validate(project)["issues"]
    assert any(issue["rule"] == "VG-09" and issue["object"] == "vb" for issue in issues)
    assert verifier(project)["verification_coverage"]["medical_visual"] == "FAIL"


def test_valid_semantic_visual_binding_is_counted_as_visual_coverage():
    claim = Claim(id="c", normalized_claim="Fact", provenance="SUMMARY")
    page = PageSpec(id="p", title="Fact", primary_message="Fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SUMMARY", goal="teach")
    project = Project(title="t", presentation_question="q", claims=[claim], pages=[page])
    register_visual_binding(project, VisualBindingRequest(id="vb", page_id="p", binding_type="label_to_numeric", from_object_id="label", to_object_id="c", semantic_value="observed risk", source_refs=["src"], locked=True))
    assert validate(project)["status"] == "PASS"
    assert verifier(project)["verification_coverage"]["medical_visual"] == "PASS"


def test_claim_revision_is_immutable_and_invalidates_dependent_page():
    claim = Claim(id="c", normalized_claim="Sourced fact", provenance="SOURCE", source_quote="Sourced fact", source_refs=[SourceRef(document_id="d", page=1, quote="Sourced fact")], conditions=["old context"])
    page = PageSpec(id="p", title="Sourced fact", primary_message="Sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[claim], pages=[page])
    project.verification_results = [verifier(project)]
    event = create_claim_revision(project, "c", ClaimRevisionRequest(conditions=["corrected context"], revision_reason="Restore the omitted population condition."))
    revised = event["claim"]
    assert claim.conditions == ["old context"]
    assert revised.id == "c:v2" and revised.version == 2 and revised.supersedes_claim_id == "c"
    assert page.revision_status == "STALE"
    assert event["revision"]["status"] == "RESOLVED_PENDING_REVERIFY"
    assert project.verification_results[0]["stale"] is True
    assert validate(project)["status"] == "BLOCK"


def test_rebuilt_verification_cannot_export_stale_claim_page():
    claim = Claim(id="c", normalized_claim="Sourced fact", provenance="SOURCE", source_quote="Sourced fact", source_refs=[SourceRef(document_id="d", page=1, quote="Sourced fact")], conditions=["old context"])
    page = PageSpec(id="p", title="Sourced fact", primary_message="Sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[claim],
                      pages=[page], documents=documented("Sourced fact"))
    create_claim_revision(project, "c", ClaimRevisionRequest(conditions=["corrected context"], revision_reason="Restore the omitted population condition."))
    project.verification_results = [verifier(project)]
    try:
        semantic_deck(project)
    except Exception as error:
        assert "stale" in str(error).lower()
    else:
        raise AssertionError("export reused a page bound to a superseded Claim version")


def test_issue_lifecycle_is_only_verified_resolved_by_independent_reverification():
    claim = Claim(id="c", normalized_claim="推荐立即治疗", provenance="SOURCE", source_quote="观察性结局", source_refs=[SourceRef(document_id="d", page=1, quote="观察性结局")])
    project = Project(title="t", presentation_question="q", claims=[claim],
                      documents=documented("观察性结局"))
    first = verifier(project)
    persist_verification_issue_lifecycle(project, first)
    project.verification_results.append(first)
    issue = project.verification_issues[0]
    issue["status"] = "RESOLVED_PENDING_REVERIFY"
    claim.normalized_claim = "观察性结局"
    second = verifier(project)
    persist_verification_issue_lifecycle(project, second)
    assert issue["status"] == "VERIFIED_RESOLVED"
    assert second["verification_result_id"] != first["verification_result_id"]


def test_human_override_preserves_unsupported_verification_result():
    claim = Claim(id="c", normalized_claim="推荐立即治疗", provenance="SOURCE", source_quote="观察性结局", source_refs=[SourceRef(document_id="d", page=1, quote="观察性结局")])
    project = Project(title="t", presentation_question="q", claims=[claim],
                      documents=documented("观察性结局"))
    result = verifier(project)
    persist_verification_issue_lifecycle(project, result)
    project.verification_results.append(result)
    issue = project.verification_issues[0]
    override = create_human_override(project, HumanOverrideRequest(verification_issue_id=issue["id"], verification_result_id=result["verification_result_id"], reviewer="专家审核", reason="专家保留该表述，并以人工综合判断单独记录。"))
    assert override["decision"] == "APPROVED_WITH_OVERRIDE"
    assert result["status"] == "HUMAN_REVIEW_REQUIRED"
    assert issue["status"] == "OPEN"


def test_adjacent_pages_cannot_imply_clinical_action_without_context_contract():
    first = Claim(id="a", normalized_claim="观察到风险", provenance="SUMMARY")
    second = Claim(id="b", normalized_claim="因此优先治疗", provenance="SUMMARY")
    relation = Relationship(id="r", from_claim_id="a", to_claim_id="b", relation_type="CLINICAL_PATHWAY", provenance="SUMMARY")
    pages = [
        PageSpec(id="p1", title="观察到风险", primary_message="观察到风险", visual_type="EVIDENCE_MAP", claim_ids=["a"], provenance="SUMMARY", goal="teach"),
        PageSpec(id="p2", title="因此优先治疗", primary_message="因此优先治疗", visual_type="CLINICAL_DECISION_MAP", claim_ids=["b"], relationship_ids=["r"], provenance="SUMMARY", goal="teach"),
    ]
    project = Project(title="t", presentation_question="q", claims=[first, second], relationships=[relation], pages=pages)
    result = verifier(project)
    assert any(issue["type"] == "CONTEXT_CONTRACT" and issue["object"] == "p2" for issue in result["issues"])
    assert result["verification_coverage"]["contextual_implication"] == "FAIL"


def test_locked_context_contract_with_relationship_and_source_can_authorize_transition():
    first = Claim(id="a", normalized_claim="观察到风险", provenance="SUMMARY")
    second = Claim(id="b", normalized_claim="因此优先治疗", provenance="SUMMARY")
    relation = Relationship(id="r", from_claim_id="a", to_claim_id="b", relation_type="CLINICAL_PATHWAY", provenance="SUMMARY")
    pages = [
        PageSpec(id="p1", title="观察到风险", primary_message="观察到风险", visual_type="EVIDENCE_MAP", claim_ids=["a"], provenance="SUMMARY", goal="teach"),
        PageSpec(id="p2", title="因此优先治疗", primary_message="因此优先治疗", visual_type="CLINICAL_DECISION_MAP", claim_ids=["b"], relationship_ids=["r"], provenance="SUMMARY", goal="teach"),
    ]
    project = Project(title="t", presentation_question="q", claims=[first, second], relationships=[relation], pages=pages)
    register_context_contract(project, ContextContractRequest(from_page_id="p1", to_page_id="p2", transition_type="CLINICAL_IMPLICATION", relationship_ids=["r"], source_refs=["src"], rationale="Clinical pathway relation has been explicitly verified.", locked=True))
    assert not any(issue["type"] == "CONTEXT_CONTRACT" for issue in verifier(project)["issues"])


def test_source_grounded_page_keeps_its_own_transition_wording_without_context_contract():
    """A SOURCE Claim's span sits on the page showing it -- nothing is inherited from the
    previous page, so the wording is not a cross-page implication. Requiring a contract here
    would demand a clinical relationship the source never stated."""
    first = Claim(id="a", normalized_claim="观察到风险", provenance="SOURCE",
                  source_quote="观察到风险", source_refs=[SourceRef(document_id="d", page=1, quote="观察到风险")])
    second = Claim(id="b", normalized_claim="因此应优先启动治疗", provenance="SOURCE",
                   source_quote="因此应优先启动治疗", source_refs=[SourceRef(document_id="d", page=2, quote="因此应优先启动治疗")])
    pages = [
        PageSpec(id="p1", title="观察到风险", primary_message="观察到风险", visual_type="EVIDENCE_MAP", claim_ids=["a"], provenance="SOURCE", goal="teach"),
        PageSpec(id="p2", title="因此应优先启动治疗", primary_message="因此应优先启动治疗", visual_type="CLINICAL_DECISION_MAP", claim_ids=["b"], provenance="SOURCE", goal="teach"),
    ]
    project = Project(title="t", presentation_question="q", claims=[first, second], pages=pages)
    assert not any(issue["type"] == "CONTEXT_CONTRACT" for issue in verifier(project)["issues"])


def test_cross_page_transition_cannot_be_laundered_by_copying_the_title_into_the_claim():
    """SUMMARY/SYNTHESIS evidence is assembled elsewhere, so showing it here does inherit
    from the previous page. Rewording the Claim to match the title does not remove that,
    and rewording a Claim is itself an immutable revision requiring reverification."""
    first = Claim(id="a", normalized_claim="观察到风险", provenance="SOURCE",
                  source_quote="观察到风险", source_refs=[SourceRef(document_id="d", page=1, quote="观察到风险")])
    second = Claim(id="b", normalized_claim="因此优先治疗", provenance="SUMMARY")
    pages = [
        PageSpec(id="p1", title="观察到风险", primary_message="观察到风险", visual_type="EVIDENCE_MAP", claim_ids=["a"], provenance="SOURCE", goal="teach"),
        PageSpec(id="p2", title="因此优先治疗", primary_message="因此优先治疗", visual_type="CLINICAL_DECISION_MAP", claim_ids=["b"], provenance="SUMMARY", goal="teach"),
    ]
    project = Project(title="t", presentation_question="q", claims=[first, second], pages=pages)
    assert any(issue["type"] == "CONTEXT_CONTRACT" and issue["object"] == "p2"
               for issue in verifier(project)["issues"])


def test_source_grounded_condition_is_not_an_inherited_transition():
    """A condition bound to the Claim is part of that Claim's own evidence, not context
    carried across from the previous page."""
    first = Claim(id="a", normalized_claim="观察到风险", provenance="SOURCE",
                  source_quote="观察到风险", source_refs=[SourceRef(document_id="d", page=1, quote="观察到风险")])
    second = Claim(id="b", normalized_claim="应在 72 小时内评估", provenance="SOURCE",
                   source_quote="应在 72 小时内评估", source_refs=[SourceRef(document_id="d", page=2, quote="应在 72 小时内评估")],
                   conditions=["72 小时内"])
    pages = [
        PageSpec(id="p1", title="观察到风险", primary_message="观察到风险", visual_type="EVIDENCE_MAP", claim_ids=["a"], provenance="SOURCE", goal="teach"),
        PageSpec(id="p2", title="应在 72 小时内评估", primary_message="应在 72 小时内评估", visual_type="DECISION_FLOW", claim_ids=["b"], provenance="SOURCE", goal="teach"),
    ]
    project = Project(title="t", presentation_question="q", claims=[first, second], pages=pages)
    assert not any(issue["type"] == "CONTEXT_CONTRACT" for issue in verifier(project)["issues"])


def test_context_contract_requires_declared_scope_before_inheritance():
    page1 = PageSpec(id="p1", title="A", primary_message="A", visual_type="EVIDENCE_MAP", claim_ids=[], provenance="SUMMARY", goal="teach")
    page2 = PageSpec(id="p2", title="B", primary_message="B", visual_type="EVIDENCE_MAP", claim_ids=[], provenance="SUMMARY", goal="teach")
    project = Project(title="t", presentation_question="q", pages=[page1, page2])
    event = register_context_contract(project, ContextContractRequest(from_page_id="p1", to_page_id="p2", transition_type="PRESENTATION_DEPENDENCY", inheritance_allowed=True, rationale="Carry source context to the following explanatory page."))
    assert event["contract"]["scope_ids"] == ["p1", "p2"]
    assert any("no inheritable semantic scope" in issue["message"] for issue in validate(project)["issues"])


def test_agent_capability_matrix_programmatically_blocks_all_required_unauthorized_writes():
    project = Project(title="t", presentation_question="q")
    forbidden = [
        ("source_extractor", "relationships"),
        ("information_triage", "claims"),
        ("medical_information_architect", "relationships"),
        ("visual_design_agent", "numeric_facts"),
    ]
    decisions = [authorize_agent_write(project, agent, resource, object_id="target") for agent, resource in forbidden]
    assert all(decision["decision"] == "BLOCK" for decision in decisions)
    assert len(project.violation_records) == 4
    assert all(record["rule_id"] == "CAP-01" and record["action"] == "BLOCK" for record in project.violation_records)
    assert all(decision in project.policy_decisions for decision in decisions)
    assert any(rule["id"] == "CAP-01" for rule in rule_registry()["rules"])


def test_agent_capability_matrix_allows_only_declared_writer_resource():
    project = Project(title="t", presentation_question="q")
    decision = authorize_agent_write(project, "medical_information_architect", "pages", object_id="p")
    assert decision["decision"] == "PASS"
    assert project.violation_records == []


def test_source_relationship_requires_its_own_provenance_not_claim_inheritance():
    first = Claim(id="a", normalized_claim="A", provenance="SOURCE", source_quote="A", source_refs=[SourceRef(document_id="d", page=1, quote="A")])
    second = Claim(id="b", normalized_claim="B", provenance="SOURCE", source_quote="B", source_refs=[SourceRef(document_id="d", page=1, quote="B")])
    relation = Relationship(id="r", from_claim_id="a", to_claim_id="b", relation_type="CAUSAL", provenance="SOURCE", risk="RED")
    project = Project(title="t", presentation_question="q", claims=[first, second], relationships=[relation])
    assert validate(project)["status"] == "BLOCK"
    assert any(issue["type"] == "RELATIONSHIP_PROVENANCE" for issue in verifier(project)["issues"])


def test_logical_relationship_requires_conditions_and_page_connector_requires_known_relation():
    claim = Claim(id="a", normalized_claim="A", provenance="SUMMARY")
    relation = Relationship(id="r", from_claim_id="a", to_claim_id="a", relation_type="ELIGIBLE_FOR", provenance="SYNTHESIS", logic_operator="AND")
    page = PageSpec(id="p", title="A", primary_message="A", visual_type="CLINICAL_DECISION_MAP", claim_ids=["a"], relationship_ids=["unknown"], provenance="SUMMARY", goal="teach")
    issues = validate(Project(title="t", presentation_question="q", claims=[claim], relationships=[relation], pages=[page]))["issues"]
    assert any("Logical clinical relationship" in issue["message"] for issue in issues)
    assert any("unknown clinical relationship" in issue["message"] for issue in issues)


def test_post_generation_visual_verifier_blocks_contract_object_or_text_omission():
    claim = Claim(id="c", normalized_claim="Sourced fact", provenance="SOURCE", source_quote="Sourced fact", source_refs=[SourceRef(document_id="d", page=1, quote="Sourced fact")], conditions=["context"])
    page = PageSpec(id="p", title="Sourced fact", primary_message="Sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[claim], pages=[page])
    project.visual_contracts = compile_visual_contracts(project, visual_router(project))
    contract = project.visual_contracts[0]
    result = verify_generated_visual_contract(project, GeneratedVisualVerificationRequest(page_id="p", visual_generation_contract_id=contract["visual_generation_contract_id"], rendered_mandatory_object_ids=[], rendered_exact_text=[], source_visible=False, visual_semantic_fidelity="PASS"))
    assert result["status"] == "BLOCK"
    assert {issue["type"] for issue in result["issues"]} >= {"MANDATORY_OBJECT_OMISSION", "EXACT_TEXT_MUTATION", "SOURCE_VISIBILITY"}


def test_post_generation_visual_verifier_passes_only_exact_contract_and_unlocks_export():
    claim = Claim(id="c", normalized_claim="Sourced fact", provenance="SOURCE", source_quote="Sourced fact", source_refs=[SourceRef(document_id="d", page=1, quote="Sourced fact")], conditions=["context"])
    page = PageSpec(id="p", title="Sourced fact", primary_message="Sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[claim],
                      pages=[page], documents=documented("Sourced fact"))
    project.visual_plans = visual_router(project)
    project.visual_contracts = compile_visual_contracts(project, project.visual_plans)
    contract = project.visual_contracts[0]
    result = verify_generated_visual_contract(project, GeneratedVisualVerificationRequest(page_id="p", visual_generation_contract_id=contract["visual_generation_contract_id"], rendered_mandatory_object_ids=["c"], rendered_exact_text=contract["exact_text_register"], rendered_data_binding_ids=contract["data_binding_ids"], rendered_relationship_ids=[], source_visible=True, visual_semantic_fidelity="PASS", generation_provenance={"engine_id": "local_deterministic_compositor"}))
    assert result["status"] == "PASS"
    project.verification_results = [verifier(project)]
    try:
        semantic_deck(project)
    except Exception as error:
        assert "Generation Execution Provenance" in str(error)
    else:
        raise AssertionError("delivery reused a route without component execution provenance")
    record_current_route_components(project, contract)
    assert semantic_deck(project)["pages"][0]["page_id"] == "p"


def test_post_generation_visual_verifier_blocks_legend_swap_and_axis_clipping():
    claim = Claim(id="c", normalized_claim="Observed response", provenance="SOURCE", source_quote="Observed response", source_refs=[SourceRef(document_id="d", page=1, quote="Observed response")], conditions=["adults"])
    page = PageSpec(id="p", title="Observed response", primary_message="Observed response", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[claim], pages=[page])
    register_visual_binding(project, VisualBindingRequest(id="legend", page_id="p", binding_type="legend_to_series", from_object_id="legend_a", to_object_id="series_a", semantic_value="intervention", source_refs=["d"]))
    register_visual_binding(project, VisualBindingRequest(id="axis", page_id="p", binding_type="axis_to_metric", from_object_id="y_axis", to_object_id="c", semantic_value="response rate", axis_baseline_policy="ZERO_REQUIRED"))
    project.visual_contracts = compile_visual_contracts(project, visual_router(project))
    contract = project.visual_contracts[0]
    result = verify_generated_visual_contract(project, GeneratedVisualVerificationRequest(
        page_id="p", visual_generation_contract_id=contract["visual_generation_contract_id"], rendered_mandatory_object_ids=["c"], rendered_exact_text=contract["exact_text_register"], rendered_data_binding_ids=contract["data_binding_ids"], rendered_relationship_ids=[], source_visible=True, visual_semantic_fidelity="PASS",
        rendered_visual_bindings=[
            {"binding_id": "legend", "binding_type": "legend_to_series", "from_object_id": "legend_a", "to_object_id": "series_b", "semantic_value": "intervention"},
            {"binding_id": "axis", "binding_type": "axis_to_metric", "from_object_id": "y_axis", "to_object_id": "c", "semantic_value": "response rate"},
        ],
        rendered_axis_scales=[{"axis_object_id": "y_axis", "data_min": 0, "data_max": 100, "axis_min": 20, "axis_max": 90}],
    ))
    assert result["status"] == "BLOCK"
    assert {issue["type"] for issue in result["issues"]} >= {"VISUAL_BINDING_FIDELITY", "AXIS_EXTENT_FIDELITY"}


def test_visual_strategy_hard_rejects_noncomparable_direct_comparison_without_changing_page_type():
    claim = Claim(id="c", normalized_claim="Different studies", provenance="SUMMARY", numeric_facts=[NumericFact(value="42%", comparability_status="NOT_COMPARABLE")])
    page = PageSpec(id="p", title="Compare", primary_message="Compare", visual_type="DIRECT_COMPARISON_CHART", claim_ids=["c"], provenance="SUMMARY", goal="compare")
    decision = select_visual_strategy(page, [claim], [])
    selected = next(item for item in decision["candidates"] if item["visual_type"] == "DIRECT_COMPARISON_CHART")
    assert selected["status"] == "INVALID_CANDIDATE"
    assert "COMPARABILITY_GATE_FAILED" in selected["hard_exclusion_reasons"]
    assert decision["current_page_visual_type"] == "DIRECT_COMPARISON_CHART"
    assert visual_router(Project(title="t", presentation_question="q", claims=[claim], pages=[page]))[0]["allowed"] is False


def test_visual_strategy_permits_no_valid_visual_instead_of_inventing_medical_structure():
    page = PageSpec(id="p", title="Empty", primary_message="Empty", visual_type="CLINICAL_DECISION_MAP", claim_ids=[], provenance="SUMMARY", goal="explain")
    decision = select_visual_strategy(page, [], [])
    assert decision["decision_status"] == "NO_VALID_VISUAL"
    assert decision["selected_primary_visual"] == "TEXT_FORWARD_EDITORIAL"


def test_visual_strategy_keeps_generation_strategy_separate_and_records_standard_candidate():
    claim = Claim(id="c", normalized_claim="随机研究流程", provenance="SUMMARY")
    page = PageSpec(id="p", title="CONSORT 随机流程", primary_message="随机研究流程", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SUMMARY", goal="explain flow")
    decision = select_visual_strategy(page, [claim], [])
    assert decision["standard_candidate"] == "CONSORT_PARTICIPANT_FLOW"
    assert decision["generation_strategy"] == "SEPARATE_ROUTER_DECISION"
    assert decision["selected_primary_visual"] == "EVIDENCE_MAP"


def test_approved_minimal_project_completes_traceable_deck_and_pptx_path():
    claim = Claim(id="c", normalized_claim="Sourced fact", provenance="SOURCE", source_quote="Sourced fact", source_refs=[SourceRef(document_id="d", page=1, quote="Sourced fact")], conditions=["adults"], review_status="APPROVED")
    page = PageSpec(id="p", title="Sourced fact", primary_message="Sourced fact", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="fact", claims=[claim],
                      pages=[page], documents=documented("Sourced fact"), workflow_state="ARCHITECTED")
    project.verification_results = [verifier(project)]
    project.visual_plans = visual_router(project)
    project.visual_contracts = compile_visual_contracts(project, project.visual_plans)
    contract = project.visual_contracts[0]
    visual_qa = verify_generated_visual_contract(project, GeneratedVisualVerificationRequest(page_id="p", visual_generation_contract_id=contract["visual_generation_contract_id"], rendered_mandatory_object_ids=["c"], rendered_exact_text=contract["exact_text_register"], rendered_data_binding_ids=contract["data_binding_ids"], rendered_relationship_ids=[], source_visible=True, visual_semantic_fidelity="PASS"))
    assert visual_qa["status"] == "PASS"
    record_current_route_components(project, contract)
    deck = semantic_deck(project)
    output = Path("data") / "test_approved_minimal_project.pptx"
    try:
        build_pptx(deck, output)
        assert verify_pptx(deck, output)["status"] == "PASS"
    finally:
        if output.exists():
            output.unlink()
        inspection = Path(str(output) + ".inspect.ndjson")
        if inspection.exists():
            inspection.unlink()


def test_project_scope_fields_are_auditable_inputs_to_triage_and_visual_contracts():
    claim = Claim(id="c", normalized_claim="COPD 证据教学", provenance="SOURCE", source_quote="COPD 证据教学", source_refs=[SourceRef(document_id="d", page=1, quote="COPD 证据教学")])
    page = PageSpec(id="p", title="COPD 证据教学", primary_message="COPD 证据教学", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SOURCE", goal="teach")
    project = Project(title="t", presentation_question="COPD 证据", project_type="teaching", project_goal="COPD 证据教学", audience="医学生", language="zh-CN", output_type="PPTX", allow_external_sources=False, claims=[claim], pages=[page])
    decision = triage_claims(project)[0]
    contract = compile_visual_contracts(project, visual_router(project))[0]
    assert "project_type=teaching" in decision.reason
    assert "goal_overlap=" in decision.reason
    assert contract["page_identity"]["project_type"] == "teaching"


def test_title_entailment_issue_routes_to_architect_not_claim_builder():
    claim = Claim(id="c", normalized_claim="可考虑进一步评估", provenance="SUMMARY")
    page = PageSpec(id="p", title="推荐立即治疗", primary_message="推荐立即治疗", visual_type="EVIDENCE_MAP", claim_ids=["c"], provenance="SUMMARY", goal="teach")
    project = Project(title="t", presentation_question="q", claims=[claim], pages=[page])
    result = verifier(project)
    persist_verification_issue_lifecycle(project, result)
    issue = next(item for item in project.verification_issues if item["type"] == "TITLE_ENTAILMENT")
    assert issue["recommended_responsible_module"] == "medical_information_architect"
    try:
        route_verification_issue(project, issue["id"], IssueRouteRequest(responsible_module="claim_builder", rationale="Attempt to rewrite the source Claim."))
    except Exception as error:
        assert "medical_information_architect" in str(error)
    else:
        raise AssertionError("title issue was incorrectly routed to Claim Builder")
    routed = route_verification_issue(project, issue["id"], IssueRouteRequest(responsible_module="medical_information_architect", rationale="Reduce the title strength to match its supporting Claim."))
    assert routed["status"] == "ROUTED"


def test_triage_override_retains_claim_and_invalidates_prior_verification():
    claim = Claim(id="c", normalized_claim="COPD 筛查路径", provenance="SUMMARY")
    project = Project(title="t", presentation_question="COPD 筛查", claims=[claim], workflow_state="TRIAGED")
    project.triage_decisions = triage_claims(project)
    project.verification_results = [verifier(project)]
    event = override_triage_decision(project, "c", TriageOverrideRequest(bucket="EXCLUDED", reviewer="编辑", rationale="本次汇报聚焦治疗证据，保留该 Claim 供追溯。"))
    assert claim in project.claims
    assert claim.triage == "EXCLUDED"
    assert project.triage_decisions[0].overridden is True
    assert "USER_OVERRIDE by 编辑" in event["after"]["reason"]
    assert project.verification_results[0]["stale"] is True


def test_recurrent_automated_revision_stops_at_retry_budget_and_requires_human_review():
    claim = Claim(id="c", normalized_claim="Fact", provenance="SUMMARY", conditions=["old"])
    project = Project(title="t", presentation_question="q", claims=[claim])
    configure_retry_budget(project, RetryBudgetRequest(module="claim_builder", max_auto_revision_attempts=3, recurrent_issue_threshold=2))
    first = create_claim_revision(project, "c", ClaimRevisionRequest(conditions=["fixed once"], responsible_module="claim_builder", revision_reason="Repair missing source-bound condition.", verification_issue_ids=["iss-critical"], automated=True))
    assert first["claim"].id == "c:v2"
    try:
        create_claim_revision(project, "c:v2", ClaimRevisionRequest(conditions=["fixed twice"], responsible_module="claim_builder", revision_reason="Retry the same missing condition correction.", verification_issue_ids=["iss-critical"], automated=True))
    except Exception as error:
        assert "human review" in str(error).lower()
    else:
        raise AssertionError("recurrent automated critical issue was not escalated")
    assert len(project.claims) == 2
    assert project.retry_budgets[0]["status"] == "HUMAN_REVIEW_REQUIRED"


def test_source_priority_orders_review_not_medical_truth_or_claim_mutation():
    guideline = {"id": "guide", "source_type": "guideline", "official_or_regulatory_status": "GUIDELINE", "jurisdiction": "CN"}
    review = {"id": "review", "source_type": "review", "official_or_regulatory_status": "UNOFFICIAL", "jurisdiction": "CN"}
    policy = SourcePriorityPolicyRequest(jurisdiction="CN", ordered_source_kinds=["OFFICIAL_GUIDELINE", "REVIEW"], rationale="Use official guideline first for conflict review.").model_dump()
    result = apply_source_priority_policy(guideline, review, policy)
    assert result["status"] == "PRIORITY_FOR_REVIEW"
    assert result["priority_source_id"] == "guide"
    assert result["non_truth_ranking"] is True
    assert "not marked medically false" in result["reason"].lower()


def test_source_priority_policy_is_not_applicable_across_jurisdictions():
    left = {"id": "cn", "source_type": "guideline", "official_or_regulatory_status": "GUIDELINE", "jurisdiction": "CN"}
    right = {"id": "us", "source_type": "guideline", "official_or_regulatory_status": "GUIDELINE", "jurisdiction": "US"}
    policy = SourcePriorityPolicyRequest(jurisdiction="CN", ordered_source_kinds=["OFFICIAL_GUIDELINE"], rationale="Chinese legal and guidance context only.").model_dump()
    assert apply_source_priority_policy(left, right, policy)["status"] == "NOT_APPLICABLE"


def test_claim_level_supersession_marks_only_explicit_target_claim():
    old_a = Claim(id="a-old", normalized_claim="Old A", provenance="SOURCE", source_quote="Old A", source_refs=[SourceRef(document_id="old", page=1, quote="Old A")])
    old_b = Claim(id="b-old", normalized_claim="Old B", provenance="SOURCE", source_quote="Old B", source_refs=[SourceRef(document_id="old", page=1, quote="Old B")])
    new_a = Claim(id="a-new", normalized_claim="New A", provenance="SOURCE", source_quote="New A", source_refs=[SourceRef(document_id="new", page=1, quote="New A")])
    project = Project(title="t", presentation_question="q", claims=[old_a, old_b, new_a])
    event = register_claim_supersession(project, ClaimSupersessionRequest(superseded_claim_id="a-old", superseding_claim_id="a-new", explicit_source_supersession=True, rationale="The new source explicitly replaces the recommendation for Claim A only."))
    assert event["record"]["superseded_claim_id"] == "a-old"
    assert old_a.superseded_by_claim_id == "a-new"
    assert old_b.superseded_by_claim_id is None


def test_claim_supersession_rejects_implicit_or_date_only_relation():
    old = Claim(id="old", normalized_claim="Old", provenance="SUMMARY")
    new = Claim(id="new", normalized_claim="New", provenance="SUMMARY")
    project = Project(title="t", presentation_question="q", claims=[old, new])
    try:
        register_claim_supersession(project, ClaimSupersessionRequest(superseded_claim_id="old", superseding_claim_id="new", explicit_source_supersession=False, rationale="Newer publication date alone."))
    except Exception as error:
        assert "explicit source version relation" in str(error).lower()
    else:
        raise AssertionError("implicit publication-date supersession was accepted")


def test_medical_review_sheet_aggregates_required_high_risk_sections():
    red = Claim(id="red", normalized_claim="Risk 20%", provenance="SOURCE", risk="RED", source_refs=[SourceRef(document_id="d", page=1, quote="20%")], numeric_facts=[NumericFact(value="20%", status="UNBOUND")])
    missing = Claim(id="missing", normalized_claim="Missing source", provenance="SOURCE")
    relationship = Relationship(id="syn", from_claim_id="red", to_claim_id="missing", relation_type="CLINICAL_PATHWAY", provenance="SYNTHESIS", risk="RED")
    project = Project(title="t", presentation_question="q", output_channel="public_xiaohongshu", claims=[red, missing], relationships=[relationship])
    # this fixture is deliberately broken; the sheet reports the failures, so a
    # FAILING verification is the correct thing to record here
    record_verification(project)
    sheet = medical_review_sheet(project)
    assert sheet["red_claims"] == [red]
    assert sheet["red_relationships"] == [relationship]
    assert sheet["synthesis_relationships"] == [relationship]
    assert sheet["numeric_issues"]
    assert sheet["source_issues"]
    assert sheet["compliance_issues"]
