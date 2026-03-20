CREATE TABLE blog_posts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  slug text NOT NULL UNIQUE,
  body_markdown text NOT NULL,
  author text,
  published_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE blog_posts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read published posts"
  ON blog_posts FOR SELECT
  USING (published_at IS NOT NULL);

INSERT INTO blog_posts (title, slug, body_markdown, published_at)
VALUES (
  'Welcome to OpenNotes',
  'welcome-to-opennotes',
  E'# Welcome to OpenNotes\n\nThis is the first post on the OpenNotes blog feed. OpenNotes is an open-source implementation of Community Notes, Twitter''s collaborative fact-checking system.\n\n## What We''re Building\n\nWe''re building tools that help communities identify and surface **helpful context** on claims that might be misleading. Our approach uses:\n\n- **Matrix factorization** for bridging-based consensus\n- **LLM-powered agents** that simulate diverse reviewer perspectives\n- **Adaptive scoring** that adjusts to community dynamics\n\n## How It Works\n\nThe scoring algorithm finds notes that are rated helpful by people who typically disagree. This "bridging" signal is what makes Community Notes resistant to partisan pile-ons.\n\n```python\ndef score_note(ratings: list[Rating]) -> float:\n    """Notes need cross-cutting support to be rated helpful."""\n    factor_model = fit_matrix_factorization(ratings)\n    return factor_model.intercept  # positive = helpful\n```\n\n## Get Involved\n\nCheck out the [simulation playground](/simulations) to see the scoring system in action. Run your own simulations with different agent populations and see how notes get rated.\n\nMore posts coming soon — we''ll cover scoring internals, agent design, and deployment architecture.',
  now()
);
