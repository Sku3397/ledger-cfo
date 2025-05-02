#!/usr/bin/env python
"""
Mypy Daemon Manager

This script manages the mypy daemon (dmypy) for improved type checking performance.
It can start, stop, restart, and status check the daemon, as well as run type checking.
"""

import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path


class MypyDaemonManager:
    """Manages the mypy daemon for improved type checking performance."""

    def __init__(self, mypy_flags=None, cache_dir=None):
        """Initialize the manager.

        Args:
            mypy_flags: List of flags to pass to mypy
            cache_dir: Directory to use for caching
        """
        self.mypy_flags = mypy_flags or []
        self.cache_dir = cache_dir

        # Ensure we use fine-grained cache
        if "--cache-fine-grained" not in self.mypy_flags:
            self.mypy_flags.append("--cache-fine-grained")

        # Set the cache directory if provided
        if self.cache_dir:
            self.mypy_flags.append(f"--cache-dir={self.cache_dir}")
            # Create the cache dir if it doesn't exist
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    def get_daemon_status(self):
        """Check if the daemon is running.

        Returns:
            bool: True if the daemon is running, False otherwise
        """
        result = subprocess.run(["dmypy", "status"], capture_output=True, text=True)
        return result.returncode == 0

    def start_daemon(self):
        """Start the mypy daemon.

        Returns:
            bool: True if the daemon started successfully, False otherwise
        """
        # First check if it's already running
        if self.get_daemon_status():
            print("Daemon is already running.")
            return True

        # Build the command
        cmd = ["dmypy", "start", "--"]

        # Add --use-fine-grained-cache for improved daemon performance
        cmd.append("--use-fine-grained-cache")

        # Add any additional mypy flags
        cmd.extend(self.mypy_flags)

        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"Started mypy daemon: {result.stdout.strip()}")
            return True
        else:
            print(f"Failed to start mypy daemon: {result.stderr.strip()}")
            return False

    def stop_daemon(self):
        """Stop the mypy daemon.

        Returns:
            bool: True if the daemon stopped successfully, False otherwise
        """
        result = subprocess.run(["dmypy", "stop"], capture_output=True, text=True)

        if result.returncode == 0:
            print(f"Stopped mypy daemon: {result.stdout.strip()}")
            return True
        else:
            print(f"Failed to stop mypy daemon: {result.stderr.strip()}")
            return False

    def restart_daemon(self):
        """Restart the mypy daemon.

        Returns:
            bool: True if the daemon restarted successfully, False otherwise
        """
        # Build the command
        cmd = ["dmypy", "restart", "--"]

        # Add --use-fine-grained-cache for improved daemon performance
        cmd.append("--use-fine-grained-cache")

        # Add any additional mypy flags
        cmd.extend(self.mypy_flags)

        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"Restarted mypy daemon: {result.stdout.strip()}")
            return True
        else:
            print(f"Failed to restart mypy daemon: {result.stderr.strip()}")
            return False

    def run_check(self, files_or_dirs=None, run_flags=None):
        """Run mypy check on the specified files or directories.

        Args:
            files_or_dirs: List of files or directories to check
            run_flags: Additional flags for dmypy run

        Returns:
            bool: True if the check passed, False otherwise
        """
        files_or_dirs = files_or_dirs or ["."]
        run_flags = run_flags or []

        # Build the command
        cmd = ["dmypy", "run"]

        # Add any run flags
        cmd.extend(run_flags)

        # Add the separator
        cmd.append("--")

        # Add mypy flags
        cmd.extend(self.mypy_flags)

        # Add files or directories to check
        cmd.extend(files_or_dirs)

        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Print the output
        if result.stdout.strip():
            print("Output:")
            print(result.stdout.strip())

        if result.stderr.strip():
            print("Errors:")
            print(result.stderr.strip())

        if result.returncode == 0:
            print("Type check passed!")
            return True
        else:
            print(f"Type check failed with exit code {result.returncode}")
            return False

    def run_check_incremental(self, files_or_dirs=None, run_flags=None):
        """Run mypy check incrementally, ensuring the daemon is running.

        Args:
            files_or_dirs: List of files or directories to check
            run_flags: Additional flags for dmypy run

        Returns:
            bool: True if the check passed, False otherwise
        """
        # Ensure daemon is running
        if not self.get_daemon_status():
            print("Daemon not running, starting it...")
            if not self.start_daemon():
                print("Failed to start daemon, running non-incremental check.")
                return self.run_check(files_or_dirs, run_flags)

        return self.run_check(files_or_dirs, run_flags)

    def run_check_with_remote_cache(
        self, branch="main", repo_url=None, files_or_dirs=None, run_flags=None
    ):
        """Run mypy check with remote cache for improved performance.

        This method fetches the mypy cache based on the merge-base with the specified branch,
        then runs mypy with that cache.

        Args:
            branch: The branch to use as the base for the cache
            repo_url: The URL of the repository containing cache data
            files_or_dirs: List of files or directories to check
            run_flags: Additional flags for dmypy run

        Returns:
            bool: True if the check passed, False otherwise
        """
        if not repo_url:
            print("No repository URL specified for remote cache.")
            return self.run_check_incremental(files_or_dirs, run_flags)

        # Get the merge base with the specified branch
        result = subprocess.run(
            ["git", "merge-base", "HEAD", f"origin/{branch}"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"Failed to get merge base with {branch}: {result.stderr.strip()}")
            return self.run_check_incremental(files_or_dirs, run_flags)

        merge_base = result.stdout.strip()
        print(f"Merge base with {branch}: {merge_base}")

        # Create a temporary cache directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Download the cache data
            cache_url = f"{repo_url}/cache/{merge_base}.tar.gz"
            download_cmd = f"curl -L {cache_url} -o {temp_dir}/cache.tar.gz"

            print(f"Downloading cache data from {cache_url}...")
            download_result = subprocess.run(
                download_cmd, shell=True, capture_output=True, text=True
            )

            if download_result.returncode != 0:
                print(
                    f"Failed to download cache data: {download_result.stderr.strip()}"
                )
                return self.run_check_incremental(files_or_dirs, run_flags)

            # Extract the cache data
            print("Extracting cache data...")
            extract_cmd = f"tar -xzf {temp_dir}/cache.tar.gz -C {temp_dir}"
            extract_result = subprocess.run(
                extract_cmd, shell=True, capture_output=True, text=True
            )

            if extract_result.returncode != 0:
                print(f"Failed to extract cache data: {extract_result.stderr.strip()}")
                return self.run_check_incremental(files_or_dirs, run_flags)

            # Update the cache directory
            self.cache_dir = f"{temp_dir}/.mypy_cache"

            # Update mypy flags
            self.mypy_flags = [
                flag for flag in self.mypy_flags if not flag.startswith("--cache-dir=")
            ]
            self.mypy_flags.append(f"--cache-dir={self.cache_dir}")

            # Restart the daemon to use the new cache
            print("Restarting daemon with the downloaded cache...")
            self.restart_daemon()

            # Run the check
            return self.run_check(files_or_dirs, run_flags)


def main():
    """Parse command line arguments and run the appropriate command."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Manage the mypy daemon for improved type checking performance"
    )
    parser.add_argument(
        "command",
        choices=["start", "stop", "restart", "status", "run", "run-cached"],
        help="Command to run",
    )
    parser.add_argument("--mypy-flags", nargs="*", help="Flags to pass to mypy")
    parser.add_argument("--cache-dir", help="Directory to use for caching")
    parser.add_argument("--files", nargs="*", help="Files or directories to check")
    parser.add_argument(
        "--branch",
        default="main",
        help="Branch to use as base for remote cache (for run-cached)",
    )
    parser.add_argument(
        "--repo-url", help="Repository URL containing cache data (for run-cached)"
    )

    args = parser.parse_args()

    manager = MypyDaemonManager(mypy_flags=args.mypy_flags, cache_dir=args.cache_dir)

    if args.command == "start":
        success = manager.start_daemon()
    elif args.command == "stop":
        success = manager.stop_daemon()
    elif args.command == "restart":
        success = manager.restart_daemon()
    elif args.command == "status":
        running = manager.get_daemon_status()
        print(f"Mypy daemon is {'running' if running else 'not running'}")
        success = True
    elif args.command == "run":
        success = manager.run_check_incremental(files_or_dirs=args.files)
    elif args.command == "run-cached":
        success = manager.run_check_with_remote_cache(
            branch=args.branch, repo_url=args.repo_url, files_or_dirs=args.files
        )
    else:
        print(f"Unknown command: {args.command}")
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
