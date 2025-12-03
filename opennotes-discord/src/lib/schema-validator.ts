import Ajv, { ValidateFunction, ErrorObject } from 'ajv';
import addFormats from 'ajv-formats';
import { createRequire } from 'module';
import { logger } from '../logger.js';

const require = createRequire(import.meta.url);
const rawSchemas = require('./openapi-schemas.json') as Record<string, unknown>;
const schemas = transformSchemas(rawSchemas);

const ajv = new Ajv({
  allErrors: true,
  strict: true,
  coerceTypes: false,
  removeAdditional: true,
  useDefaults: false,
  discriminator: true,
});

addFormats(ajv);

function transformSchemas(schemas: Record<string, unknown>): Record<string, unknown> {
  const transformed = JSON.parse(JSON.stringify(schemas)) as Record<string, unknown>;

  const addDateTimeFormat = (schema: unknown): void => {
    if (typeof schema !== 'object' || schema === null) {
      return;
    }

    const obj = schema as Record<string, unknown>;

    if (obj.properties && typeof obj.properties === 'object') {
      const props = obj.properties as Record<string, Record<string, unknown>>;

      const dateFields = ['created_at', 'updated_at', 'requested_at', 'force_published_at'];
      for (const field of dateFields) {
        if (props[field]) {
          const fieldSchema = props[field];
          if (Array.isArray(fieldSchema.anyOf)) {
            fieldSchema.anyOf = (fieldSchema.anyOf as Record<string, unknown>[]).map(option => {
              if (option.type === 'string' || (!option.type && !('$ref' in option))) {
                return { ...option, type: 'string', format: 'date-time' };
              }
              return option;
            });
          } else if (fieldSchema.type === 'string' || !fieldSchema.type) {
            fieldSchema.type = 'string';
            fieldSchema.format = 'date-time';
          }
        }
      }
    }
  };

  Object.values(transformed).forEach(schema => addDateTimeFormat(schema));

  return transformed;
}

const ENABLE_VALIDATION = process.env.ENABLE_SCHEMA_VALIDATION === 'true' || process.env.NODE_ENV !== 'production';

export class SchemaValidationError extends Error {
  constructor(
    message: string,
    public errors: ErrorObject[] | null | undefined,
    public data: unknown,
    public schemaName: string
  ) {
    super(message);
    this.name = 'SchemaValidationError';
  }
}

const compiledValidators = new Map<string, ValidateFunction>();

function getValidator(schemaName: string): ValidateFunction {
  if (compiledValidators.has(schemaName)) {
    return compiledValidators.get(schemaName)!;
  }

  const schema = schemas[schemaName];
  if (!schema) {
    throw new Error(`Schema "${schemaName}" not found in openapi-schemas.json`);
  }

  const resolvedSchema = resolveRefs(schema as Record<string, unknown>, schemas);
  const validator = ajv.compile(resolvedSchema);
  compiledValidators.set(schemaName, validator);

  return validator;
}

function resolveRefs(
  schema: Record<string, unknown>,
  allSchemas: Record<string, unknown>,
  depth: number = 0,
  maxDepth: number = 50
): Record<string, unknown> {
  if (depth > maxDepth) {
    const errorMessage = `Schema resolution exceeded max depth of ${maxDepth}. Possible circular reference.`;
    logger.error(errorMessage, { depth, maxDepth });
    throw new Error(errorMessage);
  }

  if (typeof schema !== 'object' || schema === null) {
    return schema as Record<string, unknown>;
  }

  if (Array.isArray(schema)) {
    return schema.map(item => resolveRefs(item as Record<string, unknown>, allSchemas, depth + 1, maxDepth)) as unknown as Record<string, unknown>;
  }

  if ('$ref' in schema) {
    const ref = schema.$ref as string;
    const refName = ref.split('/').pop();
    if (refName && refName in allSchemas) {
      return resolveRefs(allSchemas[refName] as Record<string, unknown>, allSchemas, depth + 1, maxDepth);
    }
    return schema;
  }

  const resolved: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(schema)) {
    resolved[key] = resolveRefs(value as Record<string, unknown>, allSchemas, depth + 1, maxDepth);
  }
  return resolved;
}

function validate(schemaName: string, data: unknown, throwOnError: boolean): boolean {
  const validator = getValidator(schemaName);
  const isValid = validator(data);

  if (!isValid) {
    const errorDetails = ajv.errorsText(validator.errors, { separator: ', ' });
    const errorMessage = `Schema validation failed for ${schemaName}: ${errorDetails}`;

    if (throwOnError) {
      throw new SchemaValidationError(errorMessage, validator.errors, data, schemaName);
    } else {
      logger.warn(errorMessage, {
        schemaName,
        errors: validator.errors,
        data,
      });
    }
  }

  return isValid;
}

export function validateNoteCreate(data: unknown): boolean {
  if (!ENABLE_VALIDATION) {return true;}
  return validate('NoteCreate', data, true);
}

export function validateNoteResponse(data: unknown): boolean {
  if (!ENABLE_VALIDATION) {return true;}
  return validate('NoteResponse', data, false);
}

export function validateNoteListResponse(data: unknown): boolean {
  if (!ENABLE_VALIDATION) {return true;}
  return validate('NoteListResponse', data, false);
}

export function validateRatingCreate(data: unknown): boolean {
  if (!ENABLE_VALIDATION) {return true;}
  return validate('RatingCreate', data, true);
}

export function validateRatingResponse(data: unknown): boolean {
  if (!ENABLE_VALIDATION) {return true;}
  return validate('RatingResponse', data, false);
}

export function validateRequestCreate(data: unknown): boolean {
  if (!ENABLE_VALIDATION) {return true;}
  return validate('RequestCreate', data, true);
}

export function validateRequestResponse(data: unknown): boolean {
  if (!ENABLE_VALIDATION) {return true;}
  return validate('RequestResponse', data, false);
}

export function validateRequestListResponse(data: unknown): boolean {
  if (!ENABLE_VALIDATION) {return true;}
  return validate('RequestListResponse', data, false);
}

export function validateScoringRequest(data: unknown): boolean {
  if (!ENABLE_VALIDATION) {return true;}
  return validate('ScoringRequest', data, true);
}

export function validateScoringResponse(data: unknown): boolean {
  if (!ENABLE_VALIDATION) {return true;}
  return validate('ScoringResponse', data, false);
}

export function validateRatingThresholdsResponse(data: unknown): boolean {
  if (!ENABLE_VALIDATION) {return true;}
  return validate('RatingThresholdsResponse', data, false);
}

export function validateHealthCheckResponse(data: unknown): boolean {
  if (!ENABLE_VALIDATION) {return true;}
  return validate('HealthCheckResponse', data, false);
}

export function getValidationErrors(schemaName: string, data: unknown): ErrorObject[] | null {
  const validator = getValidator(schemaName);
  const isValid = validator(data);
  return isValid ? null : (validator.errors || null);
}

export function formatValidationErrors(errors: ErrorObject[] | null | undefined): string {
  if (!errors || errors.length === 0) {
    return 'No validation errors';
  }

  return errors
    .map(err => {
      const path = err.instancePath || '/';
      const message = err.message || 'unknown error';
      return `  - ${path}: ${message}`;
    })
    .join('\n');
}
