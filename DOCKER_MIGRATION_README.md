# Docker Setup with Automatic Migrations

This project now includes automatic database migrations that run during container startup to fix the SQLAlchemy `metadata` reserved word issue.

## What Happens Automatically

1. **Container Startup**: When the app container starts, it runs the `docker-entrypoint.sh` script
2. **Database Wait**: The script waits for the PostgreSQL database to be healthy
3. **Migration**: Runs the `migrate_metadata_column.py` script to rename columns
4. **Application Start**: Starts the main application

## Files Added/Modified

### New Files
- `docker-entrypoint.sh` - Entrypoint script that runs migrations
- `migrate_metadata_column.py` - Python script to rename metadata columns
- `rename_metadata_column.sql` - SQL script for manual migration
- `test_migration.py` - Test script for the migration

### Modified Files
- `Dockerfile` - Added entrypoint and postgresql-client
- `Dockerfile.dev` - Added entrypoint and postgresql-client  
- `docker-compose.yml` - Added migration environment variables
- All model files - Changed `metadata` to `custom_metadata`
- All service files - Updated references to use `custom_metadata`

## How to Use

### Development
```bash
# Build and start the services
docker-compose up --build

# The app will automatically:
# 1. Wait for database to be ready
# 2. Run metadata column migration
# 3. Start the application
```

### Production
```bash
# Build the production image
docker build -t wiki-app .

# Run with proper environment variables
docker run -e DATABASE_URL="postgresql://user:pass@host:5432/db" wiki-app
```

## Migration Details

The migration script renames these columns:
- `documents.metadata` → `documents.custom_metadata`
- `document_revisions.metadata` → `document_revisions.custom_metadata`
- `audit_logs.metadata` → `audit_logs.custom_metadata`

## Troubleshooting

### Check Migration Logs
```bash
docker-compose logs app
```

### Manual Migration
If you need to run the migration manually:
```bash
# Connect to the database container
docker-compose exec db psql -U wiki -d wiki

# Run the SQL migration
\i /path/to/rename_metadata_column.sql
```

### Test Migration Script
```bash
# Test the migration script locally
python3 test_migration.py
```

## Environment Variables

The migration script uses these environment variables:
- `DATABASE_URL` - Full database connection string
- `DB_HOST` - Database host (default: 'db')
- `DB_PORT` - Database port (default: 5432)
- `DB_NAME` - Database name (default: 'wiki')
- `DB_USER` - Database user (default: 'wiki')
- `DB_PASSWORD` - Database password (default: 'wiki')

## Notes

- The migration is idempotent - it won't fail if columns are already renamed
- The script waits for the database to be healthy before running
- If migration fails, the container will exit with error code 1
- All existing data is preserved during the migration 