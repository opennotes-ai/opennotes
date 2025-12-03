# Database Backups

## fact_check_items Table with Embeddings

### Backup Information
- **File**: `fact_check_items_with_embeddings_20251104_161550.sql`
- **Size**: 106MB
- **Records**: 4,550 fact check items with embeddings
- **Created**: November 4, 2024 at 16:15:50
- **Format**: PostgreSQL dump with column-inserts (data only)

### Purpose
This backup contains the `fact_check_items` table with pre-generated embeddings from the OpenAI text-embedding-3-small model. It can be used to restore the table without having to regenerate the embeddings, which saves time and API costs.

### How to Restore

#### Method 1: Using Docker (Recommended)
```bash
# Restore the data to the running PostgreSQL container
docker exec -i opennotes-postgres-1 psql -U opennotes -d opennotes < fact_check_items_with_embeddings_20251104_161550.sql
```

#### Method 2: Direct PostgreSQL
```bash
# If you have psql installed locally
psql -h localhost -p 5432 -U opennotes -d opennotes < fact_check_items_with_embeddings_20251104_161550.sql
```

#### Method 3: Clear and Restore (if table already has data)
```bash
# First, clear the existing data
docker exec opennotes-postgres-1 psql -U opennotes -d opennotes -c "TRUNCATE TABLE fact_check_items;"

# Then restore the backup
docker exec -i opennotes-postgres-1 psql -U opennotes -d opennotes < fact_check_items_with_embeddings_20251104_161550.sql
```

### Important Notes
- This backup contains only the data (INSERT statements), not the table schema
- The table schema must already exist in the database before restoration
- The backup uses `--column-inserts` format for better compatibility
- Embeddings are stored in the `embedding` column as pgvector arrays

### Creating New Backups
To create a new backup with embeddings:
```bash
# Full backup with schema and data
docker exec opennotes-postgres-1 pg_dump -U opennotes -d opennotes --table=fact_check_items > fact_check_items_full_$(date +%Y%m%d_%H%M%S).sql

# Data only (like this backup)
docker exec opennotes-postgres-1 pg_dump -U opennotes -d opennotes --table=fact_check_items --data-only --column-inserts > fact_check_items_data_$(date +%Y%m%d_%H%M%S).sql
```

### Verifying the Restore
After restoring, verify the data:
```sql
-- Check record count
SELECT COUNT(*) FROM fact_check_items;

-- Check that embeddings are present
SELECT COUNT(*) FROM fact_check_items WHERE embedding IS NOT NULL;

-- Test similarity search
SELECT title, content <-> (SELECT embedding FROM fact_check_items LIMIT 1) AS distance
FROM fact_check_items
LIMIT 5;
```
