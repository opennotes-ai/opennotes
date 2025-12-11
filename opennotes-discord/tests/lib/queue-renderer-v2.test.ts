import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import type { ThreadChannel, Message, MessageCreateOptions } from 'discord.js';
import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
} from 'discord.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { QueueRendererV2 } = await import('../../src/lib/queue-renderer.js');
import type {
  QueueItemV2,
  QueueSummaryV2,
  QueueRenderResultV2,
  PaginationConfig,
} from '../../src/lib/queue-renderer.js';
import { v2MessageFlags, V2_COLORS } from '../../src/utils/v2-components.js';

interface ContainerData {
  type: number;
  accent_color?: number;
  components?: Array<{ type: number; content?: string }>;
}

interface MockSendOptions {
  components?: Array<{ toJSON: () => ContainerData; data: { accent_color?: number } }>;
  flags?: number;
}

describe('QueueRendererV2 - Components v2 Migration', () => {
  let mockThread: ThreadChannel;
  let mockMessage: Message;

  function createMockMessage(id: string, deleteFn?: jest.Mock): Message {
    return {
      id,
      edit: jest.fn<() => Promise<Message>>().mockResolvedValue({} as Message),
      delete: deleteFn || jest.fn<() => Promise<void>>().mockResolvedValue(undefined),
      channel: mockThread,
    } as unknown as Message;
  }

  function createTestItem(id: string, urgencyEmoji: string = '\u{1F534}'): QueueItemV2 {
    return {
      id,
      title: `Note #${id}`,
      summary: `This is the summary for note ${id}`,
      urgencyEmoji,
      ratingButtons: new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder()
          .setCustomId(`rate:${id}:helpful`)
          .setLabel('Helpful')
          .setStyle(ButtonStyle.Success),
        new ButtonBuilder()
          .setCustomId(`rate:${id}:not_helpful`)
          .setLabel('Not Helpful')
          .setStyle(ButtonStyle.Danger)
      ),
    };
  }

  function createTestSummary(): QueueSummaryV2 {
    return {
      title: 'Rating Queue',
      subtitle: '3 notes need your rating',
      stats: '\u{1F534} 1 critical \u2022 \u{1F7E0} 1 high \u2022 \u{1F7E1} 1 medium',
    };
  }

  function getSendCall(mock: jest.Mock, callIndex: number = 0): MockSendOptions {
    return mock.mock.calls[callIndex][0] as MockSendOptions;
  }

  beforeEach(() => {
    jest.clearAllMocks();

    mockMessage = createMockMessage('msg-123');

    mockThread = {
      id: 'thread-123',
      send: jest.fn<(options: MessageCreateOptions) => Promise<Message>>().mockResolvedValue(mockMessage),
    } as unknown as ThreadChannel;
  });

  describe('AC #1: Single ContainerBuilder for multiple items', () => {
    it('should render multiple items in a single container', async () => {
      const summary = createTestSummary();
      const items = [
        createTestItem('1'),
        createTestItem('2'),
        createTestItem('3'),
      ];

      const result = await QueueRendererV2.render(mockThread, summary, items);

      expect(mockThread.send).toHaveBeenCalledTimes(1);
      expect(result.messages.length).toBe(1);
    });

    it('should use V2_COLORS.PRIMARY as container accent', async () => {
      const summary = createTestSummary();
      const items = [createTestItem('1')];

      await QueueRendererV2.render(mockThread, summary, items);

      const sendCall = getSendCall(mockThread.send as jest.Mock);
      expect(sendCall.components).toBeDefined();
      expect(sendCall.components!.length).toBe(1);

      const container = sendCall.components![0];
      expect(container.data.accent_color).toBe(V2_COLORS.PRIMARY);
    });
  });

  describe('AC #2: SectionBuilder per item with button accessories', () => {
    it('should create text content for each queue item', async () => {
      const summary = createTestSummary();
      const items = [
        createTestItem('1'),
        createTestItem('2'),
      ];

      await QueueRendererV2.render(mockThread, summary, items);

      const sendCall = getSendCall(mockThread.send as jest.Mock);
      const container = sendCall.components![0];
      const containerJson = container.toJSON();
      const components = containerJson.components!;

      const textDisplays = components.filter(
        (c: { type: number }) => c.type === 10
      );
      expect(textDisplays.length).toBeGreaterThanOrEqual(2);
    });

    it('should include item content with urgency emoji', async () => {
      const summary = createTestSummary();
      const items = [createTestItem('42', '\u{1F534}')];

      await QueueRendererV2.render(mockThread, summary, items);

      const sendCall = getSendCall(mockThread.send as jest.Mock);
      const container = sendCall.components![0];
      const json = JSON.stringify(container.toJSON());

      expect(json).toContain('\u{1F534}');
      expect(json).toContain('Note #42');
    });
  });

  describe('AC #3: SeparatorBuilder between queue items', () => {
    it('should add separators between items', async () => {
      const summary = createTestSummary();
      const items = [
        createTestItem('1'),
        createTestItem('2'),
        createTestItem('3'),
      ];

      await QueueRendererV2.render(mockThread, summary, items);

      const sendCall = getSendCall(mockThread.send as jest.Mock);
      const container = sendCall.components![0];
      const containerJson = container.toJSON();
      const components = containerJson.components!;

      const separators = components.filter(
        (c: { type: number }) => c.type === 14
      );
      expect(separators.length).toBeGreaterThan(0);
    });
  });

  describe('AC #4: Simplified QueueRenderResultV2 (no itemMessages Map)', () => {
    it('should return simplified result without itemMessages Map', async () => {
      const summary = createTestSummary();
      const items = [createTestItem('1')];

      const result = await QueueRendererV2.render(mockThread, summary, items);

      expect(result.messages).toBeDefined();
      expect(Array.isArray(result.messages)).toBe(true);
      expect(result).not.toHaveProperty('itemMessages');
      expect(result).not.toHaveProperty('summaryMessage');
    });

    it('should track total items rendered', async () => {
      const summary = createTestSummary();
      const items = [
        createTestItem('1'),
        createTestItem('2'),
        createTestItem('3'),
      ];

      const result = await QueueRendererV2.render(mockThread, summary, items);

      expect(result.totalItems).toBe(3);
    });
  });

  describe('AC #5: Batching when items exceed limit', () => {
    it('should batch items when exceeding 4 per container (5 action row limit)', async () => {
      const summary = createTestSummary();
      const items = [
        createTestItem('1'),
        createTestItem('2'),
        createTestItem('3'),
        createTestItem('4'),
        createTestItem('5'),
      ];

      const mockSend = mockThread.send as jest.Mock<(options: MessageCreateOptions) => Promise<Message>>;
      mockSend.mockClear();
      mockSend.mockResolvedValue(createMockMessage('msg'));

      const result = await QueueRendererV2.render(mockThread, summary, items);

      expect(mockSend).toHaveBeenCalledTimes(2);
      expect(result.messages.length).toBe(2);
    });

    it('should fit exactly 4 items in one container with pagination', async () => {
      const summary = createTestSummary();
      const items = [
        createTestItem('1'),
        createTestItem('2'),
        createTestItem('3'),
        createTestItem('4'),
      ];
      const pagination: PaginationConfig = {
        currentPage: 1,
        totalPages: 2,
        previousButtonId: 'page:prev',
        nextButtonId: 'page:next',
      };

      const mockSend = mockThread.send as jest.Mock<(options: MessageCreateOptions) => Promise<Message>>;
      mockSend.mockClear();
      mockSend.mockResolvedValue(createMockMessage('msg'));

      const result = await QueueRendererV2.render(mockThread, summary, items, pagination);

      expect(mockSend).toHaveBeenCalledTimes(1);
      expect(result.messages.length).toBe(1);
    });
  });

  describe('AC #6: render() outputs single/minimal messages', () => {
    it('should output single message for small queues', async () => {
      const summary = createTestSummary();
      const items = [createTestItem('1')];

      const result = await QueueRendererV2.render(mockThread, summary, items);

      expect(result.messages.length).toBe(1);
    });

    it('should include summary header in the container', async () => {
      const summary = createTestSummary();
      const items = [createTestItem('1')];

      await QueueRendererV2.render(mockThread, summary, items);

      const sendCall = getSendCall(mockThread.send as jest.Mock);
      const container = sendCall.components![0];
      const json = JSON.stringify(container.toJSON());

      expect(json).toContain('Rating Queue');
      expect(json).toContain('3 notes need your rating');
    });
  });

  describe('AC #7: Simplified update() for single-message updates', () => {
    it('should update single message instead of multiple', async () => {
      const originalMessage = createMockMessage('original-msg');
      const existingResult: QueueRenderResultV2 = {
        messages: [originalMessage],
        totalItems: 1,
      };

      const newSummary = createTestSummary();
      const newItems = [createTestItem('updated-1')];

      await QueueRendererV2.update(existingResult, newSummary, newItems);

      expect(originalMessage.edit).toHaveBeenCalledTimes(1);
    });

    it('should handle transition from single to multiple messages', async () => {
      const originalMessage = createMockMessage('original-msg');
      const existingResult: QueueRenderResultV2 = {
        messages: [originalMessage],
        totalItems: 1,
      };

      const newSummary = createTestSummary();
      const newItems = [
        createTestItem('1'),
        createTestItem('2'),
        createTestItem('3'),
        createTestItem('4'),
        createTestItem('5'),
      ];

      const mockSend = mockThread.send as jest.Mock<(options: MessageCreateOptions) => Promise<Message>>;
      mockSend.mockClear();
      mockSend.mockResolvedValue(createMockMessage('new-msg'));

      const result = await QueueRendererV2.update(existingResult, newSummary, newItems);

      expect(originalMessage.edit).toHaveBeenCalledTimes(1);
      expect(mockSend).toHaveBeenCalledTimes(1);
      expect(result.messages.length).toBe(2);
    });
  });

  describe('AC #8: Simplified cleanup()', () => {
    it('should delete all messages in result', async () => {
      const msg1 = createMockMessage('msg-1');
      const msg2 = createMockMessage('msg-2');
      const result: QueueRenderResultV2 = {
        messages: [msg1, msg2],
        totalItems: 5,
      };

      await QueueRendererV2.cleanup(result);

      expect(msg1.delete).toHaveBeenCalledTimes(1);
      expect(msg2.delete).toHaveBeenCalledTimes(1);
    });

    it('should handle delete failures gracefully', async () => {
      const deleteError = new Error('Message not found');
      const failingMsg = createMockMessage(
        'fail-msg',
        jest.fn<() => Promise<void>>().mockRejectedValue(deleteError)
      );
      const result: QueueRenderResultV2 = {
        messages: [failingMsg],
        totalItems: 1,
      };

      await QueueRendererV2.cleanup(result);

      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Failed to delete message during cleanup',
        expect.objectContaining({ error: 'Message not found' })
      );
    });
  });

  describe('AC #9: MessageFlags.IsComponentsV2 applied', () => {
    it('should include IsComponentsV2 flag in message options', async () => {
      const summary = createTestSummary();
      const items = [createTestItem('1')];

      await QueueRendererV2.render(mockThread, summary, items);

      const sendCall = getSendCall(mockThread.send as jest.Mock);
      expect(sendCall.flags).toBe(v2MessageFlags());
    });

    it('should include IsComponentsV2 flag in update calls', async () => {
      const originalMessage = createMockMessage('original-msg');
      const existingResult: QueueRenderResultV2 = {
        messages: [originalMessage],
        totalItems: 1,
      };

      const newSummary = createTestSummary();
      const newItems = [createTestItem('1')];

      await QueueRendererV2.update(existingResult, newSummary, newItems);

      const editCall = (originalMessage.edit as jest.Mock).mock.calls[0][0] as MockSendOptions;
      expect(editCall.flags).toBe(v2MessageFlags());
    });
  });

  describe('AC #10: Multi-item single-message rendering', () => {
    it('should render 3 items with their rating buttons in one message', async () => {
      const summary = createTestSummary();
      const items = [
        createTestItem('1'),
        createTestItem('2'),
        createTestItem('3'),
      ];

      await QueueRendererV2.render(mockThread, summary, items);

      const sendCall = getSendCall(mockThread.send as jest.Mock);
      const container = sendCall.components![0];
      const containerJson = container.toJSON();
      const components = containerJson.components!;

      const actionRows = components.filter(
        (c: { type: number }) => c.type === 1
      );
      expect(actionRows.length).toBe(3);
    });

    it('should handle empty items list', async () => {
      const summary = createTestSummary();
      const items: QueueItemV2[] = [];

      const result = await QueueRendererV2.render(mockThread, summary, items);

      expect(result.messages.length).toBe(1);
      expect(result.totalItems).toBe(0);
    });

    it('should include pagination row when provided', async () => {
      const summary = createTestSummary();
      const items = [createTestItem('1')];
      const pagination: PaginationConfig = {
        currentPage: 1,
        totalPages: 3,
        previousButtonId: 'queue:prev',
        nextButtonId: 'queue:next',
      };

      await QueueRendererV2.render(mockThread, summary, items, pagination);

      const sendCall = getSendCall(mockThread.send as jest.Mock);
      const container = sendCall.components![0];
      const containerJson = container.toJSON();
      const components = containerJson.components!;

      const actionRows = components.filter(
        (c: { type: number }) => c.type === 1
      );
      expect(actionRows.length).toBe(2);
    });
  });

  describe('getAllMessages helper', () => {
    it('should return all messages from result', () => {
      const msg1 = createMockMessage('msg-1');
      const msg2 = createMockMessage('msg-2');
      const result: QueueRenderResultV2 = {
        messages: [msg1, msg2],
        totalItems: 5,
      };

      const allMessages = QueueRendererV2.getAllMessages(result);

      expect(allMessages).toEqual([msg1, msg2]);
    });
  });
});
