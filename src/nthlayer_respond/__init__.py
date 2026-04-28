"""nthlayer-respond (DEPRECATED) — superseded by nthlayer-workers (respond module).

This package is deprecated as of v1.0.0 (2026-04-28). Functionality moved to
nthlayer-workers as part of the v1.5 tiered architecture consolidation.

Replacement: pip install nthlayer-workers

The respond functionality is now implemented as the RespondModule worker
inside nthlayer-workers — the same multi-agent incident-response pipeline
(triage / investigation / communication / remediation), now running as a
worker module within the consolidated runtime that talks to nthlayer-core
via HTTP API. Trigger ingestion now consumes correlation_snapshot
assessments (with quality_breach fallback) rather than direct correlation
verdicts.

Some operator-interactive commands (brief, post-incident, suppress,
shift-report, oncall, delegate) will move to nthlayer-bench in a later
release. See the SRE CLI inventory document referenced in the migration
guide.

Migration: https://github.com/rsionnach/nthlayer-respond
"""

import warnings as _warnings

_warnings.warn(
    "nthlayer-respond is deprecated. Functionality moved to nthlayer-workers "
    "as of v1.5 (RespondModule). Some operator-interactive commands will "
    "move to nthlayer-bench in a later release; see migration document. "
    "Install: pip install nthlayer-workers. "
    "Migration: https://github.com/rsionnach/nthlayer-respond",
    DeprecationWarning,
    stacklevel=2,
)
del _warnings

__version__ = "1.0.0"
