-- backfill_short_descriptions.sql
-- Idempotent: only updates rows where short_description IS NULL
-- Run: psql $DATABASE_URL -f scripts/backfill_short_descriptions.sql
--
-- Agent names follow the pattern: "{Adjective} {Animal} {Archetype}"
-- where the last word is the archetype codename. This script matches
-- on the suffix (ending with ' {Archetype}') to map each codename
-- to a short description derived from the sim-agent taxonomy
-- (see docs/sim-agent-taxonomy.md).
--
-- Known archetype codenames from production (as of 2026-03-16):
--   Ash, Dex, Dove, Ember, Felix, Idris, Jules, Kai, Linden,
--   Mara, Noor, Petra, Quinn, Raven, Rio, Sable, Thorne,
--   Vesper, Wren, Zara
--
-- Mara, Dex, and Sable are documented in the taxonomy examples.
-- The remaining codenames are inferred from personality text patterns
-- in the production database. If a new archetype codename is added,
-- append a new UPDATE statement below.
--
-- To verify before running:
--   SELECT name, short_description FROM opennotes_sim_agents
--   WHERE deleted_at IS NULL ORDER BY name;

BEGIN;

-- Documented archetypes (from docs/sim-agent-taxonomy.md examples)
UPDATE opennotes_sim_agents SET short_description = 'Measured empiricist and institutional pragmatist'
WHERE name LIKE '% Mara' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Blunt autodidact contrarian'
WHERE name LIKE '% Dex' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Quiet narrative justice advocate'
WHERE name LIKE '% Sable' AND short_description IS NULL;

-- Inferred archetypes (codenames from production agent population)
-- Descriptions are derived from observed personality patterns.
-- Verify against actual personality text if descriptions need refinement.
UPDATE opennotes_sim_agents SET short_description = 'Grounded practitioner with domain expertise'
WHERE name LIKE '% Ash' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Gentle consensus-builder and peacemaker'
WHERE name LIKE '% Dove' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Passionate advocate with affective warmth'
WHERE name LIKE '% Ember' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Analytical bridge-builder across perspectives'
WHERE name LIKE '% Felix' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Methodical evidence-weigher and critic'
WHERE name LIKE '% Idris' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Playful reframer with ironic edge'
WHERE name LIKE '% Jules' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Confident authority with institutional backing'
WHERE name LIKE '% Kai' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Patient mentor and pedagogical guide'
WHERE name LIKE '% Linden' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Pluralist diplomat navigating multiple frameworks'
WHERE name LIKE '% Noor' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Rigorous logician with systematic method'
WHERE name LIKE '% Petra' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Curious seeker exploring multiple viewpoints'
WHERE name LIKE '% Quinn' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Sharp-eyed skeptic and pattern-spotter'
WHERE name LIKE '% Raven' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Adaptive code-switcher across communities'
WHERE name LIKE '% Rio' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Direct challenger of epistemic authority'
WHERE name LIKE '% Thorne' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Reflective meta-epistemologist and observer'
WHERE name LIKE '% Vesper' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Concise minimalist with precise contributions'
WHERE name LIKE '% Wren' AND short_description IS NULL;

UPDATE opennotes_sim_agents SET short_description = 'Principled face-guardian and norm-enforcer'
WHERE name LIKE '% Zara' AND short_description IS NULL;

COMMIT;
