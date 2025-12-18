import { describe, it, expect } from '@jest/globals';
import { MessageFlags } from 'discord.js';
import { buildWelcomeContainer } from '../../src/lib/welcome-content.js';
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
  });
});
