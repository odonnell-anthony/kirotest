#!/usr/bin/env python3
"""
Log aggregation and centralized logging for containerized Wiki App services.
Collects, processes, and forwards logs from multiple containers.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, AsyncGenerator
import aiofiles
import aiohttp
from dataclasses import dataclass, asdict
from collections import defaultdict, deque

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """Structured log entry."""
    timestamp: datetime
    level: str
    service: str
    container: str
    message: str
    correlation_id: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    metadata: Dict[str, Any] = None


class LogParser:
    """Parse different log formats."""
    
    def __init__(self):
        # Regex patterns for different log formats
        self.patterns = {
            'json': re.compile(r'^{.*}$'),
            'structured': re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)\s+-\s+(\w+)\s+-\s+(\w+)\s+-\s+(.+)$'),
            'nginx': re.compile(r'^(\S+)\s+\S+\s+\S+\s+\[([^\]]+)\]\s+"([^"]+)"\s+(\d+)\s+(\d+)\s+"([^"]*)"\s+"([^"]*)"'),
            'gunicorn': re.compile(r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+[+-]\d{4}\]\s+\[(\d+)\]\s+\[(\w+)\]\s+(.+)$')
        }
    
    def parse_log_line(self, line: str, service: str, container: str) -> Optional[LogEntry]:
        """Parse a single log line."""
        line = line.strip()
        if not line:
            return None
        
        try:
            # Try JSON format first
            if self.patterns['json'].match(line):
                return self._parse_json_log(line, service, container)
            
            # Try structured format
            match = self.patterns['structured'].match(line)
            if match:
                return self._parse_structured_log(match, service, container)
            
            # Try nginx format
            if service == 'nginx':
                match = self.patterns['nginx'].match(line)
                if match:
                    return self._parse_nginx_log(match, service, container)
            
            # Try gunicorn format
            if 'gunicorn' in service or 'uvicorn' in service:
                match = self.patterns['gunicorn'].match(line)
                if match:
                    return self._parse_gunicorn_log(match, service, container)
            
            # Fallback to plain text
            return LogEntry(
                timestamp=datetime.utcnow(),
                level='INFO',
                service=service,
                container=container,
                message=line
            )
            
        except Exception as e:
            logger.error(f"Error parsing log line: {e}")
            return None
    
    def _parse_json_log(self, line: str, service: str, container: str) -> LogEntry:
        """Parse JSON formatted log."""
        data = json.loads(line)
        
        # Extract timestamp
        timestamp_str = data.get('timestamp') or data.get('asctime') or data.get('@timestamp')
        if timestamp_str:
            timestamp = self._parse_timestamp(timestamp_str)
        else:
            timestamp = datetime.utcnow()
        
        # Extract level
        level = data.get('level') or data.get('levelname') or 'INFO'
        
        # Extract message
        message = data.get('message') or data.get('msg') or str(data)
        
        # Extract metadata
        metadata = {k: v for k, v in data.items() 
                   if k not in ['timestamp', 'asctime', '@timestamp', 'level', 'levelname', 'message', 'msg']}
        
        return LogEntry(
            timestamp=timestamp,
            level=level.upper(),
            service=service,
            container=container,
            message=message,
            correlation_id=data.get('correlation_id'),
            user_id=data.get('user_id'),
            request_id=data.get('request_id'),
            metadata=metadata
        )
    
    def _parse_structured_log(self, match, service: str, container: str) -> LogEntry:
        """Parse structured log format."""
        timestamp_str, level, logger_name, message = match.groups()
        
        return LogEntry(
            timestamp=self._parse_timestamp(timestamp_str),
            level=level.upper(),
            service=service,
            container=container,
            message=message,
            metadata={'logger': logger_name}
        )
    
    def _parse_nginx_log(self, match, service: str, container: str) -> LogEntry:
        """Parse nginx access log format."""
        ip, timestamp_str, request, status, size, referer, user_agent = match.groups()
        
        return LogEntry(
            timestamp=self._parse_timestamp(timestamp_str, format='%d/%b/%Y:%H:%M:%S %z'),
            level='INFO',
            service=service,
            container=container,
            message=f"{request} - {status}",
            metadata={
                'client_ip': ip,
                'request': request,
                'status_code': int(status),
                'response_size': int(size) if size != '-' else 0,
                'referer': referer if referer != '-' else None,
                'user_agent': user_agent
            }
        )
    
    def _parse_gunicorn_log(self, match, service: str, container: str) -> LogEntry:
        """Parse gunicorn log format."""
        timestamp_str, pid, level, message = match.groups()
        
        return LogEntry(
            timestamp=self._parse_timestamp(timestamp_str, format='%Y-%m-%d %H:%M:%S'),
            level=level.upper(),
            service=service,
            container=container,
            message=message,
            metadata={'pid': int(pid)}
        )
    
    def _parse_timestamp(self, timestamp_str: str, format: str = None) -> datetime:
        """Parse timestamp string."""
        if format:
            try:
                return datetime.strptime(timestamp_str, format)
            except ValueError:
                pass
        
        # Try common ISO formats
        formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue
        
        # Fallback to current time
        return datetime.utcnow()


class LogAggregator:
    """Aggregate logs from multiple sources."""
    
    def __init__(self, buffer_size: int = 10000):
        self.parser = LogParser()
        self.log_buffer: deque = deque(maxlen=buffer_size)
        self.stats = defaultdict(int)
        self.error_patterns = [
            re.compile(r'error', re.IGNORECASE),
            re.compile(r'exception', re.IGNORECASE),
            re.compile(r'failed', re.IGNORECASE),
            re.compile(r'timeout', re.IGNORECASE),
            re.compile(r'connection.*refused', re.IGNORECASE)
        ]
    
    async def collect_container_logs(self, container_name: str, log_file: str, service: str) -> AsyncGenerator[LogEntry, None]:
        """Collect logs from a container log file."""
        try:
            if not os.path.exists(log_file):
                logger.warning(f"Log file not found: {log_file}")
                return
            
            # Read existing logs
            async with aiofiles.open(log_file, 'r') as f:
                async for line in f:
                    entry = self.parser.parse_log_line(line, service, container_name)
                    if entry:
                        yield entry
            
            # Watch for new logs (simplified - in production use inotify)
            last_size = os.path.getsize(log_file)
            
            while True:
                await asyncio.sleep(1)
                
                try:
                    current_size = os.path.getsize(log_file)
                    if current_size > last_size:
                        async with aiofiles.open(log_file, 'r') as f:
                            await f.seek(last_size)
                            async for line in f:
                                entry = self.parser.parse_log_line(line, service, container_name)
                                if entry:
                                    yield entry
                        last_size = current_size
                except FileNotFoundError:
                    break
                    
        except Exception as e:
            logger.error(f"Error collecting logs from {log_file}: {e}")
    
    def add_log_entry(self, entry: LogEntry):
        """Add log entry to buffer."""
        self.log_buffer.append(entry)
        
        # Update statistics
        self.stats[f"{entry.service}_total"] += 1
        self.stats[f"{entry.service}_{entry.level.lower()}"] += 1
        
        # Check for errors
        if self._is_error_log(entry):
            self.stats[f"{entry.service}_errors"] += 1
            self.stats["total_errors"] += 1
    
    def _is_error_log(self, entry: LogEntry) -> bool:
        """Check if log entry indicates an error."""
        if entry.level in ['ERROR', 'CRITICAL', 'FATAL']:
            return True
        
        # Check message content
        for pattern in self.error_patterns:
            if pattern.search(entry.message):
                return True
        
        return False
    
    def get_recent_logs(self, limit: int = 100, service: str = None, level: str = None) -> List[LogEntry]:
        """Get recent log entries with optional filtering."""
        logs = list(self.log_buffer)
        
        # Apply filters
        if service:
            logs = [log for log in logs if log.service == service]
        
        if level:
            logs = [log for log in logs if log.level == level.upper()]
        
        # Sort by timestamp (most recent first)
        logs.sort(key=lambda x: x.timestamp, reverse=True)
        
        return logs[:limit]
    
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get error summary for the specified time period."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        recent_logs = [log for log in self.log_buffer if log.timestamp > cutoff_time]
        error_logs = [log for log in recent_logs if self._is_error_log(log)]
        
        # Group errors by service
        errors_by_service = defaultdict(list)
        for log in error_logs:
            errors_by_service[log.service].append(log)
        
        # Group errors by message pattern
        error_patterns = defaultdict(int)
        for log in error_logs:
            # Simple pattern extraction (first 50 chars)
            pattern = log.message[:50] + "..." if len(log.message) > 50 else log.message
            error_patterns[pattern] += 1
        
        return {
            "total_errors": len(error_logs),
            "total_logs": len(recent_logs),
            "error_rate": (len(error_logs) / len(recent_logs) * 100) if recent_logs else 0,
            "errors_by_service": {service: len(logs) for service, logs in errors_by_service.items()},
            "top_error_patterns": dict(sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)[:10]),
            "time_period_hours": hours
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get aggregation statistics."""
        return {
            "buffer_size": len(self.log_buffer),
            "max_buffer_size": self.log_buffer.maxlen,
            "stats": dict(self.stats),
            "timestamp": datetime.utcnow().isoformat()
        }


class LogForwarder:
    """Forward logs to external systems."""
    
    def __init__(self):
        self.elasticsearch_url = os.getenv("ELASTICSEARCH_URL")
        self.webhook_url = os.getenv("LOG_WEBHOOK_URL")
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def forward_to_elasticsearch(self, entries: List[LogEntry]):
        """Forward logs to Elasticsearch."""
        if not self.elasticsearch_url or not entries:
            return
        
        try:
            # Prepare bulk index request
            bulk_data = []
            for entry in entries:
                index_name = f"wiki-logs-{entry.timestamp.strftime('%Y.%m.%d')}"
                
                # Index metadata
                bulk_data.append(json.dumps({
                    "index": {
                        "_index": index_name,
                        "_type": "_doc"
                    }
                }))
                
                # Document data
                doc = asdict(entry)
                doc['timestamp'] = entry.timestamp.isoformat()
                bulk_data.append(json.dumps(doc))
            
            bulk_body = '\n'.join(bulk_data) + '\n'
            
            async with self.session.post(
                f"{self.elasticsearch_url}/_bulk",
                data=bulk_body,
                headers={"Content-Type": "application/x-ndjson"}
            ) as response:
                if response.status == 200:
                    logger.info(f"Forwarded {len(entries)} logs to Elasticsearch")
                else:
                    logger.error(f"Failed to forward logs to Elasticsearch: {response.status}")
                    
        except Exception as e:
            logger.error(f"Error forwarding logs to Elasticsearch: {e}")
    
    async def forward_to_webhook(self, entries: List[LogEntry]):
        """Forward logs to webhook."""
        if not self.webhook_url or not entries:
            return
        
        try:
            # Send in batches
            batch_size = 100
            for i in range(0, len(entries), batch_size):
                batch = entries[i:i + batch_size]
                
                payload = {
                    "logs": [asdict(entry) for entry in batch],
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "wiki-app-log-aggregator"
                }
                
                # Convert datetime objects to strings
                for log in payload["logs"]:
                    log["timestamp"] = log["timestamp"].isoformat() if isinstance(log["timestamp"], datetime) else log["timestamp"]
                
                async with self.session.post(self.webhook_url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Forwarded {len(batch)} logs to webhook")
                    else:
                        logger.error(f"Failed to forward logs to webhook: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error forwarding logs to webhook: {e}")


async def main():
    """Main log aggregation loop."""
    logger.info("Starting log aggregation service")
    
    aggregator = LogAggregator()
    
    # Configuration
    log_sources = [
        {"container": "wiki-app", "log_file": "/app/logs/app.log", "service": "wiki-app"},
        {"container": "wiki-worker", "log_file": "/app/logs/app.log", "service": "wiki-worker"},
        {"container": "nginx", "log_file": "/var/log/nginx/access.log", "service": "nginx"},
        {"container": "nginx", "log_file": "/var/log/nginx/error.log", "service": "nginx"},
        {"container": "postgres", "log_file": "/var/lib/postgresql/data/log/postgresql.log", "service": "postgres"}
    ]
    
    # Start log collection tasks
    tasks = []
    for source in log_sources:
        if os.path.exists(source["log_file"]):
            task = asyncio.create_task(
                collect_logs_from_source(aggregator, source)
            )
            tasks.append(task)
    
    # Start forwarding task
    forwarding_task = asyncio.create_task(
        forward_logs_periodically(aggregator)
    )
    tasks.append(forwarding_task)
    
    # Start statistics reporting task
    stats_task = asyncio.create_task(
        report_statistics_periodically(aggregator)
    )
    tasks.append(stats_task)
    
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Log aggregation stopped by user")
        for task in tasks:
            task.cancel()


async def collect_logs_from_source(aggregator: LogAggregator, source: Dict[str, str]):
    """Collect logs from a single source."""
    logger.info(f"Starting log collection from {source['container']}:{source['log_file']}")
    
    try:
        async for entry in aggregator.collect_container_logs(
            source["container"], 
            source["log_file"], 
            source["service"]
        ):
            aggregator.add_log_entry(entry)
    except Exception as e:
        logger.error(f"Error collecting logs from {source}: {e}")


async def forward_logs_periodically(aggregator: LogAggregator):
    """Periodically forward logs to external systems."""
    interval = int(os.getenv("LOG_FORWARD_INTERVAL", "300"))  # 5 minutes
    
    async with LogForwarder() as forwarder:
        while True:
            try:
                # Get recent logs for forwarding
                recent_logs = aggregator.get_recent_logs(limit=1000)
                
                if recent_logs:
                    # Forward to configured destinations
                    await forwarder.forward_to_elasticsearch(recent_logs)
                    await forwarder.forward_to_webhook(recent_logs)
                
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Error in log forwarding: {e}")
                await asyncio.sleep(interval)


async def report_statistics_periodically(aggregator: LogAggregator):
    """Periodically report aggregation statistics."""
    interval = int(os.getenv("LOG_STATS_INTERVAL", "600"))  # 10 minutes
    
    while True:
        try:
            stats = aggregator.get_statistics()
            error_summary = aggregator.get_error_summary()
            
            logger.info(f"Log aggregation stats: {stats}")
            logger.info(f"Error summary: {error_summary}")
            
            # Save stats to file
            stats_file = "/app/logs/aggregation_stats.json"
            with open(stats_file, 'w') as f:
                json.dump({
                    "stats": stats,
                    "error_summary": error_summary,
                    "timestamp": datetime.utcnow().isoformat()
                }, f, indent=2)
            
            await asyncio.sleep(interval)
            
        except Exception as e:
            logger.error(f"Error reporting statistics: {e}")
            await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())