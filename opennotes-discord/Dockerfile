FROM node:20-alpine AS builder

WORKDIR /workspace

# Enable pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy workspace configuration
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./

# Copy workspace packages (shared dependencies)
COPY packages ./packages

# Copy OpenAPI spec for type generation
COPY opennotes-server/openapi.json ./opennotes-server/openapi.json

# Copy Discord bot package
COPY opennotes-discord ./opennotes-discord

# Install all workspace dependencies (including dev for build)
RUN pnpm install --frozen-lockfile

# Clean and build workspace packages (remove stale tsbuildinfo to force fresh build)
RUN rm -rf packages/*/dist packages/*/*.tsbuildinfo && \
    pnpm --filter './packages/**' run build

# Set working directory to Discord bot
WORKDIR /workspace/opennotes-discord

# Build the application
RUN pnpm run build

# Production stage
FROM node:20-alpine

WORKDIR /app

# Enable pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy workspace files for production install
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./

# Copy BUILT workspace packages from builder (must be before pnpm install)
COPY --from=builder /workspace/packages ./packages

COPY opennotes-discord/package.json ./opennotes-discord/package.json

# Install only production dependencies (packages already have dist/)
RUN pnpm install --frozen-lockfile --prod --filter=opennotes-discord...

# Copy built application from builder
COPY --from=builder /workspace/opennotes-discord/dist ./opennotes-discord/dist

WORKDIR /app/opennotes-discord

CMD ["node", "dist/index.js"]
