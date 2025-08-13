#!/bin/bash
# Database Backup Script for Wiki App

set -e

# Configuration
BACKUP_DIR="/backups"
ARCHIVE_DIR="/backups/archive"
DB_HOST="db"
DB_PORT="5432"
DB_NAME="${POSTGRES_DB:-wiki}"
DB_USER="${POSTGRES_USER:-wiki}"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)

# Create directories if they don't exist
mkdir -p "$BACKUP_DIR" "$ARCHIVE_DIR"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to cleanup old backups
cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days"
    find "$BACKUP_DIR" -name "*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete
    find "$BACKUP_DIR" -name "*.log" -type f -mtime +$RETENTION_DAYS -delete
    find "$ARCHIVE_DIR" -name "*" -type f -mtime +$RETENTION_DAYS -delete
}

# Function to perform database backup
backup_database() {
    local backup_file="$BACKUP_DIR/wiki_backup_$DATE.sql"
    local compressed_file="$backup_file.gz"
    local log_file="$BACKUP_DIR/backup_$DATE.log"
    
    log "Starting database backup to $compressed_file"
    
    # Perform the backup
    if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --verbose --clean --if-exists --create --format=plain \
        > "$backup_file" 2> "$log_file"; then
        
        # Compress the backup
        gzip "$backup_file"
        
        # Verify the compressed backup
        if [ -f "$compressed_file" ] && [ -s "$compressed_file" ]; then
            local size=$(du -h "$compressed_file" | cut -f1)
            log "Database backup completed successfully. Size: $size"
            
            # Create a checksum
            sha256sum "$compressed_file" > "$compressed_file.sha256"
            
            return 0
        else
            log "ERROR: Backup file is empty or doesn't exist"
            return 1
        fi
    else
        log "ERROR: Database backup failed"
        cat "$log_file"
        return 1
    fi
}

# Function to backup application data
backup_app_data() {
    local uploads_backup="$BACKUP_DIR/uploads_backup_$DATE.tar.gz"
    local logs_backup="$BACKUP_DIR/logs_backup_$DATE.tar.gz"
    
    # Backup uploads directory
    if [ -d "/app/uploads" ] && [ "$(ls -A /app/uploads)" ]; then
        log "Backing up uploads directory"
        tar -czf "$uploads_backup" -C /app uploads/
        sha256sum "$uploads_backup" > "$uploads_backup.sha256"
        log "Uploads backup completed: $(du -h "$uploads_backup" | cut -f1)"
    fi
    
    # Backup recent logs (last 7 days)
    if [ -d "/app/logs" ] && [ "$(find /app/logs -name "*.log*" -mtime -7)" ]; then
        log "Backing up recent logs"
        find /app/logs -name "*.log*" -mtime -7 -print0 | \
            tar -czf "$logs_backup" --null -T -
        sha256sum "$logs_backup" > "$logs_backup.sha256"
        log "Logs backup completed: $(du -h "$logs_backup" | cut -f1)"
    fi
}

# Function to create backup manifest
create_manifest() {
    local manifest_file="$BACKUP_DIR/backup_manifest_$DATE.json"
    
    cat > "$manifest_file" << EOF
{
    "backup_date": "$(date -Iseconds)",
    "database": {
        "host": "$DB_HOST",
        "port": "$DB_PORT",
        "name": "$DB_NAME",
        "user": "$DB_USER"
    },
    "files": [
EOF

    local first=true
    for file in "$BACKUP_DIR"/*_"$DATE".*; do
        if [ -f "$file" ] && [[ ! "$file" =~ \.sha256$ ]] && [[ ! "$file" =~ \.log$ ]]; then
            if [ "$first" = true ]; then
                first=false
            else
                echo "," >> "$manifest_file"
            fi
            
            local filename=$(basename "$file")
            local size=$(stat -c%s "$file")
            local checksum=""
            
            if [ -f "$file.sha256" ]; then
                checksum=$(cut -d' ' -f1 "$file.sha256")
            fi
            
            cat >> "$manifest_file" << EOF
        {
            "filename": "$filename",
            "size": $size,
            "checksum": "$checksum"
        }
EOF
        fi
    done

    cat >> "$manifest_file" << EOF
    ]
}
EOF

    log "Backup manifest created: $manifest_file"
}

# Function to send backup notification (placeholder for monitoring integration)
send_notification() {
    local status=$1
    local message=$2
    
    # This could be extended to send notifications to monitoring systems
    # like Slack, email, or monitoring APIs
    log "NOTIFICATION [$status]: $message"
}

# Main backup process
main() {
    log "Starting backup process"
    
    local success=true
    
    # Perform database backup
    if ! backup_database; then
        success=false
        send_notification "ERROR" "Database backup failed"
    fi
    
    # Backup application data
    backup_app_data
    
    # Create backup manifest
    create_manifest
    
    # Cleanup old backups
    cleanup_old_backups
    
    # Final status
    if [ "$success" = true ]; then
        log "Backup process completed successfully"
        send_notification "SUCCESS" "Backup completed successfully"
    else
        log "Backup process completed with errors"
        send_notification "WARNING" "Backup completed with errors"
        exit 1
    fi
}

# Run the backup
main "$@"