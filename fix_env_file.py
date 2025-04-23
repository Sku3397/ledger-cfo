#!/usr/bin/env python
"""
Fix .env file script for CFO Agent.

This script checks and fixes the .env file, ensuring that all required settings
are present and correctly formatted, particularly focusing on the 
AUTHORIZED_EMAIL_SENDERS list.
"""

import os
import re
from pathlib import Path
import shutil

def main():
    print("CFO Agent Environment File Fixer")
    print("--------------------------------")
    
    # Check if .env file exists
    env_path = Path(".env")
    if not env_path.exists():
        print("Error: .env file not found!")
        # Check if there's a .env.example we can copy
        if Path(".env.example").exists():
            print("Found .env.example - creating .env from example...")
            shutil.copy(".env.example", ".env")
        elif Path(".env.correct").exists():
            print("Found .env.correct - creating .env from correct version...")
            shutil.copy(".env.correct", ".env")
        else:
            print("No template found. Cannot create .env file.")
            return 1
    
    # Read the current .env file
    with open(".env", "r") as f:
        lines = f.readlines()
    
    # Process the file
    authorized_senders_found = False
    new_lines = []
    
    for line in lines:
        # Check for AUTHORIZED_EMAIL_SENDERS line
        if line.strip().startswith("AUTHORIZED_EMAIL_SENDERS="):
            authorized_senders_found = True
            
            # Extract the current value
            current_value = line.strip().split("=", 1)[1].strip()
            
            # Parse the current senders
            if current_value.startswith('"') and current_value.endswith('"'):
                current_value = current_value[1:-1]
            elif current_value.startswith("'") and current_value.endswith("'"):
                current_value = current_value[1:-1]
                
            # Split and clean the senders
            senders = [s.strip() for s in current_value.split(",")]
            
            # Make sure required senders are included
            required_senders = ["hello@757handy.com", "cfoledger@gmail.com"]
            for sender in required_senders:
                if sender.lower() not in [s.lower() for s in senders]:
                    senders.append(sender)
            
            # Format the new line
            new_line = f"AUTHORIZED_EMAIL_SENDERS={','.join(senders)}\n"
            new_lines.append(new_line)
            print(f"Updated authorized senders: {','.join(senders)}")
        else:
            new_lines.append(line)
    
    # If AUTHORIZED_EMAIL_SENDERS wasn't found, add it
    if not authorized_senders_found:
        new_lines.append("AUTHORIZED_EMAIL_SENDERS=hello@757handy.com,cfoledger@gmail.com\n")
        print("Added missing AUTHORIZED_EMAIL_SENDERS setting")
    
    # Write the updated file
    with open(".env", "w") as f:
        f.writelines(new_lines)
    
    print("\nEnvironment file check complete.")
    print("You may need to restart the application for changes to take effect.")
    
    return 0

if __name__ == "__main__":
    exit(main()) 