-- E2E Test Data Seed for OpenNotes Server
-- Idempotent: uses INSERT ... ON CONFLICT DO NOTHING
-- Assumes discourse-dev-1 community server already exists.

-- Fixed UUIDs for deterministic test data (UUIDs generated offline in v7 format)
-- Community server: 019d473a-0b2e-795b-b6a1-4919403313b8 (already exists)

-- ============================================================
-- 1. User profiles for Discourse test users
-- ============================================================

INSERT INTO user_profiles (id, display_name, role, is_active, is_human, reputation, created_at, updated_at)
VALUES
  ('01910000-0001-7000-8000-000000000001', 'admin', 'admin', true, true, 100, NOW(), NOW()),
  ('01910000-0001-7000-8000-000000000002', 'reviewer1', 'user', true, true, 50, NOW(), NOW()),
  ('01910000-0001-7000-8000-000000000003', 'reviewer2', 'user', true, true, 50, NOW(), NOW()),
  ('01910000-0001-7000-8000-000000000004', 'newuser', 'user', true, true, 0, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- 2. Community server membership for test users
-- ============================================================

INSERT INTO community_members (id, community_id, profile_id, role, joined_at, created_at, updated_at)
VALUES
  ('01910000-0008-7000-8000-000000000001', '019d473a-0b2e-795b-b6a1-4919403313b8', '01910000-0001-7000-8000-000000000001', 'admin', NOW(), NOW(), NOW()),
  ('01910000-0008-7000-8000-000000000002', '019d473a-0b2e-795b-b6a1-4919403313b8', '01910000-0001-7000-8000-000000000002', 'member', NOW(), NOW(), NOW()),
  ('01910000-0008-7000-8000-000000000003', '019d473a-0b2e-795b-b6a1-4919403313b8', '01910000-0001-7000-8000-000000000003', 'member', NOW(), NOW(), NOW()),
  ('01910000-0008-7000-8000-000000000004', '019d473a-0b2e-795b-b6a1-4919403313b8', '01910000-0001-7000-8000-000000000004', 'member', NOW(), NOW(), NOW())
ON CONFLICT (community_id, profile_id) DO NOTHING;

-- ============================================================
-- 3. Monitored channels (General discussion, slug=general)
-- ============================================================

INSERT INTO monitored_channels (id, channel_id, name, community_server_id, enabled, similarity_threshold, created_at, updated_at)
VALUES
  ('01910000-0002-7000-8000-000000000001', 'general-4', 'general', '019d473a-0b2e-795b-b6a1-4919403313b8', true, 0.75, NOW(), NOW())
ON CONFLICT (channel_id) DO NOTHING;

-- ============================================================
-- 4. Message archives for test requests
-- ============================================================

INSERT INTO message_archive (id, content_type, content_text, platform_message_id, platform_channel_id, platform_author_id, created_at)
VALUES
  ('01910000-0003-7000-8000-000000000001', 'text', 'Test message content for pending request', 'msg-001', 'general-4', 'user-100', NOW()),
  ('01910000-0003-7000-8000-000000000002', 'text', 'Test message content for in-progress request', 'msg-002', 'general-4', 'user-101', NOW()),
  ('01910000-0003-7000-8000-000000000003', 'text', 'Test message content for completed request', 'msg-003', 'general-4', 'user-102', NOW())
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- 5. Sample requests in various states
-- ============================================================

INSERT INTO requests (id, request_id, community_server_id, message_archive_id, requested_by, status, migrated_from_content, created_at, updated_at)
VALUES
  (
    '01910000-0004-7000-8000-000000000001',
    'e2e-test-request-pending-001',
    '019d473a-0b2e-795b-b6a1-4919403313b8',
    '01910000-0003-7000-8000-000000000001',
    'user-100',
    'PENDING',
    false,
    NOW(),
    NOW()
  ),
  (
    '01910000-0004-7000-8000-000000000002',
    'e2e-test-request-inprogress-002',
    '019d473a-0b2e-795b-b6a1-4919403313b8',
    '01910000-0003-7000-8000-000000000002',
    'user-101',
    'IN_PROGRESS',
    false,
    NOW(),
    NOW()
  ),
  (
    '01910000-0004-7000-8000-000000000003',
    'e2e-test-request-completed-003',
    '019d473a-0b2e-795b-b6a1-4919403313b8',
    '01910000-0003-7000-8000-000000000003',
    'user-102',
    'COMPLETED',
    false,
    NOW(),
    NOW()
  )
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- 6. Sample notes with different statuses
-- ============================================================

INSERT INTO notes (id, author_id, community_server_id, request_id, summary, classification, status, helpfulness_score, ai_generated, force_published, created_at, updated_at)
VALUES
  (
    '01910000-0005-7000-8000-000000000001',
    '01910000-0001-7000-8000-000000000002',
    '019d473a-0b2e-795b-b6a1-4919403313b8',
    '01910000-0004-7000-8000-000000000002',
    'This post contains potentially misleading information about the topic.',
    'MISINFORMED_OR_POTENTIALLY_MISLEADING',
    'NEEDS_MORE_RATINGS',
    0,
    false,
    false,
    NOW(),
    NOW()
  ),
  (
    '01910000-0005-7000-8000-000000000002',
    '01910000-0001-7000-8000-000000000003',
    '019d473a-0b2e-795b-b6a1-4919403313b8',
    '01910000-0004-7000-8000-000000000003',
    'This post is accurate and not misleading.',
    'NOT_MISLEADING',
    'CURRENTLY_RATED_HELPFUL',
    85,
    false,
    false,
    NOW(),
    NOW()
  ),
  (
    '01910000-0005-7000-8000-000000000003',
    '01910000-0001-7000-8000-000000000002',
    '019d473a-0b2e-795b-b6a1-4919403313b8',
    NULL,
    'Additional context: this claim has been disputed by fact-checkers.',
    'MISINFORMED_OR_POTENTIALLY_MISLEADING',
    'CURRENTLY_RATED_NOT_HELPFUL',
    10,
    false,
    false,
    NOW(),
    NOW()
  )
ON CONFLICT (id) DO NOTHING;

-- Update requests to link to completed note
UPDATE requests
SET note_id = '01910000-0005-7000-8000-000000000002', status = 'COMPLETED'
WHERE id = '01910000-0004-7000-8000-000000000003'
  AND note_id IS NULL;

-- ============================================================
-- 7. Sample ratings on the helpful note
-- ============================================================

INSERT INTO ratings (id, note_id, rater_id, helpfulness_level, created_at, updated_at)
VALUES
  (
    '01910000-0006-7000-8000-000000000001',
    '01910000-0005-7000-8000-000000000002',
    '01910000-0001-7000-8000-000000000001',
    'HELPFUL',
    NOW(),
    NOW()
  ),
  (
    '01910000-0006-7000-8000-000000000002',
    '01910000-0005-7000-8000-000000000002',
    '01910000-0001-7000-8000-000000000002',
    'HELPFUL',
    NOW(),
    NOW()
  ),
  (
    '01910000-0006-7000-8000-000000000003',
    '01910000-0005-7000-8000-000000000001',
    '01910000-0001-7000-8000-000000000003',
    'SOMEWHAT_HELPFUL',
    NOW(),
    NOW()
  )
ON CONFLICT (note_id, rater_id) DO NOTHING;

-- ============================================================
-- 8. Sample moderation actions
-- ============================================================

INSERT INTO moderation_actions (id, request_id, note_id, community_server_id, action_type, action_tier, action_state, review_group, created_at, updated_at)
VALUES
  (
    '01910000-0007-7000-8000-000000000001',
    '01910000-0004-7000-8000-000000000001',
    NULL,
    '019d473a-0b2e-795b-b6a1-4919403313b8',
    'hide',
    'tier_2_consensus',
    'proposed',
    'community',
    NOW(),
    NOW()
  ),
  (
    '01910000-0007-7000-8000-000000000002',
    '01910000-0004-7000-8000-000000000002',
    '01910000-0005-7000-8000-000000000001',
    '019d473a-0b2e-795b-b6a1-4919403313b8',
    'warn',
    'tier_2_consensus',
    'under_review',
    'trusted',
    NOW(),
    NOW()
  ),
  (
    '01910000-0007-7000-8000-000000000003',
    '01910000-0004-7000-8000-000000000003',
    '01910000-0005-7000-8000-000000000002',
    '019d473a-0b2e-795b-b6a1-4919403313b8',
    'hide',
    'tier_2_consensus',
    'confirmed',
    'community',
    NOW(),
    NOW()
  )
ON CONFLICT (id) DO NOTHING;
