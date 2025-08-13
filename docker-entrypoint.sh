#!/bin/bash
set -e

echo "Starting Wiki App with automatic migrations..."

# Wait for database to be ready
echo "Waiting for database to be ready..."
until pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME; do
    echo "Database is not ready yet. Waiting..."
    sleep 2
done

echo "Database is ready!"

# Run the metadata column migration
echo "Running metadata column migration..."
python3 /app/migrate_metadata_column.py

# Start the application
echo "Starting application..."
exec "$@" 