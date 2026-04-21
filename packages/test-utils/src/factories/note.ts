import { Factory } from 'fishery';
import type { Note } from '../types.js';

export const noteFactory = Factory.define<Note>(({ sequence }) => ({
  id: `note-${sequence}`,
  messageId: `msg-${sequence}`,
  authorId: `user-${sequence}`,
  content: 'Test community note',
  createdAt: Date.now(),
  helpfulCount: 0,
  notHelpfulCount: 0,
}));
