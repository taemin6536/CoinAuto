"""
Logging utilities and integration helpers.

Provides utility functions for integrating the logging system
with existing components and simplifying common logging tasks.
"""

import functools
import time
from typing import Any, Callable, Dict, Optional
from datetime import datetime
import logging

from .logger import get_logger
from .notifications import NotificationService, AlertLevel


def log_execution_time(logger_name: Optional[str] = None):
    """
    Decorator to log function execution time.
    
    Args:
        logger_name: Logger name to use, defaults to function's module
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name or func.__module__)
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                logger.info(f"Function {func.__name__} completed", extra={
                    'function': func.__name__,
                    'execution_time_seconds': execution_time,
                    'success': True
                })
                
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                
                logger.error(f"Function {func.__name__} failed", extra={
                    'function': func.__name__,
                    'execution_time_seconds': execution_time,
                    'success': False,
                    'error': str(e)
                }, exc_info=True)
                
                raise
        
        return wrapper
    return decorator


def log_api_call(api_name: str, logger_name: Optional[str] = None):
    """
    Decorator to log API calls with request/response details.
    
    Args:
        api_name: Name of the API being called
        logger_name: Logger name to use
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name or func.__module__)
            start_time = time.time()
            
            # Log API call start
            logger.info(f"API call started: {api_name}", extra={
                'api_name': api_name,
                'function': func.__name__,
                'timestamp': datetime.now().isoformat()
            })
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                logger.info(f"API call completed: {api_name}", extra={
                    'api_name': api_name,
                    'function': func.__name__,
                    'execution_time_seconds': execution_time,
                    'success': True
                })
                
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                
                logger.error(f"API call failed: {api_name}", extra={
                    'api_name': api_name,
                    'function': func.__name__,
                    'execution_time_seconds': execution_time,
                    'success': False,
                    'error': str(e),
                    'error_type': type(e).__name__
                }, exc_info=True)
                
                raise
        
        return wrapper
    return decorator


def log_trading_action(action_type: str, market: str, logger_name: Optional[str] = None):
    """
    Decorator to log trading actions with market and action details.
    
    Args:
        action_type: Type of trading action (buy, sell, cancel, etc.)
        market: Trading market (e.g., KRW-BTC)
        logger_name: Logger name to use
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name or func.__module__)
            
            logger.info(f"Trading action: {action_type}", extra={
                'action_type': action_type,
                'market': market,
                'function': func.__name__,
                'timestamp': datetime.now().isoformat()
            })
            
            try:
                result = func(*args, **kwargs)
                
                logger.info(f"Trading action completed: {action_type}", extra={
                    'action_type': action_type,
                    'market': market,
                    'function': func.__name__,
                    'success': True,
                    'result': str(result)[:200]  # Truncate long results
                })
                
                return result
                
            except Exception as e:
                logger.error(f"Trading action failed: {action_type}", extra={
                    'action_type': action_type,
                    'market': market,
                    'function': func.__name__,
                    'success': False,
                    'error': str(e),
                    'error_type': type(e).__name__
                }, exc_info=True)
                
                raise
        
        return wrapper
    return decorator


class LoggingMixin:
    """
    Mixin class to add logging capabilities to any class.
    
    Provides convenient logging methods and automatic logger setup.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._logger = get_logger(self.__class__.__module__)
    
    @property
    def logger(self) -> logging.Logger:
        """Get logger instance for this class."""
        return self._logger
    
    def log_info(self, message: str, **extra) -> None:
        """Log info message with extra context."""
        self._logger.info(message, extra=extra)
    
    def log_warning(self, message: str, **extra) -> None:
        """Log warning message with extra context."""
        self._logger.warning(message, extra=extra)
    
    def log_error(self, message: str, error: Optional[Exception] = None, **extra) -> None:
        """Log error message with optional exception and extra context."""
        if error:
            extra['error'] = str(error)
            extra['error_type'] = type(error).__name__
        
        self._logger.error(message, extra=extra, exc_info=error is not None)
    
    def log_critical(self, message: str, error: Optional[Exception] = None, **extra) -> None:
        """Log critical message with optional exception and extra context."""
        if error:
            extra['error'] = str(error)
            extra['error_type'] = type(error).__name__
        
        self._logger.critical(message, extra=extra, exc_info=error is not None)
    
    def log_trading_event(self, event_type: str, market: str, details: Dict[str, Any]) -> None:
        """Log trading-specific events."""
        self._logger.info(f"Trading event: {event_type}", extra={
            'event_type': 'trading',
            'trading_event': event_type,
            'market': market,
            'details': details,
            'component': self.__class__.__name__
        })


class AlertingMixin:
    """
    Mixin class to add alerting capabilities to any class.
    
    Provides convenient methods for sending alerts through the notification system.
    """
    
    def __init__(self, notification_service: Optional[NotificationService] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._notification_service = notification_service
        self._component_name = self.__class__.__name__
    
    def set_notification_service(self, notification_service: NotificationService) -> None:
        """Set the notification service instance."""
        self._notification_service = notification_service
    
    def send_alert(self, level: AlertLevel, title: str, message: str,
                   details: Optional[Dict[str, Any]] = None) -> None:
        """Send alert through notification service."""
        if self._notification_service:
            self._notification_service.send_alert(
                level=level,
                title=title,
                message=message,
                component=self._component_name,
                details=details
            )
    
    def alert_critical(self, title: str, message: str, 
                      details: Optional[Dict[str, Any]] = None) -> None:
        """Send critical alert."""
        self.send_alert(AlertLevel.CRITICAL, title, message, details)
    
    def alert_error(self, title: str, message: str,
                   details: Optional[Dict[str, Any]] = None) -> None:
        """Send error alert."""
        self.send_alert(AlertLevel.ERROR, title, message, details)
    
    def alert_warning(self, title: str, message: str,
                     details: Optional[Dict[str, Any]] = None) -> None:
        """Send warning alert."""
        self.send_alert(AlertLevel.WARNING, title, message, details)
    
    def alert_info(self, title: str, message: str,
                  details: Optional[Dict[str, Any]] = None) -> None:
        """Send info alert."""
        self.send_alert(AlertLevel.INFO, title, message, details)


def setup_component_logging(component_name: str, 
                          notification_service: Optional[NotificationService] = None) -> logging.Logger:
    """
    Setup logging for a component with optional alerting.
    
    Args:
        component_name: Name of the component
        notification_service: Optional notification service for alerts
        
    Returns:
        Configured logger instance
    """
    logger = get_logger(component_name)
    
    # Add custom handler for critical errors if notification service is provided
    if notification_service:
        class AlertHandler(logging.Handler):
            def emit(self, record):
                if record.levelno >= logging.ERROR:
                    level = AlertLevel.CRITICAL if record.levelno >= logging.CRITICAL else AlertLevel.ERROR
                    
                    details = {
                        'logger': record.name,
                        'module': record.module,
                        'function': record.funcName,
                        'line': record.lineno
                    }
                    
                    if record.exc_info:
                        details['exception'] = str(record.exc_info[1])
                    
                    notification_service.send_alert(
                        level=level,
                        title=f"System Error in {component_name}",
                        message=record.getMessage(),
                        component=component_name,
                        details=details
                    )
        
        alert_handler = AlertHandler()
        alert_handler.setLevel(logging.ERROR)
        logger.addHandler(alert_handler)
    
    return logger


def create_health_check_logger(health_monitor, notification_service: Optional[NotificationService] = None):
    """
    Create a health check logger that integrates with monitoring and alerting.
    
    Args:
        health_monitor: HealthMonitor instance
        notification_service: Optional notification service
        
    Returns:
        Configured logger
    """
    logger = get_logger('health_check')
    
    class HealthCheckHandler(logging.Handler):
        def emit(self, record):
            # Send health-related alerts
            if notification_service and record.levelno >= logging.WARNING:
                level = AlertLevel.CRITICAL if record.levelno >= logging.CRITICAL else AlertLevel.WARNING
                
                notification_service.send_alert(
                    level=level,
                    title="Health Check Alert",
                    message=record.getMessage(),
                    component="health_monitor",
                    details={'logger': record.name, 'level': record.levelname}
                )
    
    health_handler = HealthCheckHandler()
    health_handler.setLevel(logging.WARNING)
    logger.addHandler(health_handler)
    
    return logger