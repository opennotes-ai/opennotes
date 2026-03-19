const ENTITY_EMOJI = [
  "🦊", "🐙", "🦉", "🐺", "🦁", "🐯", "🦅", "🐬",
  "🦇", "🐝", "🦋", "🐢", "🦎", "🐸", "🦑", "🐧",
  "🦜", "🦈", "🐲", "🦔", "🐿️", "🦩", "🦚", "🐳", "🦦",
];

const BG_PALETTE = [
  "bg-amber-100", "bg-sky-100", "bg-emerald-100", "bg-violet-100",
  "bg-rose-100", "bg-slate-200", "bg-teal-100", "bg-indigo-100",
  "bg-orange-100", "bg-cyan-100",
];

export function getAgentAvatar(agentProfileId: string): { emoji: string; bgColor: string } {
  const lastSegment = agentProfileId.split("-").pop() ?? agentProfileId;
  const hash = parseInt(lastSegment.slice(0, 8), 16) || 0;

  const emoji = ENTITY_EMOJI[hash % ENTITY_EMOJI.length];
  const bgColor = BG_PALETTE[Math.floor(hash / ENTITY_EMOJI.length) % BG_PALETTE.length];

  return { emoji, bgColor };
}
