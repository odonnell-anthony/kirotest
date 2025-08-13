# Wiki Documentation App - Operations Runbook

This runbook provides step-by-step procedures for operating, maintaining, and troubleshooting the Wiki Documentation App in production environments.

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Monitoring and Alerting](#monitoring-and-alerting)
3. [Backup and Recovery](#backup-and-recovery)
4. [Troubleshooting](#troubleshooting)
5. [Performance Tuning](#performance-tuning)
6. [Security Operations](#security-operations)
7. [Incident Response](#incident-response)
8. [Maintenance Procedures](#maintenance-procedures)
9. [Capacity Planning](#capacity-planning)
10. [Emergency Procedures](#emergency-procedures)

## Daily Operations

### Morning Health Check

Execute daily health verification:

```bash
#!/bin/bash
# Daily health check script

echo "=== Wiki App Daily Health Check ==="
echo "Date: $(date)"
echo

# Check container status
echo "1. Container Status:"
docker-compose -f docker-compose.prod.yml ps

# Check application health
echo -e "\n2. Application Health:"
curl -s -k https://localhost/api/health | jq '.'

# Check database connectivity
echo -e "\n3. Database Health:"
docker-compose -f docker-compose.prod.yml exec -T db pg_isready -U wiki

# Check Redis connectivity
echo -e "\n4. Redis Health:"
docker-compose -f docker-compose.prod.yml exec -T redis redis-cli ping

# Check disk usage
echo -e "\n5. Disk Usage:"
df -h | grep -E "(/$|/opt/wiki|/app)"

# Check recent errors
echo -e "\n6. Recent Errors (last hour):"
find /opt/wiki/logs -name "*.log" -mmin -60 -exec grep -l "ERROR\|CRITICAL" {} \; | head -5

# Check backup status
echo -e "\n7. Last Backup:"
ls -la /opt/wiki/backups/*.sql.gz | tail -1

echo -e "\n=== Health Check Complete ==="
```

### Log Review

Daily log analysis:

```bash
# Check error patterns
grep -E "ERROR|CRITICAL|FATAL" /opt/wiki/logs/app.log | tail -20

# Check security events
grep -E "SECURITY|UNAUTHORIZED|FAILED.*LOGIN" /opt/wiki/logs/security.log | tail -10

# Check performance issues
grep -E "SLOW|TIMEOUT|HIGH.*USAGE" /opt/wiki/logs/performance.log | tail -10

# Generate daily log summary
python3 scripts/log_analysis.py --daily-summary
```

### Resource Monitoring

Check system resources:

```bash
# System resource usage
echo "CPU Usage:"
top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1

echo "Memory Usage:"
free -h

echo "Disk Usage:"
df -h

# Container resource usage
echo "Container Resources:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Application metrics
python3 scripts/monitoring.py --check-resources
```

## Monitoring and Alerting

### Monitoring Dashboard

Access monitoring information:

```bash
# View system monitoring dashboard
cat /opt/wiki/logs/monitoring_dashboard.json | jq '.'

# View container monitoring dashboard
cat /opt/wiki/logs/container_monitoring_dashboard.json | jq '.'

# View log aggregation statistics
cat /opt/wiki/logs/aggregation_stats.json | jq '.'
```

### Alert Configuration

Configure alert thresholds:

```bash
# Edit monitoring configuration
cat > /opt/wiki/config/monitoring.json << 'EOF'
{
  "alert_thresholds": {
    "cpu_usage": 80.0,
    "memory_usage": 85.0,
    "disk_usage": 90.0,
    "response_time": 5.0,
    "error_rate": 5.0
  },
  "notification_channels": {
    "slack_webhook": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    "email": "admin@yourdomain.com"
  }
}
EOF
```

### Alert Response Procedures

#### High CPU Usage Alert

```bash
# 1. Identify high CPU processes
docker stats --no-stream
top -p $(docker inspect --format '{{.State.Pid}}' wiki-app-prod)

# 2. Check application logs for issues
docker-compose -f docker-compose.prod.yml logs --tail=100 app

# 3. Scale if necessary
docker-compose -f docker-compose.prod.yml up -d --scale app=3

# 4. Monitor improvement
watch "docker stats --no-stream"
```

#### High Memory Usage Alert

```bash
# 1. Check memory usage by container
docker stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}\t{{.MemPerc}}"

# 2. Check for memory leaks
docker-compose -f docker-compose.prod.yml exec app python -c "
import psutil
import os
process = psutil.Process(os.getpid())
print(f'Memory: {process.memory_info().rss / 1024 / 1024:.2f} MB')
"

# 3. Restart if necessary
docker-compose -f docker-compose.prod.yml restart app

# 4. Monitor memory usage
watch "free -h"
```

#### Service Down Alert

```bash
# 1. Check container status
docker-compose -f docker-compose.prod.yml ps

# 2. Check container logs
docker-compose -f docker-compose.prod.yml logs --tail=50 [service_name]

# 3. Restart failed service
docker-compose -f docker-compose.prod.yml restart [service_name]

# 4. Verify service recovery
curl -k https://localhost/api/health
```

## Backup and Recovery

### Manual Backup

Create immediate backup:

```bash
# Full system backup
./scripts/backup.sh

# Database only backup
docker-compose -f docker-compose.prod.yml exec -T db pg_dump -U wiki wiki | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Files only backup
tar -czf uploads_backup_$(date +%Y%m%d_%H%M%S).tar.gz -C /opt/wiki/data uploads/
```

### Backup Verification

Verify backup integrity:

```bash
# List available backups
ls -la /opt/wiki/backups/

# Verify backup file integrity
./scripts/restore.sh --verify backup_file.sql.gz

# Test restore to temporary database
./scripts/restore.sh --target-db wiki_test backup_file.sql.gz
```

### Recovery Procedures

#### Database Recovery

```bash
# 1. Stop application services
docker-compose -f docker-compose.prod.yml stop app worker scheduler

# 2. Create pre-recovery backup
./scripts/backup.sh

# 3. Restore from backup
./scripts/restore.sh --force backup_file.sql.gz

# 4. Verify database integrity
docker-compose -f docker-compose.prod.yml exec db psql -U wiki -c "
SELECT schemaname, tablename, n_tup_ins, n_tup_upd, n_tup_del 
FROM pg_stat_user_tables 
ORDER BY n_tup_ins DESC LIMIT 10;"

# 5. Start application services
docker-compose -f docker-compose.prod.yml start app worker scheduler

# 6. Verify application functionality
curl -k https://localhost/api/health
```

#### File System Recovery

```bash
# 1. Stop application
docker-compose -f docker-compose.prod.yml stop app

# 2. Backup current files
mv /opt/wiki/data/uploads /opt/wiki/data/uploads.backup

# 3. Restore files from backup
tar -xzf uploads_backup.tar.gz -C /opt/wiki/data/

# 4. Set proper permissions
chown -R 1001:1001 /opt/wiki/data/uploads

# 5. Start application
docker-compose -f docker-compose.prod.yml start app
```

#### Complete System Recovery

```bash
# 1. Provision new infrastructure
# 2. Install dependencies (see DEPLOYMENT.md)
# 3. Restore configuration files
# 4. Restore database
# 5. Restore uploaded files
# 6. Start all services
# 7. Verify functionality
```

## Troubleshooting

### Application Issues

#### Application Won't Start

```bash
# 1. Check container logs
docker-compose -f docker-compose.prod.yml logs app

# 2. Check environment variables
docker-compose -f docker-compose.prod.yml exec app env | grep -E "DATABASE|REDIS|SECRET"

# 3. Test database connection
docker-compose -f docker-compose.prod.yml exec app python -c "
import asyncpg
import asyncio
async def test():
    try:
        conn = await asyncpg.connect('postgresql://wiki:password@db:5432/wiki')
        result = await conn.fetchval('SELECT 1')
        print(f'Database connection: OK (result: {result})')
        await conn.close()
    except Exception as e:
        print(f'Database connection: FAILED ({e})')
asyncio.run(test())
"

# 4. Check Redis connection
docker-compose -f docker-compose.prod.yml exec app python -c "
import aioredis
import asyncio
async def test():
    try:
        redis = aioredis.from_url('redis://redis:6379/0')
        result = await redis.ping()
        print(f'Redis connection: OK (result: {result})')
        await redis.close()
    except Exception as e:
        print(f'Redis connection: FAILED ({e})')
asyncio.run(test())
"
```

#### Slow Response Times

```bash
# 1. Check system resources
top -bn1 | head -20

# 2. Check database performance
docker-compose -f docker-compose.prod.yml exec db psql -U wiki -c "
SELECT query, mean_time, calls, total_time
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;"

# 3. Check slow queries
grep "SLOW" /opt/wiki/logs/database.log | tail -10

# 4. Check cache hit rates
docker-compose -f docker-compose.prod.yml exec redis redis-cli info stats | grep -E "keyspace_hits|keyspace_misses"

# 5. Analyze application performance
python3 scripts/performance_analysis.py
```

#### High Error Rates

```bash
# 1. Check error logs
tail -100 /opt/wiki/logs/error.log

# 2. Check application logs for patterns
grep -E "ERROR|EXCEPTION" /opt/wiki/logs/app.log | tail -20

# 3. Check database errors
docker-compose -f docker-compose.prod.yml logs db | grep -i error

# 4. Check Redis errors
docker-compose -f docker-compose.prod.yml logs redis | grep -i error

# 5. Generate error summary
python3 scripts/error_analysis.py --last-hour
```

### Database Issues

#### Connection Pool Exhaustion

```bash
# 1. Check active connections
docker-compose -f docker-compose.prod.yml exec db psql -U wiki -c "
SELECT count(*) as active_connections, state 
FROM pg_stat_activity 
WHERE datname = 'wiki' 
GROUP BY state;"

# 2. Kill long-running queries
docker-compose -f docker-compose.prod.yml exec db psql -U wiki -c "
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE datname = 'wiki' 
AND state = 'active' 
AND query_start < now() - interval '5 minutes';"

# 3. Restart application to reset connections
docker-compose -f docker-compose.prod.yml restart app
```

#### Database Lock Issues

```bash
# 1. Check for locks
docker-compose -f docker-compose.prod.yml exec db psql -U wiki -c "
SELECT blocked_locks.pid AS blocked_pid,
       blocked_activity.usename AS blocked_user,
       blocking_locks.pid AS blocking_pid,
       blocking_activity.usename AS blocking_user,
       blocked_activity.query AS blocked_statement,
       blocking_activity.query AS current_statement_in_blocking_process
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;"

# 2. Kill blocking queries if necessary
docker-compose -f docker-compose.prod.yml exec db psql -U wiki -c "
SELECT pg_terminate_backend([blocking_pid]);"
```

### Network Issues

#### SSL Certificate Problems

```bash
# 1. Check certificate validity
openssl x509 -in nginx/ssl/cert.pem -text -noout | grep -E "Not Before|Not After"

# 2. Test SSL connection
openssl s_client -connect localhost:443 -servername yourdomain.com

# 3. Regenerate certificate if needed
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout nginx/ssl/key.pem \
    -out nginx/ssl/cert.pem \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=yourdomain.com"

# 4. Restart nginx
docker-compose -f docker-compose.prod.yml restart nginx
```

#### Load Balancer Issues

```bash
# 1. Check nginx status
docker-compose -f docker-compose.prod.yml exec nginx nginx -t

# 2. Check nginx logs
docker-compose -f docker-compose.prod.yml logs nginx | tail -50

# 3. Test backend connectivity
docker-compose -f docker-compose.prod.yml exec nginx curl -I http://app:8000/api/health

# 4. Reload nginx configuration
docker-compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

## Performance Tuning

### Database Optimization

```bash
# 1. Update database statistics
docker-compose -f docker-compose.prod.yml exec db psql -U wiki -c "ANALYZE;"

# 2. Check index usage
docker-compose -f docker-compose.prod.yml exec db psql -U wiki -c "
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;"

# 3. Identify missing indexes
python3 scripts/analyze_queries.py --suggest-indexes

# 4. Optimize configuration
python3 scripts/optimize_database.py
```

### Application Optimization

```bash
# 1. Profile application performance
python3 scripts/performance_profiler.py --duration=300

# 2. Check memory usage patterns
python3 scripts/memory_profiler.py

# 3. Optimize cache configuration
python3 scripts/cache_optimizer.py

# 4. Tune worker processes
docker-compose -f docker-compose.prod.yml up -d --scale app=4 --scale worker=3
```

### System Optimization

```bash
# 1. Check system limits
ulimit -a

# 2. Optimize Docker settings
echo '{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  },
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 64000,
      "Soft": 64000
    }
  }
}' | sudo tee /etc/docker/daemon.json

# 3. Restart Docker daemon
sudo systemctl restart docker

# 4. Restart application
docker-compose -f docker-compose.prod.yml restart
```

## Security Operations

### Security Monitoring

```bash
# 1. Check failed login attempts
grep "AUTHENTICATION.*FAILED" /opt/wiki/logs/security.log | tail -20

# 2. Check suspicious activity
grep -E "SUSPICIOUS|SECURITY.*EVENT" /opt/wiki/logs/security.log | tail -10

# 3. Check file access violations
grep "UNAUTHORIZED.*FILE" /opt/wiki/logs/security.log | tail -10

# 4. Generate security report
python3 scripts/security_report.py --daily
```

### Security Updates

```bash
# 1. Check for security updates
sudo apt list --upgradable | grep -i security

# 2. Update system packages
sudo apt update && sudo apt upgrade -y

# 3. Update Docker images
docker-compose -f docker-compose.prod.yml pull

# 4. Restart services with new images
docker-compose -f docker-compose.prod.yml up -d
```

### Incident Response

#### Security Breach Response

```bash
# 1. Isolate affected systems
docker-compose -f docker-compose.prod.yml stop

# 2. Preserve evidence
cp -r /opt/wiki/logs /opt/wiki/incident_$(date +%Y%m%d_%H%M%S)/

# 3. Analyze logs for breach indicators
python3 scripts/security_analysis.py --incident-mode

# 4. Change all passwords and secrets
./scripts/rotate_secrets.sh

# 5. Restore from clean backup if necessary
./scripts/restore.sh --verified-clean backup_file.sql.gz

# 6. Restart services
docker-compose -f docker-compose.prod.yml up -d
```

## Maintenance Procedures

### Scheduled Maintenance

#### Weekly Maintenance

```bash
#!/bin/bash
# Weekly maintenance script

echo "=== Weekly Maintenance ==="

# 1. Clean up old logs
find /opt/wiki/logs -name "*.log.*" -mtime +7 -delete

# 2. Clean up old backups
find /opt/wiki/backups -name "*.sql.gz" -mtime +30 -delete

# 3. Update system packages
sudo apt update && sudo apt list --upgradable

# 4. Check disk usage
df -h

# 5. Optimize database
docker-compose -f docker-compose.prod.yml exec db psql -U wiki -c "VACUUM ANALYZE;"

# 6. Generate weekly report
python3 scripts/weekly_report.py

echo "=== Weekly Maintenance Complete ==="
```

#### Monthly Maintenance

```bash
#!/bin/bash
# Monthly maintenance script

echo "=== Monthly Maintenance ==="

# 1. Full system backup
./scripts/backup.sh --full

# 2. Security updates
sudo apt update && sudo apt upgrade -y

# 3. Docker image updates
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d

# 4. Certificate renewal check
openssl x509 -in nginx/ssl/cert.pem -checkend 2592000 -noout || echo "Certificate expires within 30 days"

# 5. Performance analysis
python3 scripts/performance_analysis.py --monthly

# 6. Capacity planning review
python3 scripts/capacity_planning.py

echo "=== Monthly Maintenance Complete ==="
```

### Update Procedures

#### Application Updates

```bash
# 1. Create backup
./scripts/backup.sh

# 2. Pull latest code
git pull origin main

# 3. Build new images
docker-compose -f docker-compose.prod.yml build

# 4. Rolling update
docker-compose -f docker-compose.prod.yml up -d --no-deps app

# 5. Run migrations if needed
docker-compose -f docker-compose.prod.yml exec app python scripts/migrate.py

# 6. Verify update
curl -k https://localhost/api/health
```

## Capacity Planning

### Resource Monitoring

```bash
# 1. Collect resource usage data
python3 scripts/resource_collector.py --duration=86400  # 24 hours

# 2. Analyze growth trends
python3 scripts/growth_analysis.py --period=30  # 30 days

# 3. Generate capacity report
python3 scripts/capacity_report.py

# 4. Predict future needs
python3 scripts/capacity_predictor.py --forecast=90  # 90 days
```

### Scaling Decisions

```bash
# Horizontal scaling triggers
if [ $(docker stats --no-stream --format "{{.CPUPerc}}" wiki-app-prod | cut -d'%' -f1 | cut -d'.' -f1) -gt 80 ]; then
    echo "Scaling up application containers"
    docker-compose -f docker-compose.prod.yml up -d --scale app=4
fi

# Vertical scaling considerations
if [ $(free | grep Mem | awk '{print ($3/$2) * 100.0}' | cut -d'.' -f1) -gt 85 ]; then
    echo "Consider increasing memory allocation"
fi
```

## Emergency Procedures

### Service Outage Response

```bash
# 1. Immediate assessment
curl -k https://localhost/api/health
docker-compose -f docker-compose.prod.yml ps

# 2. Quick restart attempt
docker-compose -f docker-compose.prod.yml restart

# 3. If restart fails, check logs
docker-compose -f docker-compose.prod.yml logs --tail=100

# 4. Escalate if needed
python3 scripts/emergency_notification.py --outage

# 5. Implement workaround if possible
# 6. Document incident
```

### Data Corruption Response

```bash
# 1. Stop all services immediately
docker-compose -f docker-compose.prod.yml stop

# 2. Assess corruption extent
docker-compose -f docker-compose.prod.yml exec db pg_dump -U wiki wiki --schema-only > schema_check.sql

# 3. Restore from latest clean backup
./scripts/restore.sh --force latest_clean_backup.sql.gz

# 4. Verify data integrity
python3 scripts/data_integrity_check.py

# 5. Restart services
docker-compose -f docker-compose.prod.yml start

# 6. Monitor for issues
```

### Contact Information

**Emergency Contacts**:
- System Administrator: [phone/email]
- Database Administrator: [phone/email]
- Security Team: [phone/email]
- Management: [phone/email]

**Escalation Matrix**:
1. Level 1: System Administrator (0-30 minutes)
2. Level 2: Senior Administrator (30-60 minutes)
3. Level 3: Management (60+ minutes)

---

This operations runbook provides comprehensive procedures for managing the Wiki Documentation App in production. Keep this document updated as procedures evolve and new issues are discovered.