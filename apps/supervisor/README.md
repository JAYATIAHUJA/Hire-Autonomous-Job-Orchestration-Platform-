# Computer supervisor

Starts and stops one **Apply Computer** (a Docker container with Playwright Chromium) per bot.

**Phase 0:** built from CopilotKit/OpenBot at the pinned revision
`b6932d31a8d6e7896c15139dfc27a6c6911deb27` (MIT). BuildKit downloads it from the Git context
set in `compose.yml`. One patch is applied at build time (`harden-supervisor.mjs`, adapted from
OpenDots): each computer gets `HMAC-SHA256(COMPUTER_TOKEN, "hire-computer:" + botId)` and never
the master token. If the upstream line it patches changes, the build fails on purpose.

**Phase 4:** this becomes a real fork in this folder, adding placement across nodes, idle reaping,
an egress allowlist and gVisor (PLAN.md §5.12).

Licences: `LICENSE.openbot` (CopilotKit, MIT) and `LICENSE.opendots` (Atai Barkai, MIT).
