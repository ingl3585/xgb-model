"""
Comprehensive logging infrastructure for TCP-based trading system.

This module provides structured logging with JSON formatting, thread safety,
log rotation, and performance-optimized configurations for financial trading systems.
"""

import json
import logging
import logging.handlers
import os
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional


class TradingJsonFormatter(logging.Formatter):
    """
    Custom JSON formatter for trading system logs.
    
    Provides structured logging with contextual information including:
    - Timestamp with microsecond precision
    - Thread ID for multi-threaded debugging
    - Process ID for multi-process environments
    - Component identification
    - Performance metrics
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        # Build base log entry
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(timespec='microseconds'),
            'level': record.levelname,
            'component': record.name,
            'thread_id': threading.get_ident(),
            'process_id': os.getpid(),
            'message': record.getMessage()
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info)
            }
        
        # Add extra fields from the log record
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in {'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                          'filename', 'module', 'lineno', 'funcName', 'created',
                          'msecs', 'relativeCreated', 'thread', 'threadName',
                          'processName', 'process', 'getMessage', 'exc_info',
                          'exc_text', 'stack_info', 'message'}:
                extra_fields[key] = value
        
        if extra_fields:
            log_entry['extra'] = extra_fields
        
        return json.dumps(log_entry, ensure_ascii=False)


class PerformanceFilter(logging.Filter):
    """
    Filter to add performance metrics to log records.
    
    Tracks timing information for performance-critical operations
    and adds execution duration to log records when available.
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add performance metrics to log record if available."""
        # Add execution time if provided in extra fields
        if hasattr(record, 'execution_time'):
            record.performance_ms = round(record.execution_time * 1000, 3)
        
        return True


class TradingLoggerManager:
    """
    Centralized logger management for the trading system.
    
    Provides thread-safe logger creation, configuration management,
    and consistent formatting across all trading system components.
    """
    
    _instance = None
    _lock = threading.Lock()
    _loggers: Dict[str, logging.Logger] = {}
    
    def __new__(cls):
        """Implement singleton pattern for consistent logging configuration."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(TradingLoggerManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize logging manager with default configuration."""
        if not getattr(self, '_initialized', False):
            self.log_directory = 'logs'
            self.log_level = logging.INFO
            self.max_file_size = 50 * 1024 * 1024  # 50MB
            self.backup_count = 10
            self.console_logging = True
            self._setup_log_directory()
            self._initialized = True
    
    def _setup_log_directory(self) -> None:
        """Create log directory if it doesn't exist."""
        if not os.path.exists(self.log_directory):
            os.makedirs(self.log_directory)
    
    def configure_logging(self, 
                         log_level: int = logging.INFO,
                         log_directory: str = 'logs',
                         max_file_size: int = 50 * 1024 * 1024,
                         backup_count: int = 10,
                         console_logging: bool = True) -> None:
        """
        Configure global logging settings.
        
        Args:
            log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_directory: Directory for log files
            max_file_size: Maximum size per log file in bytes
            backup_count: Number of backup files to retain
            console_logging: Whether to log to console
        """
        self.log_level = log_level
        self.log_directory = log_directory
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.console_logging = console_logging
        self._setup_log_directory()
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Get or create a logger with consistent configuration.
        
        Args:
            name: Logger name (e.g., 'trading.tcp', 'trading.model')
            
        Returns:
            Configured logger instance
        """
        if name in self._loggers:
            return self._loggers[name]
        
        with self._lock:
            if name in self._loggers:
                return self._loggers[name]
            
            logger = logging.getLogger(name)
            logger.setLevel(self.log_level)
            
            # Remove any existing handlers to avoid duplicates
            logger.handlers.clear()
            
            # Create JSON formatter
            json_formatter = TradingJsonFormatter()
            
            # Add performance filter
            perf_filter = PerformanceFilter()
            
            # Configure file handler with rotation
            log_filename = os.path.join(self.log_directory, f'{name.replace(".", "_")}.log')
            file_handler = logging.handlers.RotatingFileHandler(
                log_filename,
                maxBytes=self.max_file_size,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            file_handler.setFormatter(json_formatter)
            file_handler.addFilter(perf_filter)
            logger.addHandler(file_handler)
            
            # Configure console handler if enabled
            if self.console_logging:
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(json_formatter)
                console_handler.addFilter(perf_filter)
                logger.addHandler(console_handler)
            
            # Prevent propagation to root logger
            logger.propagate = False
            
            self._loggers[name] = logger
            return logger


# Global logger manager instance
logger_manager = TradingLoggerManager()


def get_trading_logger(component: str) -> logging.Logger:
    """
    Convenience function to get a trading system logger.
    
    Args:
        component: Component name (tcp, model, signals, data, system)
        
    Returns:
        Configured logger for the component
    """
    logger_name = f'trading.{component}'
    return logger_manager.get_logger(logger_name)


def log_performance(logger: logging.Logger, operation: str):
    """
    Decorator to log performance metrics for trading operations.
    
    Args:
        logger: Logger instance to use
        operation: Description of the operation being timed
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.info(
                    f"{operation} completed successfully",
                    extra={
                        'operation': operation,
                        'execution_time': execution_time,
                        'function': func.__name__
                    }
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(
                    f"{operation} failed: {str(e)}",
                    extra={
                        'operation': operation,
                        'execution_time': execution_time,
                        'function': func.__name__,
                        'error_type': type(e).__name__
                    },
                    exc_info=True
                )
                raise
        return wrapper
    return decorator


def log_trading_event(logger: logging.Logger, 
                     event_type: str, 
                     **kwargs) -> None:
    """
    Log standardized trading events with consistent structure.
    
    Args:
        logger: Logger instance to use
        event_type: Type of trading event (signal, connection, data, etc.)
        **kwargs: Additional event-specific data
    """
    logger.info(
        f"Trading event: {event_type}",
        extra={
            'event_type': event_type,
            'event_data': kwargs
        }
    )


def setup_trading_logging(log_level: str = 'INFO',
                         log_directory: str = 'logs',
                         console_output: bool = True) -> None:
    """
    Initialize the trading system logging infrastructure.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_directory: Directory for log files
        console_output: Whether to output logs to console
    """
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    
    numeric_level = level_map.get(log_level.upper(), logging.INFO)
    
    logger_manager.configure_logging(
        log_level=numeric_level,
        log_directory=log_directory,
        console_logging=console_output
    )
    
    # Log system initialization
    system_logger = get_trading_logger('system')
    system_logger.info(
        "Trading system logging initialized",
        extra={
            'log_level': log_level,
            'log_directory': log_directory,
            'console_output': console_output
        }
    )