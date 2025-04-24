# Ledger Project Orchestration

This directory contains scripts for orchestrating the ledger project's development, testing, and deployment processes.

## Overview

The orchestration system consists of several components:

1. **Terminal Orchestrator**: Runs shell commands in background processes, polls their output, and enforces timeouts.
2. **Mypy Daemon Manager**: Manages the mypy daemon for improved type checking performance.
3. **Ledger Pipeline**: Defines the deployment pipeline for the ledger project.
4. **Master Orchestration Script**: Brings everything together into a single, cohesive system.
5. **Component Deployment Script**: Allows deploying specific components individually.

## Scripts

### Terminal Orchestrator (`terminal_orchestrator.py`)

Launches arbitrary shell commands in separate background processes, polls their stdout/stderr at intervals, enforces timeouts, and returns structured results.

```bash
python scripts/terminal_orchestrator.py --name <name> --cmd "<command>"
```

Example:
```bash
python scripts/terminal_orchestrator.py --name build-step --cmd "docker build -t myapp:latest ."
```

The orchestrator will:
1. Run the command in a background process
2. Poll for output at increasing intervals
3. Check for success or failure
4. Enforce a timeout (default: 300s)
5. Write a JSON summary to `scripts/logs/<name>.json`

### Mypy Daemon Manager (`mypy_daemon_manager.py`)

Manages the mypy daemon for improved type checking performance.

```bash
python scripts/mypy_daemon_manager.py <command> [options]
```

Commands:
- `start`: Start the mypy daemon
- `stop`: Stop the mypy daemon
- `restart`: Restart the mypy daemon
- `status`: Check if the daemon is running
- `run`: Run type checking with the daemon
- `run-cached`: Run type checking with remote cache

Example:
```bash
python scripts/mypy_daemon_manager.py run --mypy-flags --disallow-untyped-defs --files src tests
```

### Ledger Pipeline (`ledger_pipeline.py`)

Defines and runs the deployment pipeline for the ledger project.

```bash
python scripts/ledger_pipeline.py [options]
```

Options:
- `--start-from <n>`: Start from step n (0-based)
- `--end-at <n>`: End at step n (0-based, inclusive)
- `--list`: List the pipeline steps and exit

Example:
```bash
python scripts/ledger_pipeline.py --start-from 2 --end-at 4
```

### Master Orchestration Script (`orchestrate.py`)

Orchestrates the entire process, from type checking to deployment.

```bash
python scripts/orchestrate.py [options]
```

Options:
- `--skip-type-check`: Skip type checking
- `--skip-tests`: Skip running tests
- `--skip-deploy`: Skip deployment
- `--mypy-flags`: Flags to pass to mypy
- `--check-files`: Files or directories to type check
- `--test-command`: Command to run tests (default: pytest)
- `--start-from`: Step to start deployment from (0-based)
- `--end-at`: Step to end deployment at (0-based, inclusive)

Example:
```bash
python scripts/orchestrate.py --skip-tests --start-from 2
```

### Component Deployment Script (`deploy_component.py`)

Deploys a specific component or runs a specific step using the terminal orchestrator.

```bash
python scripts/deploy_component.py [component] [options]
```

Options:
- `--list`: List available components
- `--timeout <seconds>`: Timeout in seconds (default: 300)

Example:
```bash
python scripts/deploy_component.py api
python scripts/deploy_component.py --list
```

## Log Files

All orchestration logs are stored in the `scripts/logs` directory:

- `<name>.json`: Output from individual terminal orchestrator runs
- `pipeline_summary.json`: Summary of the pipeline execution

## Development Workflow

1. **Development**: During development, use the mypy daemon manager for fast type checking:
   ```bash
   python scripts/mypy_daemon_manager.py run
   ```

2. **Testing**: Before pushing changes, run the full test suite:
   ```bash
   python scripts/orchestrate.py --skip-deploy
   ```

3. **Deployment**: To deploy the application:
   ```bash
   python scripts/orchestrate.py
   ```
   
   Or to run only specific deployment steps:
   ```bash
   python scripts/ledger_pipeline.py --list  # List available steps
   python scripts/ledger_pipeline.py --start-from 2 --end-at 4  # Run steps 2-4
   ```
   
   Or to deploy a specific component:
   ```bash
   python scripts/deploy_component.py --list  # List available components
   python scripts/deploy_component.py api  # Deploy the API component
   ``` 