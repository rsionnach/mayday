# nthlayer-respond (Deprecated)

> **This repository is deprecated.** The functionality previously
> developed here has been consolidated into [`nthlayer-workers`][workers]
> as part of the tiered architecture migration.
>
> Active development continues in the new structure:
> - **respond module:** [`nthlayer-workers/src/nthlayer_workers/respond/`][module]
> - **Project front door:** [`nthlayer`][nthlayer]
> - **Architecture context:** [`opensrm/ARCHITECTURE.md`][arch]
>
> This repository is preserved for historical reference and will be
> archived 90 days from the date of this notice.
>
> If you arrived here from an article or external link, the up-to-date
> implementation is at [`nthlayer-workers`][workers]. Project context
> and architectural principles are at [`nthlayer`][nthlayer].


## Note on operator-facing CLI commands

Branch `feat/opensrm-0rg-cli` adds 6 SRE CLI subcommands — `oncall`, `brief`,
`shift-report`, `suppress`, `post-incident`, `delegate` — plus their
supporting logic modules under `src/nthlayer_respond/sre/`. These were
intentionally **not** ported to the worker module: they are operator-interactive
commands, not background computation. Their natural home in the new
architecture is [`nthlayer-bench`][bench] (Tier 3, operator interface).

Inventory + bench-equivalent shape for each command:
[opensrm/docs/superpowers/specs/2026-04-26-respond-sre-cli-inventory-for-bench.md][inventory].
Demo-prioritised: `brief` and `post-incident` first.

[bench]: https://github.com/rsionnach/nthlayer-bench
[inventory]: https://github.com/rsionnach/opensrm/blob/main/docs/superpowers/specs/2026-04-26-respond-sre-cli-inventory-for-bench.md

[workers]: https://github.com/rsionnach/nthlayer-workers
[module]: https://github.com/rsionnach/nthlayer-workers/tree/main/src/nthlayer_workers/respond
[nthlayer]: https://github.com/rsionnach/nthlayer
[arch]: https://github.com/rsionnach/opensrm/blob/main/ARCHITECTURE.md
