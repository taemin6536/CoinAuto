"""
Structured logging system with rotation and retention policies.

Implements comprehensive logging with appropriate severity levels,
log rotation, and retention policies as specified in requirements 8.1, 8.2, 8.3.
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
import json
import traceback


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging with JSON output."""
    
    def __init__(self, include_extra: bool = True):
        super().__init__()
        self.include_extra = include_extra
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception information if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields if enabled
        if self.include_extra:
            extra_fields = {
                k: v for k, v in record.__dict__.items()
                if k not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                           'filename', 'module', 'lineno', 'funcName', 'created', 'msecs',
                           'relativeCreated', 'thread', 'threadName', 'processName',
                           'process', 'getMessage', 'exc_info', 'exc_text', 'stack_info']
            }
            if extra_fields:
                log_data['extra'] = extra_fields
        
        return json.dumps(log_data, ensure_ascii=False)


class LoggerManager:
    """
    Centralized logging manager with rotation and retention policies.
    
    Provides structured logging with appropriate severity levels,
    automatic log rotation, and configurable retention policies.
    """
    
    def __init__(self, 
                 log_dir: str = "logs",
                 log_level: str = "INFO",
                 max_file_size: int = 10 * 1024 * 1024,  # 10MB
                 backup_count: int = 30,  # Keep 30 days of logs
                 console_output: bool = True,
                 structured_format: bool = True):
        """
        Initialize logging manager.
        
        Args:
            log_dir: Directory for log files
            log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            max_file_size: Maximum size per log file in bytes
            backup_count: Number of backup files to keep (days)
            console_output: Whether to output logs to console
            structured_format: Whether to use structured JSON format
        """
        self.log_dir = Path(log_dir)
        self.log_level = getattr(logging, log_level.upper())
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.console_output = console_output
        self.structured_format = structured_format
        
        # Create log directory
        self.log_dir.mkdir(exist_ok=True)
        
        # Initialize logging configuration
        self._setup_logging()
        
        # Store logger instances
        self._loggers: Dict[str, logging.Logger] = {}
        
        # Main application logger
        self.logger = self.get_logger(__name__)
        self.logger.info("LoggerManager initialized", extra={
            'log_dir': str(self.log_dir),
            'log_level': log_level,
            'max_file_size': max_file_size,
            'backup_count': backup_count
        })
    
    def _setup_logging(self) -> None:
        """Setup logging configuration with handlers and formatters."""
        # Clear any existing handlers
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        
        # Set root logger level
        root_logger.setLevel(self.log_level)
        
        # Create formatters
        if self.structured_format:
            file_formatter = StructuredFormatter()
            console_formatter = StructuredFormatter()
        else:
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            filename=self.log_dir / "trading_bot.log",
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        
        # Error file handler (separate file for errors)
        error_handler = logging.handlers.RotatingFileHandler(
            filename=self.log_dir / "errors.log",
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        root_logger.addHandler(error_handler)
        
        # Console handler
        if self.console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.log_level)
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Get or create a logger instance.
        
        Args:
            name: Logger name (typically __name__)
            
        Returns:
            Configured logger instance
        """
        if name not in self._loggers:
            logger = logging.getLogger(name)
            self._loggers[name] = logger
        
        return self._loggers[name]
    
    def log_system_event(self, event_type: str, details: Dict[str, Any], 
                        level: str = "INFO") -> None:
        """
        Log structured system events.
        
        Args:
            event_type: Type of system event
            details: Event details dictionary
            level: Log level
        """
        log_level = getattr(logging, level.upper())
        self.logger.log(log_level, f"System event: {event_type}", extra={
            'event_type': event_type,
            'event_details': details,
            'timestamp': datetime.now().isoformat()
        })
    
    def log_trading_event(self, event_type: str, market: str, 
                         details: Dict[str, Any]) -> None:
        """
        Log trading-specific events.
        
        Args:
            event_type: Type of trading event (order, trade, signal, etc.)
            market: Trading market (e.g., KRW-BTC)
            details: Event details
        """
        self.logger.info(f"Trading event: {event_type}", extra={
            'event_type': 'trading',
            'trading_event': event_type,
            'market': market,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })
    
    def log_error_with_context(self, error: Exception, context: Dict[str, Any]) -> None:
        """
        Log errors with full context and stack trace.
        
        Args:
            error: Exception instance
            context: Additional context information
        """
        self.logger.error(f"Error occurred: {str(error)}", extra={
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context,
            'timestamp': datetime.now().isoformat()
        }, exc_info=True)
    
    def cleanup_old_logs(self, retention_days: int = 30) -> None:
        """
        Clean up log files older than retention period.
        
        Args:
            retention_days: Number of days to retain logs
        """
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        for log_file in self.log_dir.glob("*.log*"):
            try:
                file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if file_mtime < cutoff_date:
                    log_file.unlink()
                    self.logger.info(f"Cleaned up old log file: {log_file}")
            except Exception as e:
                self.logger.error(f"Failed to cleanup log file {log_file}: {e}")
    
    def get_log_stats(self) -> Dict[str, Any]:
        """
        Get logging statistics.
        
        Returns:
            Dictionary with logging statistics
        """
        stats = {
            'log_directory': str(self.log_dir),
            'log_level': logging.getLevelName(self.log_level),
            'total_loggers': len(self._loggers),
            'log_files': []
        }
        
        for log_file in self.log_dir.glob("*.log*"):
            try:
                file_stat = log_file.stat()
                stats['log_files'].append({
                    'name': log_file.name,
                    'size_bytes': file_stat.st_size,
                    'modified': datetime.fromtimestamp(file_stat.st_mtime).isoformat()
                })
            except Exception:
                pass
        
        return stats


# Global logger manager instance
_logger_manager: Optional[LoggerManager] = None


def initialize_logging(log_dir: str = "logs", 
                      log_level: str = "INFO",
                      **kwargs) -> LoggerManager:
    """
    Initialize global logging system.
    
    Args:
        log_dir: Directory for log files
        log_level: Minimum log level
        **kwargs: Additional LoggerManager arguments
        
    Returns:
        LoggerManager instance
    """
    global _logger_manager
    _logger_manager = LoggerManager(log_dir=log_dir, log_level=log_level, **kwargs)
    return _logger_manager


def get_logger(name: str) -> logging.Logger:
    """
    Get logger instance from global logger manager.
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    global _logger_manager
    if _logger_manager is None:
        _logger_manager = LoggerManager()
    
    return _logger_manager.get_logger(name)