/**
 * Performance profiling script for the note-queue command
 *
 * This script simulates the note-queue command execution flow and measures
 * the time spent in each phase to identify performance bottlenecks.
 *
 * Usage:
 *   pnpm tsx scripts/profile-note-queue.ts
 */

import { Client, GatewayIntentBits } from 'discord.js';
import { apiClient } from '../src/api-client.js';
import { configCache } from '../src/queue.js';
import { MessageFetcher } from '../src/lib/message-fetcher.js';
import { NotesFormatter } from '../src/lib/notes-formatter.js';
import type { NoteWithRatings } from '../src/lib/types.js';
import { logger } from '../src/logger.js';

interface PhaseTimings {
  phaseName: string;
  durationMs: number;
  percentage?: number;
}

class PerformanceProfiler {
  private timings: PhaseTimings[] = [];
  private currentPhaseStart: number = 0;
  private currentPhaseName: string = '';
  private totalStart: number = 0;

  startTotal(): void {
    this.totalStart = performance.now();
  }

  startPhase(phaseName: string): void {
    this.currentPhaseName = phaseName;
    this.currentPhaseStart = performance.now();
  }

  endPhase(): void {
    const duration = performance.now() - this.currentPhaseStart;
    this.timings.push({
      phaseName: this.currentPhaseName,
      durationMs: duration,
    });
  }

  getTotalDuration(): number {
    return performance.now() - this.totalStart;
  }

  calculatePercentages(): void {
    const total = this.getTotalDuration();
    this.timings.forEach(timing => {
      timing.percentage = (timing.durationMs / total) * 100;
    });
  }

  getReport(): string {
    this.calculatePercentages();

    const lines = [
      '\n========================================',
      'QUEUE-NOTES PERFORMANCE PROFILE',
      '========================================\n',
    ];

    this.timings.forEach(timing => {
      const bar = '█'.repeat(Math.round((timing.percentage || 0) / 2));
      lines.push(
        `${timing.phaseName.padEnd(40)} ${timing.durationMs.toFixed(2).padStart(10)}ms  ${(timing.percentage || 0).toFixed(1).padStart(5)}%  ${bar}`
      );
    });

    lines.push('\n' + '─'.repeat(80));
    lines.push(
      `${'TOTAL EXECUTION TIME'.padEnd(40)} ${this.getTotalDuration().toFixed(2).padStart(10)}ms  100.0%`
    );
    lines.push('========================================\n');

    return lines.join('\n');
  }

  getBottleneck(): PhaseTimings | null {
    if (this.timings.length === 0) return null;
    return this.timings.reduce((max, current) =>
      current.durationMs > max.durationMs ? current : max
    );
  }
}

async function fetchMessagesForNotes(
  messageFetcher: MessageFetcher,
  notes: NoteWithRatings[]
): Promise<Map<string, any>> {
  const messageMap = new Map<string, any>();

  await Promise.all(
    notes.map(async (note) => {
      const messageInfo = await messageFetcher.fetchMessage(String(note.tweet_id));
      messageMap.set(note.note_id, messageInfo);
    })
  );

  return messageMap;
}

async function profileQueueNotesExecution(): Promise<void> {
  const profiler = new PerformanceProfiler();

  console.log('Starting note-queue performance profiling...\n');

  // Create a minimal Discord client (not connected, just for MessageFetcher)
  const client = new Client({
    intents: [
      GatewayIntentBits.Guilds,
      GatewayIntentBits.GuildMessages,
      GatewayIntentBits.MessageContent,
    ],
  });

  profiler.startTotal();

  try {
    // Phase 1: Rate limiting check (simulated - instant in practice)
    profiler.startPhase('1. Rate Limiting Check');
    const userId = 'test-user-id';
    const lastUse = Date.now() - 120000; // 2 minutes ago, so no rate limit
    const isRateLimited = lastUse && Date.now() - lastUse < 60000;
    profiler.endPhase();

    if (isRateLimited) {
      console.log('Would be rate limited (skipping profile)');
      return;
    }

    // Phase 2: Parallel API calls (thresholds + notes)
    profiler.startPhase('2. Parallel API Calls (thresholds + notes)');
    const [thresholds, notesResponse] = await Promise.all([
      configCache.getRatingThresholds(),
      apiClient.listNotesWithStatus('NEEDS_MORE_RATINGS', 1, 10),
    ]);
    profiler.endPhase();

    console.log(`Fetched ${notesResponse.notes.length} notes (total: ${notesResponse.total})\n`);

    // Phase 3: Message fetching (parallel Discord API calls)
    profiler.startPhase('3. Fetch Original Messages (Discord API)');
    const messageFetcher = new MessageFetcher(client);
    const messageMap = await fetchMessagesForNotes(messageFetcher, notesResponse.notes);
    profiler.endPhase();

    console.log(`Fetched ${messageMap.size} messages from Discord\n`);

    // Phase 4: Format queue embed
    profiler.startPhase('4. Format Queue Embed');
    const embed = NotesFormatter.formatQueueEmbed(
      notesResponse.notes,
      thresholds,
      1,
      notesResponse.total,
      10, // notesPerPage
      messageMap
    );
    profiler.endPhase();

    // Phase 5: Create button components
    profiler.startPhase('5. Create Button Components');
    const totalPages = Math.ceil(notesResponse.total / 10);
    // Simulating button creation (would normally be ActionRowBuilder)
    const buttonCount = notesResponse.notes.length + (totalPages > 1 ? 2 : 0);
    profiler.endPhase();

    console.log(`Created ${buttonCount} buttons\n`);

    // Phase 6: Thread creation (simulated - would be Discord API)
    profiler.startPhase('6. Thread Creation (Discord API)');
    // Simulate thread creation latency (150-300ms typical)
    await new Promise(resolve => setTimeout(resolve, 200));
    profiler.endPhase();

    // Phase 7: Send message to thread (simulated - would be Discord API)
    profiler.startPhase('7. Send Message to Thread (Discord API)');
    // Simulate message send latency (100-200ms typical)
    await new Promise(resolve => setTimeout(resolve, 150));
    profiler.endPhase();

    // Generate report
    const report = profiler.getReport();
    console.log(report);

    // Identify bottleneck
    const bottleneck = profiler.getBottleneck();
    if (bottleneck) {
      console.log(`🔴 PRIMARY BOTTLENECK: ${bottleneck.phaseName}`);
      console.log(`   Duration: ${bottleneck.durationMs.toFixed(2)}ms (${bottleneck.percentage?.toFixed(1)}%)\n`);
    }

    // Performance analysis
    console.log('ANALYSIS:');
    console.log('─'.repeat(80));

    const totalTime = profiler.getTotalDuration();
    if (totalTime < 2000) {
      console.log(`✅ GOOD: Total execution time (${totalTime.toFixed(0)}ms) is under 2s target`);
    } else {
      console.log(`❌ SLOW: Total execution time (${totalTime.toFixed(0)}ms) exceeds 2s target`);
    }

    // Detailed analysis
    profiler.calculatePercentages();
    const messageFetchPhase = profiler['timings'].find(t => t.phaseName.includes('Fetch Original Messages'));
    const apiCallPhase = profiler['timings'].find(t => t.phaseName.includes('Parallel API Calls'));

    if (messageFetchPhase && messageFetchPhase.percentage! > 40) {
      console.log(`\n⚠️  Message fetching takes ${messageFetchPhase.percentage?.toFixed(1)}% of total time`);
      console.log('   Recommendation: Consider lazy-loading messages on button click');
    }

    if (apiCallPhase && apiCallPhase.durationMs > 500) {
      console.log(`\n⚠️  API calls take ${apiCallPhase.durationMs.toFixed(0)}ms`);
      console.log('   Recommendation: Check database query performance and indexing');
    }

    console.log('\n');

  } catch (error) {
    console.error('Error during profiling:', error);
    throw error;
  }
}

// Run profiler
profileQueueNotesExecution()
  .then(() => {
    console.log('Profiling complete!');
    process.exit(0);
  })
  .catch((error) => {
    console.error('Profiling failed:', error);
    process.exit(1);
  });
