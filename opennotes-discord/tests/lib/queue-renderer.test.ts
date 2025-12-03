import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import type { ThreadChannel, Message } from 'discord.js';
import { EmbedBuilder } from 'discord.js';

const mockLogger = {
  info: jest.fn<(...args: unknown[]) => void>(),
  error: jest.fn<(...args: unknown[]) => void>(),
  warn: jest.fn<(...args: unknown[]) => void>(),
  debug: jest.fn<(...args: unknown[]) => void>(),
};

jest.unstable_mockModule('../../src/logger.js', () => ({
  logger: mockLogger,
}));

const { QueueRenderer } = await import('../../src/lib/queue-renderer.js');
import type { QueueRenderResult, QueueItem, QueueSummary } from '../../src/lib/queue-renderer.js';

describe('QueueRenderer - Structured Logging', () => {
  let mockThread: ThreadChannel;
  let mockSummaryMessage: Message;
  let mockItemMessage: Message;
  let mockPaginationMessage: Message;

  function createMockMessage(id: string, deleteFn?: jest.Mock): Message {
    return {
      id,
      edit: jest.fn<any>().mockResolvedValue(undefined),
      delete: deleteFn || jest.fn<any>().mockResolvedValue(undefined),
      channel: mockThread,
    } as unknown as Message;
  }

  beforeEach(() => {
    jest.clearAllMocks();

    mockSummaryMessage = createMockMessage('summary-msg-123');
    mockItemMessage = createMockMessage('item-msg-456');
    mockPaginationMessage = createMockMessage('pagination-msg-789');

    mockThread = {
      id: 'thread-123',
      send: jest.fn<any>()
        .mockResolvedValueOnce(mockSummaryMessage)
        .mockResolvedValueOnce(mockItemMessage)
        .mockResolvedValueOnce(mockPaginationMessage),
    } as unknown as ThreadChannel;
  });

  describe('update method - structured logging for delete failures', () => {
    it('should use logger.warn when item message deletion fails', async () => {
      const deleteError = new Error('Unknown message');
      const failingDeleteFn = jest.fn<any>().mockRejectedValue(deleteError);
      const mockItemMsgWithError = createMockMessage('item-msg-delete-fail', failingDeleteFn);

      const existingResult: QueueRenderResult = {
        summaryMessage: mockSummaryMessage,
        itemMessages: new Map([['item-1', mockItemMsgWithError]]),
        paginationMessage: null,
      };

      const newSummary: QueueSummary = {
        embed: new EmbedBuilder().setTitle('Updated Summary'),
      };

      const newItems: QueueItem[] = [];

      const mockSend = mockThread.send as jest.Mock<any>;
      mockSend.mockReset();
      mockSend.mockResolvedValue(createMockMessage('new-msg'));

      await QueueRenderer.update(existingResult, newSummary, newItems);

      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Failed to delete item message',
        expect.objectContaining({
          error: 'Unknown message',
        })
      );
    });

    it('should use logger.warn when pagination message deletion fails', async () => {
      const deleteError = new Error('Discord API Error');
      const failingDeleteFn = jest.fn<any>().mockRejectedValue(deleteError);
      const mockPaginationMsgWithError = createMockMessage('pagination-delete-fail', failingDeleteFn);

      const existingResult: QueueRenderResult = {
        summaryMessage: mockSummaryMessage,
        itemMessages: new Map(),
        paginationMessage: mockPaginationMsgWithError,
      };

      const newSummary: QueueSummary = {
        embed: new EmbedBuilder().setTitle('Updated Summary'),
      };

      const mockSend = mockThread.send as jest.Mock<any>;
      mockSend.mockReset();

      await QueueRenderer.update(existingResult, newSummary, []);

      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Failed to delete pagination message',
        expect.objectContaining({
          error: 'Discord API Error',
        })
      );
    });

    it('should include non-Error objects in structured log context', async () => {
      const deleteError = 'String error message';
      const failingDeleteFn = jest.fn<any>().mockRejectedValue(deleteError);
      const mockItemMsgWithError = createMockMessage('item-msg-string-error', failingDeleteFn);

      const existingResult: QueueRenderResult = {
        summaryMessage: mockSummaryMessage,
        itemMessages: new Map([['item-1', mockItemMsgWithError]]),
        paginationMessage: null,
      };

      const newSummary: QueueSummary = {
        embed: new EmbedBuilder().setTitle('Updated Summary'),
      };

      const mockSend = mockThread.send as jest.Mock<any>;
      mockSend.mockReset();
      mockSend.mockResolvedValue(createMockMessage('new-msg'));

      await QueueRenderer.update(existingResult, newSummary, []);

      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Failed to delete item message',
        expect.objectContaining({
          error: 'String error message',
        })
      );
    });
  });

  describe('cleanup method - structured logging for delete failures', () => {
    it('should use logger.warn when message deletion fails during cleanup', async () => {
      const deleteError = new Error('Message not found');
      const failingDeleteFn = jest.fn<any>().mockRejectedValue(deleteError);
      const mockMsgWithError = createMockMessage('cleanup-fail-msg', failingDeleteFn);

      const result: QueueRenderResult = {
        summaryMessage: mockMsgWithError,
        itemMessages: new Map(),
        paginationMessage: null,
      };

      await QueueRenderer.cleanup(result);

      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Failed to delete message during cleanup',
        expect.objectContaining({
          error: 'Message not found',
        })
      );
    });

    it('should handle multiple message deletion failures with structured logging', async () => {
      const summaryError = new Error('Summary delete failed');
      const itemError = new Error('Item delete failed');
      const paginationError = new Error('Pagination delete failed');

      const summaryDeleteFn = jest.fn<any>().mockRejectedValue(summaryError);
      const itemDeleteFn = jest.fn<any>().mockRejectedValue(itemError);
      const paginationDeleteFn = jest.fn<any>().mockRejectedValue(paginationError);

      const mockSummaryWithError = createMockMessage('summary-fail', summaryDeleteFn);
      const mockItemWithError = createMockMessage('item-fail', itemDeleteFn);
      const mockPaginationWithError = createMockMessage('pagination-fail', paginationDeleteFn);

      const result: QueueRenderResult = {
        summaryMessage: mockSummaryWithError,
        itemMessages: new Map([['item-1', mockItemWithError]]),
        paginationMessage: mockPaginationWithError,
      };

      await QueueRenderer.cleanup(result);

      expect(mockLogger.warn).toHaveBeenCalledTimes(3);
      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Failed to delete message during cleanup',
        expect.objectContaining({ error: 'Summary delete failed' })
      );
      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Failed to delete message during cleanup',
        expect.objectContaining({ error: 'Item delete failed' })
      );
      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Failed to delete message during cleanup',
        expect.objectContaining({ error: 'Pagination delete failed' })
      );
    });

    it('should handle non-Error objects during cleanup', async () => {
      const deleteError = { code: 10008, message: 'Unknown Message' };
      const failingDeleteFn = jest.fn<any>().mockRejectedValue(deleteError);
      const mockMsgWithError = createMockMessage('cleanup-object-error', failingDeleteFn);

      const result: QueueRenderResult = {
        summaryMessage: mockMsgWithError,
        itemMessages: new Map(),
        paginationMessage: null,
      };

      await QueueRenderer.cleanup(result);

      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Failed to delete message during cleanup',
        expect.objectContaining({
          error: '[object Object]',
        })
      );
    });
  });
});
