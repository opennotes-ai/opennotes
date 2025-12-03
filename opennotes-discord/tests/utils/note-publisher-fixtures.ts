import type { ScoreUpdateEvent } from '../../src/events/types.js';
import { TEST_SCORE_ABOVE_THRESHOLD } from '../test-constants.js';

export interface TestScenario {
  name: string;
  event: ScoreUpdateEvent;
  shouldPublishNote: boolean;
  reason: string;
}

export const createBaseScoreEvent = (overrides?: Partial<ScoreUpdateEvent>): ScoreUpdateEvent => ({
  note_id: 1,
  score: TEST_SCORE_ABOVE_THRESHOLD,
  confidence: 'standard',
  algorithm: 'MFCoreScorer',
  rating_count: 10,
  tier: 2,
  tier_name: 'Tier 2',
  timestamp: new Date().toISOString(),
  original_message_id: 'msg-123',
  channel_id: 'channel-456',
  community_server_id: 'guild-123',
  ...overrides,
});

export const testScenarios: TestScenario[] = [
  {
    name: 'Threshold Crossing: High score with standard confidence',
    event: createBaseScoreEvent({
      score: TEST_SCORE_ABOVE_THRESHOLD,
      confidence: 'standard',
      rating_count: 10,
    }),
    shouldPublishNote: true,
    reason: `Meets threshold (${TEST_SCORE_ABOVE_THRESHOLD} >= 0.7) and has standard confidence`,
  },
  {
    name: 'Threshold Crossing: Exact threshold match',
    event: createBaseScoreEvent({
      score: 0.7,
      confidence: 'standard',
      rating_count: 5,
    }),
    shouldPublishNote: true,
    reason: 'Meets threshold exactly (0.7 == 0.7)',
  },
  {
    name: 'Duplicate Post: Same original message',
    event: createBaseScoreEvent({
      original_message_id: 'msg-duplicate',
      note_id: 2,
    }),
    shouldPublishNote: false,
    reason: 'Auto-post already exists for this original message',
  },
  {
    name: 'Cooldown Violation: Recent post in channel',
    event: createBaseScoreEvent({
      channel_id: 'channel-cooldown',
      note_id: 3,
    }),
    shouldPublishNote: false,
    reason: 'Channel is on cooldown (5-minute minimum between posts)',
  },
  {
    name: 'Permission Failure: Missing SEND_MESSAGES',
    event: createBaseScoreEvent({
      channel_id: 'channel-no-send',
      note_id: 4,
    }),
    shouldPublishNote: false,
    reason: 'Bot lacks SEND_MESSAGES permission in channel',
  },
  {
    name: 'Permission Failure: Missing CREATE_PUBLIC_THREADS',
    event: createBaseScoreEvent({
      channel_id: 'channel-no-threads',
      note_id: 5,
    }),
    shouldPublishNote: false,
    reason: 'Bot lacks CREATE_PUBLIC_THREADS permission in channel',
  },
  {
    name: 'Below Threshold: Score too low',
    event: createBaseScoreEvent({
      score: 0.65,
      confidence: 'standard',
      note_id: 6,
    }),
    shouldPublishNote: false,
    reason: 'Score (0.65) below threshold (0.7)',
  },
  {
    name: 'Provisional Confidence: Not enough ratings',
    event: createBaseScoreEvent({
      score: TEST_SCORE_ABOVE_THRESHOLD,
      confidence: 'provisional',
      rating_count: 3,
      note_id: 7,
    }),
    shouldPublishNote: false,
    reason: 'Confidence is provisional (< 5 ratings)',
  },
  {
    name: 'Server Disabled: Auto-posting disabled for server',
    event: createBaseScoreEvent({
      community_server_id: 'guild-disabled',
      note_id: 8,
    }),
    shouldPublishNote: false,
    reason: 'Auto-posting disabled at server level',
  },
  {
    name: 'Channel Disabled: Auto-posting disabled for channel',
    event: createBaseScoreEvent({
      channel_id: 'channel-disabled',
      note_id: 9,
    }),
    shouldPublishNote: false,
    reason: 'Auto-posting disabled for this specific channel',
  },
];

export const errorScenarios: TestScenario[] = [
  {
    name: 'NATS Connection Failure',
    event: createBaseScoreEvent({
      note_id: 100,
    }),
    shouldPublishNote: false,
    reason: 'NATS server unavailable',
  },
  {
    name: 'Discord API Rate Limit (429)',
    event: createBaseScoreEvent({
      channel_id: 'channel-rate-limited',
      note_id: 101,
    }),
    shouldPublishNote: false,
    reason: 'Discord API returns 429 rate limit error',
  },
  {
    name: 'Database Unavailability',
    event: createBaseScoreEvent({
      note_id: 102,
    }),
    shouldPublishNote: false,
    reason: 'Cannot connect to PostgreSQL database',
  },
  {
    name: 'Original Message Deleted',
    event: createBaseScoreEvent({
      original_message_id: 'msg-deleted',
      note_id: 103,
    }),
    shouldPublishNote: false,
    reason: 'Original Discord message has been deleted',
  },
  {
    name: 'Note Content Not Found',
    event: createBaseScoreEvent({
      note_id: 999,
    }),
    shouldPublishNote: false,
    reason: 'Note does not exist in backend database',
  },
];

export const performanceScenarios = {
  generateConcurrentEvents: (count: number): ScoreUpdateEvent[] => {
    return Array.from({ length: count }, (_, i) =>
      createBaseScoreEvent({
        note_id: i + 1,
        original_message_id: `msg-${i}`,
        channel_id: `channel-${i % 10}`,
        score: 0.7 + (i % 30) / 100,
        timestamp: new Date(Date.now() + i * 100).toISOString(),
      })
    );
  },

  generateBurstEvents: (burstSize: number, burstCount: number): ScoreUpdateEvent[][] => {
    return Array.from({ length: burstCount }, (_, burstIndex) =>
      Array.from({ length: burstSize }, (_, eventIndex) => {
        const id = burstIndex * burstSize + eventIndex + 1;
        return createBaseScoreEvent({
          note_id: id,
          original_message_id: `msg-${id}`,
          channel_id: `channel-${id % 10}`,
          score: 0.7 + (id % 30) / 100,
          timestamp: new Date(Date.now() + id * 100).toISOString(),
        });
      })
    );
  },
};
