import { Factory } from 'fishery';
import type { Rating } from '../types.js';

export const ratingFactory = Factory.define<Rating>(({ sequence }) => ({
  noteId: `note-${sequence}`,
  userId: `user-${sequence}`,
  helpful: true,
  createdAt: Date.now(),
}));
