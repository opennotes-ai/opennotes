# Standalone Setup Guide

How to run Open Notes independently without the multiverse monorepo wrapper.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (with Docker Compose v2+)
- [mise](https://mise.jdx.dev/) — manages tool versions and tasks
- Python 3.11+
- Node.js 20+
- pnpm

Note: you do NOT need OpenTofu or yq. Those are only used in the multiverse infrastructure wrapper.

## Quick Start

### 1. Clone the repository

```console
git clone https://github.com/opennotes-ai/opennotes.git
cd opennotes
git submodule update --init --recursive
```

### 2. Install tools and dependencies

```console
mise install
mise run install
```

### 3. Configure environment

```console
cp .env.example .env
```

Open `.env` and fill in the required values. See [`.env.md`](.env.md) for a full reference of all variables.

Key values to set:

| Variable | How to generate |
|---|---|
| `JWT_SECRET_KEY` | `openssl rand -hex 32` |
| `CREDENTIALS_ENCRYPTION_KEY` | See `.env.md` for the Fernet key generation steps |
| `DISCORD_TOKEN` | From the [Discord Developer Portal](https://discord.com/developers/applications) |
| `DISCORD_CLIENT_ID` | From the Discord Developer Portal |

### 4. Start services

```console
mise run dev:up
```

This brings up PostgreSQL, Redis, NATS, the API server, and the Discord bot via Docker Compose.

### 5. Verify services are running

```console
mise run dev:ps
```

Expected: `postgres`, `redis`, `nats`, and `opennotes-server` containers should be up.

Health check:

```console
curl http://localhost:8000/health
```

### 6. Run database migrations

```console
mise run db:migrate
```

## Loading Pre-populated Data (Optional)

If you have access to an anonymized fixture snapshot, you can load it instead of starting from an empty database:

```console
FIXTURE_GCS_BUCKET=your-bucket mise run fixture:load
```

To load a specific snapshot by timestamp:

```console
FIXTURE_GCS_BUCKET=your-bucket mise run fixture:load -- --timestamp=2026-04-08T12:00:00Z
```

This downloads the latest (or specified) anonymized database snapshot from GCS and restores it into the local PostgreSQL container.

## Available Mise Tasks

### Services

| Task | Description |
|---|---|
| `mise run dev:up` | Start all services via Docker Compose |
| `mise run dev:down` | Stop all services |
| `mise run dev:ps` | Show service status |

### Development

| Task | Description |
|---|---|
| `mise run dev` | Generate OpenAPI spec and TypeScript types |
| `mise run install` | Install all dependencies |

### Database

| Task | Description |
|---|---|
| `mise run db:migrate` | Run pending migrations |
| `mise run db:shell` | Open psql shell |
| `mise run db:check` | Check for schema drift |
| `mise run db:migrate:create` | Create a new migration |
| `mise run db:migrate:history` | Show migration history |

### Testing

| Task | Description |
|---|---|
| `mise run test` | Run all tests |
| `mise run test:server` | Run server tests |
| `mise run test:discord` | Run Discord bot tests |

### Linting

| Task | Description |
|---|---|
| `mise run lint` | Run all linters |
| `mise run lint:server -- --fix` | Auto-fix Python issues |
| `mise run lint:discord -- --fix` | Auto-fix TypeScript issues |

### Building

| Task | Description |
|---|---|
| `mise run build:containers:all` | Build all Docker images |
| `mise run build:types:openapi` | Regenerate OpenAPI spec and TypeScript types |

### Fixtures

| Task | Description |
|---|---|
| `mise run fixture:export` | Export anonymized database fixtures |
| `mise run fixture:load` | Load fixtures from GCS |
| `mise run fixture:generate-config` | Generate Greenmask anonymization config |

## Environment Variables

See [`.env.md`](.env.md) for a complete reference of all configuration variables, their purpose, and example values.

## Differences from Multiverse Setup

The [multiverse repo](https://github.com/opennotes-ai/multiverse) wraps `opennotes/` as a submodule and adds infrastructure management (OpenTofu, GCR image push, Cloud Run production deploy tasks). The standalone setup uses Docker Compose directly, which is simpler for development and self-hosting.

| Feature | Standalone | Multiverse |
|---|---|---|
| Container management | Docker Compose | OpenTofu + Docker |
| Configuration | `.env` files | `.env` files (same format) |
| Infrastructure | Not included | OpenTofu configs |
| Production deploy | Not included | Cloud Run deploy tasks |
| Required tools | Docker, mise | Docker, mise, OpenTofu, gcloud |
