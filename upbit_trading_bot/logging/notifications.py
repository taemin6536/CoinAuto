"""
Notification and alerting system for Upbit Trading Bot.

Implements notification system for critical errors and important events
as specified in requirements 8.4 and 8.5.
"""

import asyncio
import json
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, asdict
import logging
import threading
import time
from pathlib import Path

from .logger import get_logger


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Alert message structure."""
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime
    component: str
    details: Optional[Dict[str, Any]] = None
    acknowledged: bool = False


@dataclass
class NotificationChannel:
    """Notification channel configuration."""
    name: str
    type: str  # 'email', 'webhook', 'file', 'console'
    config: Dict[str, Any]
    enabled: bool = True
    min_level: AlertLevel = AlertLevel.WARNING


class NotificationService:
    """
    Comprehensive notification and alerting system.
    
    Supports multiple notification channels including email, webhooks,
    file logging, and console output for critical errors and events.
    """
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize notification service.
        
        Args:
            config_file: Path to notification configuration file
        """
        self.logger = get_logger(__name__)
        
        # Alert storage and management
        self._alerts: List[Alert] = []
        self._max_alerts_history = 1000
        
        # Notification channels
        self._channels: Dict[str, NotificationChannel] = {}
        
        # Rate limiting
        self._rate_limits: Dict[str, Dict[str, Any]] = {}
        self._default_rate_limit = {
            'max_per_hour': 10,
            'max_per_day': 50,
            'last_reset': datetime.now(),
            'hourly_count': 0,
            'daily_count': 0
        }
        
        # Background processing
        self._processing = False
        self._process_thread: Optional[threading.Thread] = None
        self._alert_queue: List[Alert] = []
        self._queue_lock = threading.Lock()
        
        # Load configuration
        if config_file:
            self._load_config(config_file)
        else:
            self._setup_default_channels()
        
        self.logger.info("NotificationService initialized", extra={
            'channels': list(self._channels.keys()),
            'config_file': config_file
        })
    
    def _setup_default_channels(self) -> None:
        """Setup default notification channels."""
        # Console channel for immediate feedback
        self.add_channel(NotificationChannel(
            name='console',
            type='console',
            config={},
            enabled=True,
            min_level=AlertLevel.WARNING
        ))
        
        # File channel for persistent logging
        self.add_channel(NotificationChannel(
            name='file',
            type='file',
            config={'file_path': 'logs/alerts.log'},
            enabled=True,
            min_level=AlertLevel.INFO
        ))
    
    def _load_config(self, config_file: str) -> None:
        """Load notification configuration from file."""
        try:
            config_path = Path(config_file)
            if not config_path.exists():
                self.logger.warning(f"Notification config file not found: {config_file}")
                self._setup_default_channels()
                return
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Load channels from config
            for channel_config in config.get('channels', []):
                channel = NotificationChannel(
                    name=channel_config['name'],
                    type=channel_config['type'],
                    config=channel_config.get('config', {}),
                    enabled=channel_config.get('enabled', True),
                    min_level=AlertLevel(channel_config.get('min_level', 'warning'))
                )
                self.add_channel(channel)
            
            # Load rate limits
            if 'rate_limits' in config:
                self._default_rate_limit.update(config['rate_limits'])
            
            self.logger.info(f"Loaded notification config from {config_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to load notification config: {e}", exc_info=True)
            self._setup_default_channels()
    
    def add_channel(self, channel: NotificationChannel) -> None:
        """
        Add notification channel.
        
        Args:
            channel: NotificationChannel instance
        """
        self._channels[channel.name] = channel
        self._rate_limits[channel.name] = self._default_rate_limit.copy()
        self.logger.info(f"Added notification channel: {channel.name} ({channel.type})")
    
    def remove_channel(self, channel_name: str) -> None:
        """
        Remove notification channel.
        
        Args:
            channel_name: Name of channel to remove
        """
        if channel_name in self._channels:
            del self._channels[channel_name]
            del self._rate_limits[channel_name]
            self.logger.info(f"Removed notification channel: {channel_name}")
    
    def start_processing(self) -> None:
        """Start background alert processing."""
        if self._processing:
            self.logger.warning("Notification processing already started")
            return
        
        self._processing = True
        self._process_thread = threading.Thread(
            target=self._process_alerts,
            daemon=True,
            name="NotificationProcessor"
        )
        self._process_thread.start()
        self.logger.info("Notification processing started")
    
    def stop_processing(self) -> None:
        """Stop background alert processing."""
        if not self._processing:
            return
        
        self._processing = False
        if self._process_thread:
            self._process_thread.join(timeout=5)
        
        self.logger.info("Notification processing stopped")
    
    def send_alert(self, level: AlertLevel, title: str, message: str,
                   component: str = "system", details: Optional[Dict[str, Any]] = None) -> None:
        """
        Send alert through configured channels.
        
        Args:
            level: Alert severity level
            title: Alert title
            message: Alert message
            component: Component that generated the alert
            details: Additional alert details
        """
        alert = Alert(
            level=level,
            title=title,
            message=message,
            timestamp=datetime.now(),
            component=component,
            details=details or {}
        )
        
        # Add to alert history
        self._store_alert(alert)
        
        # Queue for processing
        with self._queue_lock:
            self._alert_queue.append(alert)
        
        # Log the alert
        log_level = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.ERROR: logging.ERROR,
            AlertLevel.CRITICAL: logging.CRITICAL
        }.get(level, logging.INFO)
        
        self.logger.log(log_level, f"Alert: {title} - {message}", extra={
            'alert_level': level.value,
            'component': component,
            'details': details
        })
    
    def _store_alert(self, alert: Alert) -> None:
        """Store alert in history."""
        self._alerts.append(alert)
        
        # Trim history if it exceeds maximum size
        if len(self._alerts) > self._max_alerts_history:
            self._alerts = self._alerts[-self._max_alerts_history:]
    
    def _process_alerts(self) -> None:
        """Background alert processing loop."""
        while self._processing:
            try:
                # Process queued alerts
                alerts_to_process = []
                with self._queue_lock:
                    alerts_to_process = self._alert_queue.copy()
                    self._alert_queue.clear()
                
                for alert in alerts_to_process:
                    self._send_alert_to_channels(alert)
                
                # Reset rate limits if needed
                self._reset_rate_limits()
                
                time.sleep(1)  # Process every second
                
            except Exception as e:
                self.logger.error(f"Error in alert processing: {e}", exc_info=True)
                time.sleep(5)
    
    def _send_alert_to_channels(self, alert: Alert) -> None:
        """Send alert to all appropriate channels."""
        for channel_name, channel in self._channels.items():
            try:
                # Check if channel should receive this alert
                if not channel.enabled:
                    continue
                
                if alert.level.value < channel.min_level.value:
                    continue
                
                # Check rate limits
                if not self._check_rate_limit(channel_name):
                    continue
                
                # Send to channel
                self._send_to_channel(channel, alert)
                
            except Exception as e:
                self.logger.error(f"Failed to send alert to channel {channel_name}: {e}")
    
    def _check_rate_limit(self, channel_name: str) -> bool:
        """Check if channel is within rate limits."""
        limits = self._rate_limits.get(channel_name, self._default_rate_limit)
        now = datetime.now()
        
        # Reset counters if needed
        if (now - limits['last_reset']).total_seconds() >= 3600:  # 1 hour
            limits['hourly_count'] = 0
            limits['last_reset'] = now
        
        if (now - limits['last_reset']).total_seconds() >= 86400:  # 1 day
            limits['daily_count'] = 0
        
        # Check limits
        if limits['hourly_count'] >= limits['max_per_hour']:
            return False
        
        if limits['daily_count'] >= limits['max_per_day']:
            return False
        
        # Increment counters
        limits['hourly_count'] += 1
        limits['daily_count'] += 1
        
        return True
    
    def _reset_rate_limits(self) -> None:
        """Reset rate limit counters as needed."""
        now = datetime.now()
        
        for channel_name, limits in self._rate_limits.items():
            # Reset hourly counter
            if (now - limits['last_reset']).total_seconds() >= 3600:
                limits['hourly_count'] = 0
                limits['last_reset'] = now
            
            # Reset daily counter
            if (now - limits['last_reset']).total_seconds() >= 86400:
                limits['daily_count'] = 0
    
    def _send_to_channel(self, channel: NotificationChannel, alert: Alert) -> None:
        """Send alert to specific channel."""
        if channel.type == 'console':
            self._send_console(alert)
        elif channel.type == 'file':
            self._send_file(channel, alert)
        elif channel.type == 'email':
            self._send_email(channel, alert)
        elif channel.type == 'webhook':
            self._send_webhook(channel, alert)
        else:
            self.logger.warning(f"Unknown channel type: {channel.type}")
    
    def _send_console(self, alert: Alert) -> None:
        """Send alert to console."""
        timestamp = alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        level_colors = {
            AlertLevel.INFO: '\033[94m',      # Blue
            AlertLevel.WARNING: '\033[93m',   # Yellow
            AlertLevel.ERROR: '\033[91m',     # Red
            AlertLevel.CRITICAL: '\033[95m'   # Magenta
        }
        reset_color = '\033[0m'
        
        color = level_colors.get(alert.level, '')
        print(f"{color}[{timestamp}] {alert.level.value.upper()} - {alert.component}: {alert.title}{reset_color}")
        print(f"  {alert.message}")
        
        if alert.details:
            print(f"  Details: {json.dumps(alert.details, indent=2)}")
    
    def _send_file(self, channel: NotificationChannel, alert: Alert) -> None:
        """Send alert to file."""
        file_path = Path(channel.config.get('file_path', 'logs/alerts.log'))
        file_path.parent.mkdir(exist_ok=True)
        
        alert_data = {
            'timestamp': alert.timestamp.isoformat(),
            'level': alert.level.value,
            'component': alert.component,
            'title': alert.title,
            'message': alert.message,
            'details': alert.details
        }
        
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(alert_data) + '\n')
    
    def _send_email(self, channel: NotificationChannel, alert: Alert) -> None:
        """Send alert via email."""
        config = channel.config
        
        # Create message
        msg = EmailMessage()
        msg['From'] = config['from_email']
        msg['To'] = config['to_email']
        msg['Subject'] = f"[{alert.level.value.upper()}] {alert.title}"
        
        # Email body
        body = f"""
Alert Details:
- Level: {alert.level.value.upper()}
- Component: {alert.component}
- Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
- Message: {alert.message}

Additional Details:
{json.dumps(alert.details, indent=2) if alert.details else 'None'}
        """
        
        msg.set_content(body)
        
        # Send email
        context = ssl.create_default_context()
        with smtplib.SMTP(config['smtp_server'], config['smtp_port']) as server:
            server.starttls(context=context)
            server.login(config['username'], config['password'])
            server.send_message(msg)
    
    def _send_webhook(self, channel: NotificationChannel, alert: Alert) -> None:
        """Send alert via webhook."""
        import requests
        
        config = channel.config
        url = config['url']
        
        payload = {
            'timestamp': alert.timestamp.isoformat(),
            'level': alert.level.value,
            'component': alert.component,
            'title': alert.title,
            'message': alert.message,
            'details': alert.details
        }
        
        headers = config.get('headers', {'Content-Type': 'application/json'})
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
    
    def get_alerts(self, level: Optional[AlertLevel] = None,
                   component: Optional[str] = None,
                   hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get alert history with optional filtering.
        
        Args:
            level: Filter by alert level
            component: Filter by component
            hours: Number of hours of history to return
            
        Returns:
            List of alert dictionaries
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        filtered_alerts = []
        for alert in self._alerts:
            if alert.timestamp < cutoff_time:
                continue
            
            if level and alert.level != level:
                continue
            
            if component and alert.component != component:
                continue
            
            filtered_alerts.append(asdict(alert))
        
        return filtered_alerts
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get summary of recent alerts."""
        now = datetime.now()
        last_24h = now - timedelta(hours=24)
        last_hour = now - timedelta(hours=1)
        
        recent_alerts = [a for a in self._alerts if a.timestamp >= last_24h]
        hourly_alerts = [a for a in self._alerts if a.timestamp >= last_hour]
        
        # Count by level
        level_counts = {}
        for level in AlertLevel:
            level_counts[level.value] = len([a for a in recent_alerts if a.level == level])
        
        return {
            'total_alerts_24h': len(recent_alerts),
            'total_alerts_1h': len(hourly_alerts),
            'alerts_by_level_24h': level_counts,
            'active_channels': len([c for c in self._channels.values() if c.enabled]),
            'last_alert': self._alerts[-1].timestamp.isoformat() if self._alerts else None
        }
    
    # Convenience methods for common alert types
    def alert_critical_error(self, title: str, message: str, component: str = "system",
                           details: Optional[Dict[str, Any]] = None) -> None:
        """Send critical error alert."""
        self.send_alert(AlertLevel.CRITICAL, title, message, component, details)
    
    def alert_error(self, title: str, message: str, component: str = "system",
                   details: Optional[Dict[str, Any]] = None) -> None:
        """Send error alert."""
        self.send_alert(AlertLevel.ERROR, title, message, component, details)
    
    def alert_warning(self, title: str, message: str, component: str = "system",
                     details: Optional[Dict[str, Any]] = None) -> None:
        """Send warning alert."""
        self.send_alert(AlertLevel.WARNING, title, message, component, details)
    
    def alert_info(self, title: str, message: str, component: str = "system",
                  details: Optional[Dict[str, Any]] = None) -> None:
        """Send info alert."""
        self.send_alert(AlertLevel.INFO, title, message, component, details)