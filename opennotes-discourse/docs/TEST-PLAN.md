# OpenNotes Discourse Plugin — Test Plan

## 1. Overview

This test plan covers all 14 MVP v1 features from the spec (section 12). Tests run against a **real opennotes-server** with both Docker stacks (Discourse + OpenNotes) running simultaneously.

**Two test modes:**
- **Automated specs** (`.spec.ts`) — Playwright test suite for regression/CI
- **Interactive verification checklist** — Playwright skill sessions for visual/UX, exploratory testing

**Test data:** Server-side state seeded via SQL/Alembic fixtures. Discourse-side state seeded via existing `seed.sh` script.

## 2. Test Environment

### Prerequisites

| Component | How to Start | URL |
|---|---|---|
| Discourse + plugin | `mise run discourse:up` | http://localhost:4200 |
| OpenNotes server | `mise run dev` (or `docker compose up`) | http://localhost:8000 |
| PostgreSQL (OpenNotes) | Included in docker compose | localhost:5432 |
| Redis | Included in docker compose | localhost:6379 |

### Test Data Requirements

#### Discourse-Side (via `seed.sh`)

| Entity | Details |
|---|---|
| **Admin** | admin@opennotes.local / opennotes-dev-password (TL4) |
| **Reviewer 1** | reviewer1@test.local / password-for-testing (TL2) |
| **Reviewer 2** | reviewer2@test.local / password-for-testing (TL2) |
| **New User** | newuser@test.local / password-for-testing (TL0) |
| **TL1 User** | basic@test.local / password-for-testing (TL1) — *new, to be added* |
| **TL3 User** | trusted@test.local / password-for-testing (TL3) — *new, to be added* |
| **Categories** | General Discussion, Announcements, Off Topic |
| **Plugin settings** | opennotes_enabled: true, server_url: http://host.docker.internal:8000 |

#### Server-Side (via SQL fixtures)

| Entity | Details |
|---|---|
| **Community Server** | platform: "discourse", platform_community_server_id: "localhost:4200" |
| **API Key** | Service account key for plugin authentication |
| **Monitored Channels** | General Discussion, Announcements mapped to community server |
| **Per-Category Config** | General Discussion: auto_action_min_score=0.90, review_group=community; Announcements: auto_action_min_score=0.80, review_group=staff |
| **Sample Requests** | 3 requests in various states (PENDING, IN_PROGRESS, COMPLETED) |
| **Sample Notes** | Notes with different statuses (NEEDS_MORE_RATINGS, CURRENTLY_RATED_HELPFUL, CURRENTLY_RATED_NOT_HELPFUL) |
| **Sample ModerationActions** | Actions in various states (proposed, applied, retro_review, confirmed, overturned) |
| **User Profiles** | Mapped to Discourse users with provider_scope="localhost:4200" |

### Test Execution Order

Tests are organized in dependency order. **Bootstrap suite runs first** to set up the community server and sync state. Remaining suites rely primarily on **SQL fixture data** seeded before tests, not on state from prior suites. Where a test depends on prior suite state, the preconditions column says so explicitly.

```
1. bootstrap.spec.ts       — Plugin setup, community server registration (MUST run first)
2. identity.spec.ts        — User identity mapping, trust level sync (uses fixtures)
3. classification.spec.ts  — Post scanning, two-tier routing (uses fixtures)
4. review.spec.ts          — Community review queue, voting, flag routing (uses fixtures)
5. consensus.spec.ts       — Consensus actions, webhook handling (uses fixtures)
6. moderation.spec.ts      — Tier 1 auto-action, retroactive review, overturn (uses fixtures)
7. staff.spec.ts           — Staff overrides, review queue actions (uses fixtures)
8. admin.spec.ts           — Settings, dashboard, per-category config (independent)
9. error.spec.ts           — Degraded mode, server down, webhook failures (independent)
```

---

## 3. Automated Test Specs

### 3.1 Bootstrap & Provisioning (`bootstrap.spec.ts`)

**Feature:** Bootstrap/provisioning

| # | Test Case | Preconditions | Steps | Expected |
|---|---|---|---|---|
| B1 | Plugin registers community server on setup | Server running, plugin enabled | 1. Enable plugin in admin settings<br>2. Enter server URL and API key<br>3. Save settings | Server has CommunityServer record with platform="discourse" |
| B2 | Plugin registers webhook on setup | B1 complete | 1. Check server webhook registrations | Webhook registered with correct callback URL and HMAC secret |
| B3 | Monitored categories sync | B1 complete | 1. Set opennotes_monitored_categories to ["General Discussion", "Announcements"]<br>2. Save settings | Server has 2 monitored channels for this community |
| B4 | Category sync on change | B3 complete | 1. Add a third category to monitored list<br>2. Save | Server has 3 monitored channels (note: test adds, not removes, to preserve state for later suites) |
| B5 | Settings sync to community config | B1 complete | 1. Set opennotes_staff_approval_required=true<br>2. Set opennotes_auto_hide_on_consensus=true<br>3. Save | Server community config reflects both settings |
| B6 | reviewer_min_trust_level setting enforced | B1 complete | 1. Set opennotes_reviewer_min_trust_level=3<br>2. Login as TL2 user<br>3. Navigate to /community-reviews | Vote widget not visible (TL2 < TL3 threshold) |
| B7 | route_flags_to_community setting | B1 complete | 1. Set opennotes_route_flags_to_community=true<br>2. Flag a post | Flag routed to OpenNotes as a request (not just Discourse native flag queue) |

### 3.2 Identity Mapping (`identity.spec.ts`)

**Feature:** Identity mapping

| # | Test Case | Preconditions | Steps | Expected |
|---|---|---|---|---|
| I1 | First-time user creates profile on interaction | Server running, user has no profile | 1. Login as reviewer1<br>2. Navigate to community reviews<br>3. Vote on a note | Server creates UserProfile + UserIdentity with provider="discourse", provider_scope="localhost:4200" |
| I2 | Returning user uses cached identity | I1 complete | 1. Login as reviewer1<br>2. Vote on another note | No new profile created, existing profile used |
| I3 | Trust level stored as profile metadata | I1 complete | 1. Check server profile for reviewer1 | Profile metadata includes trust_level=2 |
| I4 | TL0 user cannot vote | Server running | 1. Login as newuser (TL0)<br>2. Navigate to community reviews | Vote widget not visible or disabled |
| I4b | TL1 user cannot vote | Server running, TL1 user exists | 1. Login as TL1 user<br>2. Navigate to community reviews | Vote widget not visible or disabled |
| I5 | Admin action triggers elevated verification | Server running | 1. Login as admin<br>2. Force-publish a note | Server re-verifies admin status against Discourse API |

### 3.3 Post Classification (`classification.spec.ts`)

**Feature:** Post scanning, two-tier action model

| # | Test Case | Preconditions | Steps | Expected |
|---|---|---|---|---|
| C1 | New post triggers classification | Monitored category exists | 1. Login as reviewer1<br>2. Create post in General Discussion | Server receives request via SyncPostToOpennotes job |
| C2 | Edited post triggers re-classification | C1 complete | 1. Edit the post from C1 | Server receives updated request |
| C3 | Post in non-monitored category not scanned | Off Topic not monitored | 1. Create post in Off Topic | No request created on server |
| C4 | Tier 2: low-confidence creates review item | Classification below auto-action threshold | 1. Create post that triggers low-confidence flag | ReviewableOpennotesItem created, post stays visible, "Under Review" banner shown |
| C5 | Tier 1: high-confidence triggers immediate hide | Classification above auto-action threshold | 1. Create post that triggers high-confidence flag | Post auto-hidden, ModerationAction created (state: applied), retroactive note created |
| C6 | Classification labels visible to staff | C4 or C5 | 1. Login as admin<br>2. View the flagged post in /review | Classification labels and scores visible |

### 3.4 Community Review Queue (`review.spec.ts`)

**Feature:** Community review queue UI, voting

| # | Test Case | Preconditions | Steps | Expected |
|---|---|---|---|---|
| R1 | Community review page shows pending items | Pending requests exist | 1. Login as reviewer1<br>2. Navigate to /community-reviews | Pending review items displayed with post content, context, category |
| R2 | User can vote "Helpful" on a note | R1 visible | 1. Click "Helpful" on a note | Rating created on server, vote count updated |
| R3 | User can vote "Not Helpful" on a note | R1 visible | 1. Click "Not Helpful" on a note | Rating created on server |
| R4 | User cannot vote twice on same note | R2 complete | 1. Try to vote again on the same note | Vote rejected or widget disabled |
| R5 | Review group filters items | Per-category review groups configured | 1. Login as reviewer1 (TL2)<br>2. Check items from staff-only category | Staff-only items not visible to TL2 user |
| R6 | TL3 user sees trusted items | Trusted review group items exist | 1. Login as trusted (TL3)<br>2. Navigate to /community-reviews | Sees items from both community and trusted groups |
| R7 | Scores hidden until consensus | Pending items | 1. Login as reviewer1<br>2. View a pending item | Score/tally not shown until consensus reached |
| R8 | Default review group catches all to staff | No label routing configured for category | 1. Login as reviewer1 (TL2)<br>2. Check items from unconfigured category | Items not visible to TL2 (default: staff-only) |
| R9 | Flag creates server request | route_flags_to_community=true | 1. Login as reviewer1<br>2. Flag a post<br>3. Check server | Request created on server from flag_created event |
| R10 | Staff sees rating tallies in /review | Items with ratings | 1. Login as admin<br>2. View item in /review | Current rating tallies and individual notes with ratings visible |

### 3.5 Consensus & Action (`consensus.spec.ts`)

**Feature:** Consensus -> action, outbound webhooks

| # | Test Case | Preconditions | Steps | Expected |
|---|---|---|---|---|
| A1 | Consensus "helpful" hides post | Note with enough ratings trending helpful | 1. Submit final rating that triggers consensus<br>2. Wait for webhook delivery | Post hidden, "Community Reviewed" badge shown, ModerationAction state: applied |
| A2 | Consensus "not helpful" upholds post | Note with enough ratings trending not helpful | 1. Submit final rating<br>2. Wait for webhook | Post stays visible, "Reviewed -- No Action" badge shown |
| A3 | Webhook triggers Discourse action | Server sends webhook | 1. Trigger scoring on server<br>2. Observe Discourse state | ReviewableOpennotesItem updated, post action executed |
| A4 | Polling fallback catches missed webhook | Webhook delivery blocked | 1. Block webhook delivery<br>2. Wait for polling cycle (5 min or trigger manually) | Plugin catches up, applies correct action |
| A5 | Webhook with invalid HMAC signature rejected | Webhook endpoint reachable | 1. Send webhook with wrong HMAC signature | Plugin rejects webhook, returns 401 |
| A6 | Stale polling is no-op after webhook | Webhook already processed | 1. Process consensus via webhook<br>2. Trigger manual polling cycle | Polling detects state already updated, takes no action |

### 3.6 Moderation Actions (`moderation.spec.ts`)

**Feature:** Two-tier model, retroactive review, review groups

| # | Test Case | Preconditions | Steps | Expected |
|---|---|---|---|---|
| M1 | Tier 1 auto-hide creates full artifact set | High-confidence post | 1. Create post triggering Tier 1 | ModerationAction (applied) + Request + retroactive Note created atomically |
| M2 | Retroactive review note visible | M1 complete | 1. Login as reviewer in correct review group<br>2. Navigate to /community-reviews | Retroactive note visible: "This post was auto-hidden for [reason]" |
| M3 | Retroactive consensus confirms action | M2 visible | 1. Multiple reviewers vote "Helpful" (action was correct) | ModerationAction state: confirmed, post stays hidden |
| M4 | Retroactive consensus overturns action | Auto-hidden post | 1. Multiple reviewers vote "Not Helpful" (action was wrong) | Post unhidden, ModerationAction state: overturned, scan_exempt=true, staff annotation added |
| M5 | Overturned post has scan-exempt flag | M4 complete | 1. Edit the overturned post (minor edit) | Post not re-scanned (cosine similarity short-circuit) |
| M6 | Substantial edit clears scan-exempt | M4 complete | 1. Substantially edit the overturned post | scan_exempt cleared, full re-classification runs |
| M7 | Staff can remove scan-exempt manually | M4 complete | 1. Login as admin<br>2. Remove scan_exempt flag on post | Flag removed, next edit triggers normal classification |
| M8 | Classifier evidence stored for audit | M1 complete | 1. Query ModerationAction on server | classifier_evidence JSONB has labels, scores, threshold, model_version, category_config_snapshot |

### 3.7 Staff Overrides (`staff.spec.ts`)

**Feature:** Staff override

| # | Test Case | Preconditions | Steps | Expected |
|---|---|---|---|---|
| S1 | Staff force-publish (agree/hide) | Pending review item | 1. Login as admin<br>2. Go to /review<br>3. Click "Agree" on item | Note force-published, post hidden, server updated |
| S2 | Staff dismiss (disagree/uphold) | Pending review item | 1. Login as admin<br>2. Click "Disagree" on item | Note dismissed, post upheld |
| S3 | Staff ignore/dismiss item | Pending item | 1. Click "Ignore" on item | Item removed from queue, request deleted on server |
| S4 | Staff escalate item | Under community review | 1. Click "Escalate" | Item removed from community review, escalated flag set on server |
| S5 | Staff overturn auto-action | Tier 1 auto-hidden post | 1. Login as admin<br>2. Overturn the auto-hide in /review | Post unhidden, ModerationAction state: overturned |

### 3.8 Admin Settings & Dashboard (`admin.spec.ts`)

**Feature:** Admin settings, admin dashboard, per-category config

| # | Test Case | Preconditions | Steps | Expected |
|---|---|---|---|---|
| D1 | Admin can view all plugin settings | Plugin enabled | 1. Login as admin<br>2. Go to plugin settings | All opennotes_* settings visible with correct defaults |
| D2 | Per-category threshold config | Multiple categories | 1. Configure auto_action_min_score=0.80 for Announcements<br>2. Save | Server community config updated for that category |
| D3 | Per-category review group routing | Multiple categories | 1. Configure label_routing for General Discussion<br>2. Save | Server stores label-to-review-group mapping |
| D4 | Dashboard shows scoring analysis | Scoring data exists on server | 1. Go to admin dashboard | Activity metrics, classification breakdown, consensus health displayed |
| D5 | Dashboard shows top reviewers | Rating data exists | 1. Go to admin dashboard | Top reviewers section populated |
| D6 | Enable/disable plugin | Plugin running | 1. Toggle opennotes_enabled off<br>2. Create a post | No classification triggered |

### 3.9 Error & Degradation (`error.spec.ts`)

**Feature:** Error scenarios

| # | Test Case | Preconditions | Steps | Expected |
|---|---|---|---|---|
| E1 | Server unreachable: posts still publish | Server stopped | 1. Stop opennotes-server<br>2. Create a post in monitored category | Post publishes normally, no error shown to user, Sidekiq job retries |
| E2 | Server unreachable: review queue shows error | Server stopped | 1. Navigate to /community-reviews | Friendly error message: "OpenNotes server is temporarily unavailable" |
| E3 | Invalid API key | Wrong key configured | 1. Set bad API key in admin settings<br>2. Create a post | Classification fails gracefully, admin alerted |
| E4 | Webhook delivery failure + polling recovery | Webhook endpoint blocked | 1. Block webhook delivery<br>2. Trigger consensus on server<br>3. Wait for polling cycle | Plugin eventually picks up the consensus result |
| E5 | Duplicate webhook delivery | Same webhook sent twice | 1. Deliver same webhook event twice | Action only applied once (idempotent) |
| E6 | Server returns 429 (rate limited) | Rate limit triggered | 1. Trigger many API calls quickly | Plugin respects Retry-After, retries appropriately |
| E7 | Plugin restart recovers from missed webhooks | Webhooks dead-lettered during downtime | 1. Stop Discourse container<br>2. Trigger consensus on server (webhooks dead-letter)<br>3. Restart Discourse | Polling on restart catches up and applies missed actions |
| E8 | Stale polling after webhook already processed | Webhook delivered, then poll runs | 1. Deliver webhook<br>2. Trigger polling cycle | No duplicate action — poll detects Reviewable already updated |

---

## 4. Interactive Verification Checklist (Playwright Skill)

These items are verified via live Playwright skill sessions during implementation. They focus on visual/UX aspects that automated tests can't fully cover.

### 4.1 UI & Visual

- [ ] "Under Review" banner renders correctly on flagged posts
- [ ] "Community Reviewed" badge appears after consensus
- [ ] "Reviewed -- No Action" badge appears when post upheld
- [ ] Vote widget shows Helpful / Somewhat Helpful / Not Helpful options
- [ ] Vote widget is disabled/hidden for TL0/TL1 users
- [ ] Review queue page layout: post content, context, category, reason flagged
- [ ] Staff annotation ("this post was hidden but restored") renders correctly
- [ ] Admin dashboard charts render with real data
- [ ] Per-category settings UI is intuitive (label routing, thresholds)
- [ ] Plugin settings page shows all opennotes_* settings with descriptions

### 4.2 Flows

- [ ] Full Tier 1 flow: create post → auto-hidden → retroactive review → overturn → post restored
- [ ] Full Tier 2 flow: create post → classified → community reviews → consensus → action applied
- [ ] Staff override flow: review queue → force-publish → post hidden
- [ ] Bootstrap flow: fresh plugin install → configure → community server registered → categories synced
- [ ] Identity flow: new user → first vote → profile created → subsequent votes use cached identity

### 4.3 Edge Cases

- [ ] Rapid multiple votes from different users
- [ ] Post edited while under review
- [ ] Multiple classification labels on same post (most restrictive review group applied)
- [ ] Admin changes review group while votes are in progress
- [ ] Server comes back online after being down — queued jobs process correctly

---

## 5. Test Infrastructure

### 5.1 New Files Needed

```
opennotes-discourse/
  tests/
    e2e/
      specs/
        smoke.spec.ts          # Existing
        bootstrap.spec.ts      # New
        identity.spec.ts       # New
        classification.spec.ts # New
        review.spec.ts         # New
        consensus.spec.ts      # New
        moderation.spec.ts     # New
        staff.spec.ts          # New
        admin.spec.ts          # New
        error.spec.ts          # New
      fixtures/
        users.ts               # Existing — add TL3 user
        server-seed.sql        # New — server-side test data
      helpers/
        (existing page objects) # May need extension for new UI elements
        opennotes-api.ts       # New — helper to call opennotes-server API for setup/assertions
```

### 5.2 New Page Objects Needed

| Page Object | Purpose | Key Methods |
|---|---|---|
| `CommunityReviewPage` | Community review queue UI | `getReviewItems()`, `voteHelpful(noteId)`, `voteNotHelpful(noteId)`, `isVoteWidgetVisible()` |
| `ModerationBannerPage` | Post-level banners/badges | `getReviewBanner()`, `getConsensusBadge()`, `getStaffAnnotation()` |
| `SettingsPage` (extend AdminPage) | Per-category config UI | `setCategoryThreshold(category, score)`, `setLabelRouting(category, routing)` |
| `DashboardPage` | Admin dashboard | `getActivityMetrics()`, `getScoringHealth()`, `getTopReviewers()` |

### 5.3 Server API Helper

```typescript
class OpenNotesAPI {
  constructor(private baseUrl: string, private apiKey: string) {}

  async getRequests(filters?: Record<string, string>): Promise<Request[]>
  async getNotes(requestId: string): Promise<Note[]>
  async getRatings(noteId: string): Promise<Rating[]>
  async getModerationAction(actionId: string): Promise<ModerationAction>
  async getCommunityServer(): Promise<CommunityServer>
  async getMonitoredChannels(): Promise<MonitoredChannel[]>
  async triggerScoring(communityServerId: string): Promise<void>
}
```

### 5.4 Mise Tasks

```
mise run discourse:test:e2e              # Run all automated specs
mise run discourse:test:e2e:headed       # Run with visible browser
mise run discourse:test:e2e:report       # Generate HTML report
mise run discourse:test:seed:server      # Seed server-side test data
mise run discourse:test:reset            # Reset all test data
```
