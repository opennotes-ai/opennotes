# Feedback Bell Wireframe

## Overview

Per-card concierge-bell feedback affordance. Bell sits in the bottom-right corner of every relevant card. Hover (desktop) or tap (mobile) opens a popover with 3 icon buttons (thumbs up / thumbs down / message). Clicking any icon opens a Dialog (desktop) or Drawer (mobile) with email + message + 3-way type toggle + Send.

## Components

- `FeedbackBell` — concierge bell button rendered inside a card; owns popover state and `bell_location` prop
- `FeedbackPopover` — 3-icon popover (ThumbsUp / ThumbsDown / MessageSquare)
- `FeedbackForm` — shared form body (email, message, ToggleGroup, Send button)
- `FeedbackDialog` — desktop wrapper (`Dialog` + `DialogContent`) hosting `FeedbackForm`
- `FeedbackDrawer` — mobile wrapper (`Drawer` + `DrawerContent`) hosting `FeedbackForm`
- `FeedbackSurface` — `<Show when={isDesktop()} fallback={<FeedbackDrawer/>}><FeedbackDialog/></Show>` switch

## Mobile Layout (375px) — Bell on a Card

```
┌─────────────────────────────────────┐
│  Card title                         │
│  ─────────────────────────────      │
│  Some report content lorem ipsum    │
│  dolor sit amet consectetur adip-   │
│  iscing elit sed do eiusmod         │
│                                     │
│                            [🔔]     │  ← bell, 24×24, opacity 0.5 → 1 on hover/focus
└─────────────────────────────────────┘
```

## Mobile Layout — Popover Open (after tap)

```
┌─────────────────────────────────────┐
│  Card title                         │
│  ─────────────────────────────      │
│  Some report content lorem ipsum    │
│  dolor sit amet consectetur adip-   │
│  iscing elit sed do eiusmod         │
│                  ┌──────────────┐   │
│                  │ [👍][👎][💬] │   │  ← popover, 3×40 icon buttons
│                  └──────▽───────┘   │
│                            [🔔]     │
└─────────────────────────────────────┘
```

## Mobile Layout — Drawer Open (after icon tap)

```
┌─────────────────────────────────────┐
│  (page dimmed behind drawer)        │
├─────────────────────────────────────┤
│  ════                               │  ← drag handle
│  Send feedback                      │
│  ─────────────────                  │
│                                     │
│  [_____________________________]    │  ← email input (no "optional" label)
│                                     │
│  ┌─────────────────────────────┐    │
│  │ Message…                    │    │  ← textarea, autoexpand
│  │                             │    │
│  └─────────────────────────────┘    │
│                                     │
│  ( 👍 )  ( 👎 )  (●💬)              │  ← ToggleGroup, single-select, ●=active
│                                     │
│  [        Send         ]            │  ← disabled if type=message & len ≤ 4
│                                     │
│           [ Cancel ]                │
└─────────────────────────────────────┘
```

## Desktop Layout (1024px+) — Bell on a Card

```
┌────────────────────────────────────────────────────────────────┐
│  Card title                                                    │
│  ─────────────────────────────                                 │
│  Some report content lorem ipsum dolor sit amet consectetur    │
│  adipiscing elit sed do eiusmod tempor incididunt ut labore    │
│                                                                │
│                                                          [🔔]  │  ← bell, hover reveals popover
└────────────────────────────────────────────────────────────────┘
```

## Desktop Layout — Popover Open (on hover)

```
                                                       ┌──────────────┐
                                                       │ [👍][👎][💬] │
                                                       └──────▽───────┘
┌────────────────────────────────────────────────────────────────┐
│  Card title                                                    │
│  ...                                                           │
│                                                          [🔔]  │
└────────────────────────────────────────────────────────────────┘
```

Popover anchors above the bell with the arrow pointing down. `solid-ui` Popover handles repositioning if there's no space above.

## Desktop Layout — Dialog Open

```
                  ┌────────────────────────────────────────┐
                  │  Send feedback                    [✕]  │
                  │  ──────────────────                    │
                  │                                        │
                  │  [____________________________]        │  ← email
                  │                                        │
                  │  ┌──────────────────────────────┐      │
                  │  │ Message…                     │      │  ← textarea
                  │  │                              │      │
                  │  └──────────────────────────────┘      │
                  │                                        │
                  │  ( 👍 )  ( 👎 )  (●💬)                 │  ← ToggleGroup
                  │                                        │
                  │              [   Send   ]              │
                  └────────────────────────────────────────┘
```

Dialog: `sm:max-w-[425px]`, centered, modal overlay dims page.

## Interactions

### FeedbackBell
- Render: bottom-right of host card via `class="absolute right-2 bottom-2"`. Card must be `relative`.
- Visual: `Bell-concierge` 16px icon, `text-muted-foreground` opacity-50 → opacity-100 on hover/focus.
- Desktop hover: opens `FeedbackPopover` after 150ms hover delay (avoid noise on cursor pass-through).
- Desktop click: same as hover-open + locks open until user moves away or escapes.
- Mobile tap: opens `FeedbackPopover` (no hover, since touch).
- Aria: `aria-label="Send feedback about {bell_location}"`.

### FeedbackPopover
- 3 icon buttons in a row, 40×40, gap-2.
- Click any icon → close popover, open `FeedbackSurface` with `initialType` = clicked icon's type.
- Fires `POST /api/feedback` (open) with `{page_path, user_agent, referrer, bell_location, initial_type}`. uid is read server-side from cookie.
- Stores returned `id` in form state for use on Send. If POST fails, stores `null` and form falls back to combined POST on Send.

### FeedbackForm
- Email field: `type="email"`, no label saying "optional", placeholder `"name@example.com"` is enough.
- Message field: textarea, 3 rows default, auto-grow up to 8 rows.
- Toggle: solid-ui `ToggleGroup` (single-select), 3 options. Pre-selected from `initialType`.
- Send button: `disabled` when `type === "message" && message.trim().length <= 4`. Always enabled for thumbs up/down (message can be empty).
- On Send:
  - If `feedbackId` set → `PATCH /api/feedback/{id}` with `{email, message, final_type}`.
  - If `feedbackId` null (open POST failed) → `POST /api/feedback` with the combined shape (all fields).
- Success: surface closes, brief toast `"Thanks for the feedback!"`.
- Failure: inline error above Send `"Couldn't send — try again?"`, form contents preserved, Send re-enabled.

### Toggle change after open
- User clicked thumbs-up → opened with `initialType=thumbs_up`. They flip toggle to message → `final_type=message`. Server sees both `initial_type=thumbs_up` and `final_type=message` and that's the change-of-mind signal we want.

## Data Requirements

```ts
type FeedbackType = "thumbs_up" | "thumbs_down" | "message";

interface FeedbackBellProps {
  bell_location: string;       // stable id, e.g. "card:safety-recommendation"
  ariaContext?: string;        // human-readable context for aria-label
}

interface FeedbackOpenRequest {
  page_path: string;
  user_agent: string;
  referrer: string;
  bell_location: string;
  initial_type: FeedbackType;
}

interface FeedbackOpenResponse { id: string; }

interface FeedbackSubmitRequest {
  email: string | null;
  message: string | null;
  final_type: FeedbackType;
}

interface FeedbackCombinedRequest extends FeedbackOpenRequest, FeedbackSubmitRequest {}
```

## States

### Form — submitting
```
│  [        Sending...   ⏳ ]            │   (button disabled, spinner)
```

### Form — error
```
│  ⚠ Couldn't send — try again?         │
│  [        Send         ]              │   (re-enabled, fields preserved)
```

### Form — success
```
(Dialog/Drawer dismissed, toast appears top-right)
       ┌───────────────────────┐
       │ ✓ Thanks for feedback │
       └───────────────────────┘
```

### Bell — disabled / unavailable
Bell hides entirely if the feedback API is known-down (404 on a probe). Out of scope for v1; bell always renders.

## Accessibility Notes

- All icon-only buttons have `aria-label`s (Bell, ThumbsUp, ThumbsDown, MessageSquare, ToggleGroup items).
- Popover trap-focus on tap-open (mobile); does not trap on hover-open (desktop, dismisses on mouseleave).
- Esc closes popover or surface depending on what's open.
- Tab order: email → message → toggle (left→right) → Send → Cancel.
- ToggleGroup uses `aria-pressed` on each toggle; whole group has `aria-label="Feedback type"`.
- Color contrast: bell at opacity-50 must still meet 3:1 against card background; bump if needed.
