-- Task-1184: Diagnostic queries for model_name data audit
-- Run against production DB to identify any remaining malformed values.

-- 1. All distinct model_name values in opennotes_sim_agents (the migration target)
SELECT model_name, COUNT(*) AS agent_count
FROM opennotes_sim_agents
WHERE deleted_at IS NULL
GROUP BY model_name
ORDER BY agent_count DESC;

-- 2. Values that do NOT match canonical provider:model format
--    (no colon, or still have slash-based format)
--    NOTE: vertex_ai paths like google-vertex:global/gemini-2.5-pro are VALID
--    post-migration — the migration intentionally preserves sub-path segments.
SELECT id, name, model_name
FROM opennotes_sim_agents
WHERE deleted_at IS NULL
  AND (
    model_name NOT LIKE '%:%'               -- missing colon separator
    OR model_name LIKE '%/%:%'              -- slash before colon (old format residual)
  )
ORDER BY model_name;

-- 3. All distinct ai_model values in notes (added after the migration)
SELECT ai_model, COUNT(*) AS note_count
FROM notes
WHERE ai_model IS NOT NULL
GROUP BY ai_model
ORDER BY note_count DESC;

-- 4. Notes with malformed ai_model values
SELECT id, ai_model, created_at
FROM notes
WHERE ai_model IS NOT NULL
  AND (
    ai_model NOT LIKE '%:%'                -- missing colon separator
    OR ai_model LIKE '%/%:%'               -- slash before colon
  )
ORDER BY created_at DESC
LIMIT 100;

-- 5. Cross-reference: model_name values that exist in sim_agents
--    but are NOT valid per the ModelId.from_pydantic_ai() parser
--    (i.e., empty provider or model portion)
SELECT id, name, model_name
FROM opennotes_sim_agents
WHERE deleted_at IS NULL
  AND (
    model_name LIKE ':%'                    -- empty provider
    OR model_name LIKE '%:'                 -- empty model
    OR LENGTH(model_name) < 3              -- too short to be valid
  );
