"""
Logging utility for 3decision Plugin

Provides configurable logging that can be enabled/disabled via settings.

Version: 1.1
"""

import logging
import sys
from typing import Optional


class PluginLogHandler(logging.Handler):
    """Custom log handler that can be enabled/disabled"""
    
    def __init__(self, enabled: bool = False):
        super().__init__()
        self._enabled = enabled
        self.setLevel(logging.DEBUG)
        
        # Set up formatter
        formatter = logging.Formatter(
            '%(asctime)s - 3decision Plugin - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        self.setFormatter(formatter)
    
    def set_enabled(self, enabled: bool):
        """Enable or disable logging output"""
        self._enabled = enabled
    
    def is_enabled(self) -> bool:
        """Check if logging is enabled"""
        return self._enabled
    
    def emit(self, record):
        """Emit a log record if logging is enabled"""
        if self._enabled:
            try:
                msg = self.format(record)
                print(msg)
                sys.stdout.flush()
            except Exception:
                self.handleError(record)


class PluginLogger:
    """Singleton logger for the 3decision plugin"""
    
    _instance: Optional['PluginLogger'] = None
    _logger: Optional[logging.Logger] = None
    _handler: Optional[PluginLogHandler] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._logger is None:
            self._setup_logger()
    
    def _setup_logger(self):
        """Set up the logger with custom handler"""
        self._logger = logging.getLogger('3decision_plugin')
        self._logger.setLevel(logging.DEBUG)
        
        # Clear any existing handlers
        self._logger.handlers.clear()
        
        # Add our custom handler
        self._handler = PluginLogHandler(enabled=False)  # Disabled by default
        self._logger.addHandler(self._handler)
        
        # Prevent propagation to avoid duplicate messages
        self._logger.propagate = False
    
    def set_enabled(self, enabled: bool):
        """Enable or disable logging output"""
        if self._handler:
            self._handler.set_enabled(enabled)
    
    def is_enabled(self) -> bool:
        """Check if logging is enabled"""
        return self._handler.is_enabled() if self._handler else False
    
    def debug(self, message: str):
        """Log a debug message"""
        if self._logger:
            self._logger.debug(message)
    
    def info(self, message: str):
        """Log an info message"""
        if self._logger:
            self._logger.info(message)
    
    def warning(self, message: str):
        """Log a warning message"""
        if self._logger:
            self._logger.warning(message)
    
    def error(self, message: str):
        """Log an error message"""
        if self._logger:
            self._logger.error(message)
    
    def critical(self, message: str):
        """Log a critical message"""
        if self._logger:
            self._logger.critical(message)


# Global logger instance
logger = PluginLogger()

# Convenience functions for easy import
def log_debug(message: str):
    """Log a debug message"""
    logger.debug(message)

def log_info(message: str):
    """Log an info message"""
    logger.info(message)

def log_warning(message: str):
    """Log a warning message"""
    logger.warning(message)

def log_error(message: str):
    """Log an error message"""
    logger.error(message)

def log_critical(message: str):
    """Log a critical message"""
    logger.critical(message)

def set_logging_enabled(enabled: bool):
    """Enable or disable logging output"""
    logger.set_enabled(enabled)

def is_logging_enabled() -> bool:
    """Check if logging is enabled"""
    return logger.is_enabled()
