FROM node:20-alpine AS builder

WORKDIR /workspace

# Set CI mode to prevent interactive prompts
ENV CI=true

# Enable pnpm (corepack reads the pinned version from root package.json's
# packageManager field — keeping pnpm aligned with the host toolchain)
RUN corepack enable

# Copy root workspace files (lockfile and workspace config live at repo root)
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./

# Copy each workspace member's package.json so pnpm can resolve the full
# workspace graph against the root lockfile. Playground/platform package.jsons
# are copied (no source) so --frozen-lockfile sees every member the lockfile
# expects; the --filter keeps the install scoped to opennotes-discord's graph.
COPY packages/shared-types/package.json ./packages/shared-types/package.json
COPY packages/test-utils/package.json ./packages/test-utils/package.json
COPY opennotes-discord/package.json ./opennotes-discord/package.json
COPY opennotes-playground/package.json ./opennotes-playground/package.json
COPY opennotes-platform/package.json ./opennotes-platform/package.json

# Install dependencies scoped to the opennotes-discord graph
RUN pnpm install --frozen-lockfile --filter opennotes-discord...

# Copy workspace package source and build (cached unless packages/ source changes)
COPY packages ./packages
RUN rm -rf packages/*/dist packages/*/*.tsbuildinfo && \
    pnpm --filter './packages/**' run build

# Copy OpenAPI spec for type generation and Discord bot source
COPY opennotes-server/openapi.json ./opennotes-server/openapi.json
COPY opennotes-discord ./opennotes-discord

# Build the Discord bot
WORKDIR /workspace/opennotes-discord
RUN pnpm run build

# Production stage
FROM node:20-alpine

WORKDIR /app

# Set CI mode to prevent interactive prompts
ENV CI=true

# Enable pnpm (corepack reads the pinned version from the copied root
# package.json's packageManager field)
RUN corepack enable

# Copy root workspace files for production install
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./

# Copy BUILT workspace packages from builder (must be before pnpm install)
COPY --from=builder /workspace/packages ./packages

# Copy workspace member package.jsons so pnpm can resolve the workspace graph
COPY --from=builder /workspace/opennotes-discord/package.json ./opennotes-discord/package.json
COPY --from=builder /workspace/opennotes-playground/package.json ./opennotes-playground/package.json
COPY --from=builder /workspace/opennotes-platform/package.json ./opennotes-platform/package.json

# Install only production dependencies scoped to the opennotes-discord graph
RUN pnpm install --frozen-lockfile --prod --filter opennotes-discord...

# Copy built application into the discord workspace directory
COPY --from=builder /workspace/opennotes-discord/dist ./opennotes-discord/dist

WORKDIR /app/opennotes-discord

CMD ["node", "--require", "./dist/instrumentation.cjs", "dist/index.js"]
