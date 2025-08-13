#!/usr/bin/env python3
"""
Comprehensive monitoring script for Wiki Documentation App.
Monitors system health, performance metrics, and generates alerts.
"""

import asyncio
import json
import logging
import os
import psutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import aiohttp
import asyncpg
import aioredis
from dataclasses import dataclass, asdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/monitoring.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class HealthCheck:
    """Health check result."""
    service: str
    status: str
    response_time: float
    details: Dict[str, Any]
    timestamp: datetime


@dataclass
class MetricData:
    """System metric data."""
    name: str
    value: float
    unit: str
    timestamp: datetime
    tags: Dict[str, str]


class SystemMonitor:
    """System resource monitoring."""
    
    def __init__(self):
        self.metrics: List[MetricData] = []
    
    def collect_cpu_metrics(self) -> List[MetricData]:
        """Collect CPU metrics."""
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        load_avg = os.getloadavg()
        
        timestamp = datetime.utcnow()
        
        return [
            MetricData("cpu.usage_percent", cpu_percent, "%", timestamp, {"type": "system"}),
            MetricData("cpu.count", cpu_count, "cores", timestamp, {"type": "system"}),
            MetricData("cpu.load_avg_1m", load_avg[0], "load", timestamp, {"type": "system"}),
            MetricData("cpu.load_avg_5m", load_avg[1], "load", timestamp, {"type": "system"}),
            MetricData("cpu.load_avg_15m", load_avg[2], "load", timestamp, {"type": "system"}),
        ]
    
    def collect_memory_metrics(self) -> List[MetricData]:
        """Collect memory metrics."""
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        timestamp = datetime.utcnow()
        
        return [
            MetricData("memory.total", memory.total, "bytes", timestamp, {"type": "system"}),
            MetricData("memory.available", memory.available, "bytes", timestamp, {"type": "system"}),
            MetricData("memory.used", memory.used, "bytes", timestamp, {"type": "system"}),
            MetricData("memory.usage_percent", memory.percent, "%", timestamp, {"type": "system"}),
            MetricData("swap.total", swap.total, "bytes", timestamp, {"type": "system"}),
            MetricData("swap.used", swap.used, "bytes", timestamp, {"type": "system"}),
            MetricData("swap.usage_percent", swap.percent, "%", timestamp, {"type": "system"}),
        ]
    
    def collect_disk_metrics(self) -> List[MetricData]:
        """Collect disk metrics."""
        metrics = []
        timestamp = datetime.utcnow()
        
        # Disk usage for important paths
        paths = ["/", "/app/uploads", "/app/logs", "/backups"]
        
        for path in paths:
            if os.path.exists(path):
                usage = psutil.disk_usage(path)
                path_tag = path.replace("/", "_") or "root"
                
                metrics.extend([
                    MetricData(f"disk.total", usage.total, "bytes", timestamp, {"path": path, "mount": path_tag}),
                    MetricData(f"disk.used", usage.used, "bytes", timestamp, {"path": path, "mount": path_tag}),
                    MetricData(f"disk.free", usage.free, "bytes", timestamp, {"path": path, "mount": path_tag}),
                    MetricData(f"disk.usage_percent", (usage.used / usage.total) * 100, "%", timestamp, {"path": path, "mount": path_tag}),
                ])
        
        # Disk I/O
        disk_io = psutil.disk_io_counters()
        if disk_io:
            metrics.extend([
                MetricData("disk.read_bytes", disk_io.read_bytes, "bytes", timestamp, {"type": "io"}),
                MetricData("disk.write_bytes", disk_io.write_bytes, "bytes", timestamp, {"type": "io"}),
                MetricData("disk.read_count", disk_io.read_count, "operations", timestamp, {"type": "io"}),
                MetricData("disk.write_count", disk_io.write_count, "operations", timestamp, {"type": "io"}),
            ])
        
        return metrics
    
    def collect_network_metrics(self) -> List[MetricData]:
        """Collect network metrics."""
        net_io = psutil.net_io_counters()
        timestamp = datetime.utcnow()
        
        if net_io:
            return [
                MetricData("network.bytes_sent", net_io.bytes_sent, "bytes", timestamp, {"type": "network"}),
                MetricData("network.bytes_recv", net_io.bytes_recv, "bytes", timestamp, {"type": "network"}),
                MetricData("network.packets_sent", net_io.packets_sent, "packets", timestamp, {"type": "network"}),
                MetricData("network.packets_recv", net_io.packets_recv, "packets", timestamp, {"type": "network"}),
                MetricData("network.errin", net_io.errin, "errors", timestamp, {"type": "network"}),
                MetricData("network.errout", net_io.errout, "errors", timestamp, {"type": "network"}),
            ]
        
        return []
    
    def collect_process_metrics(self) -> List[MetricData]:
        """Collect process-specific metrics."""
        metrics = []
        timestamp = datetime.utcnow()
        
        # Find application processes
        app_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_info']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if any(keyword in cmdline.lower() for keyword in ['gunicorn', 'uvicorn', 'celery', 'wiki']):
                    app_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Collect metrics for each process
        for proc in app_processes:
            try:
                proc_name = proc.info['name']
                pid = proc.info['pid']
                
                metrics.extend([
                    MetricData("process.cpu_percent", proc.info['cpu_percent'], "%", timestamp, {"process": proc_name, "pid": str(pid)}),
                    MetricData("process.memory_rss", proc.info['memory_info'].rss, "bytes", timestamp, {"process": proc_name, "pid": str(pid)}),
                    MetricData("process.memory_vms", proc.info['memory_info'].vms, "bytes", timestamp, {"process": proc_name, "pid": str(pid)}),
                ])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return metrics
    
    def collect_all_metrics(self) -> List[MetricData]:
        """Collect all system metrics."""
        all_metrics = []
        
        try:
            all_metrics.extend(self.collect_cpu_metrics())
            all_metrics.extend(self.collect_memory_metrics())
            all_metrics.extend(self.collect_disk_metrics())
            all_metrics.extend(self.collect_network_metrics())
            all_metrics.extend(self.collect_process_metrics())
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
        
        return all_metrics


class ServiceHealthChecker:
    """Health checker for application services."""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def check_http_service(self, name: str, url: str) -> HealthCheck:
        """Check HTTP service health."""
        start_time = time.time()
        
        try:
            async with self.session.get(url) as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    data = await response.json()
                    return HealthCheck(
                        service=name,
                        status="healthy",
                        response_time=response_time,
                        details={"status_code": response.status, "response": data},
                        timestamp=datetime.utcnow()
                    )
                else:
                    return HealthCheck(
                        service=name,
                        status="unhealthy",
                        response_time=response_time,
                        details={"status_code": response.status, "error": "Non-200 status code"},
                        timestamp=datetime.utcnow()
                    )
        
        except Exception as e:
            response_time = time.time() - start_time
            return HealthCheck(
                service=name,
                status="unhealthy",
                response_time=response_time,
                details={"error": str(e)},
                timestamp=datetime.utcnow()
            )
    
    async def check_database(self) -> HealthCheck:
        """Check PostgreSQL database health."""
        start_time = time.time()
        
        try:
            db_url = os.getenv("DATABASE_URL", "postgresql://wiki:wiki@localhost:5432/wiki")
            
            conn = await asyncpg.connect(db_url)
            
            # Test basic query
            result = await conn.fetchval("SELECT 1")
            
            # Get database stats
            stats = await conn.fetchrow("""
                SELECT 
                    (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_connections,
                    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections,
                    pg_database_size(current_database()) as db_size
            """)
            
            await conn.close()
            
            response_time = time.time() - start_time
            
            return HealthCheck(
                service="postgresql",
                status="healthy",
                response_time=response_time,
                details={
                    "query_result": result,
                    "active_connections": stats['active_connections'],
                    "max_connections": stats['max_connections'],
                    "database_size": stats['db_size']
                },
                timestamp=datetime.utcnow()
            )
        
        except Exception as e:
            response_time = time.time() - start_time
            return HealthCheck(
                service="postgresql",
                status="unhealthy",
                response_time=response_time,
                details={"error": str(e)},
                timestamp=datetime.utcnow()
            )
    
    async def check_redis(self) -> HealthCheck:
        """Check Redis health."""
        start_time = time.time()
        
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            
            redis = aioredis.from_url(redis_url)
            
            # Test ping
            pong = await redis.ping()
            
            # Get Redis info
            info = await redis.info()
            
            await redis.close()
            
            response_time = time.time() - start_time
            
            return HealthCheck(
                service="redis",
                status="healthy",
                response_time=response_time,
                details={
                    "ping_result": pong,
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory": info.get("used_memory", 0),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0)
                },
                timestamp=datetime.utcnow()
            )
        
        except Exception as e:
            response_time = time.time() - start_time
            return HealthCheck(
                service="redis",
                status="unhealthy",
                response_time=response_time,
                details={"error": str(e)},
                timestamp=datetime.utcnow()
            )


class AlertManager:
    """Alert management and notification system."""
    
    def __init__(self):
        self.alert_thresholds = {
            "cpu_usage": 80.0,
            "memory_usage": 85.0,
            "disk_usage": 90.0,
            "response_time": 5.0,
            "error_rate": 5.0
        }
        self.alert_history: List[Dict] = []
    
    def check_metric_alerts(self, metrics: List[MetricData]) -> List[Dict]:
        """Check metrics against alert thresholds."""
        alerts = []
        
        for metric in metrics:
            alert = self._check_single_metric(metric)
            if alert:
                alerts.append(alert)
        
        return alerts
    
    def _check_single_metric(self, metric: MetricData) -> Optional[Dict]:
        """Check a single metric against thresholds."""
        if metric.name == "cpu.usage_percent" and metric.value > self.alert_thresholds["cpu_usage"]:
            return {
                "type": "cpu_high",
                "severity": "warning",
                "message": f"High CPU usage: {metric.value:.1f}%",
                "metric": asdict(metric),
                "threshold": self.alert_thresholds["cpu_usage"]
            }
        
        elif metric.name == "memory.usage_percent" and metric.value > self.alert_thresholds["memory_usage"]:
            return {
                "type": "memory_high",
                "severity": "warning",
                "message": f"High memory usage: {metric.value:.1f}%",
                "metric": asdict(metric),
                "threshold": self.alert_thresholds["memory_usage"]
            }
        
        elif metric.name == "disk.usage_percent" and metric.value > self.alert_thresholds["disk_usage"]:
            return {
                "type": "disk_high",
                "severity": "critical",
                "message": f"High disk usage on {metric.tags.get('path', 'unknown')}: {metric.value:.1f}%",
                "metric": asdict(metric),
                "threshold": self.alert_thresholds["disk_usage"]
            }
        
        return None
    
    def check_service_alerts(self, health_checks: List[HealthCheck]) -> List[Dict]:
        """Check service health for alerts."""
        alerts = []
        
        for check in health_checks:
            if check.status == "unhealthy":
                alerts.append({
                    "type": "service_down",
                    "severity": "critical",
                    "message": f"Service {check.service} is unhealthy",
                    "health_check": asdict(check)
                })
            
            elif check.response_time > self.alert_thresholds["response_time"]:
                alerts.append({
                    "type": "slow_response",
                    "severity": "warning",
                    "message": f"Slow response from {check.service}: {check.response_time:.2f}s",
                    "health_check": asdict(check),
                    "threshold": self.alert_thresholds["response_time"]
                })
        
        return alerts
    
    async def send_alert(self, alert: Dict):
        """Send alert notification."""
        # Log the alert
        logger.warning(f"ALERT [{alert['severity'].upper()}]: {alert['message']}")
        
        # Store in history
        alert['timestamp'] = datetime.utcnow().isoformat()
        self.alert_history.append(alert)
        
        # Keep only last 1000 alerts
        if len(self.alert_history) > 1000:
            self.alert_history = self.alert_history[-1000:]
        
        # Here you could add integrations with:
        # - Slack/Discord webhooks
        # - Email notifications
        # - PagerDuty/OpsGenie
        # - Prometheus Alertmanager
        
        # Example webhook notification (uncomment and configure)
        # await self._send_webhook_alert(alert)
    
    async def _send_webhook_alert(self, alert: Dict):
        """Send alert via webhook."""
        webhook_url = os.getenv("ALERT_WEBHOOK_URL")
        if not webhook_url:
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "text": f"🚨 {alert['message']}",
                    "severity": alert['severity'],
                    "timestamp": alert['timestamp']
                }
                
                async with session.post(webhook_url, json=payload) as response:
                    if response.status == 200:
                        logger.info("Alert sent via webhook successfully")
                    else:
                        logger.error(f"Failed to send webhook alert: {response.status}")
        
        except Exception as e:
            logger.error(f"Error sending webhook alert: {e}")


class MonitoringDashboard:
    """Generate monitoring dashboard data."""
    
    def __init__(self):
        self.metrics_history: List[MetricData] = []
        self.health_history: List[HealthCheck] = []
    
    def add_metrics(self, metrics: List[MetricData]):
        """Add metrics to history."""
        self.metrics_history.extend(metrics)
        
        # Keep only last 24 hours of data
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        self.metrics_history = [m for m in self.metrics_history if m.timestamp > cutoff_time]
    
    def add_health_checks(self, health_checks: List[HealthCheck]):
        """Add health checks to history."""
        self.health_history.extend(health_checks)
        
        # Keep only last 24 hours of data
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        self.health_history = [h for h in self.health_history if h.timestamp > cutoff_time]
    
    def generate_dashboard_data(self) -> Dict:
        """Generate dashboard data."""
        current_time = datetime.utcnow()
        
        # Get latest metrics
        latest_metrics = {}
        for metric in reversed(self.metrics_history):
            if metric.name not in latest_metrics:
                latest_metrics[metric.name] = metric
        
        # Get latest health checks
        latest_health = {}
        for health in reversed(self.health_history):
            if health.service not in latest_health:
                latest_health[health.service] = health
        
        # Calculate uptime percentages
        uptime_stats = {}
        for service in latest_health.keys():
            service_checks = [h for h in self.health_history if h.service == service]
            if service_checks:
                healthy_count = sum(1 for h in service_checks if h.status == "healthy")
                uptime_stats[service] = (healthy_count / len(service_checks)) * 100
        
        return {
            "timestamp": current_time.isoformat(),
            "system_metrics": {name: asdict(metric) for name, metric in latest_metrics.items()},
            "service_health": {name: asdict(health) for name, health in latest_health.items()},
            "uptime_stats": uptime_stats,
            "summary": {
                "total_metrics": len(self.metrics_history),
                "total_health_checks": len(self.health_history),
                "monitoring_duration_hours": 24
            }
        }
    
    def save_dashboard_data(self, filepath: str):
        """Save dashboard data to file."""
        dashboard_data = self.generate_dashboard_data()
        
        with open(filepath, 'w') as f:
            json.dump(dashboard_data, f, indent=2, default=str)


async def main():
    """Main monitoring loop."""
    logger.info("Starting Wiki App monitoring system")
    
    system_monitor = SystemMonitor()
    alert_manager = AlertManager()
    dashboard = MonitoringDashboard()
    
    # Monitoring interval (seconds)
    interval = int(os.getenv("MONITORING_INTERVAL", "60"))
    
    while True:
        try:
            logger.info("Running monitoring cycle")
            
            # Collect system metrics
            metrics = system_monitor.collect_all_metrics()
            dashboard.add_metrics(metrics)
            
            # Check service health
            async with ServiceHealthChecker() as health_checker:
                health_checks = []
                
                # Check application health
                app_url = os.getenv("APP_HEALTH_URL", "http://localhost:8000/api/health")
                health_checks.append(await health_checker.check_http_service("wiki-app", app_url))
                
                # Check database
                health_checks.append(await health_checker.check_database())
                
                # Check Redis
                health_checks.append(await health_checker.check_redis())
            
            dashboard.add_health_checks(health_checks)
            
            # Check for alerts
            metric_alerts = alert_manager.check_metric_alerts(metrics)
            service_alerts = alert_manager.check_service_alerts(health_checks)
            
            all_alerts = metric_alerts + service_alerts
            
            # Send alerts
            for alert in all_alerts:
                await alert_manager.send_alert(alert)
            
            # Save dashboard data
            dashboard_file = "/app/logs/monitoring_dashboard.json"
            dashboard.save_dashboard_data(dashboard_file)
            
            # Log summary
            healthy_services = sum(1 for h in health_checks if h.status == "healthy")
            total_services = len(health_checks)
            
            logger.info(f"Monitoring cycle completed: {healthy_services}/{total_services} services healthy, "
                       f"{len(all_alerts)} alerts generated")
            
            # Wait for next cycle
            await asyncio.sleep(interval)
            
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in monitoring cycle: {e}")
            await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())