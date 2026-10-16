# Computer supervisor, built from the pinned CopilotKit/OpenBot revision in compose.yml
# (build context "openbot"). It creates one Apply Computer per bot, with its own volumes.
# Phase 4 replaces this with a real fork in this folder (placement, reaping, egress allowlist).
FROM oven/bun:1.3.14-alpine
WORKDIR /app
COPY --from=openbot supervisor/package.json supervisor/bun.lock ./
RUN bun install --frozen-lockfile
COPY --from=openbot supervisor/src ./src
COPY LICENSE.openbot LICENSE.opendots ./
COPY harden-supervisor.mjs /tmp/harden-supervisor.mjs
RUN bun /tmp/harden-supervisor.mjs /app/src/environment.ts && rm /tmp/harden-supervisor.mjs
EXPOSE 4300
CMD ["bun", "src/index.ts"]
