# Wiki Documentation App - Production Deployment Guide

This guide covers the complete production deployment of the Wiki Documentation App using Docker containers with comprehensive monitoring, logging, and backup systems.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Production Deployment](#production-deployment)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [Configuration](#configuration)
6. [Monitoring and Logging](#monitoring-and-logging)
7. [Backup and Recovery](#backup-and-recovery)
8. [Security Considerations](#security-considerations)
9. [Troubleshooting](#troubleshooting)
10. [Maintenance](#maintenance)

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 20.04+ recommended)
- **CPU**: Minimum 4 cores, 8+ cores recommended
- **Memory**: Minimum 8GB RAM, 16GB+ recommended
- **Storage**: Minimum 100GB SSD, 500GB+ recommended
- **Network**: Stable internet connection for updates and monitoring

### Software Dependencies

- Docker Engine 20.10+
- Docker Compose 2.0+
- Git
- OpenSSL (for SSL certificates)
- Python 3.11+ (for monitoring scripts)

### Installation Commands

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install Python dependencies for monitoring
sudo apt install python3-pip python3-venv -y
pip3 install docker psutil aiohttp asyncpg aioredis aiofiles
```

## Quick Start

For development or testing environments:

```bash
# Clone the repository
git clone <repository-url>
cd wiki-documentation-app

# Start development environment
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

The application will be available at `http://localhost:8000`.

## Production Deployment

### 1. Prepare the Environment

```bash
# Create application directory
sudo mkdir -p /opt/wiki
cd /opt/wiki

# Clone the repository
git clone <repository-url> .

# Create data directories
sudo mkdir -p /opt/wiki/data/{postgres,redis,uploads} /opt/wiki/logs /opt/wiki/backups

# Set permissions
sudo chown -R $USER:$USER /opt/wiki
```

### 2. Configure Environment Variables

Create production environment file:

```bash
# Create .env.prod file
cat > .env.prod << 'EOF'
# Database Configuration
POSTGRES_DB=wiki
POSTGRES_USER=wiki
POSTGRES_PASSWORD=<SECURE_PASSWORD>

# Redis Configuration
REDIS_PASSWORD=<SECURE_REDIS_PASSWORD>

# Application Secrets
SECRET_KEY=<SECURE_SECRET_KEY>
JWT_SECRET_KEY=<SECURE_JWT_SECRET>

# Application Configuration
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
LOG_FORMAT=json

# External Services (optional)
ELASTICSEARCH_URL=http://elasticsearch:9200
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
EOF

# Secure the environment file
chmod 600 .env.prod
```

### 3. Create Docker Secrets

```bash
# Create secrets for sensitive data
echo "<SECURE_POSTGRES_PASSWORD>" | docker secret create postgres_password -
echo "<SECURE_REDIS_PASSWORD>" | docker secret create redis_password -
echo "<SECURE_SECRET_KEY>" | docker secret create secret_key -
echo "<SECURE_JWT_SECRET>" | docker secret create jwt_secret_key -
```

### 4. Generate SSL Certificates

```bash
# Create SSL directory
mkdir -p nginx/ssl

# Generate self-signed certificate (replace with real certificates in production)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout nginx/ssl/key.pem \
    -out nginx/ssl/cert.pem \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=yourdomain.com"

# Set proper permissions
chmod 600 nginx/ssl/key.pem
chmod 644 nginx/ssl/cert.pem
```

### 5. Deploy the Application

```bash
# Build and start production services
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d

# Check service status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f
```

### 6. Initialize the Database

```bash
# Run database migrations
docker-compose -f docker-compose.prod.yml exec app python scripts/migrate.py

# Create initial admin user (optional)
docker-compose -f docker-compose.prod.yml exec app python scripts/create_admin.py
```

### 7. Verify Deployment

```bash
# Check application health
curl -k https://localhost/api/health

# Check all services
docker-compose -f docker-compose.prod.yml exec app python scripts/health_check.py
```

## Kubernetes Deployment

### 1. Prepare Kubernetes Cluster

Ensure you have a Kubernetes cluster with:
- Ingress controller (nginx-ingress recommended)
- Storage classes: `fast-ssd` and `shared-storage`
- LoadBalancer support

### 2. Create Secrets

```bash
# Create namespace
kubectl apply -f k8s/namespace.yaml

# Create secrets (base64 encode your values)
kubectl create secret generic wiki-app-secrets \
    --from-literal=postgres-password=<BASE64_ENCODED_PASSWORD> \
    --from-literal=redis-password=<BASE64_ENCODED_PASSWORD> \
    --from-literal=secret-key=<BASE64_ENCODED_SECRET> \
    --from-literal=jwt-secret-key=<BASE64_ENCODED_JWT_SECRET> \
    -n wiki-app

# Create TLS secret
kubectl create secret tls wiki-app-tls \
    --cert=nginx/ssl/cert.pem \
    --key=nginx/ssl/key.pem \
    -n wiki-app
```

### 3. Deploy Services

```bash
# Deploy in order
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/app.yaml

# Check deployment status
kubectl get pods -n wiki-app
kubectl get services -n wiki-app
```

### 4. Configure Ingress

```bash
# Create ingress for external access
cat > k8s/ingress.yaml << 'EOF'
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: wiki-app-ingress
  namespace: wiki-app
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
spec:
  tls:
  - hosts:
    - yourdomain.com
    secretName: wiki-app-tls
  rules:
  - host: yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: nginx-service
            port:
              number: 80
EOF

kubectl apply -f k8s/ingress.yaml
```

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `ENVIRONMENT` | Deployment environment | `development` | No |
| `DEBUG` | Enable debug mode | `false` | No |
| `DATABASE_URL` | PostgreSQL connection URL | - | Yes |
| `REDIS_URL` | Redis connection URL | - | Yes |
| `SECRET_KEY` | Application secret key | - | Yes |
| `JWT_SECRET_KEY` | JWT signing key | - | Yes |
| `LOG_LEVEL` | Logging level | `INFO` | No |
| `LOG_FORMAT` | Log format (text/json) | `json` | No |
| `MAX_UPLOAD_SIZE` | Max file upload size | `104857600` | No |
| `WORKERS` | Number of worker processes | `4` | No |

### Database Configuration

The PostgreSQL configuration is optimized for production workloads:

- **Connection pooling**: 200 max connections
- **Memory settings**: 512MB shared buffers
- **Logging**: Slow queries (>1s) logged
- **Backup**: Automated daily backups with 30-day retention

### Redis Configuration

Redis is configured for caching and session management:

- **Memory limit**: 1GB with LRU eviction
- **Persistence**: AOF enabled with periodic snapshots
- **Security**: Password authentication required

## Monitoring and Logging

### System Monitoring

The deployment includes comprehensive monitoring:

```bash
# Start monitoring services
python3 scripts/monitoring.py &
python3 scripts/container_monitoring.py &
python3 scripts/log_aggregation.py &
```

### Monitoring Dashboard

Access monitoring data:

```bash
# View system metrics
cat /app/logs/monitoring_dashboard.json

# View container metrics
cat /app/logs/container_monitoring_dashboard.json

# View log aggregation stats
cat /app/logs/aggregation_stats.json
```

### Log Management

Logs are automatically rotated and aggregated:

- **Application logs**: `/app/logs/app.log`
- **Error logs**: `/app/logs/error.log`
- **Security logs**: `/app/logs/security.log`
- **Database logs**: `/app/logs/database.log`
- **Audit logs**: `/app/logs/audit.log`

### Alerting

Configure webhook alerts:

```bash
# Set alert webhook URL
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Test alert
curl -X POST $ALERT_WEBHOOK_URL -H 'Content-type: application/json' \
    --data '{"text":"Test alert from Wiki App"}'
```

## Backup and Recovery

### Automated Backups

Backups run daily at 2 AM:

```bash
# Manual backup
./scripts/backup.sh

# List available backups
./scripts/restore.sh --list

# Restore from backup
./scripts/restore.sh wiki_backup_20231201_120000.sql.gz
```

### Backup Components

1. **Database**: Full PostgreSQL dump with compression
2. **Files**: Uploaded files and attachments
3. **Logs**: Recent application logs
4. **Configuration**: Environment and configuration files

### Recovery Procedures

#### Database Recovery

```bash
# Stop application
docker-compose -f docker-compose.prod.yml stop app worker

# Restore database
./scripts/restore.sh --force backup_file.sql.gz

# Start application
docker-compose -f docker-compose.prod.yml start app worker
```

#### File Recovery

```bash
# Extract file backup
tar -xzf uploads_backup_20231201_120000.tar.gz -C /opt/wiki/data/

# Set permissions
chown -R 1001:1001 /opt/wiki/data/uploads
```

### Disaster Recovery

For complete system recovery:

1. **Provision new infrastructure**
2. **Install dependencies**
3. **Restore configuration files**
4. **Restore database from backup**
5. **Restore uploaded files**
6. **Start services and verify**

## Security Considerations

### Container Security

- **Non-root users**: All containers run as non-root
- **Read-only filesystems**: Where possible
- **Security scanning**: Regular image vulnerability scans
- **Secrets management**: Docker secrets for sensitive data

### Network Security

- **TLS encryption**: All external traffic encrypted
- **Internal networks**: Isolated container networks
- **Rate limiting**: API endpoint rate limiting
- **Firewall rules**: Restrict unnecessary ports

### Application Security

- **Authentication**: JWT-based with secure defaults
- **Authorization**: Role-based access control
- **Input validation**: Comprehensive input sanitization
- **File uploads**: Malware scanning and type validation
- **Audit logging**: Complete audit trail

### Security Monitoring

- **Failed login attempts**: Automated detection
- **Suspicious patterns**: Request pattern analysis
- **File access**: Security audit trails
- **System changes**: Configuration change tracking

## Troubleshooting

### Common Issues

#### Application Won't Start

```bash
# Check container logs
docker-compose -f docker-compose.prod.yml logs app

# Check database connectivity
docker-compose -f docker-compose.prod.yml exec app python -c "
import asyncpg
import asyncio
async def test():
    conn = await asyncpg.connect('postgresql://wiki:password@db:5432/wiki')
    print(await conn.fetchval('SELECT 1'))
    await conn.close()
asyncio.run(test())
"
```

#### Database Connection Issues

```bash
# Check PostgreSQL status
docker-compose -f docker-compose.prod.yml exec db pg_isready -U wiki

# Check database logs
docker-compose -f docker-compose.prod.yml logs db

# Reset database connection pool
docker-compose -f docker-compose.prod.yml restart app
```

#### High Memory Usage

```bash
# Check container resource usage
docker stats

# Check application metrics
python3 scripts/monitoring.py --check-memory

# Restart services if needed
docker-compose -f docker-compose.prod.yml restart
```

#### SSL Certificate Issues

```bash
# Check certificate validity
openssl x509 -in nginx/ssl/cert.pem -text -noout

# Regenerate certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem

# Restart nginx
docker-compose -f docker-compose.prod.yml restart nginx
```

### Performance Tuning

#### Database Optimization

```bash
# Run database optimization
docker-compose -f docker-compose.prod.yml exec app python scripts/optimize_database.py

# Check slow queries
docker-compose -f docker-compose.prod.yml exec db psql -U wiki -c "
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;"
```

#### Application Scaling

```bash
# Scale application containers
docker-compose -f docker-compose.prod.yml up -d --scale app=3 --scale worker=2

# Check load balancing
curl -H "Host: yourdomain.com" http://localhost/api/health
```

## Maintenance

### Regular Maintenance Tasks

#### Daily
- Monitor system health and alerts
- Check backup completion
- Review error logs

#### Weekly
- Update system packages
- Clean up old log files
- Review security alerts

#### Monthly
- Update Docker images
- Review and rotate secrets
- Performance analysis
- Capacity planning

### Update Procedures

#### Application Updates

```bash
# Pull latest code
git pull origin main

# Build new images
docker-compose -f docker-compose.prod.yml build

# Rolling update
docker-compose -f docker-compose.prod.yml up -d --no-deps app
```

#### System Updates

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Update Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Restart services
docker-compose -f docker-compose.prod.yml restart
```

### Health Checks

```bash
# Comprehensive health check
python3 scripts/health_check.py --full

# Service-specific checks
curl -k https://localhost/api/health
docker-compose -f docker-compose.prod.yml exec db pg_isready
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping
```

### Log Rotation

```bash
# Manual log rotation
docker-compose -f docker-compose.prod.yml exec app logrotate /etc/logrotate.conf

# Clean old logs
find /opt/wiki/logs -name "*.log.*" -mtime +30 -delete
```

## Support and Documentation

### Additional Resources

- **API Documentation**: Available at `/api/docs` (development only)
- **Architecture Documentation**: See `ARCHITECTURE.md`
- **Security Documentation**: See `SECURITY.md`
- **Contributing Guidelines**: See `CONTRIBUTING.md`

### Getting Help

1. **Check logs**: Always start with application and system logs
2. **Review monitoring**: Check monitoring dashboards for anomalies
3. **Search documentation**: Use this guide and additional documentation
4. **Community support**: Check project issues and discussions

### Reporting Issues

When reporting issues, include:

- **Environment details**: OS, Docker version, deployment method
- **Error messages**: Complete error logs and stack traces
- **Steps to reproduce**: Detailed reproduction steps
- **System state**: Resource usage, container status, recent changes

---

This deployment guide provides comprehensive instructions for production deployment of the Wiki Documentation App. Follow the security best practices and monitoring recommendations for a robust, scalable deployment.