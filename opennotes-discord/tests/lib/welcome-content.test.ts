import { describe, it, expect } from '@jest/globals';
import { MessageFlags, ComponentType, Message } from 'discord.js';
import { buildWelcomeContainer, WELCOME_MESSAGE_REVISION, extractRevisionFromMessage } from '../../src/lib/welcome-content.js';
import { V2_COLORS } from '../../src/utils/v2-components.js';

describe('welcome-content', () => {
  describe('buildWelcomeContainer', () => {
    it('should return a ContainerBuilder', () => {
      const container = buildWelcomeContainer();

      expect(container).toBeDefined();
      expect(container.data).toBeDefined();
    });

    it('should use PRIMARY accent color', () => {
      const container = buildWelcomeContainer();

      expect(container.data.accent_color).toBe(V2_COLORS.PRIMARY);
    });

    it('should include About OpenNotes header', () => {
      const container = buildWelcomeContainer();

      const hasAboutHeader = container.components.some(
        (c: any) => c.data?.content?.includes('About OpenNotes')
      );
      expect(hasAboutHeader).toBe(true);
    });

    it('should include description of Open Notes', () => {
      const container = buildWelcomeContainer();

      const allTextContent = container.components
        .flatMap((c: any) => {
          if (c.data?.content) return [c.data.content];
          if (c.components) {
            return c.components.map((inner: any) => inner.data?.content || '');
          }
          return [];
        })
        .join(' ');

      expect(allTextContent).toContain('community moderation tool');
    });

    it('should include How It Works section', () => {
      const container = buildWelcomeContainer();

      const allTextContent = container.components
        .flatMap((c: any) => {
          if (c.data?.content) return [c.data.content];
          if (c.components) {
            return c.components.map((inner: any) => inner.data?.content || '');
          }
          return [];
        })
        .join(' ');

      expect(allTextContent).toContain('How It Works');
    });

    it('should include Note Submission section', () => {
      const container = buildWelcomeContainer();

      const allTextContent = container.components
        .flatMap((c: any) => {
          if (c.data?.content) return [c.data.content];
          if (c.components) {
            return c.components.map((inner: any) => inner.data?.content || '');
          }
          return [];
        })
        .join(' ');

      expect(allTextContent).toContain('Note Submission');
    });

    it('should include Commands section', () => {
      const container = buildWelcomeContainer();

      const allTextContent = container.components
        .flatMap((c: any) => {
          if (c.data?.content) return [c.data.content];
          if (c.components) {
            return c.components.map((inner: any) => inner.data?.content || '');
          }
          return [];
        })
        .join(' ');

      expect(allTextContent).toContain('Commands');
      expect(allTextContent).toContain('/note write');
      expect(allTextContent).toContain('/note request');
    });

    it('should include Scoring System section', () => {
      const container = buildWelcomeContainer();

      const allTextContent = container.components
        .flatMap((c: any) => {
          if (c.data?.content) return [c.data.content];
          if (c.components) {
            return c.components.map((inner: any) => inner.data?.content || '');
          }
          return [];
        })
        .join(' ');

      expect(allTextContent).toContain('Scoring System');
    });

    it('should include Community Moderation section', () => {
      const container = buildWelcomeContainer();

      const allTextContent = container.components
        .flatMap((c: any) => {
          if (c.data?.content) return [c.data.content];
          if (c.components) {
            return c.components.map((inner: any) => inner.data?.content || '');
          }
          return [];
        })
        .join(' ');

      expect(allTextContent).toContain('Community Moderation');
    });

    it('should include tagline at the bottom', () => {
      const container = buildWelcomeContainer();

      const allTextContent = container.components
        .flatMap((c: any) => {
          if (c.data?.content) return [c.data.content];
          if (c.components) {
            return c.components.map((inner: any) => inner.data?.content || '');
          }
          return [];
        })
        .join(' ');

      expect(allTextContent).toContain('Community-powered context');
    });

    it('should have separator components between sections', () => {
      const container = buildWelcomeContainer();

      const separatorCount = container.components.filter(
        (c: any) => c.data?.type === 14
      ).length;

      expect(separatorCount).toBeGreaterThanOrEqual(5);
    });

    it('should include revision text at the end', () => {
      const container = buildWelcomeContainer();
      const components = container.components;
      const lastComponent = components[components.length - 1] as any;

      expect(lastComponent.data?.content).toContain('Revision');
      expect(lastComponent.data?.content).toContain(WELCOME_MESSAGE_REVISION);
    });
  });

  describe('WELCOME_MESSAGE_REVISION', () => {
    it('should be in YYYY-MM-DD.N format', () => {
      expect(WELCOME_MESSAGE_REVISION).toMatch(/^\d{4}-\d{2}-\d{2}\.\d+$/);
    });

    it('should be exported', () => {
      expect(WELCOME_MESSAGE_REVISION).toBeDefined();
      expect(typeof WELCOME_MESSAGE_REVISION).toBe('string');
    });
  });

  describe('extractRevisionFromMessage', () => {
    function createMockMessage(revisionContent?: string): Message {
      const components = revisionContent
        ? [
            {
              type: ComponentType.Container,
              components: [
                {
                  toJSON: () => ({
                    type: ComponentType.TextDisplay,
                    content: 'Some other content',
                  }),
                },
                {
                  toJSON: () => ({
                    type: ComponentType.TextDisplay,
                    content: revisionContent,
                  }),
                },
              ],
            },
          ]
        : [];

      return { components } as unknown as Message;
    }

    it('should extract revision from message with valid revision', () => {
      const message = createMockMessage('-# Revision 2025-12-24.1');
      const revision = extractRevisionFromMessage(message);
      expect(revision).toBe('2025-12-24.1');
    });

    it('should return null for message without revision', () => {
      const message = createMockMessage('Some content without revision');
      const revision = extractRevisionFromMessage(message);
      expect(revision).toBeNull();
    });

    it('should return null for message without components', () => {
      const message = { components: [] } as unknown as Message;
      const revision = extractRevisionFromMessage(message);
      expect(revision).toBeNull();
    });

    it('should return null for message with null components', () => {
      const message = { components: null } as unknown as Message;
      const revision = extractRevisionFromMessage(message);
      expect(revision).toBeNull();
    });

    it('should handle different revision numbers', () => {
      const message = createMockMessage('-# Revision 2025-01-15.42');
      const revision = extractRevisionFromMessage(message);
      expect(revision).toBe('2025-01-15.42');
    });
  });
});
