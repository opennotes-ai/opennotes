import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const OPENAPI_SOURCE = path.resolve(__dirname, '../../opennotes-server/openapi.json');
const OUTPUT_FILE = path.resolve(__dirname, '../src/lib/openapi-schemas.json');

const USED_SCHEMAS = [
  'NoteCreateAttributes',
  'NoteJSONAPIAttributes',
  'NoteData',
  'NoteClassification',
  'NoteStatus',
  'NoteUpdateAttributes',
  'RatingCreateAttributes',
  'RatingAttributes',
  'RatingData',
  'RatingUpdateAttributes',
  'HelpfulnessLevel',
  'RequestCreateAttributes',
  'RequestAttributes',
  'RequestListJSONAPIResponse',
  'RequestResource',
  'RequestStatus',
  'RequestUpdateAttributes',
  'ScoringRequest',
  'ScoringResponse',
  'EnrollmentData',
  'RatingThresholdsResponse',
  'HealthCheckResponse',
  'ServiceStatus',
  'JSONAPILinks',
  'JSONAPIMeta',
];

const SCHEMA_ALIASES: Record<string, string> = {
  'NoteCreate': 'NoteCreateAttributes',
  'NoteResponse': 'NoteJSONAPIAttributes',
  'RatingCreate': 'RatingCreateAttributes',
  'RatingResponse': 'RatingAttributes',
  'NoteUpdate': 'NoteUpdateAttributes',
  'RatingUpdate': 'RatingUpdateAttributes',
  'RequestCreate': 'RequestCreateAttributes',
  'RequestResponse': 'RequestAttributes',
  'RequestListResponse': 'RequestListJSONAPIResponse',
  'RequestUpdate': 'RequestUpdateAttributes',
};

const CUSTOM_SCHEMAS: Record<string, unknown> = {
  NoteListResponse: {
    properties: {
      notes: {
        items: {
          $ref: '#/components/schemas/NoteResponse',
        },
        type: 'array',
        title: 'Notes',
      },
      total: {
        type: 'integer',
        title: 'Total',
      },
      page: {
        type: 'integer',
        title: 'Page',
      },
      size: {
        type: 'integer',
        title: 'Size',
      },
    },
    additionalProperties: false,
    type: 'object',
    required: ['notes', 'total', 'page', 'size'],
    title: 'NoteListResponse',
  },
  ScoringRequest: {
    title: 'ScoringRequest',
    type: 'object',
    properties: {
      notes: {
        type: 'array',
        items: {
          $ref: '#/components/schemas/NoteData',
        },
      },
      ratings: {
        type: 'array',
        items: {
          $ref: '#/components/schemas/RatingData',
        },
      },
      enrollment: {
        type: 'array',
        items: {
          $ref: '#/components/schemas/EnrollmentData',
        },
      },
      status: {
        anyOf: [
          { type: 'array', items: { type: 'object' } },
          { type: 'null' },
        ],
      },
    },
    required: ['notes', 'ratings', 'enrollment'],
  },
  ScoringResponse: {
    title: 'ScoringResponse',
    type: 'object',
    properties: {
      data: {
        type: 'object',
        properties: {
          type: { type: 'string' },
          id: { type: 'string' },
          attributes: {
            type: 'object',
            properties: {
              scored_notes: { type: 'array', items: { type: 'object' } },
              helpful_scores: { type: 'array', items: { type: 'object' } },
              auxiliary_info: { type: 'array', items: { type: 'object' } },
            },
          },
        },
      },
    },
    required: ['data'],
  },
};

interface OpenAPISchema {
  components: {
    schemas: Record<string, unknown>;
  };
}

async function extractSchemas() {
  console.log('Reading OpenAPI schema from:', OPENAPI_SOURCE);

  const openapiContent = fs.readFileSync(OPENAPI_SOURCE, 'utf-8');
  const openapi = JSON.parse(openapiContent) as OpenAPISchema;

  if (!openapi.components?.schemas) {
    throw new Error('Invalid OpenAPI schema: missing components.schemas');
  }

  const extractedSchemas: Record<string, unknown> = {};
  const missingSchemas: string[] = [];

  for (const schemaName of USED_SCHEMAS) {
    if (schemaName in openapi.components.schemas) {
      extractedSchemas[schemaName] = openapi.components.schemas[schemaName];
    } else {
      missingSchemas.push(schemaName);
    }
  }

  for (const [aliasName, targetName] of Object.entries(SCHEMA_ALIASES)) {
    if (targetName in extractedSchemas) {
      extractedSchemas[aliasName] = extractedSchemas[targetName];
      console.log(`📎 Added alias: ${aliasName} -> ${targetName}`);
    }
  }

  for (const [customName, customSchema] of Object.entries(CUSTOM_SCHEMAS)) {
    extractedSchemas[customName] = customSchema;
    console.log(`📝 Added custom schema: ${customName}`);
  }

  if (missingSchemas.length > 0) {
    console.warn('⚠️  WARNING: The following schemas were not found in OpenAPI:');
    missingSchemas.forEach(name => console.warn(`  - ${name}`));
    console.warn('\nUpdate USED_SCHEMAS in this script if schemas have been renamed.');
  }

  console.log(`\n✅ Extracted ${Object.keys(extractedSchemas).length} schemas`);

  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(extractedSchemas, null, 2));

  console.log(`📝 Schemas written to: ${OUTPUT_FILE}`);
  console.log('\nNext steps:');
  console.log('  1. Review the extracted schemas');
  console.log('  2. Audit TypeScript types against these schemas');
  console.log('  3. Set up runtime validation with ajv');
}

extractSchemas().catch(error => {
  console.error('❌ Error extracting schemas:', error);
  process.exit(1);
});
