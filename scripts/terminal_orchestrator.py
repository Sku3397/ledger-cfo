#!/usr/bin/env python
"""
Terminal Orchestrator Script for ledger project.

This script launches shell commands in separate background processes,
polls their stdout/stderr at intervals, enforces timeouts, and returns
structured results.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import threading
from datetime import datetime
from pathlib import Path


class TerminalOrchestrator:
    """Class to manage running terminal commands with polling and timeouts."""

    def __init__(self, name, cmd, log_dir="scripts/logs"):
        """Initialize the orchestrator.

        Args:
            name: Name for this command execution (e.g., ledger-step-1)
            cmd: Command string to execute
            log_dir: Directory to store log files
        """
        self.name = name
        self.cmd = cmd
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{name}.json"
        self.process = None
        self.exit_code = None
        self.output = ""
        self.status = "running"
        self.start_time = None
        self.end_time = None
        
        # Define polling intervals in seconds
        self.poll_intervals = [2, 5, 10, 30, 60, 120, 300]
        self.timeout = 300  # 5 minutes max execution time
        
        # Patterns that indicate early success
        self.success_patterns = ["DONE", "OK", "Success", "Finished", "Complete"]

    def run(self):
        """Run the command and poll for results."""
        print(f"Starting command: {self.name}\nCommand: {self.cmd}")
        
        # Start the process
        self.start_time = datetime.now()
        
        # Using shell=True for command string parsing
        self.process = subprocess.Popen(
            self.cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Start polling thread to avoid blocking
        poll_thread = threading.Thread(target=self._poll_process)
        poll_thread.daemon = True
        poll_thread.start()
        
        # Wait for the thread to complete
        poll_thread.join(self.timeout)
        
        # If thread is still alive after timeout, process is still running
        if poll_thread.is_alive():
            print(f"Command '{self.name}' timed out after {self.timeout} seconds")
            self.status = "timeout"
            self._terminate_process()
        
        # Write final results
        self._write_results()
        
        return {
            "name": self.name,
            "exit_code": self.exit_code,
            "status": self.status,
            "output": self.output
        }

    def _poll_process(self):
        """Poll the process at increasing intervals."""
        elapsed_time = 0
        
        # Use a separate thread to read output to avoid blocking
        stdout_thread = threading.Thread(target=self._read_output)
        stdout_thread.daemon = True
        stdout_thread.start()
        
        for interval in self.poll_intervals:
            time.sleep(interval)
            elapsed_time += interval
            
            # Check if process has completed
            if self.process.poll() is not None:
                self.exit_code = self.process.returncode
                self.status = "success" if self.exit_code == 0 else "failure"
                self.end_time = datetime.now()
                print(f"Command '{self.name}' completed with exit code {self.exit_code}")
                break
            
            # Check for success patterns
            if any(pattern in self.output for pattern in self.success_patterns):
                print(f"Command '{self.name}' completed successfully (pattern match)")
                self.status = "success"
                self._terminate_process()
                break
            
            # Check if we've reached the timeout
            if elapsed_time >= self.timeout:
                print(f"Command '{self.name}' timed out after {elapsed_time} seconds")
                self.status = "timeout"
                self._terminate_process()
                break
            
            print(f"Polling '{self.name}' after {elapsed_time}s - still running")
        
        # Make sure we get the final output
        stdout_thread.join(10)  # Wait up to 10 seconds for output thread

    def _read_output(self):
        """Read process output continuously."""
        for line in iter(self.process.stdout.readline, ''):
            if line:
                self.output += line
                print(f"[{self.name}] {line.rstrip()}")
        
        # Read any stderr
        for line in iter(self.process.stderr.readline, ''):
            if line:
                self.output += f"ERROR: {line}"
                print(f"[{self.name}] ERROR: {line.rstrip()}")

    def _terminate_process(self):
        """Terminate the process if it's still running."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            
            self.exit_code = self.process.returncode
            self.end_time = datetime.now()

    def _write_results(self):
        """Write results to a JSON file."""
        result = {
            "name": self.name,
            "exit_code": self.exit_code,
            "status": self.status,
            "output": self.output,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": (self.end_time - self.start_time).total_seconds() if self.end_time and self.start_time else None
        }
        
        with open(self.log_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"Results written to {self.log_file}")


def main():
    """Parse arguments and run the orchestrator."""
    parser = argparse.ArgumentParser(description='Run a command with polling and timeout')
    parser.add_argument('--name', required=True, help='Name for this command execution')
    parser.add_argument('--cmd', required=True, help='Command to execute')
    parser.add_argument('--log-dir', default='scripts/logs', help='Directory to store logs')
    
    args = parser.parse_args()
    
    orchestrator = TerminalOrchestrator(
        name=args.name,
        cmd=args.cmd,
        log_dir=args.log_dir
    )
    
    result = orchestrator.run()
    
    # Exit with the same code as the command
    if result["exit_code"] is not None:
        sys.exit(result["exit_code"])
    else:
        sys.exit(1 if result["status"] != "success" else 0)


if __name__ == "__main__":
    main() 