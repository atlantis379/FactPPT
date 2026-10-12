"""Transport corruption/identity tests; no model or workflow approvals."""
import copy
import pytest
from app.worker_context import pack, unpack, fingerprint, metrics


def sample():
    text = "只适用于满足以下条件的人群；阈值≥300/μL，并非所有患者。" * 10
    return {"kind": "SUMMARY", "input_sha256": "business-version", "sources": [
        {"id": "S01", "units": [{"id": "S01:p1:u1", "text": text}]},
        {"id": "S02", "units": [{"id": "S02:p1:u1", "text": text},
                                 {"id": "S02:p1:u2", "text": text.replace("≥", ">")}]}
    ], "result_contract": {"sections": []}}


def test_roundtrip_keeps_sources_and_operators():
    brief = sample()
    packet = pack(brief)
    assert unpack(packet) == brief
    assert metrics(brief, packet)["packet_utf8_bytes"] < metrics(brief, packet)["original_utf8_bytes"]
    assert packet["payload"]["sources"][0]["id"] == "S01"
    assert isinstance(packet["payload"]["sources"][1]["units"][1]["text"], str)


def resign(packet):
    packet["packet_sha256"] = fingerprint({k: v for k, v in packet.items() if k != "packet_sha256"})


def test_packet_corruption_and_missing_references_rejected():
    packet = pack(sample())
    damaged = copy.deepcopy(packet)
    damaged["shared_texts"]["t1"] += "不得使用"
    with pytest.raises(ValueError, match="packet hash"):
        unpack(damaged)
    resign(damaged)
    with pytest.raises(ValueError, match="Original context"):
        unpack(damaged)
    missing = copy.deepcopy(packet)
    missing["shared_texts"].clear()
    resign(missing)
    with pytest.raises(ValueError, match="Missing"):
        unpack(missing)


def test_reserved_key_and_blind_read_isolation():
    brief = sample()
    brief["collision"] = {"$shared_text": "secret"}
    with pytest.raises(ValueError, match="Reserved"):
        pack(brief)
    with pytest.raises(ValueError, match="supports"):
        pack({"kind": "SECOND_READ", "text": "first reader answer"})


def test_short_queue_receipt_does_not_replay_evidence_or_completed_history():
    from app.deckflow_api import workflow_ack
    result = {"id": "w", "stage": "SUMMARY_REVIEW_REQUIRED", "sources": [{"text": "private-source"}],
              "tasks": [{"id": "done", "kind": "SUMMARY", "status": "COMPLETE", "brief": "private-brief"},
                        {"id": "todo", "kind": "SUMMARY_REVIEW", "status": "PENDING", "lease_token": "private-token"}]}
    short = workflow_ack(result, "SUMMARY_REVIEW")
    assert len(short["tasks"]) == 1 and short["tasks"][0]["id"] == "todo"
    assert "private" not in str(short) and "sources" not in short
