BEGIN;

UPDATE opennotes_sim_agents
SET short_description = 'The Sage'
WHERE name ILIKE '%sage%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Diplomat'
WHERE name ILIKE '%diplomat%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Disruptor'
WHERE name ILIKE '%disruptor%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Mentor'
WHERE name ILIKE '%mentor%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Jester'
WHERE name ILIKE '%jester%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Wallflower'
WHERE name ILIKE '%wallflower%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Inquisitor'
WHERE name ILIKE '%inquisitor%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Solidarity Builder'
WHERE name ILIKE '%solidarity%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Contrarian'
WHERE name ILIKE '%contrarian%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Scientist'
WHERE name ILIKE '%scientist%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Sage Elder'
WHERE name ILIKE '%elder%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The True Believer'
WHERE name ILIKE '%true believer%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Critical Theorist'
WHERE name ILIKE '%critical theorist%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Internet Researcher'
WHERE name ILIKE '%internet researcher%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Practitioner'
WHERE name ILIKE '%practitioner%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Student'
WHERE name ILIKE '%student%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Witness'
WHERE name ILIKE '%witness%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Cynic'
WHERE name ILIKE '%cynic%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Diplomat of Knowledge'
WHERE name ILIKE '%diplomat of knowledge%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'The Dogmatist'
WHERE name ILIKE '%dogmatist%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'Measured empiricist and institutional pragmatist'
WHERE name ILIKE '%mara%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'Blunt autodidact contrarian'
WHERE name ILIKE '%dex%' AND short_description IS NULL;

UPDATE opennotes_sim_agents
SET short_description = 'Quiet narrative justice advocate'
WHERE name ILIKE '%sable%' AND short_description IS NULL;

COMMIT;
