import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const OPENAPI_SOURCE = path.resolve(__dirname, '../../opennotes-server/openapi.json');
const OUTPUT_FILE = path.resolve(__dirname, '../src/lib/openapi-schemas.json');

const USED_SCHEMAS = [
  'NoteCreate',
  'NoteResponse',
  'NoteData',
  'NoteListResponse',
  'NoteSummaryStats',
  'NoteClassification',
  'NoteStatus',
  'NoteUpdate',
  'RatingCreate',
  'RatingResponse',
  'RatingData',
  'RatingStats',
  'RatingUpdate',
  'HelpfulnessLevel',
  'RequestCreate',
  'RequestResponse',
  'RequestListResponse',
  'RequestStatus',
  'RequestUpdate',
  'RequestInfo',
  'ScoringRequest',
  'ScoringResponse',
  'EnrollmentData',
  'RatingThresholdsResponse',
  'HealthCheckResponse',
  'ServiceStatus',
];

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
