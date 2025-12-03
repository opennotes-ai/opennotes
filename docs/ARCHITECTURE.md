# Architecture

```
Discord User
    ↓ Slash Commands / Context Menu
opennotes-discord (TypeScript/Discord.js)
    ↓ HTTP API
opennotes-server (Python/FastAPI)
    ↓ PostgreSQL / Redis / NATS
    ↓ Scoring Algorithm
communitynotes (Python/PyTorch)
    ↓ LLM Integration
OpenAI / Anthropic / OpenRouter
```

## Infrastructure Components

- **PostgreSQL**: Persistent storage with Alembic migrations for notes, users, ratings, and community configuration
- **Redis**: High-performance caching layer for rate limiting, session management, and query optimization
- **NATS JetStream**: Event streaming for real-time updates and background worker coordination
- **OpenTelemetry**: Distributed tracing with Prometheus metrics, Grafana dashboards, Loki logging, and Tempo tracing
- **Background Workers**: Asynchronous task processing for scoring, notifications, and data synchronization
- **OAuth/JWT**: Discord OAuth flow with JWT-based session management and refresh tokens
