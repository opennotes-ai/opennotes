# OpenNotes for Discourse -- User Guide

This guide explains how OpenNotes works from a community member's perspective.

## What OpenNotes Does

OpenNotes helps your community moderate content in two ways:

1. **AI moderation** catches clearly harmful content right away.
2. **Community review** lets members like you weigh in on moderation decisions, especially when the AI isn't sure or when you think it got something wrong.

No moderation decision is permanent. Every automated action can be reviewed and reversed by the community.

## What You'll See

### Posts Under Review

When the AI flags a post but isn't confident enough to act on it automatically, you'll see an "Under Review" banner on the post. The post stays visible while the community decides what to do.

### Auto-Hidden Posts

When the AI is highly confident content is harmful, it may hide the post immediately. You'll see a note explaining that the post was auto-hidden and is open for community review.

### Community Review Badges

After the community reaches a decision:
- **"Community Reviewed"** -- the community agreed the post needed action
- **"Reviewed -- No Action"** -- the community decided the post was fine

### Restored Posts

If a post was auto-hidden but the community voted to reverse that decision, you'll see a staff annotation explaining that the post was hidden and later restored.

## Participating in Reviews

### Who Can Vote

Your forum administrator sets the minimum trust level required to participate in community reviews. Typically, you need to be at least a **Member** (trust level 2). You earn trust levels through normal participation in the forum.

### The Review Page

Visit `/community-reviews` to see items waiting for community input. Each item shows:
- The flagged post and its context
- The category it was posted in
- Why it was flagged

### How Voting Works

For each item, you can vote:
- **Helpful** -- the moderation action (or proposed action) is appropriate
- **Not Helpful** -- the content is fine and shouldn't be acted on

You can only vote once per item.

### How Consensus Is Reached

OpenNotes uses a bridging-based algorithm adapted from Twitter/X Community Notes. This means:

- Votes from people who usually disagree with each other carry more weight than votes from people who always agree
- This makes it harder for any single group to dominate moderation decisions
- Consensus reflects genuine cross-perspective agreement, not just majority rule

Once enough votes are in and a clear consensus emerges, the agreed-upon action is applied (or the post is left alone).

### Scores and Tallies

While voting is in progress, you won't see the current vote count or score. This is intentional -- it prevents bandwagon effects and encourages independent judgment. Results become visible after consensus is reached.

## Frequently Asked Questions

**Can the AI make mistakes?**
Yes. That's why every automated decision goes through community review. If the community decides the AI was wrong, the action is reversed and the post is restored.

**What happens if I flag a post?**
Depending on your forum's configuration, flags may be sent to OpenNotes for community review (in addition to the normal staff flag queue). This means your flag could be reviewed by the community, not just staff.

**Can a restored post be flagged again?**
Posts that are restored after an overturn are marked as reviewed. Minor edits won't trigger re-classification. If the post is substantially rewritten, it may be classified again.

**Who can see my votes?**
Staff can see individual votes and tallies. Other community members see only the final consensus result, not individual votes.

**What if there aren't enough voters?**
Items stay in the review queue until enough votes are cast. Staff can also take action directly on any item without waiting for community consensus.
