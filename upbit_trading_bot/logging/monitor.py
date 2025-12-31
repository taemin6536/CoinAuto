"""
Health check and monitoring system for Upbit Trading Bot.

Implements health check endpoints and system monitoring capabilities
as specified in requirements 8.4 and 8.5.
"""

import asyncio
import json
import psutil
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from pathlib import Path
import logging

from .logger import get_logger


@dataclass
class HealthStatus:
    """Health status information."""
    component: str
    status: str  # 'healthy', 'warning', 'critical'
    message: str
    last_check: datetime
    details: Optional[Dict[str, Any]] = None


@dataclass
class SystemMetrics:
    """System performance metrics."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_usage_percent: float
    disk_free_gb: float
    network_bytes_sent: int
    network_bytes_recv: int
    process_count: int
    uptime_seconds: float


class HealthMonitor:
    """
    Health monitoring system for trading bot components.
    
    Provides health checks for various system components and
    exposes health status through endpoints.
    """
    
    def __init__(self, check_interval: int = 30):
        """
        Initialize health monitor.
        
        Args:
            check_interval: Health check interval in seconds
        """
        self.check_interval = check_interval
        self.logger = get_logger(__name__)
        
        # Health status storage
        self._health_status: Dict[str, HealthStatus] = {}
        self._health_checks: Dict[str, Callable[[], HealthStatus]] = {}
        
        # Monitoring state
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._start_time = datetime.now()
        
        # Register default health checks
        self._register_default_checks()
        
        self.logger.info("HealthMonitor initialized", extra={
            'check_interval': check_interval
        })
    
    def _register_default_checks(self) -> None:
        """Register default system health checks."""
        self.register_health_check('system_resources', self._check_system_resources)
        self.register_health_check('disk_space', self._check_disk_space)
        self.register_health_check('log_directory', self._check_log_directory)
    
    def register_health_check(self, component: str, 
                            check_func: Callable[[], HealthStatus]) -> None:
        """
        Register a health check function for a component.
        
        Args:
            component: Component name
            check_func: Function that returns HealthStatus
        """
        self._health_checks[component] = check_func
        self.logger.info(f"Registered health check for component: {component}")
    
    def start_monitoring(self) -> None:
        """Start continuous health monitoring."""
        if self._monitoring:
            self.logger.warning("Health monitoring already started")
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="HealthMonitor"
        )
        self._monitor_thread.start()
        self.logger.info("Health monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        if not self._monitoring:
            return
        
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        self.logger.info("Health monitoring stopped")
    
    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._monitoring:
            try:
                self._run_health_checks()
                time.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"Error in health monitoring loop: {e}", exc_info=True)
                time.sleep(self.check_interval)
    
    def _run_health_checks(self) -> None:
        """Run all registered health checks."""
        for component, check_func in self._health_checks.items():
            try:
                status = check_func()
                self._health_status[component] = status
                
                # Log warnings and critical issues
                if status.status in ['warning', 'critical']:
                    log_level = logging.WARNING if status.status == 'warning' else logging.ERROR
                    self.logger.log(log_level, f"Health check {component}: {status.message}",
                                  extra={'component': component, 'status': status.status})
                
            except Exception as e:
                # Create error status for failed health check
                error_status = HealthStatus(
                    component=component,
                    status='critical',
                    message=f"Health check failed: {str(e)}",
                    last_check=datetime.now(),
                    details={'error': str(e)}
                )
                self._health_status[component] = error_status
                self.logger.error(f"Health check failed for {component}: {e}", exc_info=True)
    
    def get_health_status(self, component: Optional[str] = None) -> Dict[str, Any]:
        """
        Get health status for component(s).
        
        Args:
            component: Specific component name, or None for all
            
        Returns:
            Health status information
        """
        if component:
            status = self._health_status.get(component)
            if status:
                return asdict(status)
            else:
                return {'error': f'Component {component} not found'}
        
        # Return all health statuses
        result = {
            'overall_status': self._calculate_overall_status(),
            'uptime_seconds': (datetime.now() - self._start_time).total_seconds(),
            'last_check': datetime.now().isoformat(),
            'components': {}
        }
        
        for comp, status in self._health_status.items():
            result['components'][comp] = asdict(status)
        
        return result
    
    def _calculate_overall_status(self) -> str:
        """Calculate overall system health status."""
        if not self._health_status:
            return 'unknown'
        
        statuses = [status.status for status in self._health_status.values()]
        
        if 'critical' in statuses:
            return 'critical'
        elif 'warning' in statuses:
            return 'warning'
        else:
            return 'healthy'
    
    def _check_system_resources(self) -> HealthStatus:
        """Check system resource usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            status = 'healthy'
            message = 'System resources normal'
            details = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': memory.available / (1024**3)
            }
            
            # Check thresholds
            if cpu_percent > 90 or memory.percent > 90:
                status = 'critical'
                message = f'High resource usage: CPU {cpu_percent}%, Memory {memory.percent}%'
            elif cpu_percent > 70 or memory.percent > 70:
                status = 'warning'
                message = f'Elevated resource usage: CPU {cpu_percent}%, Memory {memory.percent}%'
            
            return HealthStatus(
                component='system_resources',
                status=status,
                message=message,
                last_check=datetime.now(),
                details=details
            )
            
        except Exception as e:
            return HealthStatus(
                component='system_resources',
                status='critical',
                message=f'Failed to check system resources: {str(e)}',
                last_check=datetime.now(),
                details={'error': str(e)}
            )
    
    def _check_disk_space(self) -> HealthStatus:
        """Check disk space availability."""
        try:
            disk_usage = psutil.disk_usage('/')
            free_percent = (disk_usage.free / disk_usage.total) * 100
            
            status = 'healthy'
            message = f'Disk space available: {free_percent:.1f}%'
            details = {
                'free_percent': free_percent,
                'free_gb': disk_usage.free / (1024**3),
                'total_gb': disk_usage.total / (1024**3)
            }
            
            if free_percent < 5:
                status = 'critical'
                message = f'Critical disk space: {free_percent:.1f}% free'
            elif free_percent < 15:
                status = 'warning'
                message = f'Low disk space: {free_percent:.1f}% free'
            
            return HealthStatus(
                component='disk_space',
                status=status,
                message=message,
                last_check=datetime.now(),
                details=details
            )
            
        except Exception as e:
            return HealthStatus(
                component='disk_space',
                status='critical',
                message=f'Failed to check disk space: {str(e)}',
                last_check=datetime.now(),
                details={'error': str(e)}
            )
    
    def _check_log_directory(self) -> HealthStatus:
        """Check log directory accessibility and size."""
        try:
            log_dir = Path('logs')
            
            if not log_dir.exists():
                return HealthStatus(
                    component='log_directory',
                    status='critical',
                    message='Log directory does not exist',
                    last_check=datetime.now()
                )
            
            # Calculate total log size
            total_size = sum(f.stat().st_size for f in log_dir.glob('**/*') if f.is_file())
            total_size_mb = total_size / (1024**2)
            
            status = 'healthy'
            message = f'Log directory accessible, size: {total_size_mb:.1f}MB'
            details = {
                'size_mb': total_size_mb,
                'file_count': len(list(log_dir.glob('*.log*')))
            }
            
            # Check if log directory is getting too large
            if total_size_mb > 1000:  # 1GB
                status = 'warning'
                message = f'Log directory large: {total_size_mb:.1f}MB'
            
            return HealthStatus(
                component='log_directory',
                status=status,
                message=message,
                last_check=datetime.now(),
                details=details
            )
            
        except Exception as e:
            return HealthStatus(
                component='log_directory',
                status='critical',
                message=f'Failed to check log directory: {str(e)}',
                last_check=datetime.now(),
                details={'error': str(e)}
            )


class SystemMonitor:
    """
    System performance monitoring with metrics collection.
    
    Collects and stores system performance metrics for analysis
    and monitoring purposes.
    """
    
    def __init__(self, collection_interval: int = 60, 
                 max_metrics_history: int = 1440):  # 24 hours at 1-minute intervals
        """
        Initialize system monitor.
        
        Args:
            collection_interval: Metrics collection interval in seconds
            max_metrics_history: Maximum number of metrics to keep in memory
        """
        self.collection_interval = collection_interval
        self.max_metrics_history = max_metrics_history
        self.logger = get_logger(__name__)
        
        # Metrics storage
        self._metrics_history: List[SystemMetrics] = []
        self._start_time = time.time()
        
        # Monitoring state
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        # Initial network counters
        self._initial_net_io = psutil.net_io_counters()
        
        self.logger.info("SystemMonitor initialized", extra={
            'collection_interval': collection_interval,
            'max_history': max_metrics_history
        })
    
    def start_monitoring(self) -> None:
        """Start system metrics collection."""
        if self._monitoring:
            self.logger.warning("System monitoring already started")
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="SystemMonitor"
        )
        self._monitor_thread.start()
        self.logger.info("System monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop system metrics collection."""
        if not self._monitoring:
            return
        
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        self.logger.info("System monitoring stopped")
    
    def _monitor_loop(self) -> None:
        """Main monitoring loop for metrics collection."""
        while self._monitoring:
            try:
                metrics = self._collect_metrics()
                self._store_metrics(metrics)
                time.sleep(self.collection_interval)
            except Exception as e:
                self.logger.error(f"Error in system monitoring loop: {e}", exc_info=True)
                time.sleep(self.collection_interval)
    
    def _collect_metrics(self) -> SystemMetrics:
        """Collect current system metrics."""
        # CPU and memory
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # Disk usage
        disk_usage = psutil.disk_usage('/')
        
        # Network I/O
        net_io = psutil.net_io_counters()
        
        # Process count
        process_count = len(psutil.pids())
        
        # Uptime
        uptime_seconds = time.time() - self._start_time
        
        return SystemMetrics(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used_mb=memory.used / (1024**2),
            memory_available_mb=memory.available / (1024**2),
            disk_usage_percent=disk_usage.used / disk_usage.total * 100,
            disk_free_gb=disk_usage.free / (1024**3),
            network_bytes_sent=net_io.bytes_sent,
            network_bytes_recv=net_io.bytes_recv,
            process_count=process_count,
            uptime_seconds=uptime_seconds
        )
    
    def _store_metrics(self, metrics: SystemMetrics) -> None:
        """Store metrics in history, maintaining size limit."""
        self._metrics_history.append(metrics)
        
        # Trim history if it exceeds maximum size
        if len(self._metrics_history) > self.max_metrics_history:
            self._metrics_history = self._metrics_history[-self.max_metrics_history:]
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current system metrics."""
        if not self._metrics_history:
            return {'error': 'No metrics available'}
        
        latest_metrics = self._metrics_history[-1]
        return asdict(latest_metrics)
    
    def get_metrics_history(self, hours: int = 1) -> List[Dict[str, Any]]:
        """
        Get metrics history for specified time period.
        
        Args:
            hours: Number of hours of history to return
            
        Returns:
            List of metrics dictionaries
        """
        if not self._metrics_history:
            return []
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        filtered_metrics = [
            metrics for metrics in self._metrics_history
            if metrics.timestamp >= cutoff_time
        ]
        
        return [asdict(metrics) for metrics in filtered_metrics]
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary statistics of collected metrics."""
        if not self._metrics_history:
            return {'error': 'No metrics available'}
        
        # Calculate averages and peaks
        cpu_values = [m.cpu_percent for m in self._metrics_history]
        memory_values = [m.memory_percent for m in self._metrics_history]
        
        return {
            'collection_period_hours': len(self._metrics_history) * self.collection_interval / 3600,
            'total_samples': len(self._metrics_history),
            'cpu_stats': {
                'current': cpu_values[-1] if cpu_values else 0,
                'average': sum(cpu_values) / len(cpu_values) if cpu_values else 0,
                'peak': max(cpu_values) if cpu_values else 0
            },
            'memory_stats': {
                'current': memory_values[-1] if memory_values else 0,
                'average': sum(memory_values) / len(memory_values) if memory_values else 0,
                'peak': max(memory_values) if memory_values else 0
            },
            'uptime_hours': self._metrics_history[-1].uptime_seconds / 3600 if self._metrics_history else 0
        }