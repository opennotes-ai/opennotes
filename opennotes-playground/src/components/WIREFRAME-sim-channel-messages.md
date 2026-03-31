# SIM Channel Messages Wireframe

## Overview

Discord-styled chat message feed for the SIM channel of a simulation. Renders as a new section on the simulation detail page. Messages ordered oldest-to-newest in a fixed-height scrollable frame. Cursor-based "Load more" at the top.

## Components

- Section header: "SIM Channel" title
- Message container: Fixed-height scrollable div, auto-scrolled to bottom on initial load
- Load more button: Appears at top of container when older messages exist
- Message row: Emoji avatar + agent name + timestamp + message text
- Empty state: Placeholder when no messages

## Mobile Layout (375px)

```
┌─────────────────────────────────────┐
│  SIM Channel                        │
├─────────────────────────────────────┤
│ ┌─────────────────────────────────┐ │
│ │                                 │ │
│ │    [ Load more messages ]       │ │
│ │                                 │ │
│ │ ┌───┐ AgentName    12:04 PM    │ │
│ │ │🦊 │ Message text here that   │ │
│ │ └───┘ can wrap to multiple      │ │
│ │       lines on mobile           │ │
│ │                                 │ │
│ │ ┌───┐ AnotherAgent  12:05 PM   │ │
│ │ │🐙 │ A shorter message        │ │
│ │ └───┘                           │ │
│ │                                 │ │
│ │ ┌───┐ AgentName    12:06 PM    │ │
│ │ │🦊 │ Same agent, new message  │ │
│ │ └───┘                           │ │
│ │                                 │ │
│ └─────────────────────────────────┘ │
│           ↑ fixed height, scrolls   │
└─────────────────────────────────────┘
```

## Desktop Layout (1024px+)

```
┌──────────────────────────────────────────────────────────────────┐
│  SIM Channel                                                     │
├──────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │                                                              │ │
│ │                  [ Load more messages ]                      │ │
│ │                                                              │ │
│ │ ┌────┐                                                       │ │
│ │ │ 🦊 │  SkepticalAnalyst                        12:04 PM    │ │
│ │ │ bg │  I've found an interesting pattern in the claims      │ │
│ │ └────┘  about economic data. Cross-referencing with the      │ │
│ │         original sources now.                                │ │
│ │                                                              │ │
│ │ ┌────┐                                                       │ │
│ │ │ 🐙 │  ContextMapper                           12:05 PM    │ │
│ │ │ bg │  Agreed, I noticed the same. The GDP figures don't    │ │
│ │ └────┘  match the cited report.                              │ │
│ │                                                              │ │
│ │ ┌────┐                                                       │ │
│ │ │ 🔬 │  EvidenceHunter                          12:06 PM    │ │
│ │ │ bg │  Pulling the primary source now to verify.            │ │
│ │ └────┘                                                       │ │
│ │                                                              │ │
│ │ ┌────┐                                                       │ │
│ │ │ 🦊 │  SkepticalAnalyst                        12:07 PM    │ │
│ │ │ bg │  Update: confirmed the discrepancy. Flagging this     │ │
│ │ └────┘  claim as potentially misleading.                     │ │
│ │                                                              │ │
│ └──────────────────────────────────────────────────────────────┘ │
│                      ↑ 400px fixed height, overflow-y: auto      │
└──────────────────────────────────────────────────────────────────┘
```

## Message Row Detail

```
┌────┐
│ 🦊 │  AgentName                                    HH:MM AM/PM
│ bg │  Message text content that may span multiple lines. Long
└────┘  messages wrap naturally within the available width.

 ↑        ↑                                              ↑
avatar   name (font-semibold)                    timestamp (muted)
32x32    text-sm                                 text-xs
rounded  text-foreground                         text-muted-foreground
```

Avatar: 32x32 rounded square with emoji centered on colored background.
- Emoji: hashed from last segment of SimAgent.id into curated entity emoji table
- Background color: independently hashed into palette of 8-10 muted tones

## States

### Loading

```
┌──────────────────────────────────────┐
│  SIM Channel                         │
├──────────────────────────────────────┤
│ ┌──────────────────────────────────┐ │
│ │                                  │ │
│ │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │ │
│ │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │ │
│ │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │ │
│ │        (Skeleton pulses)         │ │
│ │                                  │ │
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```

### Empty

```
┌──────────────────────────────────────┐
│  SIM Channel                         │
├──────────────────────────────────────┤
│ ┌──────────────────────────────────┐ │
│ │                                  │ │
│ │                                  │ │
│ │       No messages yet.           │ │
│ │                                  │ │
│ │                                  │ │
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```

### Load More Loading

```
┌──────────────────────────────────────┐
│ ┌──────────────────────────────────┐ │
│ │                                  │ │
│ │      [ Loading...  ]             │ │
│ │       (button disabled)          │ │
│ │                                  │ │
│ │  existing messages below...      │ │
```

## Interactions

### Initial Load
- Fetch last 20 messages (cursor-based, no `before` param = latest)
- Auto-scroll container to bottom (most recent message visible)
- If fewer than 20 messages returned, no "Load more" button

### Scroll to Top
- "Load more" button visible at top of scroll container
- Button text: "Load more messages"

### Load More Click
- Send request with `before=<oldest_message_id>` to fetch previous 20
- Button shows "Loading..." in disabled state during fetch
- Prepend older messages to top of list
- Preserve scroll position (user stays at same visual position, not jumped to top)
- If response returns fewer than 20 messages, hide "Load more" (no more history)

### Scroll Behavior
- Container has `overflow-y: auto` with fixed height (~400px desktop, ~300px mobile)
- No infinite scroll trigger — only explicit "Load more" button

## Data Requirements

### API Response (JSON:API)

```
GET /api/v2/simulations/{simulation_id}/channel-messages?page[size]=20&before=<uuid>

{
  data: [{
    type: "sim-channel-messages",
    id: "<uuid>",
    attributes: {
      message_text: string,
      agent_name: string,
      agent_profile_id: string,  // for avatar hashing
      created_at: string (ISO 8601)
    }
  }],
  meta: { count: number, has_more: boolean }
}
```

### Component Props

```typescript
interface SimChannelMessagesProps {
  simulationId: string;
}
```

### Avatar Utility

```typescript
function getAgentAvatar(agentProfileId: string): { emoji: string; bgColor: string }
// Pure function, deterministic from ID
```

## Accessibility Notes

- Container has `role="log"` and `aria-label="SIM channel messages"`
- Load more button has `aria-label="Load older messages"`
- Messages use semantic time element for timestamps
- Keyboard: Tab reaches "Load more" button, Enter activates it
