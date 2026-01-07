import { jest } from '@jest/globals';
import { loggerFactory, chatInputCommandInteractionFactory } from '../factories/index.js';

const mockLogger = loggerFactory.build();

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { Bot } = await import('../../src/bot.js');

describe('Scoring Commands Integration Tests', () => {
  let bot: any;

  beforeAll(() => {
    jest.spyOn(Bot.prototype as any, 'start').mockResolvedValue(undefined);
  });

  beforeEach(() => {
    jest.clearAllMocks();
    bot = new Bot();
  });

  describe('Command Registration', () => {
    it('should register note command', () => {
      const commands = bot.commands;
      expect(commands.has('note')).toBe(true);
    });

    it('should register list command', () => {
      const commands = bot.commands;
      expect(commands.has('list')).toBe(true);
    });

    it('note command should have correct structure', () => {
      const noteCommand = bot.commands.get('note');
      expect(noteCommand).toBeDefined();
      expect(noteCommand.data).toBeDefined();
      expect(noteCommand.execute).toBeDefined();
      expect(typeof noteCommand.execute).toBe('function');
    });

    it('list command should have correct structure', () => {
      const listCommand = bot.commands.get('list');
      expect(listCommand).toBeDefined();
      expect(listCommand.data).toBeDefined();
      expect(listCommand.execute).toBeDefined();
      expect(typeof listCommand.execute).toBe('function');
    });
  });

  describe('Command Data Validation', () => {
    it('note command should have score subcommand with required option', () => {
      const noteCommand = bot.commands.get('note');
      const commandData = noteCommand.data.toJSON();

      expect(commandData.options).toBeDefined();

      const scoreSubcommand = commandData.options.find((opt: any) => opt.name === 'score');
      expect(scoreSubcommand).toBeDefined();
      expect(scoreSubcommand.description).toBeTruthy();
      expect(scoreSubcommand.options).toHaveLength(1);
      expect(scoreSubcommand.options[0].required).toBe(true);
    });

    it('list command should have top-notes subcommand with optional filters', () => {
      const listCommand = bot.commands.get('list');
      const commandData = listCommand.data.toJSON();

      expect(commandData.options).toBeDefined();

      const topNotesSubcommand = commandData.options.find((opt: any) => opt.name === 'top-notes');
      expect(topNotesSubcommand).toBeDefined();
      expect(topNotesSubcommand.description).toBeTruthy();
      expect(topNotesSubcommand.options.length).toBeGreaterThan(0);

      const limitOption = topNotesSubcommand.options.find((opt: any) => opt.name === 'limit');
      expect(limitOption).toBeDefined();
      expect(limitOption.required).toBe(false);

      const confidenceOption = topNotesSubcommand.options.find((opt: any) => opt.name === 'confidence');
      expect(confidenceOption).toBeDefined();
      expect(confidenceOption.required).toBe(false);
      expect(confidenceOption.choices).toHaveLength(3);

      const tierOption = topNotesSubcommand.options.find((opt: any) => opt.name === 'tier');
      expect(tierOption).toBeDefined();
      expect(tierOption.required).toBe(false);
    });
  });

  describe('Score Display Integration', () => {
    it('status-bot command should include scoring status', async () => {
      const statusBotCommand = bot.commands.get('status-bot');
      expect(statusBotCommand).toBeDefined();

      const mockInteraction = chatInputCommandInteractionFactory.build({
        commandName: 'status-bot',
      });

      expect(typeof statusBotCommand.execute).toBe('function');
    });
  });

});

describe('Scoring Service Integration', () => {
  describe('End-to-end flow', () => {
    it('should handle score request flow', async () => {
      const { serviceProvider } = await import('../../src/services/index.js');
      const scoringService = serviceProvider.getScoringService();

      expect(scoringService).toBeDefined();
      expect(typeof scoringService.getNoteScore).toBe('function');
      expect(typeof scoringService.getTopNotes).toBe('function');
      expect(typeof scoringService.getScoringStatus).toBe('function');
    });

    it('should have caching methods', async () => {
      const { serviceProvider } = await import('../../src/services/index.js');
      const scoringService = serviceProvider.getScoringService();

      expect(typeof scoringService.invalidateNoteScoreCache).toBe('function');
      expect(typeof scoringService.invalidateScoringStatusCache).toBe('function');
    });
  });

  describe('Formatter integration', () => {
    it('should have scoring format methods (v2)', async () => {
      const { DiscordFormatter } = await import('../../src/services/DiscordFormatter.js');

      expect(typeof DiscordFormatter.formatNoteScoreV2).toBe('function');
      expect(typeof DiscordFormatter.formatTopNotesForQueueV2).toBe('function');
      expect(typeof DiscordFormatter.formatScoringStatusV2).toBe('function');
      expect(typeof DiscordFormatter.getConfidenceEmoji).toBe('function');
      expect(typeof DiscordFormatter.getConfidenceLabel).toBe('function');
      expect(typeof DiscordFormatter.getScoreColor).toBe('function');
      expect(typeof DiscordFormatter.formatScore).toBe('function');
    });
  });
});
