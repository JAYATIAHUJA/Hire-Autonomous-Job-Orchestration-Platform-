# Apply Computer

The per-run browser computer the apply agent drives: Playwright Chromium, element-reference
actions, human takeover, "type a secret for me", CAPTCHA detection and a live screencast.

**Phase 0:** the image is built straight from CopilotKit/OpenBot `agent-computer/` at the pinned
revision `b6932d31a8d6e7896c15139dfc27a6c6911deb27` (MIT). Nothing is changed. See the
`computer-image` service in `compose.yml` (profile `computers`).

**Phase 4:** this folder becomes a real fork that adds file upload, `<select>` handling, iframe
frames, form-scan, an egress allowlist and gVisor (PLAN.md §5.12). When forking, keep
`LICENSE.openbot` and the Apache-2.0 and BSD notices referenced in `screencast.ts`.
