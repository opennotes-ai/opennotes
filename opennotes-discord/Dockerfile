FROM node:20-alpine AS builder

WORKDIR /workspace

# Set CI mode to prevent interactive prompts
ENV CI=true

# Enable pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy dependency resolution files only (lockfile, workspace config, package.json per package)
COPY opennotes-discord/pnpm-workspace.yaml opennotes-discord/package.json opennotes-discord/pnpm-lock.yaml ./
COPY opennotes-discord/packages/shared-types/package.json ./packages/shared-types/package.json
COPY opennotes-discord/packages/test-utils/package.json ./packages/test-utils/package.json

# Install all workspace dependencies (cached unless lockfile or package.json changes)
RUN pnpm install --frozen-lockfile

# Copy workspace package source and build (cached unless packages/ source changes)
COPY opennotes-discord/packages ./packages
RUN rm -rf packages/*/dist packages/*/*.tsbuildinfo && \
    pnpm --filter './packages/**' run build

# Copy OpenAPI spec for type generation and Discord bot source
COPY opennotes-server/openapi.json ./opennotes-server/openapi.json
COPY opennotes-discord ./opennotes-discord

# Set working directory to Discord bot for final build steps
WORKDIR /workspace/opennotes-discord
RUN pnpm install --frozen-lockfile
RUN pnpm run build

# Production stage
FROM node:20-alpine

WORKDIR /app

# Set CI mode to prevent interactive prompts
ENV CI=true

# Enable pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy workspace files for production install
COPY opennotes-discord/pnpm-workspace.yaml opennotes-discord/package.json opennotes-discord/pnpm-lock.yaml ./

# Copy BUILT workspace packages from builder (must be before pnpm install)
COPY --from=builder /workspace/packages ./packages

# Install only production dependencies (packages already have dist/)
RUN pnpm install --frozen-lockfile --prod

# Copy built application directly to /app/dist (matches package.json start script)
COPY --from=builder /workspace/opennotes-discord/dist ./dist

CMD ["node", "--require", "./dist/instrumentation.cjs", "dist/index.js"]
