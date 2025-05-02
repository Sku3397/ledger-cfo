#!/usr/bin/env python
"""
Master Orchestration Script for Ledger Project

This script orchestrates the entire process, from type checking to deployment,
using the various tools we've built:
1. Mypy daemon for type checking
2. Terminal orchestrator for running commands with monitoring
3. Ledger pipeline for deployment
"""

import argparse
import os
import sys
import json
import time
from pathlib import Path


def run_command(cmd, capture_output=True):
    """Run a command and return the result."""
    import subprocess

    if capture_output:
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        return result.returncode, result.stdout, result.stderr
    else:
        return subprocess.call(cmd, shell=True), "", ""


def ensure_dirs():
    """Ensure the required directories exist."""
    Path("scripts/logs").mkdir(parents=True, exist_ok=True)


def type_check(args):
    """Run type checking with the mypy daemon manager."""
    print("\n=== Running Type Checking ===\n")

    # Use the mypy daemon manager to run the type check
    cmd = ["python", "scripts/mypy_daemon_manager.py", "run"]

    # Add any mypy flags
    if args.mypy_flags:
        cmd.append("--mypy-flags")
        cmd.extend(args.mypy_flags)

    # Add files to check
    if args.check_files:
        cmd.append("--files")
        cmd.extend(args.check_files)

    # Run the command
    exit_code, stdout, stderr = run_command(cmd, capture_output=False)

    if exit_code != 0:
        print("\n=== Type checking failed ===\n")
        return False

    print("\n=== Type checking succeeded ===\n")
    return True


def run_tests(args):
    """Run tests for the project."""
    print("\n=== Running Tests ===\n")

    # Use the terminal orchestrator to run the tests
    cmd = [
        "python",
        "scripts/terminal_orchestrator.py",
        "--name",
        "ledger-tests",
        "--cmd",
        args.test_command or "pytest",
    ]

    # Run the command
    exit_code = os.system(" ".join(cmd))

    # Check the result
    result_file = Path("scripts/logs/ledger-tests.json")
    if result_file.exists():
        with open(result_file, "r") as f:
            result = json.load(f)

        if result["status"] != "success":
            print("\n=== Tests failed ===\n")
            return False
    else:
        print("\n=== Failed to run tests ===\n")
        return False

    print("\n=== Tests succeeded ===\n")
    return True


def run_deployment(args):
    """Run the deployment pipeline."""
    print("\n=== Running Deployment ===\n")

    # Use the ledger pipeline to deploy
    cmd = ["python", "scripts/ledger_pipeline.py"]

    # Add start-from if specified
    if args.start_from is not None:
        cmd.extend(["--start-from", str(args.start_from)])

    # Add end-at if specified
    if args.end_at is not None:
        cmd.extend(["--end-at", str(args.end_at)])

    # Run the command
    exit_code = os.system(" ".join(cmd))

    if exit_code != 0:
        print("\n=== Deployment failed ===\n")
        return False

    print("\n=== Deployment succeeded ===\n")
    return True


def main():
    """Parse command line arguments and run the orchestration."""
    parser = argparse.ArgumentParser(
        description="Orchestrate the entire ledger process"
    )

    # General options
    parser.add_argument(
        "--skip-type-check", action="store_true", help="Skip type checking"
    )
    parser.add_argument("--skip-tests", action="store_true", help="Skip running tests")
    parser.add_argument("--skip-deploy", action="store_true", help="Skip deployment")

    # Type checking options
    parser.add_argument("--mypy-flags", nargs="*", help="Flags to pass to mypy")
    parser.add_argument(
        "--check-files", nargs="*", help="Files or directories to type check"
    )

    # Test options
    parser.add_argument("--test-command", help="Command to run tests (default: pytest)")

    # Deployment options
    parser.add_argument(
        "--start-from", type=int, help="Step to start deployment from (0-based)"
    )
    parser.add_argument(
        "--end-at", type=int, help="Step to end deployment at (0-based, inclusive)"
    )

    args = parser.parse_args()

    # Ensure directories exist
    ensure_dirs()

    # Track overall success
    success = True

    # Run type checking
    if not args.skip_type_check:
        type_check_success = type_check(args)
        success = success and type_check_success

        if not type_check_success and not args.skip_tests and not args.skip_deploy:
            print("Type checking failed, skipping tests and deployment")
            return 1

    # Run tests
    if not args.skip_tests:
        tests_success = run_tests(args)
        success = success and tests_success

        if not tests_success and not args.skip_deploy:
            print("Tests failed, skipping deployment")
            return 1

    # Run deployment
    if not args.skip_deploy:
        deploy_success = run_deployment(args)
        success = success and deploy_success

    # Print final status
    if success:
        print("\n=== All steps completed successfully ===\n")
        return 0
    else:
        print("\n=== Some steps failed, check logs for details ===\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
