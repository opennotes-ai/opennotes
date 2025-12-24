import { Factory } from 'fishery';
import type {
  LatestScanResponse,
  FlaggedMessageResource,
  NoteRequestsResultResponse,
  ExplanationResultResponse,
} from '../../src/lib/api-client.js';

export interface FlaggedMessageTransientParams {
  matchScore?: number;
  matchedClaim?: string;
  matchedSource?: string;
  factCheckItemId?: string;
}

export const flaggedMessageFactory = Factory.define<FlaggedMessageResource, FlaggedMessageTransientParams>(
  ({ sequence, transientParams }) => {
    const {
      matchScore = 0.9,
      matchedClaim = `Test claim ${sequence}`,
      matchedSource = 'snopes',
      factCheckItemId = '12345678-1234-1234-1234-123456789abc',
    } = transientParams;

    return {
      type: 'flagged-messages',
      id: `msg-${sequence}`,
      attributes: {
        channel_id: `channel-${sequence}`,
        content: `Flagged content ${sequence}`,
        author_id: `author-${sequence}`,
        timestamp: new Date().toISOString(),
        matches: [
          {
            scan_type: 'similarity' as const,
            score: matchScore,
            matched_claim: matchedClaim,
            matched_source: matchedSource,
            fact_check_item_id: factCheckItemId,
          },
        ],
      },
    };
  }
);

export interface LatestScanTransientParams {
  status?: string;
  messagesScanned?: number;
  flaggedMessages?: FlaggedMessageResource[];
}

export const latestScanResponseFactory = Factory.define<LatestScanResponse, LatestScanTransientParams>(
  ({ sequence, transientParams }) => {
    const {
      status = 'completed',
      messagesScanned = 100,
      flaggedMessages = [],
    } = transientParams;

    return {
      data: {
        type: 'bulk-scans',
        id: `scan-${sequence}`,
        attributes: {
          status,
          initiated_at: new Date().toISOString(),
          messages_scanned: messagesScanned,
          messages_flagged: flaggedMessages.length,
        },
      },
      included: flaggedMessages,
      jsonapi: { version: '1.1' },
    };
  }
);

export interface NoteRequestsResultTransientParams {
  createdCount?: number;
  requestIds?: string[];
}

export const noteRequestsResultFactory = Factory.define<NoteRequestsResultResponse, NoteRequestsResultTransientParams>(
  ({ sequence, transientParams }) => {
    const { createdCount = 0, requestIds = [] } = transientParams;

    return {
      data: {
        type: 'note-request-batches',
        id: `batch-${sequence}`,
        attributes: {
          created_count: createdCount,
          request_ids: requestIds,
        },
      },
      jsonapi: { version: '1.1' },
    };
  }
);

export interface ExplanationResultTransientParams {}

export const explanationResultFactory = Factory.define<ExplanationResultResponse, ExplanationResultTransientParams>(
  ({ sequence }) => ({
    data: {
      type: 'scan-explanations',
      id: `explanation-${sequence}`,
      attributes: {
        explanation: `This is a test explanation ${sequence}`,
      },
    },
    jsonapi: { version: '1.1' },
  })
);
