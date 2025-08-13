#!/bin/bash
# Database Restore Script for Wiki App

set -e

# Configuration
BACKUP_DIR="/backups"
DB_HOST="db"
DB_PORT="5432"
DB_NAME="${POSTGRES_DB:-wiki}"
DB_USER="${POSTGRES_USER:-wiki}"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to show usage
usage() {
    echo "Usage: $0 [OPTIONS] BACKUP_FILE"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -f, --force             Force restore without confirmation"
    echo "  -t, --target-db NAME    Target database name (default: $DB_NAME)"
    echo "  -v, --verify            Verify backup before restore"
    echo ""
    echo "Examples:"
    echo "  $0 wiki_backup_20231201_120000.sql.gz"
    echo "  $0 -f -t wiki_test backup.sql.gz"
    echo "  $0 --verify --target-db wiki_staging backup.sql.gz"
}

# Function to verify backup file
verify_backup() {
    local backup_file="$1"
    local checksum_file="$backup_file.sha256"
    
    log "Verifying backup file integrity"
    
    if [ ! -f "$backup_file" ]; then
        log "ERROR: Backup file not found: $backup_file"
        return 1
    fi
    
    if [ ! -f "$checksum_file" ]; then
        log "WARNING: Checksum file not found: $checksum_file"
        log "Skipping integrity verification"
        return 0
    fi
    
    if sha256sum -c "$checksum_file"; then
        log "Backup file integrity verified successfully"
        return 0
    else
        log "ERROR: Backup file integrity check failed"
        return 1
    fi
}

# Function to create database backup before restore
create_pre_restore_backup() {
    local target_db="$1"
    local backup_file="$BACKUP_DIR/pre_restore_backup_$(date +%Y%m%d_%H%M%S).sql.gz"
    
    log "Creating pre-restore backup of $target_db"
    
    if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$target_db" \
        --verbose --clean --if-exists --create --format=plain | gzip > "$backup_file"; then
        log "Pre-restore backup created: $backup_file"
        return 0
    else
        log "WARNING: Failed to create pre-restore backup"
        return 1
    fi
}

# Function to restore database
restore_database() {
    local backup_file="$1"
    local target_db="$2"
    local temp_file="/tmp/restore_$(date +%Y%m%d_%H%M%S).sql"
    
    log "Starting database restore from $backup_file to $target_db"
    
    # Decompress backup file
    if [[ "$backup_file" == *.gz ]]; then
        log "Decompressing backup file"
        if ! gunzip -c "$backup_file" > "$temp_file"; then
            log "ERROR: Failed to decompress backup file"
            return 1
        fi
    else
        cp "$backup_file" "$temp_file"
    fi
    
    # Stop application connections (if possible)
    log "Terminating active connections to $target_db"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$target_db' AND pid <> pg_backend_pid();" || true
    
    # Restore database
    log "Restoring database from backup"
    if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -f "$temp_file"; then
        log "Database restore completed successfully"
        
        # Clean up temporary file
        rm -f "$temp_file"
        
        # Run post-restore checks
        post_restore_checks "$target_db"
        
        return 0
    else
        log "ERROR: Database restore failed"
        rm -f "$temp_file"
        return 1
    fi
}

# Function to run post-restore checks
post_restore_checks() {
    local target_db="$1"
    
    log "Running post-restore checks"
    
    # Check database connectivity
    if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$target_db" -c "SELECT 1;" > /dev/null; then
        log "✓ Database connectivity check passed"
    else
        log "✗ Database connectivity check failed"
        return 1
    fi
    
    # Check table counts
    local table_count=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$target_db" -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
    log "✓ Found $table_count tables in restored database"
    
    # Check for critical tables
    local critical_tables=("users" "documents" "folders" "files")
    for table in "${critical_tables[@]}"; do
        local exists=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$target_db" -t -c \
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '$table');")
        if [[ "$exists" =~ "t" ]]; then
            log "✓ Critical table '$table' exists"
        else
            log "✗ Critical table '$table' missing"
            return 1
        fi
    done
    
    # Update database statistics
    log "Updating database statistics"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$target_db" -c "ANALYZE;" || true
    
    log "Post-restore checks completed successfully"
}

# Function to list available backups
list_backups() {
    log "Available backup files:"
    echo ""
    
    for backup in "$BACKUP_DIR"/*.sql.gz; do
        if [ -f "$backup" ]; then
            local filename=$(basename "$backup")
            local size=$(du -h "$backup" | cut -f1)
            local date=$(stat -c %y "$backup" | cut -d' ' -f1,2 | cut -d'.' -f1)
            
            printf "  %-40s %8s  %s\n" "$filename" "$size" "$date"
        fi
    done
    
    echo ""
}

# Parse command line arguments
FORCE=false
VERIFY=false
TARGET_DB="$DB_NAME"
BACKUP_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -v|--verify)
            VERIFY=true
            shift
            ;;
        -t|--target-db)
            TARGET_DB="$2"
            shift 2
            ;;
        -l|--list)
            list_backups
            exit 0
            ;;
        -*)
            log "ERROR: Unknown option $1"
            usage
            exit 1
            ;;
        *)
            if [ -z "$BACKUP_FILE" ]; then
                BACKUP_FILE="$1"
            else
                log "ERROR: Multiple backup files specified"
                usage
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate arguments
if [ -z "$BACKUP_FILE" ]; then
    log "ERROR: No backup file specified"
    usage
    exit 1
fi

# Convert relative path to absolute
if [[ "$BACKUP_FILE" != /* ]]; then
    BACKUP_FILE="$BACKUP_DIR/$BACKUP_FILE"
fi

# Main restore process
main() {
    log "Starting restore process"
    log "Backup file: $BACKUP_FILE"
    log "Target database: $TARGET_DB"
    
    # Verify backup if requested
    if [ "$VERIFY" = true ]; then
        if ! verify_backup "$BACKUP_FILE"; then
            log "ERROR: Backup verification failed"
            exit 1
        fi
    fi
    
    # Confirmation prompt
    if [ "$FORCE" = false ]; then
        echo ""
        echo "WARNING: This will replace the existing database '$TARGET_DB' with the backup data."
        echo "All current data in '$TARGET_DB' will be lost!"
        echo ""
        read -p "Are you sure you want to continue? (yes/no): " -r
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            log "Restore cancelled by user"
            exit 0
        fi
    fi
    
    # Create pre-restore backup
    create_pre_restore_backup "$TARGET_DB" || log "WARNING: Pre-restore backup failed"
    
    # Perform restore
    if restore_database "$BACKUP_FILE" "$TARGET_DB"; then
        log "Database restore completed successfully"
        echo ""
        echo "IMPORTANT: Remember to:"
        echo "1. Restart the application services"
        echo "2. Clear application caches"
        echo "3. Verify application functionality"
        echo "4. Update any configuration if needed"
    else
        log "ERROR: Database restore failed"
        exit 1
    fi
}

# Run the restore
main "$@"