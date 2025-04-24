#!/usr/bin/env python
"""
Ledger Pipeline Runner

This script defines and runs the pipeline for the ledger project using the 
terminal orchestrator to manage command execution.
"""

import os
import sys
import json
import time
from pathlib import Path

# Define the pipeline steps
PIPELINE_STEPS = [
    {
        "name": "ledger-step-1",
        "description": "Build the ledger Docker image",
        "cmd": "docker build -t ledger-app:latest ."
    },
    {
        "name": "ledger-step-2",
        "description": "Tag the Docker image for Cloud Registry",
        "cmd": "docker tag ledger-app:latest gcr.io/ledger-457022/ledger-app:latest"
    },
    {
        "name": "ledger-step-3",
        "description": "Push the Docker image to Cloud Registry",
        "cmd": "docker push gcr.io/ledger-457022/ledger-app:latest"
    },
    {
        "name": "ledger-step-4",
        "description": "Deploy the Cloud Run service",
        "cmd": "gcloud run deploy ledger --image gcr.io/ledger-457022/ledger-app:latest --platform managed --region us-central1 --allow-unauthenticated"
    },
    {
        "name": "ledger-step-5",
        "description": "Get the deployed service URL",
        "cmd": "gcloud run services describe ledger --platform managed --region us-central1 --format='value(status.url)'"
    },
    {
        "name": "ledger-step-6",
        "description": "Test the deployed service",
        "cmd": "curl -X POST -H 'Content-Type: application/json' $(gcloud run services describe ledger --platform managed --region us-central1 --format='value(status.url)')/api/v1/ledger/process -d '{\"query\": \"test query\"}'"
    }
]

def run_pipeline(start_from=0, end_at=None):
    """Run the pipeline steps from start_from to end_at (inclusive)."""
    
    if end_at is None:
        end_at = len(PIPELINE_STEPS) - 1
    
    results = []
    
    print(f"Starting ledger pipeline from step {start_from} to step {end_at}")
    
    # Create logs directory if it doesn't exist
    logs_dir = Path("scripts/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Run each step
    for i, step in enumerate(PIPELINE_STEPS[start_from:end_at+1], start=start_from):
        print(f"\n== Step {i}: {step['description']} ==")
        
        # Run the step using the orchestrator
        cmd = f"python scripts/terminal_orchestrator.py --name {step['name']} --cmd \"{step['cmd']}\""
        exit_code = os.system(cmd)
        
        # Load the results
        result_file = logs_dir / f"{step['name']}.json"
        if result_file.exists():
            with open(result_file, 'r') as f:
                result = json.load(f)
            
            results.append(result)
            
            # If the step failed, stop the pipeline
            if result['status'] != 'success':
                print(f"\n!! Step {i}: {step['description']} failed !!")
                print(f"Status: {result['status']}")
                print(f"Exit code: {result['exit_code']}")
                print("Output:")
                print(result['output'])
                print("\nPipeline execution stopped due to step failure")
                break
        else:
            print(f"Error: Result file not found for step {step['name']}")
            break
    
    # Write the pipeline summary
    summary_file = logs_dir / "pipeline_summary.json"
    summary = {
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "steps_executed": len(results),
        "steps_succeeded": sum(1 for r in results if r['status'] == 'success'),
        "steps_failed": sum(1 for r in results if r['status'] != 'success'),
        "details": results
    }
    
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print("\n== Pipeline Summary ==")
    print(f"Steps executed: {summary['steps_executed']}")
    print(f"Steps succeeded: {summary['steps_succeeded']}")
    print(f"Steps failed: {summary['steps_failed']}")
    print(f"Summary written to: {summary_file}")
    
    # Return True if all steps succeeded
    return all(r['status'] == 'success' for r in results)

def main():
    """Parse command line arguments and run the pipeline."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run the ledger pipeline')
    parser.add_argument('--start-from', type=int, default=0, help='Step to start from (0-based)')
    parser.add_argument('--end-at', type=int, default=None, help='Step to end at (0-based, inclusive)')
    parser.add_argument('--list', action='store_true', help='List the pipeline steps and exit')
    
    args = parser.parse_args()
    
    # List steps and exit if requested
    if args.list:
        print("Ledger Pipeline Steps:")
        for i, step in enumerate(PIPELINE_STEPS):
            print(f"{i}. {step['name']}: {step['description']}")
        return
    
    # Validate step range
    if args.start_from < 0 or args.start_from >= len(PIPELINE_STEPS):
        print(f"Error: start-from must be between 0 and {len(PIPELINE_STEPS) - 1}")
        return
    
    if args.end_at is not None and (args.end_at < args.start_from or args.end_at >= len(PIPELINE_STEPS)):
        print(f"Error: end-at must be between {args.start_from} and {len(PIPELINE_STEPS) - 1}")
        return
    
    # Run the pipeline
    success = run_pipeline(args.start_from, args.end_at)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 