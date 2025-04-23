import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
import traceback

class CFOLogger:
    def __init__(self, log_dir="logs"):
        """Initialize the logger with proper UTF-8 encoding for Windows compatibility."""
        # Normalize path to handle cross-platform compatibility
        self.log_dir = os.path.normpath(log_dir)
        
        # Create logs directory if it doesn't exist
        if not os.path.exists(self.log_dir):
            try:
                os.makedirs(self.log_dir)
            except Exception as e:
                print(f"Error creating log directory: {str(e)}")
                # Fallback to current directory
                self.log_dir = "."
                if not os.path.exists(self.log_dir):
                    os.makedirs(self.log_dir)
            
        self.log_file = os.path.join(self.log_dir, f"cfo_agent_{datetime.now().strftime('%Y%m%d')}.log")
        
        # Configure logger
        self.logger = logging.getLogger("CFOAgentLogger")
        self.logger.setLevel(logging.INFO)
        
        # Clear any existing handlers to prevent duplicate logging
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        try:
            # Console handler with UTF-8 encoding
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            
            # File handler with UTF-8 encoding and rotation
            file_handler = RotatingFileHandler(
                self.log_file, 
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8',
                delay=True  # Delay file creation until first log
            )
            file_handler.setLevel(logging.DEBUG)
            
            # Create formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            file_handler.setFormatter(formatter)
            
            # Add handlers to logger
            self.logger.addHandler(console_handler)
            self.logger.addHandler(file_handler)
            
            # Test log file creation
            self.info("Logger initialized successfully")
            
        except Exception as e:
            print(f"Error configuring logger: {str(e)}")
            # Create simplified logger as fallback
            self._setup_fallback_logger()
        
    def _setup_fallback_logger(self):
        """Set up a simplified fallback logger if the main logger fails."""
        self.logger = logging.getLogger("CFOAgentFallbackLogger")
        self.logger.setLevel(logging.INFO)
        
        # Clear any existing handlers
        if self.logger.handlers:
            self.logger.handlers.clear()
            
        # Console-only handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - FALLBACK - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        self.logger.warning("Using fallback logger due to error initializing main logger")
        
    def info(self, message):
        """Log an info level message."""
        try:
            self.logger.info(message)
        except Exception as e:
            print(f"Logging error: {str(e)} - Message: {message}")
        
    def error(self, message, exc_info=True):
        """Log an error with exception information."""
        try:
            self.logger.error(message, exc_info=exc_info)
        except Exception as e:
            print(f"Logging error: {str(e)} - Error message: {message}")
        
    def warning(self, message):
        """Log a warning message."""
        try:
            self.logger.warning(message)
        except Exception as e:
            print(f"Logging error: {str(e)} - Warning: {message}")
        
    def debug(self, message):
        """Log a debug message."""
        try:
            self.logger.debug(message)
        except Exception as e:
            print(f"Logging error: {str(e)} - Debug: {message}")

    def critical(self, message, exc_info=True):
        """Log a critical error with exception information."""
        try:
            self.logger.critical(message, exc_info=exc_info)
        except Exception as e:
            print(f"Logging error: {str(e)} - Critical: {message}")

# Global logger instance
try:
    cfo_logger = CFOLogger()
except Exception as e:
    # Last-resort fallback if logger instantiation fails
    print(f"Fatal error creating logger: {str(e)}")
    
    # Create a minimal logger as fallback
    basic_logger = logging.getLogger("BasicLogger")
    basic_handler = logging.StreamHandler(sys.stdout)
    basic_logger.addHandler(basic_handler)
    cfo_logger = basic_logger 