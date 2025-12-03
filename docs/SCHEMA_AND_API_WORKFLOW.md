# Schema and API Workflow

This document describes OpenNotes' schema-driven development workflow, database schema patterns, and API validation system.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Database Schema Patterns](#database-schema-patterns)
4. [API Schema Workflow](#api-schema-workflow)
5. [Making Schema Changes](#making-schema-changes)
6. [API Endpoint Validation](#api-endpoint-validation)
7. [Commands Reference](#commands-reference)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)
10. [API Endpoint Documentation](#api-endpoint-documentation)
11. [Related Documentation](#related-documentation)

---

## 1. Overview

Open Notes uses a **schema-driven development workflow** that eliminates duplication and prevents schema drift between services. Data schemas are defined once in Python using Pydantic, automatically generating OpenAPI specifications and TypeScript types.

**Key Benefits:**
- **Zero Duplication**: Schema defined once, used everywhere
- **Zero Drift**: Impossible for schemas to drift between services
- **Type Safety**: Runtime validation (Python) + compile-time checking (TypeScript)
- **Breaking Changes Caught Early**: TypeScript compiler catches schema changes immediately

---

## 2. Architecture

### Schema Flow

```
┌──────────────────────────────────────────────────────────────┐
│ 1. Python Pydantic Models (Single Source of Truth)           │
│    opennotes-server/src/notes/schemas.py                     │
│    - NoteCreate, NoteResponse, RatingCreate, etc.            │
│    - Enums: NoteStatus, HelpfulnessLevel, etc.               │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     │ FastAPI auto-generates
                     ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. OpenAPI Specification (Auto-Generated)                    │
│    opennotes-server/openapi.json                             │
│    - Complete API documentation                              │
│    - All schemas, endpoints, request/response formats        │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     │ openapi-typescript generates
                     ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. TypeScript Types (Auto-Generated)                         │
│    opennotes-discord/src/lib/generated-types.ts              │
│    - Exact TypeScript equivalents of Pydantic models         │
│    - Full type safety for API client                         │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     │ Validates against
                     ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. API Client Validation                                     │
│    opennotes/scripts/validate-api-endpoints.py               │
│    - Ensures Discord bot endpoints match OpenAPI spec        │
│    - Catches mismatches before runtime                       │
└──────────────────────────────────────────────────────────────┘
```

### Generated Files (DO NOT EDIT)

- ❌ `opennotes-server/openapi.json` - Auto-generated from Pydantic
- ❌ `opennotes-discord/src/lib/generated-types.ts` - Auto-generated from OpenAPI

### Source Files (EDIT THESE)

- ✅ `opennotes-server/src/notes/schemas.py` - Single source of truth
- ✅ `opennotes-discord/src/lib/types.ts` - Bot-specific types (not API types)

---

## 3. Database Schema Patterns

This section establishes unified patterns for consistency across the Open Notes database schema. All new models and migrations should follow these patterns.

### 3.1 Primary Key Pattern (UUID v7)

Use UUID v7 for all new primary keys. UUID v7 provides time-ordering while maintaining global uniqueness.

```python
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

class MyModel(Base):
    __tablename__ = "my_models"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
        index=True
    )
```

**Key Points:**
- Always use `server_default=text("uuidv7()")` - let PostgreSQL 18+ generate the UUID
- Always add `index=True` on primary key for explicit indexing
- Never use Python-side UUID generation (`uuid4()`)
- Don't mix UUID versions (v4 and v7)

**When NOT to Use UUID v7:**
- **External Platform IDs** (Discord, Twitter, GitHub): Use `BigInteger` or `String`
- **Legacy Integer PKs**: Keep as-is; migrate opportunistically during refactoring
- **Composite Keys**: Use appropriate types for each component

### 3.2 External ID Pattern

External IDs from platforms (Discord, Twitter, GitHub) should use types that match the platform's ID format.

#### Discord Snowflake IDs

Discord IDs are 64-bit snowflakes. Store as `BigInteger` or `String(64)`:

```python
class MyModel(Base):
    __tablename__ = "my_models"

    # ✅ CORRECT: BigInteger for numeric Discord IDs
    discord_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True
    )

    # ✅ ALSO CORRECT: String(64) for Discord IDs stored as strings
    discord_id_str: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True
    )
```

#### GitHub IDs

GitHub IDs are 32-bit integers but use String(255) for future-proofing:

```python
class MyModel(Base):
    github_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )
```

#### Anti-Patterns

❌ **DON'T: Store external platform IDs as UUID**
```python
# WRONG: Discord IDs are not UUIDs
discord_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
```

❌ **DON'T: Use inappropriate types for external IDs**
```python
# WRONG: Integer type might overflow for future IDs
discord_id: Mapped[int] = mapped_column(Integer)

# WRONG: UUID provides false sense of internal ID
api_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
```

### 3.3 Community Server Reference Pattern

References to `CommunityServer` should use proper foreign key relationships.

#### Relational Pattern (Preferred)

Use a UUID foreign key when you need referential integrity:

```python
from sqlalchemy import ForeignKey

class MyModel(Base):
    __tablename__ = "my_models"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
        index=True
    )

    # ✅ CORRECT: Proper foreign key relationship
    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id"),
        nullable=False,
        index=True
    )
```

#### Denormalized with Platform ID

If you need to store platform-specific IDs (Discord guild ID) for performance, denormalize but keep the FK:

```python
class MyModel(Base):
    __tablename__ = "my_models"

    # ✅ CORRECT: FK maintains referential integrity
    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id"),
        nullable=False,
        index=True
    )

    # ✅ OPTIONAL: Denormalized platform ID for fast lookups
    # Only add if performance analysis justifies it
    platform_id: Mapped[str] = mapped_column(
        String(64),
        nullable=True,
        index=True
    )
```

**When to Use Each Pattern:**

| Pattern | Use When |
|---------|----------|
| Relational FK | Need referential integrity, frequent queries by CommunityServer |
| Denormalized + FK | Need fast lookups by platform ID AND referential integrity |
| Denormalized only | ❌ Only in legacy code - don't add new models this way |

### 3.4 Timestamp Pattern

All timestamps should be timezone-aware and stored in UTC.

```python
from datetime import datetime

class MyModel(Base):
    __tablename__ = "my_models"

    # ✅ CORRECT: Timezone-aware, UTC by default
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    # For columns that track updates
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Optional: Track when something was completed
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
```

**Key Points:**
- Always use `DateTime(timezone=True)`
- Always use `server_default=func.now()` for database-level defaults
- Store all times in UTC (PostgreSQL handles this automatically)
- Index frequently-queried timestamp columns

**Anti-Patterns:**

❌ **DON'T: Use timezone=False**
```python
# WRONG: Timezone-naive timestamps cause serialization issues
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
```

❌ **DON'T: Use Python-side datetime defaults**
```python
# WRONG: Inconsistent across app instances
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(UTC)
)
```

### 3.5 String Field Length Pattern

Use consistent string field lengths across the schema.

| Type | Standard Length | Rationale |
|------|-----------------|-----------|
| Discord ID | String(64) | Snowflake ID margin of safety |
| Twitter ID | BigInteger | 64-bit snowflakes |
| GitHub ID | String(255) | Future-proofing |
| API Key/Token | String(255) | Tokens are variable length |
| URL | String(2048) | HTTP standard URL length limit |
| Username | String(255) | Supports Unicode up to ~256 chars |
| Email | String(255) | RFC 5321 limit is 254 chars |
| Description/Notes | Text | Unlimited, indexed if frequently searched |
| Status/Type | String(50) | Enum values are short |
| Channel ID | String(64) | Discord Snowflake |

#### Migration Pattern: Increasing String Length

When a String field needs to be longer (always safe operation):

```python
# In Alembic migration
def upgrade() -> None:
    op.alter_column(
        'my_table',
        'my_string_field',
        type_=sa.String(255),  # New length
        existing_type=sa.String(50)
    )

def downgrade() -> None:
    op.alter_column(
        'my_table',
        'my_string_field',
        type_=sa.String(50),  # Original length
        existing_type=sa.String(255)
    )
```

### 3.6 Boolean Field Pattern

Boolean fields should have clear semantics and appropriate defaults.

```python
class MyModel(Base):
    # ✅ CORRECT: Clear affirmative naming, nullable=False, explicit default
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true"
    )

    # For tracking successful operations
    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false"
    )
```

**Naming Conventions:**
- Use `is_*` prefix for properties: `is_active`, `is_deleted`, `is_public`
- Use `*_enabled` for features: `notifications_enabled`, `auto_publish_enabled`
- Use `success` for operation outcomes (not `is_successful`)

**Anti-Patterns:**

❌ **DON'T: Use negative field names**
```python
# WRONG: Confusing logic (if not not_deleted)
is_not_deleted: Mapped[bool] = mapped_column(Boolean)
```

❌ **DON'T: Make boolean nullable**
```python
# WRONG: NULL has unclear meaning
is_active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
```

### 3.7 Foreign Key Pattern

Foreign keys should always include cascade behavior and be properly indexed.

```python
from sqlalchemy import ForeignKey, UniqueConstraint

class Child(Base):
    __tablename__ = "children"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()")
    )

    # ✅ CORRECT: FK with explicit cascade behavior
    parent_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("parents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Relationship for ORM convenience
    parent: Mapped["Parent"] = relationship(
        "Parent",
        back_populates="children"
    )
```

**Cascade Behavior:**
- `ondelete="CASCADE"`: Use when child records are meaningless without parent (OrderItems → Order)
- `ondelete="RESTRICT"`: Use when deleting parent would be invalid (CommunityMember → CommunityServer)
- `ondelete="SET NULL"`: Use only if FK is nullable (rare)

**Anti-Patterns:**

❌ **DON'T: Missing cascade behavior**
```python
# WRONG: Orphaned records when parent deleted
parent_id: Mapped[UUID] = mapped_column(
    PGUUID(as_uuid=True),
    ForeignKey("parents.id")  # No ondelete specified
)
```

❌ **DON'T: Forget to index FK**
```python
# WRONG: No index, slow joins and lookups
parent_id: Mapped[UUID] = mapped_column(
    PGUUID(as_uuid=True),
    ForeignKey("parents.id")  # No index=True
)
```

### 3.8 Unique Constraint Pattern

Unique constraints should be explicit and indexed.

```python
class MyModel(Base):
    __tablename__ = "my_models"

    # ✅ CORRECT: Unique index on column
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )

    # ✅ CORRECT: Explicit unique constraint for composite uniqueness
    __table_args__ = (
        UniqueConstraint("username", "community_server_id", name="uq_username_per_server"),
    )
```

**Single Column Uniqueness:** Use `unique=True` on the column definition.

**Composite Uniqueness:** Use `__table_args__`:
```python
__table_args__ = (
    UniqueConstraint("username", "community_server_id", name="uq_username_per_server"),
    UniqueConstraint("api_key", name="uq_api_key"),
)
```

### 3.9 Migration Testing Checklist

When creating migrations, verify:

- [ ] Migration compiles without syntax errors
- [ ] Upgrade path successfully converts schema
- [ ] Downgrade path reverts schema exactly
- [ ] No data loss during upgrade/downgrade
- [ ] All foreign keys remain valid
- [ ] Indexes are properly created/dropped
- [ ] Default values apply correctly
- [ ] Constraints are enforced
- [ ] Schema drift check passes (`alembic check`)

---

## 4. API Schema Workflow

### 4.1 Single Source of Truth: Pydantic Models

All data schemas are defined **once** in Python using Pydantic:

**Location:** `opennotes-server/src/notes/schemas.py`

```python
class NoteCreate(BaseModel):
    note_id: int = Field(..., description="External note ID")
    author_participant_id: str = Field(..., description="Author's participant ID")
    tweet_id: int = Field(..., description="Tweet/Post ID being annotated")
    summary: str = Field(..., description="Note summary text")
    classification: NoteClassification = Field(..., description="Note classification")
```

**Why Pydantic?**
- Runtime validation at API boundaries
- Automatic OpenAPI schema generation
- Clear, self-documenting code
- Field-level validation rules

### 4.2 OpenAPI Generation

FastAPI automatically generates OpenAPI specifications from Pydantic models:

**Generated file:** `opennotes-server/openapi.json`

**When it's generated:**
- Automatically on server startup
- Via `scripts/generate-openapi.py` script
- During deployment via `mise run deploy:server`

**What it contains:**
- All API endpoints with request/response types
- Complete schema definitions for all Pydantic models
- Enum definitions, validation rules, field descriptions
- API documentation for tools like Swagger UI

### 4.3 TypeScript Type Generation

TypeScript types are auto-generated from the OpenAPI spec:

**Command:** `pnpm types:generate` (in `opennotes-discord/`)

**Generated file:** `opennotes-discord/src/lib/generated-types.ts`

**How it works:**
```bash
# Uses openapi-typescript package
openapi-typescript ../opennotes-server/openapi.json -o src/lib/generated-types.ts
```

**When it runs:**
- Automatically before every build (`prebuild` script)
- Manually via `pnpm types:generate`
- During deployment

**What you get:**
```typescript
// Auto-generated from Pydantic models
export type NoteResponse = {
  id: number;
  note_id: number;
  author_participant_id: string;
  tweet_id: number;
  summary: string;
  classification: "NOT_MISLEADING" | "MISINFORMED_OR_POTENTIALLY_MISLEADING";
  status: "NEEDS_MORE_RATINGS" | "CURRENTLY_RATED_HELPFUL" | "CURRENTLY_RATED_NOT_HELPFUL";
  created_at: string;
  updated_at: string | null;
  ratings: RatingResponse[];
  ratings_count: number;
};
```

---

## 5. Making Schema Changes

### 5.1 Adding a New Field to an Existing Schema

**Step 1: Update the Pydantic Model** (Python)

```python
# opennotes-server/src/notes/schemas.py
class NoteCreate(BaseModel):
    # ... existing fields ...
    new_field: str | None = Field(None, description="New field description")
```

**Step 2: Regenerate TypeScript Types** (automatic during build)

```bash
cd opennotes-discord
pnpm run build  # Automatically runs types:generate
```

**Step 3: TypeScript Types Now Include New Field**

```typescript
// src/lib/generated-types.ts (auto-updated)
export type NoteCreate = {
  // ... existing fields ...
  new_field?: string;  // ✅ Automatically added!
};
```

**Step 4: Use the New Field**

```typescript
// Your code automatically has type safety
import type { components } from './lib/generated-types.js';
type NoteCreate = components['schemas']['NoteCreate'];

const note: NoteCreate = {
  // ... existing fields ...
  new_field: 'value',  // ✅ TypeScript knows about this!
};
```

### 5.2 Adding a New Schema

**Step 1: Define in Pydantic**

```python
# opennotes-server/src/notes/schemas.py
class NewFeatureCreate(BaseModel):
    field1: str
    field2: int

class NewFeatureResponse(NewFeatureCreate):
    id: int
    created_at: datetime
```

**Step 2: Use in FastAPI Endpoint**

```python
# opennotes-server/src/api/routes/features.py
@router.post("/features/", response_model=NewFeatureResponse)
async def create_feature(feature: NewFeatureCreate):
    # ... implementation ...
```

**Step 3: Regenerate Types**

```bash
cd opennotes-server
uv run python scripts/generate-openapi.py --output openapi.json

cd ../opennotes-discord
pnpm types:generate
```

**Step 4: Types Available in TypeScript**

```typescript
import type { components } from './lib/generated-types.js';

type NewFeatureCreate = components['schemas']['NewFeatureCreate'];
type NewFeatureResponse = components['schemas']['NewFeatureResponse'];
```

### 5.3 Changing an Enum

**Step 1: Update Enum in Python**

```python
# opennotes-server/src/notes/schemas.py
class HelpfulnessLevel(str, PyEnum):
    HELPFUL = "HELPFUL"
    SOMEWHAT_HELPFUL = "SOMEWHAT_HELPFUL"
    NOT_HELPFUL = "NOT_HELPFUL"
    VERY_HELPFUL = "VERY_HELPFUL"  # ✅ New value
```

**Step 2: Regenerate Types**

TypeScript types automatically update to include new enum value:

```typescript
export type HelpfulnessLevel =
  | "HELPFUL"
  | "SOMEWHAT_HELPFUL"
  | "NOT_HELPFUL"
  | "VERY_HELPFUL";  // ✅ Automatically added!
```

**Step 3: TypeScript Catches Missing Cases**

```typescript
function handleRating(level: HelpfulnessLevel) {
  switch (level) {
    case "HELPFUL": return "👍";
    case "SOMEWHAT_HELPFUL": return "👌";
    case "NOT_HELPFUL": return "👎";
    // ❌ TypeScript error: "VERY_HELPFUL" not handled!
  }
}
```

---

## 6. API Endpoint Validation

The validation system ensures the Discord bot's API client stays in sync with the server's actual endpoints.

### 6.1 Why Validation Matters

Previously, endpoint mismatches between the Discord bot and server could cause silent failures:
- Discord bot calling `/api/v1/note-requests` instead of `/api/v1/requests`
- Resulting in 404 errors with empty error objects
- Issues not caught until runtime

With automated validation, these issues are caught during development and in PR reviews.

### 6.2 Validation Scripts

#### Generate OpenAPI Specification

**Location:** `opennotes/opennotes-server/scripts/generate-openapi.py`

**Purpose:** Exports the FastAPI application's OpenAPI schema to a JSON file.

**Usage:**
```bash
# From opennotes-server directory
uv run python scripts/generate-openapi.py --output openapi.json

# Or using mise task
mise run api:generate-spec
```

**Output:** Creates `openapi.json` containing:
- All API endpoints (paths and HTTP methods)
- Request/response schemas
- Authentication requirements
- API metadata (title, version, description)

#### Validate API Endpoints

**Location:** `opennotes/scripts/validate-api-endpoints.py`

**Purpose:** Compares Discord bot API client endpoints with the OpenAPI specification.

**Usage:**
```bash
# From repository root
python3 opennotes/scripts/validate-api-endpoints.py

# Or using mise task
mise run api:validate-endpoints

# With custom paths
python3 opennotes/scripts/validate-api-endpoints.py \
  --openapi opennotes/opennotes-server/openapi.json \
  --api-client opennotes/opennotes-discord/src/lib/api-client.ts
```

**What it validates:**
- All `fetchWithRetry()` calls in the Discord bot's API client
- Endpoint paths match exactly (or account for path parameters)
- HTTP methods (GET, POST, PUT, PATCH, DELETE) match
- Reports missing endpoints or method mismatches

**Exit codes:**
- `0` - All endpoints validated successfully
- `1` - Validation failed (endpoint mismatches found)
- `2` - Script execution error

### 6.3 Local Development Workflow

#### Pre-commit Validation

Run validation before committing changes to either the server or Discord bot:

```bash
# Quick validation
mise run api:validate

# Full CI checks (includes linting, tests, and API validation)
mise run ci:check
```

#### When to Re-validate

You should run validation when:

1. **Adding new API endpoints** to opennotes-server
2. **Modifying API client calls** in opennotes-discord
3. **Changing endpoint paths** or HTTP methods
4. **Before creating a pull request**

#### Updating the OpenAPI Spec

The OpenAPI spec is generated from the FastAPI application, so any changes to routers, endpoints, or schemas are automatically reflected:

```bash
# Regenerate after modifying server endpoints
mise run api:generate-spec
```

The spec is **not committed to git** (it's in `.gitignore`) because it's generated from source code. CI/CD regenerates it fresh for each validation.

### 6.4 CI/CD Integration

#### GitHub Actions

**Workflow:** `.github/workflows/ci.yml`

**Job:** `validate-api-endpoints`

**Triggers:**
- Pull requests to `main` or `develop`
- Pushes to `main` or `develop`
- Changes to:
  - `opennotes/opennotes-server/**`
  - `opennotes/opennotes-discord/**`
  - `.github/workflows/**`

**Steps:**
1. Checkout code with submodules
2. Set up Python 3.11
3. Install `uv` package manager
4. Install opennotes-server dependencies
5. Generate OpenAPI specification
6. Run validation script
7. Upload OpenAPI spec as artifact (for debugging)

**Status:** Validation must pass for CI to succeed.

### 6.5 Example Output

#### Successful Validation

```
Loading OpenAPI specification...
Parsing API client...
Validating endpoints...

======================================================================
API ENDPOINT VALIDATION REPORT
======================================================================

OpenAPI Spec: opennotes/opennotes-server/openapi.json
API Client: opennotes/opennotes-discord/src/lib/api-client.ts

Total OpenAPI endpoints: 44
Total client endpoint calls: 5

----------------------------------------------------------------------
CLIENT ENDPOINTS VALIDATION
----------------------------------------------------------------------
✓ POST   /api/v1/scoring/score                    [scoreNotes]
✓ POST   /api/v1/notes                            [createNote]
✓ POST   /api/v2/ratings                          [rateNote]
✓ GET    /health                                  [healthCheck]
✓ POST   /api/v1/requests                         [requestNote]

======================================================================
✓ ALL ENDPOINTS VALIDATED SUCCESSFULLY
======================================================================
```

#### Failed Validation

```
----------------------------------------------------------------------
CLIENT ENDPOINTS VALIDATION
----------------------------------------------------------------------
✓ POST   /api/v1/scoring/score                    [scoreNotes]
✗ POST   /api/v1/note-requests                    [requestNote]
  → NOT FOUND in OpenAPI spec

======================================================================
✗ VALIDATION FAILED: 1 ENDPOINT(S) NOT FOUND
======================================================================

Errors:
  - POST /api/v1/note-requests (function: requestNote)
```

---

## 7. Commands Reference

### Server Commands (Python)

| Command | Description |
|---------|-------------|
| `mise run api:generate-spec` | Generate OpenAPI specification |
| `uv run python scripts/generate-openapi.py --output openapi.json` | Manual OpenAPI generation |

### Discord Bot Commands (TypeScript)

| Command | Description |
|---------|-------------|
| `pnpm types:generate` | Generate TypeScript types from OpenAPI |
| `pnpm run build` | Build (auto-generates types first via prebuild) |
| `pnpm run type-check` | Type check without building |

### Validation Commands

| Command | Description |
|---------|-------------|
| `mise run api:validate` | Validate API endpoints |
| `mise run api:validate-endpoints` | Same as above |
| `mise run ci:check` | Full CI checks (includes API validation) |

### Full Schema Change Workflow

```bash
# 1. Update Pydantic models
vim opennotes-server/src/notes/schemas.py

# 2. Generate OpenAPI spec
cd opennotes-server && uv run python scripts/generate-openapi.py --output openapi.json

# 3. Generate TypeScript types
cd ../opennotes-discord && pnpm types:generate

# 4. Verify types
pnpm run type-check

# 5. Run tests
pnpm test
```

---

## 8. Best Practices

### For Server Developers

**DO:**
- Use descriptive endpoint names in FastAPI decorators
- Add docstrings to endpoint functions (appears in OpenAPI docs)
- Define request/response models with Pydantic for better OpenAPI schemas
- Run validation after adding or modifying endpoints
- Coordinate with Discord bot team when making breaking changes

**DON'T:**
- Commit `openapi.json` (it's generated)
- Make breaking API changes without communicating to the team

### For Discord Bot Developers

**DO:**
- Check OpenAPI spec before implementing API client methods
- Use exact endpoint paths from the spec
- Match HTTP methods (GET, POST, PUT, PATCH, DELETE)
- Run validation before committing changes
- Update API client when server endpoints change
- Use generated types in Discord bot code
- Let prebuild script handle generation automatically

**DON'T:**
- Edit `generated-types.ts` manually
- Create duplicate TypeScript types for API schemas
- Skip type generation after schema changes
- Commit changes without regenerating types
- Ignore TypeScript type errors after schema changes

### For All Developers

**DO:**
- Always update Pydantic models first (single source of truth)
- Run type generation after schema changes
- Add validation rules to Pydantic models
- Write descriptive field docstrings
- Run `mise run ci:check` before creating PRs
- Fix validation errors before requesting review
- Document breaking changes in PR descriptions

---

## 9. Troubleshooting

### Types Out of Sync

**Symptom:** TypeScript types don't match API responses

**Solution:**
```bash
cd opennotes-server && uv run python scripts/generate-openapi.py --output openapi.json
cd ../opennotes-discord && pnpm types:generate
```

### Build Fails After Schema Change

**Symptom:** `pnpm run build` fails with type errors

**Cause:** Breaking change in Pydantic schema

**Solution:**
1. Review OpenAPI spec changes
2. Update Discord bot code to handle new schema
3. Update tests
4. Rebuild

### Generated Types Missing

**Symptom:** `generated-types.ts` doesn't exist

**Solution:**
```bash
cd opennotes-discord
pnpm types:generate
```

### Wrong Types Generated

**Symptom:** Generated types don't match expectations

**Solution:**
1. Check `openapi.json` was generated correctly
2. Verify Pydantic models have proper type hints
3. Regenerate OpenAPI spec
4. Regenerate TypeScript types

### Validation Fails with "OpenAPI spec not found"

**Solution:** Generate the spec first:
```bash
mise run api:generate-spec
```

### Validation Fails with "API client file not found"

**Solution:** Ensure you're running from the repository root:
```bash
cd /path/to/multiverse
python3 opennotes/scripts/validate-api-endpoints.py
```

### Endpoint Mismatch Found

**Diagnosis:**
1. Check the validation output to see which endpoint failed
2. Compare the bot's API client method with the server's router
3. Look for typos, incorrect HTTP methods, or path parameter mismatches

**Fix:**
- **If server is correct:** Update the Discord bot's API client
- **If bot is correct:** Update the server endpoint
- **If both are wrong:** Fix both, ensuring they match

### Path Parameter Warnings

The validator may show warnings like:
```
⚠ GET    /api/v1/notes/123456                     [getNotes]
  → Matches OpenAPI path: /api/v1/notes/{note_id}
```

This is **informational**, not an error. The validator detected that the bot is using a literal value where the server expects a path parameter.

---

## 10. API Endpoint Documentation

This section documents API endpoints used by Discord bot commands.

### OpenAPI Specification Details

#### FastAPI Configuration

The server's OpenAPI configuration is in `opennotes/opennotes-server/src/main.py`:

```python
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.DEBUG else None,
    docs_url=f"{settings.API_V1_PREFIX}/docs" if settings.DEBUG else None,
    redoc_url=f"{settings.API_V1_PREFIX}/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)
```

#### Accessing OpenAPI Docs

When running the server in debug mode:

- **Swagger UI:** http://localhost:8000/api/v1/docs
- **ReDoc:** http://localhost:8000/api/v1/redoc
- **OpenAPI JSON:** http://localhost:8000/api/v1/openapi.json

#### OpenAPI Spec Structure

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Open Notes Scoring API",
    "version": "1.0.0"
  },
  "paths": {
    "/api/v1/notes": {
      "post": {
        "summary": "Create a new community note",
        "operationId": "create_note_api_v1_notes_post",
        "requestBody": { ... },
        "responses": { ... }
      }
    }
  },
  "components": {
    "schemas": { ... },
    "securitySchemes": { ... }
  }
}
```

### Discord Bot Commands

The Discord bot provides the following commands:

#### Slash Commands

| Command | Subcommand | Description |
|---------|------------|-------------|
| `/note` | `write` | Write a note for a message |
| `/note` | `request` | Request a note for a message |
| `/note` | `view` | View notes for a message |
| `/note` | `score` | Score a specific note |
| `/note` | `rate` | Rate a note as helpful or not |
| `/note` | `force-publish` | Force publish a note |
| `/list` | `notes` | List notes with filters |
| `/list` | `requests` | List note requests |
| `/list` | `top-notes` | List top-rated notes |
| `/config` | `admin` | Manage server admins (set/remove/list) |
| `/config` | `llm` | Configure LLM settings |
| `/config` | `opennotes` | Configure Open Notes settings (view/set/reset) |
| `/config` | `content-monitor` | Configure content monitoring |
| `/config` | `note-publisher` | Configure note publishing |
| `/about-opennotes` | - | About Open Notes |
| `/status-bot` | - | Bot status |
| `/setup-monitoring` | - | Set up channel monitoring |

#### Context Menu Commands

| Command | Description |
|---------|-------------|
| **Request Note** | Right-click on a message to request a note for it |

---

## 11. Related Documentation

### Internal References

- **Pydantic Models:** `opennotes-server/src/notes/schemas.py`
- **Generated Types:** `opennotes-discord/src/lib/generated-types.ts`
- **API Client:** `opennotes-discord/src/lib/api-client.ts`
- **Validation Script:** `opennotes/scripts/validate-api-endpoints.py`
- **OpenAPI Generator:** `opennotes-server/scripts/generate-openapi.py`

### External References

- [FastAPI OpenAPI Documentation](https://fastapi.tiangolo.com/tutorial/metadata/)
- [OpenAPI 3.1 Specification](https://spec.openapis.org/oas/v3.1.0)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [openapi-typescript Package](https://github.com/drwpow/openapi-typescript)
- [PostgreSQL Data Types](https://www.postgresql.org/docs/current/datatype.html)
- [RFC 5321 - Email Address Format](https://tools.ietf.org/html/rfc5321)
- [Discord Snowflake Format](https://discord.com/developers/docs/reference#snowflakes)

### ADRs

- ADR-001: UUID v7 Standardization Decision
- ADR-002: Infrastructure Schema Migration Strategy

---

**Last Updated:** 2025-12-02
**Status:** Active
**Version:** 1.0
