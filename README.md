<div align="center">
<h1 align="center">
<a href="https://opennotes.ai"><img src="docs/images/logo.svg" alt="Open Notes" width="512" /></a>
</h1>

[Homepage](https://opennotes.ai) • [Philosophy](docs/PHILOSOPHY.md) • [Architecture](docs/ARCHITECTURE.md)

![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/opennotes-ai/opennotes/ci.yml?label=CI%20Build)
<a href="https://discord.gg/CsxBasRrte"><img alt="Discord" src="https://img.shields.io/discord/1448846366938759308?label=Discord"></a>

</div>

<hr/>
<div>

- [What is Open Notes?](#what-is-open-notes)
- [Why Open Notes?](#why-open-notes)
- [How It Works](#how-it-works)
- [Current Status](#current-status)
- [Modules and Directory Structure](#modules-and-directory-structure)
- [Quick Start](#quick-start)
- [Standalone Setup](#standalone-setup)
- [Development Setup](#development-setup)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [License](#license)

</div>
<hr/>

## What is Open Notes?

Open Notes is an AI-powered content moderation system that catches harmful content immediately and lets communities review those decisions afterward.

It works as a plugin for platforms you already use. Discourse is the first supported platform, with Discord available as a bot integration and Reddit planned next.

## Why Open Notes?

Existing community moderation approaches have real weaknesses:

- **No enforcement mechanism.** Systems like Twitter/X Community Notes annotate content but can't act on it. Harmful content stays up while the annotation process plays out.
- **Slow convergence.** Notes take hours or days to accumulate enough ratings to reach consensus. In the meantime, the damage is done.
- **Vulnerable to brigading.** After a Community Note gets published, it's often inundated with highly partisan voting. A significant percentage of published notes get un-published as a result.

These are structural problems, not implementation bugs. Open Notes addresses them by leading with AI moderation and using community oversight as a check on those automated decisions.

## How It Works

Open Notes has two layers that work together.

**AI moderation acts first.** When content is posted to a monitored channel, Open Notes classifies it immediately. Content that's clearly harmful gets acted on right away—hidden, flagged, or whatever action the community has configured. This happens in seconds, not hours.

**Community oversight reviews those decisions.** Every automated action creates a review item. Community members vote on whether the action was correct using the same bridging-based algorithm from Twitter/X Community Notes—where agreement across people who usually *disagree* counts for more than echo-chamber consensus. If the community decides the AI got it wrong, the action is reversed.

This means harmful content gets addressed immediately, but no decision is permanent. The AI handles speed; the community handles judgment. Communities still control what gets monitored, what thresholds trigger action, and who can participate in reviews.

## Current Status

![Version](https://img.shields.io/badge/version-0.0.1-blue) ![Stage](https://img.shields.io/badge/stage-alpha-orange)

Early but functional. [Add to your Discord](https://discord.com/oauth2/authorize?client_id=1423014656343019552) or self-host.

Contributor docs, issue templates, and the like are coming. Prioritizing core functionality first since many pieces need to work together for Open Notes to be useful.

## Modules and Directory Structure

- **opennotes-server**: FastAPI backend with PostgreSQL persistence, Redis caching, NATS messaging, OAuth/JWT authentication, and OpenTelemetry observability
- **opennotes-discourse**: Discourse plugin providing AI moderation, community review queue, and admin dashboard
- **opennotes-discord**: Discord bot with TypeScript/Discord.js providing slash commands and context menu integration
- **communitynotes**: Official Twitter/X Community Notes algorithm (git submodule)

### Directory Structure

A non-exhaustive map of the repository.

```
opennotes/
├── opennotes-server/         # FastAPI backend (Python)
│   ├── src/                  # Source code
│   │   ├── auth/            # OAuth, JWT, session management
│   │   ├── cache/           # Redis caching layer
│   │   ├── events/          # NATS event streaming
│   │   ├── notes/           # Note creation, scoring, embeddings
│   │   ├── users/           # User profiles and identities
│   │   ├── webhooks/        # Discord webhook delivery
│   │   ├── monitoring/      # OpenTelemetry instrumentation
│   │   ├── llm_config/      # LLM provider configuration
│   │   ├── workers/         # Background task workers
│   │   └── main.py          # FastAPI application
│   ├── alembic/             # Database migrations
│   ├── tests/               # Test suite
│   ├── pyproject.toml       # Python dependencies
│   └── .env.example          # Configuration template
│
├── opennotes-discourse/       # Discourse plugin (Ruby/Ember)
│   ├── plugin/               # Plugin source
│   │   ├── plugin.rb         # Entry point, event hooks, settings
│   │   ├── app/              # Controllers, models, serializers
│   │   ├── assets/           # Ember/Glimmer UI components
│   │   └── config/           # Settings, locales
│   ├── docs/                 # Admin and user guides
│   └── tests/                # E2E test suite (Playwright)
│
├── opennotes-discord/        # Discord bot (TypeScript)
│   ├── src/                  # Source code
│   │   ├── commands/        # Slash commands
│   │   │   ├── note.ts      # /note (write, request, view, rate, score)
│   │   │   ├── config.ts    # /config
│   │   │   ├── list.ts      # /list
│   │   │   ├── about-opennotes.ts # /about-opennotes
│   │   │   ├── status-bot.ts # /status-bot
│   │   │   └── note-request-context.ts # Context menu
│   │   ├── services/        # Business logic layer
│   │   └── lib/             # Shared utilities
│   ├── package.json         # Node.js dependencies (pnpm)
│   └── .env.example          # Configuration template
│
├── docs/                     # Documentation
│   ├── ARCHITECTURE.md      # System architecture and infrastructure
│   ├── AUTHENTICATION.md    # OAuth/JWT flow documentation
│   └── SCHEMA_AND_API_WORKFLOW.md # API schemas and workflows
│
└── communitynotes/           # Official scoring algorithm (git submodule)
    ├── scoring/src/         # Python scoring implementation
    └── README.md            # Algorithm documentation
```

## Quick Start

### Prerequisites

- [Python 3.11+](https://github.com/python/cpython) with [uv](https://github.com/astral-sh/uv)
- [Node.js 18+](https://github.com/nodejs/node) with [pnpm](https://github.com/pnpm/pnpm)
- [PostgreSQL 15+](https://github.com/postgres/postgres)
- [Redis 7+](https://github.com/redis/redis)
- [NATS Server 2.10+](https://github.com/nats-io/nats-server)
- Discord bot credentials
- Git with submodule support

### 1. Clone and Initialize Submodules

```console
git clone <repository-url>
cd opennotes
git submodule update --init --recursive
```

### 2. Configure Environment

```console
cp .env.example .env
# Edit .env with your credentials (see .env.md for variable reference)
```

### 3. Start the Server

```console
cd opennotes-server
uv sync --extra scoring
uv run python -m src.main
```

Server runs at http://localhost:8000

### 4. Start the Discord Bot

```console
cd opennotes-discord
pnpm install
pnpm run build
pnpm start
```

## Standalone Setup

For running Open Notes independently without the multiverse monorepo, see [docs/STANDALONE-SETUP.md](docs/STANDALONE-SETUP.md).

The standalone setup uses Docker Compose and mise tasks (`mise run dev:up`, `mise run dev:down`, `mise run dev:ps`) and does not require OpenTofu or yq.

## Development Setup

### Server Development

```console
cd opennotes-server

# Install dependencies
uv sync --extra scoring

# Run tests
uv run pytest

# Run with auto-reload
uv run uvicorn src.main:app --reload

# Lint and format
uv run ruff check .
uv run ruff format .

# Type checking
uv run basedpyright src/
```

### Bot Development

```console
cd opennotes-discord

# Install dependencies
pnpm install

# Run in watch mode
pnpm run dev

# Build TypeScript
pnpm run build

# Lint
pnpm run lint

# Run tests
pnpm test
```

### API Documentation

When the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Spec**: http://localhost:8000/openapi.json

## Configuration

### Server Configuration

Copy `.env.example` to `.env` and configure (see `.env.md` for full reference):

- Database connection (PostgreSQL)
- Redis connection
- NATS connection
- Discord OAuth credentials
- JWT secrets and encryption keys
- LLM provider API keys
- OpenTelemetry endpoints

### Bot Configuration

Copy `.env.example` to `.env` and configure:

- Discord bot token and client ID
- Server URL
- Environment and logging settings

## Documentation

- [docs/STANDALONE-SETUP.md](docs/STANDALONE-SETUP.md) - Full standalone setup guide (Docker Compose, mise tasks, fixtures)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture and infrastructure components
- [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md) - OAuth/JWT authentication flow
- [docs/SCHEMA_AND_API_WORKFLOW.md](docs/SCHEMA_AND_API_WORKFLOW.md) - API schemas and workflows
- [opennotes-discourse/docs/ADMIN-GUIDE.md](opennotes-discourse/docs/ADMIN-GUIDE.md) - Discourse plugin setup and configuration
- [opennotes-discourse/docs/USER-GUIDE.md](opennotes-discourse/docs/USER-GUIDE.md) - How community review works for participants
- [communitynotes/README.md](communitynotes/README.md) - Community Notes Algorithm overview

## License

Open Notes is [open-core](https://en.wikipedia.org/wiki/Open-core_model), which means everything is open-source under MIT License by default, with the option to place some *future* functionality targeted towards larger scale users under other licenses. No bait-and-switch.

Legal: [LICENSE](LICENSE)
