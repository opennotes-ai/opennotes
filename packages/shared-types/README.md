# @opennotes/shared-types

Shared TypeScript types and error definitions for Open Notes services.

## Overview

This package provides common error handling utilities and type definitions used across Open Notes services (Discord bot, API server). It serves as the single source of truth for error handling patterns, ensuring consistency across the entire system.

## Installation

This package is intended for use within the Open Notes monorepo as a workspace dependency:

```json
{
  "dependencies": {
    "@opennotes/shared-types": "workspace:*"
  }
}
```

## Error Handling

### Error Classes

#### `ErrorWithContext`

Base error class that adds contextual information for debugging.

```typescript
import { ErrorWithContext } from '@opennotes/shared-types';

throw new ErrorWithContext(
  'Failed to process request',
  { userId: '123', action: 'create_note' },
  'err_abc123' // optional, auto-generated if not provided
);
```

**Properties:**
- `message: string` - Error message
- `context: Record<string, any>` - Contextual information for debugging
- `errorId: string` - Unique error identifier (format: `err_<12-char-nanoid>`)
- `stack: string` - Stack trace

#### `ApiError`

Specialized error for API-related failures with endpoint and status code information.

```typescript
import { ApiError } from '@opennotes/shared-types';

throw new ApiError(
  'API request failed',
  '/api/v1/notes',
  404,
  { detail: 'Note not found' },
  { note_id: 123 },
  { userId: '456' }
);
```

**Properties:**
- All properties from `ErrorWithContext`
- `endpoint: string` - API endpoint that failed
- `statusCode: number` - HTTP status code
- `responseBody?: any` - Response body from failed request
- `requestBody?: any` - Request body that caused the error
- `detail?: string` - Extracted error detail from response

**Methods:**
- `getUserMessage(): string` - Returns user-friendly error message based on status code or response detail

**Status Code Messages:**
- `400` - "Invalid request. Please check your input."
- `401` - "Authentication required."
- `403` - "You do not have permission to perform this action."
- `404` - "Resource not found."
- `409` - "This action conflicts with existing data."
- `429` - "Too many requests. Please try again later."
- `500` - "Server error occurred. Please try again later."
- `503` - "Service temporarily unavailable. Please try again later."
- Default - "An error occurred. Please try again."

### Utility Functions

#### `generateErrorId()`

Generates a unique error ID with the format `err_<random>`.

```typescript
import { generateErrorId } from '@opennotes/shared-types';

const errorId = generateErrorId();
// => "err_V1StGXR8_Z5j"
```

#### `formatErrorForUser(errorId, message?)`

Formats an error message for user display with error ID and support instructions.

```typescript
import { formatErrorForUser } from '@opennotes/shared-types';

const userMessage = formatErrorForUser(
  'err_abc123',
  'Failed to create note'
);
// => "Failed to create note\n\nError ID: `err_abc123`\n\nIf this issue persists, please contact support with the Error ID."
```

#### `extractErrorDetails(error)`

Extracts detailed information from an unknown error.

```typescript
import { extractErrorDetails } from '@opennotes/shared-types';

try {
  // ... code that may throw
} catch (error) {
  const details = extractErrorDetails(error);
  // => { message: string, stack?: string, type: string }
}
```

### Type Definitions

#### `CommandErrorContext`

Context information for command errors (Discord bot specific).

```typescript
import type { CommandErrorContext } from '@opennotes/shared-types';

const context: CommandErrorContext = {
  command: 'write-note',
  userId: '123456789',
  guildId: '987654321',
  channelId: '555555555',
  messageId: '777777777',
  input: { content: 'Note content...' }
};
```

## Usage Examples

### Basic Error Handling

```typescript
import { ErrorWithContext, extractErrorDetails } from '@opennotes/shared-types';

async function processData(data: any) {
  try {
    // Process data
  } catch (error) {
    const errorDetails = extractErrorDetails(error);
    throw new ErrorWithContext(
      'Failed to process data',
      { ...errorDetails, originalData: data }
    );
  }
}
```

### API Error Handling

```typescript
import { ApiError, formatErrorForUser } from '@opennotes/shared-types';

async function fetchNote(noteId: number) {
  try {
    const response = await fetch(`/api/v1/notes/${noteId}`);
    if (!response.ok) {
      const body = await response.json();
      throw new ApiError(
        'Failed to fetch note',
        `/api/v1/notes/${noteId}`,
        response.status,
        body,
        { note_id: noteId }
      );
    }
    return response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      const userMessage = formatErrorForUser(
        error.errorId,
        error.getUserMessage()
      );
      console.error(userMessage);
    }
    throw error;
  }
}
```

### Discord Command Error Handling

```typescript
import {
  ErrorWithContext,
  formatErrorForUser,
  type CommandErrorContext
} from '@opennotes/shared-types';
import { CommandInteraction } from 'discord.js';

async function handleCommand(interaction: CommandInteraction) {
  const context: CommandErrorContext = {
    command: interaction.commandName,
    userId: interaction.user.id,
    guildId: interaction.guildId || undefined,
    channelId: interaction.channelId
  };

  try {
    // Command logic
  } catch (error) {
    const err = error instanceof ErrorWithContext
      ? error
      : new ErrorWithContext('Command failed', context);

    const userMessage = formatErrorForUser(err.errorId);
    await interaction.reply({ content: userMessage, ephemeral: true });
  }
}
```

## Benefits

- **Single Source of Truth**: Error handling patterns defined once, used everywhere
- **Consistency**: All services use the same error classes and utilities
- **Traceability**: Every error has a unique ID for debugging and support
- **User-Friendly**: Automatic generation of user-facing error messages
- **Type Safety**: Full TypeScript support with type definitions
- **Context-Rich**: Errors include contextual information for debugging

## Development

### Building

```bash
pnpm build
```

### Type Checking

```bash
pnpm type-check
```

### Cleaning Build Artifacts

```bash
pnpm clean
```

## Architecture

This package follows these design principles:

1. **Zero Dependencies** (except nanoid for ID generation)
2. **Pure TypeScript** - No runtime dependencies on Node.js or browser APIs
3. **ESM First** - Modern ES modules with proper exports
4. **Type-Safe** - Strict TypeScript mode with full type coverage
5. **Composable** - Small, focused utilities that work together

## Future Extensions

Potential future additions to this package:

- Python type stubs generation for opennotes-server
- Additional error types (ValidationError, AuthError, RateLimitError)
- Error serialization utilities for logging and monitoring
- Error recovery strategies and retry logic
- Structured logging formats

## License

MIT
