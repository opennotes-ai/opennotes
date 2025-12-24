# Open Notes Test Utilities

Shared testing utilities and patterns for Open Notes services. This package provides consistent mock factories, test data generators, and Jest helpers for both TypeScript and Python services.

## Structure

```
packages/test-utils/
├── src/
│   ├── types.ts           # Shared type definitions
│   ├── mock-data.ts       # Legacy mock data functions
│   ├── jest-helpers.ts    # Jest mock helpers
│   ├── factories/         # Fishery test factories
│   │   ├── index.ts       # Factory exports
│   │   ├── note.ts        # Note factory
│   │   └── rating.ts      # Rating factory
│   └── index.ts           # Main exports
├── dist/                  # Compiled TypeScript
├── package.json
├── tsconfig.json
│
└── python/              # Python/pytest utilities
    ├── opennotes_test_utils/
    │   ├── __init__.py
    │   └── fixtures.py        # Test fixtures and data
    ├── pyproject.toml
    └── README.md
```

## Installation

### TypeScript (Discord Bot)

The package is automatically available as a workspace dependency:

```json
{
  "devDependencies": {
    "@opennotes/test-utils": "workspace:*"
  }
}
```

Install workspace dependencies:

```bash
cd opennotes
pnpm install
```

### Python (Server)

Install as an editable package:

```bash
cd opennotes-server
uv pip install -e ../opennotes-discord/packages/test-utils/python
```

## Usage

### TypeScript Testing Patterns

#### Mock Data Factories

Create consistent test data for Notes and Ratings:

```typescript
import {
  createMockNote,
  createMockRating,
  createMockFetchResponse,
} from '@opennotes/test-utils';

describe('Note Tests', () => {
  it('should process a note', () => {
    const note = createMockNote({
      content: 'Custom note content',
      authorId: 'user-123',
    });

    expect(note.id).toBe('note-123');
    expect(note.content).toBe('Custom note content');
  });

  it('should handle ratings', () => {
    const rating = createMockRating({
      helpful: false,
      userId: 'rater-456',
    });

    expect(rating.helpful).toBe(false);
  });
});
```

#### Jest Mock Helpers

Create consistent Jest mocks for common services:

```typescript
import {
  createMockLogger,
  createMockCache,
  createMockInteraction,
} from '@opennotes/test-utils';

describe('Service Tests', () => {
  it('should use mocked logger', () => {
    const logger = createMockLogger();

    logger.info('test message');

    expect(logger.info).toHaveBeenCalledWith('test message');
  });

  it('should use mocked cache', () => {
    const cache = createMockCache();

    cache.set('key', 'value');

    expect(cache.set).toHaveBeenCalledWith('key', 'value');
  });

  it('should mock Discord interaction', () => {
    const interaction = createMockInteraction({
      user: { id: 'custom-user-id', username: 'testuser' },
    });

    expect(interaction.user.id).toBe('custom-user-id');
    expect(interaction.deferReply).toBeDefined();
  });
});
```

#### HTTP Response Mocks

Create mock fetch responses for API testing:

```typescript
import { createMockFetchResponse } from '@opennotes/test-utils';

describe('API Client', () => {
  it('should handle successful response', async () => {
    const mockResponse = createMockFetchResponse({ status: 'ok' });

    global.fetch = jest.fn().mockResolvedValue(mockResponse);

    const result = await apiClient.healthCheck();
    expect(result.status).toBe('ok');
  });

  it('should handle error response', async () => {
    const mockResponse = createMockFetchResponse(
      { error: 'Not found' },
      { status: 404, ok: false }
    );

    global.fetch = jest.fn().mockResolvedValue(mockResponse);
    // Test error handling...
  });
});
```

#### Fishery Factories (Recommended)

Fishery factories provide type-safe, consistent test data with automatic sequencing. This is the recommended approach for creating test fixtures.

**Basic Usage:**

```typescript
import { noteFactory, ratingFactory } from '@opennotes/test-utils';

describe('Note Tests', () => {
  it('should build a single note', () => {
    const note = noteFactory.build();

    expect(note.id).toBe('note-1');
    expect(note.content).toBe('Test community note');
  });

  it('should build with overrides', () => {
    const note = noteFactory.build({
      content: 'Custom content',
      authorId: 'custom-author',
    });

    expect(note.content).toBe('Custom content');
    expect(note.authorId).toBe('custom-author');
  });

  it('should build multiple items', () => {
    const notes = noteFactory.buildList(3);

    expect(notes).toHaveLength(3);
    expect(notes[0].id).toBe('note-1');
    expect(notes[1].id).toBe('note-2');
    expect(notes[2].id).toBe('note-3');
  });
});
```

**Creating Custom Factories:**

```typescript
import { Factory } from '@opennotes/test-utils';
import type { NoteRequest } from '../src/types.js';

export const noteRequestFactory = Factory.define<NoteRequest>(({ sequence }) => ({
  id: `discord-123456789-${sequence}`,
  messageId: `msg-${sequence}`,
  channelId: `channel-${sequence}`,
  guildId: `guild-${sequence}`,
  authorId: `author-${sequence}`,
  content: 'Test message content',
  requestedBy: `user-${sequence}`,
  requestedAt: new Date().toISOString(),
  status: 'pending',
}));
```

**Factory Patterns:**

```typescript
// Extend factories with params for common variations
const adminUserFactory = userFactory.params({ admin: true });

// Use transient params for computed properties
type UserTransient = { generateEmail: boolean };

const userFactory = Factory.define<User, UserTransient>(
  ({ sequence, transientParams }) => {
    const name = `User ${sequence}`;
    return {
      id: `user-${sequence}`,
      name,
      email: transientParams.generateEmail
        ? `user-${sequence}@example.com`
        : null,
    };
  }
);

// Build with transient params
const user = userFactory.build({}, { transient: { generateEmail: true } });

// Use associations for related objects
const postFactory = Factory.define<Post>(({ associations }) => ({
  id: 'post-1',
  title: 'My Post',
  author: associations.author || userFactory.build(),
}));

// Override association when building
const customAuthor = userFactory.build({ name: 'Custom Author' });
const post = postFactory.build({}, { associations: { author: customAuthor } });
```

**When to use Fishery vs createMock functions:**

| Use Case | Recommended Approach |
|----------|---------------------|
| Simple one-off mocks | `createMockNote()` |
| Multiple related items | `noteFactory.buildList(5)` |
| Unique IDs needed | `noteFactory` (auto-sequencing) |
| Complex nested data | `Factory.define()` |
| Type-safe overrides | Fishery factories |

### Python Testing Patterns

#### Test Fixtures

Use shared test data in pytest fixtures:

```python
import pytest
from opennotes_test_utils import sample_participant_ids, test_user_data

@pytest.fixture
def participants():
    """Get standard participant IDs for scoring tests"""
    return sample_participant_ids()

@pytest.fixture
def test_user():
    """Get standard test user data"""
    return test_user_data()

def test_scoring(participants):
    """Test scoring with standard participant IDs"""
    assert participants["author1"] == "author_participant_1"
    assert participants["rater1"] == "rater_participant_1"

def test_authentication(test_user):
    """Test authentication with standard user data"""
    assert test_user["username"] == "testuser"
    assert test_user["email"] == "test@example.com"
```

#### Direct Usage

Use utilities directly without fixtures:

```python
from opennotes_test_utils import sample_participant_ids, test_user_data

def test_note_creation():
    """Test note creation with standard test data"""
    participants = sample_participant_ids()

    note = create_note(
        author_id=participants["author1"],
        content="Test note"
    )

    assert note.author_id == "author_participant_1"

def test_user_registration():
    """Test user registration"""
    user_data = test_user_data()

    response = client.post("/api/v1/auth/register", json=user_data)

    assert response.status_code == 201
```

## Available Utilities

### TypeScript

#### Types

```typescript
interface Note {
  id: string;
  messageId: string;
  authorId: string;
  content: string;
  createdAt: number;
  helpfulCount: number;
  notHelpfulCount: number;
}

interface Rating {
  noteId: string;
  userId: string;
  helpful: boolean;
  createdAt: number;
}

interface ServiceResult<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: any;
  };
}
```

#### Fishery Factories

- `Factory` - Re-exported from fishery for creating custom factories
- `noteFactory` - Factory for creating Note objects with auto-sequencing
- `ratingFactory` - Factory for creating Rating objects with auto-sequencing

#### Mock Data Functions (Legacy)

- `createMockNote(overrides?: Partial<Note>): Note`
- `createMockRating(overrides?: Partial<Rating>): Rating`
- `createMockFetchResponse(data: any, options?: { status?: number; ok?: boolean }): Response`

#### Jest Helpers

- `createMockLogger(): MockLogger` - Logger with error, warn, info, debug methods
- `createMockCache(): MockCache` - Cache with get, set, delete, start, stop, getMetrics
- `createMockInteraction(overrides?: any)` - Discord interaction mock

### Python

#### Fixtures

- `sample_participant_ids() -> dict[str, str]` - Standard participant IDs for scoring tests
  - Keys: `author1`, `author2`, `rater1`, `rater2`, `rater3`

- `test_user_data() -> dict[str, str]` - Standard user data for authentication tests
  - Keys: `username`, `email`, `password`, `full_name`

## Testing Best Practices

### 1. Use Consistent Test Data

Always use the shared factories and fixtures for consistent test data across services:

```typescript
// ✅ Good - Uses shared factory
const note = createMockNote({ content: 'Test' });

// ❌ Bad - Duplicates mock data structure
const note = {
  id: 'note-123',
  messageId: 'msg-456',
  // ... duplicating structure
};
```

### 2. Override Only What You Need

Use the `overrides` parameter to customize only the fields you care about:

```typescript
const note = createMockNote({
  content: 'Specific test content',
  // All other fields use defaults
});
```

### 3. Extend Service-Specific Mocks Locally

Keep service-specific mocks in their respective test directories:

```typescript
// tests/utils/service-mocks.ts
import { createMockLogger } from '@opennotes/test-utils';

export { createMockLogger }; // Re-export shared utilities

// Add service-specific mocks
export function createMockStatusService() {
  return {
    execute: jest.fn<(guilds?: number) => Promise<ServiceResult<StatusResult>>>(),
  };
}
```

### 4. Don't Abstract Service-Specific Types

Keep types that are specific to a service (like `ErrorCode` enums, `StatusResult` interfaces) local to that service. The shared package should only contain truly shared domain concepts.

## Migration Guide

### From Discord Bot Tests

Replace inline mock creation with shared utilities:

```typescript
// Before
const mockLogger = {
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  info: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

// After
import { createMockLogger } from '@opennotes/test-utils';
const mockLogger = createMockLogger();
```

### From Server Tests

Replace inline fixtures with shared utilities:

```python
# Before
@pytest.fixture
def sample_participant_ids():
    return {
        "author1": "author_participant_1",
        "author2": "author_participant_2",
        # ...
    }

# After
from opennotes_test_utils import sample_participant_ids

@pytest.fixture
def participants():
    return sample_participant_ids()
```

## Development

### Building TypeScript Package

```bash
cd packages/test-utils
pnpm install
pnpm run build
```

### Testing Changes

After making changes, test in both services:

```bash
# Test Discord bot
cd opennotes-discord
pnpm test

# Test server
cd opennotes-server
uv run pytest
```

## Contributing

When adding new test utilities:

1. **Consider if it's truly shared** - Only add utilities used by multiple services
2. **Keep it generic** - Avoid service-specific logic
3. **Document with examples** - Show how to use the utility
4. **Test in both services** - Ensure compatibility
5. **Update this README** - Document new utilities

## Version History

### 1.1.0 (2024-12-23)

- Added Fishery factory support for type-safe test fixtures
- New factories: `noteFactory`, `ratingFactory`
- Re-exported `Factory` from fishery for creating custom factories
- Added documentation for factory patterns (transient params, associations)

### 1.0.0 (2024-10-28)

- Initial release
- TypeScript utilities: mock data factories, Jest helpers
- Python utilities: test fixtures for participant IDs and user data
- Consolidated ~200 lines of duplicate test infrastructure
