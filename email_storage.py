import json
import os
from datetime import datetime, timedelta
from typing import Set, List
from logger import cfo_logger
import threading

class EmailStorage:
    """Handles persistent storage of processed email IDs."""
    
    def __init__(self, storage_file: str = "processed_emails.json", max_age_days: int = 30):
        """Initialize the email storage.
        
        Args:
            storage_file: Path to the JSON file for storing email IDs
            max_age_days: Maximum age of stored email IDs in days
        """
        self.storage_file = storage_file
        self.max_age_days = max_age_days
        self.processed_ids: Set[str] = set()
        self._load_from_file()
    
    def _load_from_file(self) -> None:
        """Load processed email IDs from storage file."""
        try:
            if os.path.exists(self.storage_file):
                try:
                    with open(self.storage_file, 'r') as f:
                        data = json.load(f)
                        # Filter out old entries
                        cutoff_date = (datetime.now() - timedelta(days=self.max_age_days)).isoformat()
                        current_data = {
                            msg_id: timestamp 
                            for msg_id, timestamp in data.items() 
                            if timestamp >= cutoff_date
                        }
                        self.processed_ids = set(current_data.keys())
                        # Save filtered data back if any old entries were removed
                        if len(current_data) != len(data):
                            self._save_to_file()
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    cfo_logger.warning(f"Could not decode email storage file: {str(e)}. Creating a new one.")
                    self.processed_ids = set()
                    self._save_to_file()  # Create a new valid file
                except PermissionError:
                    cfo_logger.warning("Permission denied when accessing email storage file. Using in-memory storage only.")
                    self.processed_ids = set()
            else:
                self.processed_ids = set()
                # Try to create the storage file
                try:
                    self._save_to_file()
                except Exception as e:
                    cfo_logger.warning(f"Could not create email storage file: {str(e)}. Using in-memory storage only.")
        except Exception as e:
            cfo_logger.error(f"Error loading email storage: {str(e)}")
            self.processed_ids = set()
    
    def _save_to_file(self) -> None:
        """Save processed email IDs to storage file."""
        try:
            # Create storage directory if it doesn't exist
            storage_dir = os.path.dirname(self.storage_file)
            if storage_dir and not os.path.exists(storage_dir):
                try:
                    os.makedirs(storage_dir, exist_ok=True)
                except Exception as e:
                    cfo_logger.warning(f"Could not create storage directory: {str(e)}")
                    return
                
            # Create data dictionary with timestamps
            current_time = datetime.now().isoformat()
            data = {msg_id: current_time for msg_id in self.processed_ids}
            
            # Save to file (use a temp file to prevent corruption)
            temp_file = f"{self.storage_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(data, f)
                
            # Rename temp file to actual file
            if os.path.exists(self.storage_file):
                os.remove(self.storage_file)
            os.rename(temp_file, self.storage_file)
                
        except Exception as e:
            cfo_logger.error(f"Error saving email storage: {str(e)}")
    
    def add(self, message_id: str) -> None:
        """Add a message ID to storage.
        
        Args:
            message_id: The email message ID to store
        """
        if not message_id:
            return
            
        self.processed_ids.add(message_id)
        
        # Save in a background thread to avoid blocking
        threading.Thread(
            target=self._save_to_file,
            daemon=True
        ).start()
    
    def contains(self, message_id: str) -> bool:
        """Check if a message ID exists in storage.
        
        Args:
            message_id: The email message ID to check
            
        Returns:
            bool: True if the message ID exists in storage
        """
        return message_id in self.processed_ids
    
    def get_all(self) -> Set[str]:
        """Get all stored message IDs.
        
        Returns:
            Set[str]: Set of all stored message IDs
        """
        return self.processed_ids.copy()
    
    def clear(self) -> None:
        """Clear all stored message IDs."""
        self.processed_ids.clear()
        self._save_to_file() 