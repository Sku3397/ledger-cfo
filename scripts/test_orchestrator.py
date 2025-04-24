#!/usr/bin/env python
"""
Test script for the terminal orchestrator.
This script runs various tests to verify the functionality of the orchestrator.
"""

import os
import time
import json
from pathlib import Path

# Test cases:
# 1. Quick success - command that completes quickly and successfully
# 2. Slow success - command that takes some time to complete
# 3. Failure - command that fails
# 4. Timeout - command that times out

# Function to run a test
def run_test(name, cmd):
    print(f"Running test: {name}")
    os.system(f"python scripts/terminal_orchestrator.py --name {name} --cmd \"{cmd}\"")
    
    # Check if log file exists
    log_file = Path(f"scripts/logs/{name}.json")
    if log_file.exists():
        with open(log_file, 'r') as f:
            result = json.load(f)
        print(f"Test {name} completed with status: {result['status']}")
        print(f"Exit code: {result['exit_code']}")
        print(f"Duration: {result.get('duration_seconds', 'N/A')} seconds")
        print("Output excerpt:")
        output_excerpt = result['output'][:200] + "..." if len(result['output']) > 200 else result['output']
        print(output_excerpt)
    else:
        print(f"Error: Log file not found for test {name}")
    
    print("-" * 40)

# Run tests
def main():
    # Test 1: Quick success
    run_test("test-quick-success", "echo OK && exit 0")
    
    # Test 2: Slow success
    run_test("test-slow-success", "echo Starting && sleep 5 && echo DONE")
    
    # Test 3: Failure
    run_test("test-failure", "echo 'This will fail' && exit 1")
    
    # Test 4: Pattern Match
    run_test("test-pattern-match", "echo 'Starting work' && sleep 2 && echo 'OK' && sleep 10")
    
    # Test 5: Timeout (reduced timeout for testing)
    # This would normally timeout after 300s, but we want to see it within our test
    # So we modify the timeout in the script temporarily
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp:
        with open('scripts/terminal_orchestrator.py', 'r') as f:
            content = f.read()
        
        # Replace timeout with a shorter value for testing
        modified_content = content.replace('self.timeout = 300', 'self.timeout = 10')
        temp.write(modified_content)
        temp_path = temp.name
    
    # Run timeout test with modified orchestrator
    print("Running timeout test (modified orchestrator with 10s timeout)")
    os.system(f"python {temp_path} --name test-timeout --cmd \"echo 'Starting long process' && sleep 30 && echo 'Done'\"")
    
    # Restore original file
    os.unlink(temp_path)
    
    # Check the result
    log_file = Path("scripts/logs/test-timeout.json")
    if log_file.exists():
        with open(log_file, 'r') as f:
            result = json.load(f)
        print(f"Test test-timeout completed with status: {result['status']}")
        print(f"Exit code: {result['exit_code']}")
        print(f"Duration: {result.get('duration_seconds', 'N/A')} seconds")
    else:
        print("Error: Log file not found for timeout test")
    
    print("All tests completed")

if __name__ == "__main__":
    main() 