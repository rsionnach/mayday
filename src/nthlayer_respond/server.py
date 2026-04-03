"""HTTP server for incident approval workflows.

Starlette ASGI app with routes for approve, reject, status, and
Slack interaction callbacks. Embedded in `nthlayer-respond serve`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from nthlayer_respond.config import RespondConfig
from nthlayer_respond.types import IncidentState

logger = logging.getLogger(__name__)


class ApprovalServer:
    """HTTP server for incident approval workflows."""

    def __init__(
        self,
        coordinator: Any,
        context_store: Any,
        config: RespondConfig,
    ) -> None:
        self._coordinator = coordinator
        self._context_store = context_store
        self._config = config
        self._timeouts: dict[str, asyncio.Task] = {}

    def build_app(self) -> Starlette:
        """Build the Starlette ASGI application."""
        routes = [
            Route(
                "/api/v1/incidents/{incident_id}/approve",
                self.handle_approve,
                methods=["POST"],
            ),
            Route(
                "/api/v1/incidents/{incident_id}/reject",
                self.handle_reject,
                methods=["POST"],
            ),
            Route(
                "/api/v1/incidents/{incident_id}",
                self.handle_status,
                methods=["GET"],
            ),
            Route(
                "/api/v1/slack/interactions",
                self.handle_slack_interaction,
                methods=["POST"],
            ),
        ]
        return Starlette(routes=routes)

    async def handle_approve(self, request: Request) -> JSONResponse:
        """POST /api/v1/incidents/{id}/approve"""
        incident_id = request.path_params["incident_id"]
        body = await request.json() if await request.body() else {}
        approved_by = body.get("approved_by")

        try:
            ctx = await self._coordinator.approve(
                incident_id, approved_by=approved_by
            )
        except ValueError as exc:
            msg = str(exc)
            if "not found" in msg.lower():
                return JSONResponse({"error": msg}, status_code=404)
            return JSONResponse({"error": msg}, status_code=409)

        self.cancel_timeout(incident_id)

        return JSONResponse({
            "incident_id": ctx.id,
            "state": ctx.state.value,
            "action": ctx.remediation.proposed_action if ctx.remediation else None,
            "target": ctx.remediation.target if ctx.remediation else None,
            "approved_by": approved_by,
            "execution_result": ctx.remediation.execution_result if ctx.remediation else None,
            "verdict_id": ctx.verdict_chain[-1] if ctx.verdict_chain else None,
        })

    async def handle_reject(self, request: Request) -> JSONResponse:
        """POST /api/v1/incidents/{id}/reject"""
        incident_id = request.path_params["incident_id"]
        body = await request.json() if await request.body() else {}
        reason = body.get("reason")
        rejected_by = body.get("rejected_by")

        if not reason:
            return JSONResponse(
                {"error": "reason is required"}, status_code=400
            )

        try:
            ctx = await self._coordinator.reject(
                incident_id, reason, rejected_by=rejected_by
            )
        except ValueError as exc:
            msg = str(exc)
            if "not found" in msg.lower():
                return JSONResponse({"error": msg}, status_code=404)
            return JSONResponse({"error": msg}, status_code=409)

        self.cancel_timeout(incident_id)

        return JSONResponse({
            "incident_id": ctx.id,
            "state": ctx.state.value,
            "rejected_by": rejected_by,
            "reason": reason,
        })

    async def handle_status(self, request: Request) -> JSONResponse:
        """GET /api/v1/incidents/{id}"""
        incident_id = request.path_params["incident_id"]
        ctx = self._context_store.load(incident_id)

        if ctx is None:
            return JSONResponse(
                {"error": f"Incident {incident_id!r} not found"}, status_code=404
            )

        result: dict[str, Any] = {
            "incident_id": ctx.id,
            "state": ctx.state.value,
            "created_at": ctx.created_at,
            "updated_at": ctx.updated_at,
            "trigger_source": ctx.trigger_source,
        }
        if ctx.remediation:
            result["proposed_action"] = ctx.remediation.proposed_action
            result["target"] = ctx.remediation.target
            result["requires_human_approval"] = ctx.remediation.requires_human_approval
            result["executed"] = ctx.remediation.executed
        if ctx.triage:
            result["severity"] = ctx.triage.severity
        return JSONResponse(result)

    async def handle_slack_interaction(self, request: Request) -> Response:
        """POST /api/v1/slack/interactions — Slack callback endpoint.

        Placeholder — full implementation in Task 7.
        """
        return Response(status_code=200)

    def start_timeout(self, incident_id: str) -> None:
        """Start a background timeout task for an incident."""
        self.cancel_timeout(incident_id)
        task = asyncio.create_task(self._timeout_task(incident_id))
        self._timeouts[incident_id] = task

    def cancel_timeout(self, incident_id: str) -> None:
        """Cancel the timeout task for an incident if active."""
        task = self._timeouts.pop(incident_id, None)
        if task and not task.done():
            task.cancel()

    async def _timeout_task(self, incident_id: str) -> None:
        """Wait for timeout, then auto-reject if still awaiting approval."""
        try:
            await asyncio.sleep(self._config.approval_timeout_seconds)
        except asyncio.CancelledError:
            return

        ctx = self._context_store.load(incident_id)
        if ctx is None or ctx.state != IncidentState.AWAITING_APPROVAL:
            return

        try:
            await self._coordinator.reject(
                incident_id,
                f"Approval timed out after {self._config.approval_timeout_seconds}s",
                rejected_by="system/timeout",
            )
            logger.info("Approval timed out", extra={"incident_id": incident_id})
        except Exception as exc:
            logger.warning("Timeout reject failed: %s", exc)
        finally:
            self._timeouts.pop(incident_id, None)

    async def recover_pending_approvals(self) -> None:
        """On startup, scan for AWAITING_APPROVAL incidents and start timeouts."""
        import time as _time
        from datetime import datetime, timezone

        active = self._context_store.list_active()
        for incident_id in active:
            ctx = self._context_store.load(incident_id)
            if ctx is None or ctx.state != IncidentState.AWAITING_APPROVAL:
                continue

            try:
                updated = datetime.fromisoformat(ctx.updated_at)
                elapsed = _time.time() - updated.replace(tzinfo=timezone.utc).timestamp()
                remaining = self._config.approval_timeout_seconds - elapsed
            except (ValueError, TypeError):
                remaining = self._config.approval_timeout_seconds

            if remaining <= 0:
                try:
                    await self._coordinator.reject(
                        incident_id,
                        "Approval timed out (expired during server downtime)",
                        rejected_by="system/timeout",
                    )
                except Exception as exc:
                    logger.warning("Timeout recovery reject failed: %s", exc)
            else:
                self.cancel_timeout(incident_id)
                task = asyncio.create_task(self._timeout_with_delay(incident_id, remaining))
                self._timeouts[incident_id] = task

    async def _timeout_with_delay(self, incident_id: str, delay: float) -> None:
        """Like _timeout_task but with a custom delay (for recovery)."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        ctx = self._context_store.load(incident_id)
        if ctx is None or ctx.state != IncidentState.AWAITING_APPROVAL:
            return

        try:
            await self._coordinator.reject(
                incident_id,
                f"Approval timed out after {self._config.approval_timeout_seconds}s",
                rejected_by="system/timeout",
            )
        except Exception as exc:
            logger.warning("Timeout reject failed: %s", exc)
        finally:
            self._timeouts.pop(incident_id, None)
