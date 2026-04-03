"""Tests for ApprovalServer HTTP routes."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from nthlayer_respond.config import RespondConfig
from nthlayer_respond.context_store import SQLiteContextStore
from nthlayer_respond.server import ApprovalServer
from nthlayer_respond.types import (
    IncidentContext,
    IncidentState,
    RemediationResult,
)


@pytest.fixture
def context_store(tmp_path):
    s = SQLiteContextStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def mock_coordinator():
    coord = AsyncMock()
    return coord


@pytest.fixture
def config():
    return RespondConfig(approval_timeout_seconds=900)


@pytest.fixture
def server(mock_coordinator, context_store, config):
    return ApprovalServer(mock_coordinator, context_store, config)


@pytest.fixture
def client(server):
    return TestClient(server.build_app())


def _awaiting_context(incident_id="INC-TEST-001"):
    return IncidentContext(
        id=incident_id,
        state=IncidentState.AWAITING_APPROVAL,
        created_at="2026-04-03T10:00:00Z",
        updated_at="2026-04-03T10:00:00Z",
        trigger_source="nthlayer-correlate",
        trigger_verdict_ids=["vrd-trigger"],
        topology={},
        remediation=RemediationResult(
            proposed_action="rollback",
            target="fraud-detect",
            requires_human_approval=True,
            reasoning="needs approval",
        ),
        verdict_chain=["vrd-triage", "vrd-investigation", "vrd-remediation"],
    )


def test_approve_success(client, mock_coordinator, context_store):
    """POST /api/v1/incidents/{id}/approve calls coordinator.approve."""
    ctx = _awaiting_context()
    context_store.save(ctx)

    resolved_ctx = _awaiting_context()
    resolved_ctx.state = IncidentState.RESOLVED
    resolved_ctx.verdict_chain.append("vrd-approved")
    mock_coordinator.approve = AsyncMock(return_value=resolved_ctx)

    resp = client.post(
        "/api/v1/incidents/INC-TEST-001/approve",
        json={"approved_by": "rob@nthlayer.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "resolved"
    assert data["approved_by"] == "rob@nthlayer.com"
    mock_coordinator.approve.assert_called_once_with(
        "INC-TEST-001", approved_by="rob@nthlayer.com"
    )


def test_approve_wrong_state(client, mock_coordinator, context_store):
    """POST approve on non-AWAITING_APPROVAL returns 409."""
    ctx = _awaiting_context()
    ctx.state = IncidentState.RESOLVED
    context_store.save(ctx)

    mock_coordinator.approve = AsyncMock(
        side_effect=ValueError("not AWAITING_APPROVAL")
    )

    resp = client.post(
        "/api/v1/incidents/INC-TEST-001/approve",
        json={"approved_by": "rob"},
    )
    assert resp.status_code == 409


def test_approve_not_found(client, mock_coordinator):
    """POST approve on nonexistent incident returns 404."""
    mock_coordinator.approve = AsyncMock(
        side_effect=ValueError("not found")
    )

    resp = client.post(
        "/api/v1/incidents/INC-MISSING/approve",
        json={},
    )
    assert resp.status_code == 404


def test_reject_success(client, mock_coordinator, context_store):
    """POST /api/v1/incidents/{id}/reject calls coordinator.reject."""
    ctx = _awaiting_context()
    context_store.save(ctx)

    escalated_ctx = _awaiting_context()
    escalated_ctx.state = IncidentState.ESCALATED
    mock_coordinator.reject = AsyncMock(return_value=escalated_ctx)

    resp = client.post(
        "/api/v1/incidents/INC-TEST-001/reject",
        json={"reason": "Wrong target", "rejected_by": "rob@nthlayer.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "escalated"
    mock_coordinator.reject.assert_called_once_with(
        "INC-TEST-001", "Wrong target", rejected_by="rob@nthlayer.com"
    )


def test_reject_missing_reason(client, mock_coordinator, context_store):
    """POST reject without reason returns 400."""
    ctx = _awaiting_context()
    context_store.save(ctx)

    resp = client.post(
        "/api/v1/incidents/INC-TEST-001/reject",
        json={},
    )
    assert resp.status_code == 400


def test_get_incident_status(client, context_store):
    """GET /api/v1/incidents/{id} returns incident state."""
    ctx = _awaiting_context()
    context_store.save(ctx)

    resp = client.get("/api/v1/incidents/INC-TEST-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["incident_id"] == "INC-TEST-001"
    assert data["state"] == "awaiting_approval"
    assert data["proposed_action"] == "rollback"
    assert data["target"] == "fraud-detect"


def test_get_incident_not_found(client):
    """GET nonexistent incident returns 404."""
    resp = client.get("/api/v1/incidents/INC-MISSING")
    assert resp.status_code == 404
