#!/usr/bin/env python
"""
Deploy Component Script

This script allows deploying a specific component or running a specific step
using the terminal orchestrator.
"""

import argparse
import os
import sys
import json
from pathlib import Path
import time

# Define available components and their deployment commands
COMPONENTS = {
    "api": {
        "description": "Deploy the API component",
        "cmd": "gcloud run deploy ledger-api --image gcr.io/ledger-457022/ledger-api:latest --platform managed --region us-central1 --allow-unauthenticated"
    },
    "ui": {
        "description": "Deploy the UI component",
        "cmd": "gcloud run deploy ledger-ui --image gcr.io/ledger-457022/ledger-ui:latest --platform managed --region us-central1 --allow-unauthenticated"
    },
    "worker": {
        "description": "Deploy the background worker",
        "cmd": "gcloud run deploy ledger-worker --image gcr.io/ledger-457022/ledger-worker:latest --platform managed --region us-central1 --no-allow-unauthenticated"
    },
    "database": {
        "description": "Deploy the database schema updates",
        "cmd": "python -m scripts.database.migrate"
    },
    "all": {
        "description": "Deploy all components",
        "cmd": "python scripts/orchestrate.py"
    }
}

def ensure_dirs():
    """Ensure the required directories exist."""
    Path("scripts/logs").mkdir(parents=True, exist_ok=True)

def deploy_component(component_name, timeout=300):
    """Deploy a specific component using the terminal orchestrator.
    
    Args:
        component_name: Name of the component to deploy
        timeout: Timeout in seconds
        
    Returns:
        bool: True if the deployment succeeded, False otherwise
    """
    if component_name not in COMPONENTS:
        print(f"Error: Unknown component '{component_name}'")
        return False
    
    component = COMPONENTS[component_name]
    print(f"\n=== Deploying component: {component_name} ===")
    print(f"Description: {component['description']}")
    print(f"Command: {component['cmd']}\n")
    
    # Use the terminal orchestrator to run the deployment
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"deploy-{component_name}-{timestamp}"
    
    cmd = f"python scripts/terminal_orchestrator.py --name {name} --cmd \"{component['cmd']}\""
    
    # Run the command
    exit_code = os.system(cmd)
    
    # Check the result
    result_file = Path(f"scripts/logs/{name}.json")
    if result_file.exists():
        with open(result_file, 'r') as f:
            result = json.load(f)
        
        if result['status'] == 'success':
            print(f"\n=== Successfully deployed component: {component_name} ===\n")
            return True
        else:
            print(f"\n=== Failed to deploy component: {component_name} ===")
            print(f"Status: {result['status']}")
            print(f"Exit code: {result['exit_code']}")
            print("Output excerpt:")
            output_excerpt = result['output'][:500] + "..." if len(result['output']) > 500 else result['output']
            print(output_excerpt)
            print("\n")
            return False
    else:
        print(f"\n=== Failed to deploy component: {component_name} ===")
        print(f"Error: Result file not found: {result_file}")
        print("\n")
        return False

def list_components():
    """List all available components."""
    print("Available components:")
    for name, details in COMPONENTS.items():
        print(f"  {name}: {details['description']}")

def main():
    """Parse command line arguments and deploy the specified component."""
    parser = argparse.ArgumentParser(description='Deploy a specific component')
    parser.add_argument('component', nargs='?', help='Component to deploy')
    parser.add_argument('--list', action='store_true', help='List available components')
    parser.add_argument('--timeout', type=int, default=300, help='Timeout in seconds')
    
    args = parser.parse_args()
    
    # Ensure directories exist
    ensure_dirs()
    
    # List components and exit if requested
    if args.list or not args.component:
        list_components()
        return 0
    
    # Deploy the specified component
    success = deploy_component(args.component, args.timeout)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 