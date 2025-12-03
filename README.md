<div align="center">
<h1 align="center">
<a href="https://opennotes.ai"><img src="docs/images/logo.svg" alt="Open Notes" width="512" /></a>
</h1>

[Homepage](https://opennotes.ai) • [Philosophy](docs/PHILOSOPHY.md) • [Architecture](docs/ARCHITECTURE.md)
</div>

<hr/>
<div>

- [What is Open Notes?](#what-is-open-notes)
- [How It Works](#how-it-works)
- [Current Status](#current-status)
- [Modules and Directory Structure](#modules-and-directory-structure)
- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [License](#license)

</div>
<hr/>

## What is Open Notes?

Open Notes is a system for community-driven constructive moderation and annotation that can be added to anything, powered by the open-source Twitter/X Community Notes algorithm.

Discord is the demo/reference integration, but we want it go anywhere. Reddit is planned next, with more suggestions welcome!

## How It Works

The system has three parts.

**Requests** flag content without doing the work yourself. See something fishy? Hit "request note"—you're saying "someone should annotate this." Reasons include:
- "I want more context"
- "This is confusing"
- "This seems misleading"
- "Needs sources"

Requests queue publicly for anyone to fulfill.

**Notes** can come from anyone. We're on Discord, so servers are already gated—no need for Twitter's elaborate contributor vetting. Two paths to create a note:
- Write one yourself
- Punt to AI--it drafts a note, but *doesn't auto-post*

Every note, human or AI, goes through voting. Your community doesn't become the target of an AI slop firehose.

**Voting** early days it'll start simple—with helpful/unhelpful votes getting tallied[^vote-mechanism] after a minimum vote threshold is reached. A key difference from voting systems like Reddit's: we pick one winner per message, not create a comment section. The annotation should be *the* context, not a debate.

When enough voting history accumulates, it enables the real magic: bridging-based ranking (the Community Notes algorithm):
- Notes upvoted by people who usually *disagree* with each other rank higher
- Same vote count from an echo chamber loses to cross-divide consensus
- That's constructive moderation: communities self-regulating through annotations, not bans

**Content Monitoring** (opt-in)

- Matches posts against fact-check databases (currently a subset of Snopes)
- Matches auto-generate requests plus create draft notes in the regular note queue: human votes still required to actually publish the notes
- Approved notes feed back into the matching pool
- Fact-check DBs shared across servers; user-generated notes stay server-local
- Admins choose which channels to monitor, if any

[^vote-mechanism]: Using a bayesian average initially, and using more and more of the Community Notes algorithm as the scale increases.

## Current Status

![Version](https://img.shields.io/badge/version-0.0.1-blue) ![Stage](https://img.shields.io/badge/stage-alpha-orange)

Early but functional. [Add to your Discord](https://discord.com/oauth2/authorize?client_id=1423014656343019552) or self-host.

Contributor docs, issue templates, and the like are coming. Prioritizing core functionality first since many pieces need to work together for Open Notes to be useful.

## Modules and Directory Structure

- **opennotes-server**: FastAPI backend with PostgreSQL persistence, Redis caching, NATS messaging, OAuth/JWT authentication, and OpenTelemetry observability
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
│   └── .env.yaml.example    # Configuration template
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
│   └── .env.yaml.example    # Configuration template
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

### 2. Start the Server

```console
cd opennotes-server
cp .env.yaml.example .env.yaml
# Edit .env.yaml with your credentials and configuration
uv sync --extra scoring
uv run python -m src.main
```

Server runs at http://localhost:8000

### 3. Start the Discord Bot

```console
cd opennotes-discord
cp .env.yaml.example .env.yaml
# Edit .env.yaml with your Discord credentials
pnpm install
pnpm run build
pnpm start
```

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

Copy `.env.yaml.example` to `.env.yaml` and configure:

- Database connection (PostgreSQL)
- Redis connection
- NATS connection
- Discord OAuth credentials
- JWT secrets and encryption keys
- LLM provider API keys
- OpenTelemetry endpoints

### Bot Configuration

Copy `.env.yaml.example` to `.env.yaml` and configure:

- Discord bot token and client ID
- Server URL
- Environment and logging settings

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture and infrastructure components
- [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md) - OAuth/JWT authentication flow
- [docs/SCHEMA_AND_API_WORKFLOW.md](docs/SCHEMA_AND_API_WORKFLOW.md) - API schemas and workflows
- [communitynotes/README.md](communitynotes/README.md) - Community Notes Algorithm overview

## License

Open Notes is [open-core](https://en.wikipedia.org/wiki/Open-core_model), which means everything is open-source under MIT License by default, with the option to place some *future* functionality targeted towards larger scale users under other licenses. No bait-and-switch.

Legal: [LICENSE](LICENSE)
