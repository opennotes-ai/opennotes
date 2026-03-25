import { ButtonStyle, type APIButtonComponentWithCustomId } from 'discord.js';
import {
  NAV_GRAPH,
  HUB_ACTIONS,
  buildMenuButton,
  buildBackButton,
  buildFullMenuButton,
  buildContextualNav,
  buildNavHub,
  type NavAction,
} from '../../src/lib/navigation-components.js';

type ButtonJSON = APIButtonComponentWithCustomId;

function buttonJSON(builder: { toJSON(): unknown }): ButtonJSON {
  return builder.toJSON() as ButtonJSON;
}

function rowButtons(row: { toJSON(): { components: unknown[] } }): ButtonJSON[] {
  return row.toJSON().components as ButtonJSON[];
}

describe('navigation-components', () => {
  describe('buildMenuButton', () => {
    it('should create a button with nav:menu custom ID', () => {
      const json = buttonJSON(buildMenuButton());

      expect(json.custom_id).toBe('nav:menu');
      expect(json.label).toBe('Menu');
      expect(json.style).toBe(ButtonStyle.Secondary);
    });

    it('should have a book emoji', () => {
      const json = buttonJSON(buildMenuButton());

      expect(json.emoji).toBeDefined();
      expect(json.emoji!.name).toBe('\u{1F4D6}');
    });
  });

  describe('buildBackButton', () => {
    it('should create a button with nav:back custom ID', () => {
      const json = buttonJSON(buildBackButton());

      expect(json.custom_id).toBe('nav:back');
      expect(json.label).toBe('Back');
      expect(json.style).toBe(ButtonStyle.Secondary);
    });

    it('should have a left arrow emoji', () => {
      const json = buttonJSON(buildBackButton());

      expect(json.emoji).toBeDefined();
      expect(json.emoji!.name).toBe('\u25C0');
    });
  });

  describe('buildFullMenuButton', () => {
    it('should create a button with nav:hub custom ID', () => {
      const json = buttonJSON(buildFullMenuButton());

      expect(json.custom_id).toBe('nav:hub');
      expect(json.label).toBe('Full Menu');
      expect(json.style).toBe(ButtonStyle.Secondary);
    });

    it('should have a house emoji', () => {
      const json = buttonJSON(buildFullMenuButton());

      expect(json.emoji).toBeDefined();
      expect(json.emoji!.name).toBe('\u{1F3E0}');
    });
  });

  describe('NAV_GRAPH', () => {
    const expectedContexts = [
      'list:notes',
      'list:requests',
      'vibecheck:scan',
      'vibecheck:status',
      'vibecheck:create-requests',
      'note:write',
      'note:request',
      'note:view',
      'note:score',
      'note:rate',
      'clear:notes',
      'clear:requests',
      'config',
      'status-bot',
      'about-opennotes',
      'note-request-context',
    ];

    it('should have entries for all command contexts', () => {
      for (const context of expectedContexts) {
        expect(NAV_GRAPH[context]).toBeDefined();
        expect(Array.isArray(NAV_GRAPH[context])).toBe(true);
      }
    });

    it('should have at least one action per context', () => {
      for (const context of expectedContexts) {
        expect(NAV_GRAPH[context].length).toBeGreaterThanOrEqual(1);
      }
    });

    it('should have valid NavAction shape for all entries', () => {
      for (const [_context, actions] of Object.entries(NAV_GRAPH)) {
        for (const action of actions) {
          expect(action).toHaveProperty('label');
          expect(action).toHaveProperty('customId');
          expect(typeof action.label).toBe('string');
          expect(typeof action.customId).toBe('string');
          expect(action.customId).toMatch(/^nav:/);
        }
      }
    });

    it('should have custom IDs within 100 char limit', () => {
      for (const actions of Object.values(NAV_GRAPH)) {
        for (const action of actions) {
          expect(action.customId.length).toBeLessThanOrEqual(100);
        }
      }
    });

    it('should not have duplicate custom IDs within a single context', () => {
      for (const [_context, actions] of Object.entries(NAV_GRAPH)) {
        const ids = actions.map(a => a.customId);
        expect(new Set(ids).size).toBe(ids.length);
      }
    });
  });

  describe('buildContextualNav', () => {
    it('should include a menu button as first component', () => {
      const buttons = rowButtons(buildContextualNav('list:notes'));

      expect(buttons[0].custom_id).toBe('nav:menu');
    });

    it('should include nav graph actions for the given context', () => {
      const buttons = rowButtons(buildContextualNav('list:notes'));
      const actions = NAV_GRAPH['list:notes'];

      expect(buttons.length).toBe(1 + actions.length);

      for (let i = 0; i < actions.length; i++) {
        expect(buttons[i + 1].custom_id).toBe(actions[i].customId);
        expect(buttons[i + 1].label).toBe(actions[i].label);
      }
    });

    it('should use Secondary style for all buttons', () => {
      const buttons = rowButtons(buildContextualNav('note:view'));

      for (const button of buttons) {
        expect(button.style).toBe(ButtonStyle.Secondary);
      }
    });

    it('should set emoji on action buttons when provided', () => {
      const buttons = rowButtons(buildContextualNav('list:notes'));

      for (let i = 1; i < buttons.length; i++) {
        expect(buttons[i].emoji).toBeDefined();
      }
    });

    it('should return row with only menu button for unknown context', () => {
      const buttons = rowButtons(buildContextualNav('unknown:context'));

      expect(buttons).toHaveLength(1);
      expect(buttons[0].custom_id).toBe('nav:menu');
    });
  });

  describe('HUB_ACTIONS', () => {
    it('should contain 6 hub actions', () => {
      expect(HUB_ACTIONS).toHaveLength(6);
    });

    it('should have valid NavAction shape for all entries', () => {
      for (const action of HUB_ACTIONS) {
        expect(action).toHaveProperty('label');
        expect(action).toHaveProperty('customId');
        expect(action.customId).toMatch(/^nav:/);
      }
    });

    it('should include core navigation destinations', () => {
      const labels = HUB_ACTIONS.map(a => a.label);
      expect(labels).toContain('List Notes');
      expect(labels).toContain('List Requests');
      expect(labels).toContain('Write Note');
      expect(labels).toContain('Status');
      expect(labels).toContain('About');
    });
  });

  describe('buildNavHub', () => {
    it('should return action rows with buttons', () => {
      const rows = buildNavHub();

      expect(rows.length).toBeGreaterThanOrEqual(1);
      for (const row of rows) {
        const buttons = rowButtons(row);
        expect(buttons.length).toBeGreaterThanOrEqual(1);
        expect(buttons.length).toBeLessThanOrEqual(5);
      }
    });

    it('should use Primary style for hub buttons', () => {
      const rows = buildNavHub();

      for (const row of rows) {
        const buttons = rowButtons(row);
        for (const button of buttons) {
          expect(button.style).toBe(ButtonStyle.Primary);
        }
      }
    });

    it('should include all hub actions across rows', () => {
      const rows = buildNavHub();
      const allButtons = rows.flatMap(
        (r): ButtonJSON[] => rowButtons(r),
      );

      expect(allButtons).toHaveLength(HUB_ACTIONS.length);
      for (const action of HUB_ACTIONS) {
        const found = allButtons.find(
          (b: ButtonJSON) => b.custom_id === action.customId,
        );
        expect(found).toBeDefined();
        expect(found!.label).toBe(action.label);
      }
    });

    it('should split into multiple rows when exceeding 5 buttons per row', () => {
      const rows = buildNavHub();

      expect(rows.length).toBe(2);
      expect(rowButtons(rows[0])).toHaveLength(5);
      expect(rowButtons(rows[1])).toHaveLength(1);
    });

    it('should set emoji on hub buttons', () => {
      const rows = buildNavHub();
      const allButtons = rows.flatMap(
        (r): ButtonJSON[] => rowButtons(r),
      );

      for (const button of allButtons) {
        expect(button.emoji).toBeDefined();
      }
    });
  });
});
