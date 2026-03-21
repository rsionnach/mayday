# src/nthlayer_respond/agents/communication.py
"""CommunicationAgent — two-phase incident communication drafting."""
from __future__ import annotations

from datetime import datetime, timezone

from nthlayer_respond.agents.base import AgentBase
from nthlayer_respond.types import (
    AgentRole,
    CommunicationResult,
    CommunicationUpdate,
    IncidentContext,
)


class CommunicationAgent(AgentBase):
    """Draft incident communications in two pipeline phases.

    Phase 1 (context.remediation is None): draft initial status update.
    Phase 2 (context.remediation is not None): draft resolution update.

    Judgment SLO: human edit rate < 15%.
    """

    role = AgentRole.COMMUNICATION
    default_timeout = 20

    # ------------------------------------------------------------------ #
    # Judgment interface                                                   #
    # ------------------------------------------------------------------ #

    def build_prompt(self, context: IncidentContext) -> tuple[str, str]:
        system = (
            "You are a communication agent. "
            "Draft incident communications. "
            "You MUST NOT contradict investigation findings. "
            "You MUST NOT communicate resolution until remediation is confirmed. "
            "Judgment SLO: less than 15% human edit rate. "
            "Respond with ONLY valid JSON."
        )

        if context.remediation is None:
            # Phase 1 — initial status update
            triage = context.triage
            severity = triage.severity if triage is not None else "unknown"
            blast_radius = triage.blast_radius if triage is not None else []
            user = (
                f"Draft an initial status update. "
                f"We know: severity={severity}, "
                f"affected services={blast_radius}. "
                f"Investigation is ongoing."
            )
        else:
            # Phase 2 — resolution update
            inv = context.investigation
            rem = context.remediation
            root_cause = inv.root_cause if inv is not None else "under investigation"
            user = (
                f"Draft a resolution update. "
                f"Root cause: {root_cause}. "
                f"Remediation: {rem.proposed_action} on {rem.target}. "
                f"Outcome: {rem.execution_result}."
            )

        return system, user

    def parse_response(
        self, response: str, context: IncidentContext
    ) -> CommunicationResult:
        data = self._parse_json(response)

        timestamp = datetime.now(tz=timezone.utc).isoformat()

        updates: list[CommunicationUpdate] = []
        for raw in data.get("updates") or []:
            updates.append(
                CommunicationUpdate(
                    channel=raw.get("channel", ""),
                    timestamp=timestamp,
                    update_type=raw.get("update_type", ""),
                    content=raw.get("content", ""),
                )
            )

        reasoning: str = data.get("reasoning", "")
        return CommunicationResult(updates_sent=updates, reasoning=reasoning)

    def _apply_result(
        self, context: IncidentContext, result: CommunicationResult
    ) -> IncidentContext:
        if context.communication is None:
            context.communication = result
        else:
            # APPEND — do not replace; phase 2 adds to phase 1's updates
            context.communication.updates_sent.extend(result.updates_sent)
            context.communication.reasoning = result.reasoning
        return context
