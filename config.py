import os
import re
from dotenv import load_dotenv
from logger import cfo_logger

class Config:
    """Configuration manager for the CFO Agent.
    
    Handles loading of environment variables, API keys, and application settings.
    """
    
    def __init__(self, env_file=".env"):
        """Initialize the configuration from environment variables."""
        try:
            # Check if env file exists
            if not os.path.exists(env_file):
                cfo_logger.warning(f"Environment file {env_file} not found. Using system environment variables.")
            else:
                # Load environment variables from .env file
                load_dotenv(env_file)
                cfo_logger.info(f"Loaded configuration from {env_file}")
            
            # QuickBooks API credentials - always required now
            self.quickbooks_client_id = self._get_env("QUICKBOOKS_CLIENT_ID", required=True)
            self.quickbooks_client_secret = self._get_env("QUICKBOOKS_CLIENT_SECRET", required=True)
            self.quickbooks_refresh_token = self._get_env("QUICKBOOKS_REFRESH_TOKEN", required=True)
            self.quickbooks_realm_id = self._get_env("QUICKBOOKS_REALM_ID", required=True)
            self.quickbooks_environment = "production"  # Always use production
            
            # Webhook configuration for real-time email notifications
            self.WEBHOOK_URL = self._get_env("WEBHOOK_URL", required=False)
            self.WEBHOOK_PORT = int(self._get_env("WEBHOOK_PORT", required=False, default="8008"))
            
            # Company information
            self.company_name = os.getenv("COMPANY_NAME", "My Company")
            self.company_tax_id = os.getenv("COMPANY_TAX_ID", "")
            
            # Validate fiscal year format (MM-DD)
            fiscal_year = os.getenv("COMPANY_FISCAL_YEAR", "01-01")
            if self._validate_date_format(fiscal_year, "%m-%d"):
                self.company_fiscal_year = fiscal_year
            else:
                cfo_logger.warning(f"Invalid COMPANY_FISCAL_YEAR format: {fiscal_year}. Must be MM-DD. Defaulting to 01-01.")
                self.company_fiscal_year = "01-01"
            
            # Application settings
            self.log_level = os.getenv("LOG_LEVEL", "INFO")
            if self.log_level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                cfo_logger.warning(f"Invalid LOG_LEVEL: {self.log_level}. Defaulting to INFO.")
                self.log_level = "INFO"
                
            # Parse data retention days
            try:
                self.data_retention_days = int(os.getenv("DATA_RETENTION_DAYS", "365"))
                if self.data_retention_days <= 0:
                    cfo_logger.warning("DATA_RETENTION_DAYS must be positive. Defaulting to 365.")
                    self.data_retention_days = 365
            except ValueError:
                cfo_logger.warning(f"Invalid DATA_RETENTION_DAYS: {os.getenv('DATA_RETENTION_DAYS')}. Must be an integer. Defaulting to 365.")
                self.data_retention_days = 365
            
            # Chat interface settings
            self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
            self.chat_model = os.getenv("CHAT_MODEL", "gpt-4")
            
            # Parse max context window
            try:
                self.max_context_window = int(os.getenv("MAX_CONTEXT_WINDOW", "8192"))
                if self.max_context_window <= 0:
                    cfo_logger.warning("MAX_CONTEXT_WINDOW must be positive. Defaulting to 8192.")
                    self.max_context_window = 8192
            except ValueError:
                cfo_logger.warning(f"Invalid MAX_CONTEXT_WINDOW: {os.getenv('MAX_CONTEXT_WINDOW')}. Must be an integer. Defaulting to 8192.")
                self.max_context_window = 8192
            
            # Email configuration
            self.EMAIL_IMAP_SERVER = self._get_env('EMAIL_IMAP_SERVER', required=True)
            self.EMAIL_SMTP_SERVER = self._get_env('EMAIL_SMTP_SERVER', required=True)
            self.EMAIL_USERNAME = self._get_env('EMAIL_USERNAME', required=True)
            
            # Gmail OAuth credentials
            self.GMAIL_CREDENTIALS_FILE = self._get_env('GMAIL_CREDENTIALS_FILE', required=False, default="credentials.json")
            self.GMAIL_TOKEN_FILE = self._get_env('GMAIL_TOKEN_FILE', required=False, default="token.pickle")
            
            # For backward compatibility, keep EMAIL_PASSWORD optional
            self.EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
            
            # Email monitoring settings
            self.EMAIL_CHECK_INTERVAL = int(self._get_env('EMAIL_CHECK_INTERVAL', required=False, default="60"))
            self.AUTHORIZED_EMAIL_SENDERS = self._parse_email_list(
                self._get_env('AUTHORIZED_EMAIL_SENDERS', required=False, default="hello@757handy.com,cfoledger@gmail.com")
            )
            
            # Security settings
            self.JWT_SECRET_KEY = self._get_env('JWT_SECRET_KEY', required=True)
            self.JWT_TOKEN_EXPIRY_DAYS = int(self._get_env('JWT_TOKEN_EXPIRY_DAYS', required=False, default="7"))
            
            # Application URL
            self.APP_URL = self._get_env('APP_URL', required=True)
            
            # Always use production mode
            self.demo_mode = False
            
            cfo_logger.info("Configuration loaded successfully")
            
        except Exception as e:
            cfo_logger.error(f"Error loading configuration: {str(e)}")
            raise
    
    def _get_env(self, var_name, required=True, default=""):
        """Get an environment variable with proper error handling."""
        value = os.getenv(var_name, default)
        if required and not value:
            error_msg = f"Required environment variable {var_name} is not set"
            cfo_logger.warning(error_msg)
            raise ValueError(error_msg)
        return value
    
    def _validate_date_format(self, date_string, format_string):
        """Validate that a date string matches the expected format."""
        import datetime
        try:
            datetime.datetime.strptime(date_string, format_string)
            return True
        except ValueError:
            return False
    
    def _parse_boolean(self, value):
        """Parse a string boolean value."""
        if isinstance(value, bool):
            return value
        return value.lower() in ('true', 'yes', '1', 't', 'y')
    
    def _parse_email_list(self, email_string):
        """
        Parse a comma-separated list of email addresses.
        
        Args:
            email_string: Comma-separated list of emails
            
        Returns:
            List of email addresses
        """
        if not email_string:
            return []
            
        emails = [email.strip() for email in email_string.split(',')]
        validated_emails = []
        
        for email in emails:
            # Basic email validation
            if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                validated_emails.append(email.lower())
            else:
                cfo_logger.warning(f"Invalid email in AUTHORIZED_EMAIL_SENDERS: {email}")
        
        return validated_emails

# Global config instance
try:
    config = Config()
except Exception as e:
    cfo_logger.critical(f"Failed to initialize configuration: {str(e)}")
    # Create a minimal config to allow the application to partially function
    from types import SimpleNamespace
    config = SimpleNamespace(
        quickbooks_environment="production",
        company_name="Company (Config Error)",
        log_level="INFO",
        data_retention_days=365,
        chat_model="gpt-4",
        max_context_window=8192,
        demo_mode=False,
        AUTHORIZED_EMAIL_SENDERS=["hello@757handy.com"],
        EMAIL_CHECK_INTERVAL=60,
        JWT_TOKEN_EXPIRY_DAYS=7,
        # Add minimal configuration to avoid attribute errors
        quickbooks_client_id="",
        quickbooks_client_secret="",
        quickbooks_refresh_token="",
        quickbooks_realm_id="",
        company_tax_id="",
        company_fiscal_year="01-01",
        openai_api_key="",
        EMAIL_IMAP_SERVER="",
        EMAIL_SMTP_SERVER="",
        EMAIL_USERNAME="",
        EMAIL_PASSWORD="",
        JWT_SECRET_KEY="",
        APP_URL="",
        # Add Gmail API credentials
        GMAIL_CREDENTIALS_FILE="credentials.json",
        GMAIL_TOKEN_FILE="token.pickle"
    ) 