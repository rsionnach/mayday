# src/nthlayer_respond/agents/triage.py
"""TriageAgent — first concrete agent in the Mayday pipeline."""
from __future__ import annotations

import json
from typing import Any

from nthlayer_respond.agents.base import AgentBase
from nthlayer_respond.types import AgentRole, IncidentContext, TriageResult


class TriageAgent(AgentBase):
    """Assess severity, blast radius, affected SLOs, and team assignment.

    Judgment SLO: severity reversal rate < 10%.
    """

    role = AgentRole.TRIAGE
    default_timeout = 15

    # ------------------------------------------------------------------ #
    # Judgment interface                                                   #
    # ------------------------------------------------------------------ #

    def build_prompt(self, context: IncidentContext) -> tuple[str, str]:
        system = (
            "You are a triage agent for incident response. "
            "Assess severity (0-4, where 0 is P0 critical), blast radius, "
            "affected SLOs, and team assignment. "
            "Your judgment SLO: less than 10% severity reversal rate. "
            "Respond with ONLY valid JSON."
        )

        parts: list[str] = []

        if context.trigger_source == "sitrep":
            parts.append(
                "You have pre-correlated context from SitRep. "
                "The following SitRep verdicts informed this incident:"
            )
            for vid in context.trigger_verdict_ids:
                try:
                    v = self._verdict_store.get(vid)
                    if v is not None:
                        parts.append(
                            f"  - service={v.subject.service!r}  "
                            f"summary={v.subject.summary!r}  "
                            f"confidence={v.judgment.confidence}  "
                            f"reasoning={v.judgment.reasoning!r}"
                        )
                except Exception:  # noqa: BLE001
                    pass
        else:
            # pagerduty or manual
            parts.append(
                "No pre-correlation available. Raw alert only. "
                "Assess based solely on the topology information below."
            )

        # Always include topology
        parts.append(f"\nTopology: {json.dumps(context.topology)}")

        user = "\n".join(parts)
        return system, user

    def parse_response(self, response: str, context: IncidentContext) -> TriageResult:
        data = self._parse_json(response)

        raw_severity = data.get("severity", 2)
        severity = max(0, min(4, int(raw_severity)))

        blast_radius: list[str] = data.get("blast_radius") or []
        affected_slos: list[str] = data.get("affected_slos") or []
        assigned_team: str | None = data.get("assigned_team")
        reasoning: str = data.get("reasoning", "")

        return TriageResult(
            severity=severity,
            blast_radius=blast_radius,
            affected_slos=affected_slos,
            assigned_team=assigned_team,
            reasoning=reasoning,
        )

    def _apply_result(
        self, context: IncidentContext, result: TriageResult
    ) -> IncidentContext:
        context.triage = result
        return context

    # ------------------------------------------------------------------ #
    # Post-execute hook: autonomy reduction                               #
    # ------------------------------------------------------------------ #

    async def _post_execute(
        self, context: IncidentContext, result: Any
    ) -> IncidentContext:
        """Trigger autonomy reduction when a model-update signal is present
        and severity is low enough that the update may have distorted judgment.

        Condition: any trigger verdict carries tag "agent_model_update"
        AND result.severity <= 2.
        """
        if not (hasattr(result, "severity") and result.severity <= 2):
            return context

        for vid in context.trigger_verdict_ids:
            try:
                v = self._verdict_store.get(vid)
                tags = (v.judgment.tags or []) if v is not None else []
                if "agent_model_update" in tags:
                    arbiter_url: str = self._config.get("arbiter_url", "")
                    await self._request_autonomy_reduction(
                        agent_name="triage",
                        arbiter_url=arbiter_url,
                        reason=(
                            f"Trigger verdict {vid} flagged agent_model_update; "
                            f"incident {context.id} severity={result.severity}"
                        ),
                    )
                    break
            except Exception:  # noqa: BLE001
                pass

        return context
