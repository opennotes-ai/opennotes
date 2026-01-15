FROM node:20-alpine AS builder

WORKDIR /workspace

# Set CI mode to prevent interactive prompts
ENV CI=true

# Enable pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy workspace configuration from opennotes-discord (where workspace is defined)
COPY opennotes-discord/pnpm-workspace.yaml opennotes-discord/package.json opennotes-discord/pnpm-lock.yaml ./

# Copy workspace packages (shared dependencies) from opennotes-discord
COPY opennotes-discord/packages ./packages

# Copy OpenAPI spec for type generation
COPY opennotes-server/openapi.json ./opennotes-server/openapi.json

# Copy Discord bot package
COPY opennotes-discord ./opennotes-discord

# Install all workspace dependencies (including dev for build)
RUN pnpm install --frozen-lockfile

# Clean and build workspace packages (remove stale tsbuildinfo to force fresh build)
RUN rm -rf packages/*/dist packages/*/*.tsbuildinfo && \
    pnpm --filter './packages/**' run build

# Set working directory to Discord bot for final build steps
WORKDIR /workspace/opennotes-discord

# Set up node_modules symlinks for this workspace package
# (pnpm workspaces require node_modules at each package location)
RUN pnpm install --frozen-lockfile

# Build the application
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
