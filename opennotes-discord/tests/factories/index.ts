/**
 * Test Factories for Discord Bot
 *
 * This directory contains Fishery factories for creating test fixtures.
 * Factories provide type-safe, consistent test data with automatic sequencing.
 *
 * Usage:
 *   import { noteFactory } from './factories/index.js';
 *   const note = noteFactory.build({ content: 'Custom content' });
 *   const notes = noteFactory.buildList(5);
 *
 * Re-export shared factories from @opennotes/test-utils:
 */
export { Factory, noteFactory, ratingFactory } from '@opennotes/test-utils';

/**
 * Discord-specific factories will be added here by subtasks 856.01-856.12:
 * - noteRequestFactory (task-856.01)
 * - noteRequestEventFactory (task-856.02)
 * - discordInteractionFactory (task-856.03)
 * - etc.
 */
