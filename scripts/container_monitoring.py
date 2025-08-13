#!/usr/bin/env python3
"""
Container monitoring and resource usage tracking for Wiki App.
Monitors Docker containers, resource usage, and performance metrics.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import docker
import psutil
from dataclasses import dataclass, asdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/container_monitoring.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ContainerMetrics:
    """Container resource metrics."""
    container_id: str
    container_name: str
    image: str
    status: str
    cpu_percent: float
    memory_usage: int
    memory_limit: int
    memory_percent: float
    network_rx_bytes: int
    network_tx_bytes: int
    block_read_bytes: int
    block_write_bytes: int
    pids: int
    timestamp: datetime


@dataclass
class ContainerHealth:
    """Container health status."""
    container_id: str
    container_name: str
    status: str
    health_status: Optional[str]
    restart_count: int
    uptime: timedelta
    last_restart: Optional[datetime]
    exit_code: Optional[int]
    timestamp: datetime


class DockerMonitor:
    """Monitor Docker containers and their resources."""
    
    def __init__(self):
        try:
            self.client = docker.from_env()
            logger.info("Connected to Docker daemon")
        except Exception as e:
            logger.error(f"Failed to connect to Docker daemon: {e}")
            raise
    
    def get_wiki_containers(self) -> List[docker.models.containers.Container]:
        """Get all containers related to the wiki app."""
        try:
            all_containers = self.client.containers.list(all=True)
            wiki_containers = []
            
            # Filter containers by name patterns or labels
            wiki_patterns = ['wiki', 'postgres', 'redis', 'nginx', 'celery']
            
            for container in all_containers:
                container_name = container.name.lower()
                if any(pattern in container_name for pattern in wiki_patterns):
                    wiki_containers.append(container)
            
            return wiki_containers
            
        except Exception as e:
            logger.error(f"Error getting containers: {e}")
            return []
    
    def get_container_metrics(self, container: docker.models.containers.Container) -> Optional[ContainerMetrics]:
        """Get resource metrics for a container."""
        try:
            # Get container stats
            stats = container.stats(stream=False)
            
            # Calculate CPU percentage
            cpu_percent = self._calculate_cpu_percent(stats)
            
            # Get memory stats
            memory_usage = stats['memory_stats'].get('usage', 0)
            memory_limit = stats['memory_stats'].get('limit', 0)
            memory_percent = (memory_usage / memory_limit * 100) if memory_limit > 0 else 0
            
            # Get network stats
            network_stats = stats.get('networks', {})
            network_rx_bytes = sum(net.get('rx_bytes', 0) for net in network_stats.values())
            network_tx_bytes = sum(net.get('tx_bytes', 0) for net in network_stats.values())
            
            # Get block I/O stats
            blkio_stats = stats.get('blkio_stats', {}).get('io_service_bytes_recursive', [])
            block_read_bytes = sum(item.get('value', 0) for item in blkio_stats if item.get('op') == 'Read')
            block_write_bytes = sum(item.get('value', 0) for item in blkio_stats if item.get('op') == 'Write')
            
            # Get process count
            pids = stats.get('pids_stats', {}).get('current', 0)
            
            return ContainerMetrics(
                container_id=container.id[:12],
                container_name=container.name,
                image=container.image.tags[0] if container.image.tags else container.image.id[:12],
                status=container.status,
                cpu_percent=cpu_percent,
                memory_usage=memory_usage,
                memory_limit=memory_limit,
                memory_percent=memory_percent,
                network_rx_bytes=network_rx_bytes,
                network_tx_bytes=network_tx_bytes,
                block_read_bytes=block_read_bytes,
                block_write_bytes=block_write_bytes,
                pids=pids,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Error getting metrics for container {container.name}: {e}")
            return None
    
    def _calculate_cpu_percent(self, stats: Dict) -> float:
        """Calculate CPU percentage from container stats."""
        try:
            cpu_stats = stats['cpu_stats']
            precpu_stats = stats['precpu_stats']
            
            cpu_delta = cpu_stats['cpu_usage']['total_usage'] - precpu_stats['cpu_usage']['total_usage']
            system_delta = cpu_stats['system_cpu_usage'] - precpu_stats['system_cpu_usage']
            
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * len(cpu_stats['cpu_usage']['percpu_usage']) * 100.0
                return round(cpu_percent, 2)
            
            return 0.0
            
        except (KeyError, ZeroDivisionError):
            return 0.0
    
    def get_container_health(self, container: docker.models.containers.Container) -> ContainerHealth:
        """Get health status for a container."""
        try:
            # Reload container to get latest info
            container.reload()
            
            # Get container attributes
            attrs = container.attrs
            
            # Calculate uptime
            started_at = attrs['State'].get('StartedAt')
            if started_at:
                start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                uptime = datetime.utcnow().replace(tzinfo=start_time.tzinfo) - start_time
            else:
                uptime = timedelta(0)
            
            # Get restart count
            restart_count = attrs['RestartCount']
            
            # Get last restart time
            last_restart = None
            if restart_count > 0:
                finished_at = attrs['State'].get('FinishedAt')
                if finished_at and finished_at != '0001-01-01T00:00:00Z':
                    last_restart = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
            
            # Get health status
            health_status = None
            health = attrs.get('State', {}).get('Health')
            if health:
                health_status = health.get('Status')
            
            # Get exit code
            exit_code = attrs['State'].get('ExitCode')
            
            return ContainerHealth(
                container_id=container.id[:12],
                container_name=container.name,
                status=container.status,
                health_status=health_status,
                restart_count=restart_count,
                uptime=uptime,
                last_restart=last_restart,
                exit_code=exit_code,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Error getting health for container {container.name}: {e}")
            return ContainerHealth(
                container_id=container.id[:12],
                container_name=container.name,
                status="unknown",
                health_status=None,
                restart_count=0,
                uptime=timedelta(0),
                last_restart=None,
                exit_code=None,
                timestamp=datetime.utcnow()
            )
    
    def get_docker_system_info(self) -> Dict[str, Any]:
        """Get Docker system information."""
        try:
            info = self.client.info()
            version = self.client.version()
            
            return {
                "docker_version": version.get('Version'),
                "api_version": version.get('ApiVersion'),
                "containers_total": info.get('Containers', 0),
                "containers_running": info.get('ContainersRunning', 0),
                "containers_paused": info.get('ContainersPaused', 0),
                "containers_stopped": info.get('ContainersStopped', 0),
                "images_total": info.get('Images', 0),
                "memory_total": info.get('MemTotal', 0),
                "cpu_count": info.get('NCPU', 0),
                "storage_driver": info.get('Driver'),
                "kernel_version": info.get('KernelVersion'),
                "operating_system": info.get('OperatingSystem'),
                "server_version": info.get('ServerVersion')
            }
            
        except Exception as e:
            logger.error(f"Error getting Docker system info: {e}")
            return {}


class ContainerAlertManager:
    """Manage alerts for container issues."""
    
    def __init__(self):
        self.alert_thresholds = {
            "cpu_percent": 80.0,
            "memory_percent": 85.0,
            "restart_count": 5,
            "unhealthy_duration": 300  # 5 minutes
        }
        self.alert_history: List[Dict] = []
    
    def check_container_alerts(self, metrics: List[ContainerMetrics], health: List[ContainerHealth]) -> List[Dict]:
        """Check containers for alert conditions."""
        alerts = []
        
        # Check resource usage alerts
        for metric in metrics:
            alerts.extend(self._check_resource_alerts(metric))
        
        # Check health alerts
        for health_check in health:
            alerts.extend(self._check_health_alerts(health_check))
        
        return alerts
    
    def _check_resource_alerts(self, metrics: ContainerMetrics) -> List[Dict]:
        """Check resource usage for alerts."""
        alerts = []
        
        # High CPU usage
        if metrics.cpu_percent > self.alert_thresholds["cpu_percent"]:
            alerts.append({
                "type": "high_cpu",
                "severity": "warning",
                "container": metrics.container_name,
                "message": f"High CPU usage: {metrics.cpu_percent:.1f}%",
                "value": metrics.cpu_percent,
                "threshold": self.alert_thresholds["cpu_percent"],
                "timestamp": metrics.timestamp.isoformat()
            })
        
        # High memory usage
        if metrics.memory_percent > self.alert_thresholds["memory_percent"]:
            alerts.append({
                "type": "high_memory",
                "severity": "warning",
                "container": metrics.container_name,
                "message": f"High memory usage: {metrics.memory_percent:.1f}%",
                "value": metrics.memory_percent,
                "threshold": self.alert_thresholds["memory_percent"],
                "timestamp": metrics.timestamp.isoformat()
            })
        
        return alerts
    
    def _check_health_alerts(self, health: ContainerHealth) -> List[Dict]:
        """Check container health for alerts."""
        alerts = []
        
        # Container not running
        if health.status != "running":
            alerts.append({
                "type": "container_down",
                "severity": "critical",
                "container": health.container_name,
                "message": f"Container is {health.status}",
                "status": health.status,
                "exit_code": health.exit_code,
                "timestamp": health.timestamp.isoformat()
            })
        
        # High restart count
        if health.restart_count > self.alert_thresholds["restart_count"]:
            alerts.append({
                "type": "high_restarts",
                "severity": "warning",
                "container": health.container_name,
                "message": f"High restart count: {health.restart_count}",
                "restart_count": health.restart_count,
                "threshold": self.alert_thresholds["restart_count"],
                "timestamp": health.timestamp.isoformat()
            })
        
        # Unhealthy status
        if health.health_status == "unhealthy":
            alerts.append({
                "type": "unhealthy_container",
                "severity": "critical",
                "container": health.container_name,
                "message": f"Container health check failed",
                "health_status": health.health_status,
                "timestamp": health.timestamp.isoformat()
            })
        
        return alerts
    
    async def send_alert(self, alert: Dict):
        """Send container alert."""
        logger.warning(f"CONTAINER ALERT [{alert['severity'].upper()}]: {alert['message']}")
        
        # Store in history
        self.alert_history.append(alert)
        
        # Keep only last 1000 alerts
        if len(self.alert_history) > 1000:
            self.alert_history = self.alert_history[-1000:]


class ContainerMonitoringDashboard:
    """Generate container monitoring dashboard."""
    
    def __init__(self):
        self.metrics_history: List[ContainerMetrics] = []
        self.health_history: List[ContainerHealth] = []
    
    def add_metrics(self, metrics: List[ContainerMetrics]):
        """Add metrics to history."""
        self.metrics_history.extend(metrics)
        
        # Keep only last 24 hours
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        self.metrics_history = [m for m in self.metrics_history if m.timestamp > cutoff_time]
    
    def add_health_data(self, health_data: List[ContainerHealth]):
        """Add health data to history."""
        self.health_history.extend(health_data)
        
        # Keep only last 24 hours
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        self.health_history = [h for h in self.health_history if h.timestamp > cutoff_time]
    
    def generate_dashboard_data(self, docker_info: Dict) -> Dict:
        """Generate dashboard data."""
        # Get latest metrics for each container
        latest_metrics = {}
        for metric in reversed(self.metrics_history):
            if metric.container_name not in latest_metrics:
                latest_metrics[metric.container_name] = metric
        
        # Get latest health for each container
        latest_health = {}
        for health in reversed(self.health_history):
            if health.container_name not in latest_health:
                latest_health[health.container_name] = health
        
        # Calculate resource usage trends
        resource_trends = self._calculate_resource_trends()
        
        # Calculate uptime statistics
        uptime_stats = {}
        for container_name, health in latest_health.items():
            uptime_stats[container_name] = {
                "uptime_seconds": health.uptime.total_seconds(),
                "restart_count": health.restart_count,
                "status": health.status
            }
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "docker_system": docker_info,
            "container_metrics": {name: asdict(metric) for name, metric in latest_metrics.items()},
            "container_health": {name: asdict(health) for name, health in latest_health.items()},
            "resource_trends": resource_trends,
            "uptime_stats": uptime_stats,
            "summary": {
                "total_containers": len(latest_metrics),
                "running_containers": sum(1 for h in latest_health.values() if h.status == "running"),
                "total_metrics_collected": len(self.metrics_history),
                "monitoring_duration_hours": 24
            }
        }
    
    def _calculate_resource_trends(self) -> Dict:
        """Calculate resource usage trends."""
        trends = {}
        
        # Group metrics by container
        container_metrics = {}
        for metric in self.metrics_history:
            if metric.container_name not in container_metrics:
                container_metrics[metric.container_name] = []
            container_metrics[metric.container_name].append(metric)
        
        # Calculate trends for each container
        for container_name, metrics in container_metrics.items():
            if len(metrics) < 2:
                continue
            
            # Sort by timestamp
            metrics.sort(key=lambda x: x.timestamp)
            
            # Calculate averages for different time periods
            now = datetime.utcnow()
            hour_ago = now - timedelta(hours=1)
            
            recent_metrics = [m for m in metrics if m.timestamp > hour_ago]
            
            if recent_metrics:
                avg_cpu = sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics)
                avg_memory = sum(m.memory_percent for m in recent_metrics) / len(recent_metrics)
                
                trends[container_name] = {
                    "avg_cpu_1h": round(avg_cpu, 2),
                    "avg_memory_1h": round(avg_memory, 2),
                    "data_points": len(recent_metrics)
                }
        
        return trends
    
    def save_dashboard_data(self, filepath: str, docker_info: Dict):
        """Save dashboard data to file."""
        dashboard_data = self.generate_dashboard_data(docker_info)
        
        # Convert datetime objects to strings for JSON serialization
        def convert_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, timedelta):
                return obj.total_seconds()
            return obj
        
        with open(filepath, 'w') as f:
            json.dump(dashboard_data, f, indent=2, default=convert_datetime)


async def main():
    """Main container monitoring loop."""
    logger.info("Starting container monitoring system")
    
    try:
        monitor = DockerMonitor()
        alert_manager = ContainerAlertManager()
        dashboard = ContainerMonitoringDashboard()
        
        # Monitoring interval
        interval = int(os.getenv("CONTAINER_MONITORING_INTERVAL", "60"))
        
        while True:
            try:
                logger.info("Running container monitoring cycle")
                
                # Get wiki containers
                containers = monitor.get_wiki_containers()
                logger.info(f"Found {len(containers)} wiki-related containers")
                
                # Collect metrics and health data
                metrics = []
                health_data = []
                
                for container in containers:
                    # Get metrics
                    container_metrics = monitor.get_container_metrics(container)
                    if container_metrics:
                        metrics.append(container_metrics)
                    
                    # Get health
                    container_health = monitor.get_container_health(container)
                    health_data.append(container_health)
                
                # Add to dashboard
                dashboard.add_metrics(metrics)
                dashboard.add_health_data(health_data)
                
                # Check for alerts
                alerts = alert_manager.check_container_alerts(metrics, health_data)
                
                # Send alerts
                for alert in alerts:
                    await alert_manager.send_alert(alert)
                
                # Get Docker system info
                docker_info = monitor.get_docker_system_info()
                
                # Save dashboard data
                dashboard_file = "/app/logs/container_monitoring_dashboard.json"
                dashboard.save_dashboard_data(dashboard_file, docker_info)
                
                # Log summary
                running_containers = sum(1 for h in health_data if h.status == "running")
                logger.info(f"Container monitoring cycle completed: {running_containers}/{len(containers)} containers running, "
                           f"{len(alerts)} alerts generated")
                
                # Wait for next cycle
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Error in container monitoring cycle: {e}")
                await asyncio.sleep(interval)
                
    except KeyboardInterrupt:
        logger.info("Container monitoring stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in container monitoring: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())