#!/usr/bin/env python3
"""
Multi-process entrypoint for running the FastAPI server and taskiq worker together.

This script starts both processes and handles graceful shutdown when either
process exits or when a termination signal is received.

Usage:
    python scripts/run_with_worker.py

Environment Variables:
    SERVER_HOST: Host to bind the API server (default: 0.0.0.0)
    SERVER_PORT: Port for the API server (default: 8000)
    LOG_LEVEL: Logging level (default: info)
    TASKIQ_TASK_MODULES: Space-separated list of task modules (default: src.tasks.example)
"""

import os
import signal
import subprocess
import sys
import time


def get_env_var(name: str, default: str) -> str:
    """Get environment variable with default."""
    return os.environ.get(name, default)


class ProcessManager:
    """Manages API server and worker processes."""

    def __init__(self) -> None:
        self.api_process: subprocess.Popen | None = None
        self.worker_process: subprocess.Popen | None = None
        self.shutdown_requested = False

    def start_api_server(self) -> subprocess.Popen:
        """Start the FastAPI server process."""
        host = get_env_var("SERVER_HOST", "0.0.0.0")
        port = get_env_var("SERVER_PORT", "8000")
        log_level = get_env_var("LOG_LEVEL", "info").lower()

        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "src.main:app",
            "--host",
            host,
            "--port",
            port,
            "--log-level",
            log_level,
        ]

        print(f"Starting API server: {' '.join(cmd)}")
        return subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)

    def start_worker(self) -> subprocess.Popen:
        """Start the taskiq worker process."""
        task_modules = get_env_var("TASKIQ_TASK_MODULES", "src.tasks.example").split()

        cmd = [
            sys.executable,
            "-m",
            "taskiq",
            "worker",
            "src.tasks.broker:broker",
            *task_modules,
        ]

        print(f"Starting taskiq worker: {' '.join(cmd)}")
        print(f"Task modules: {task_modules}")
        return subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)

    def handle_signal(self, signum: int, _frame: object) -> None:
        """Handle termination signals."""
        if self.shutdown_requested:
            return

        self.shutdown_requested = True
        signal_name = signal.Signals(signum).name
        print(f"\nReceived {signal_name}, shutting down processes...")
        self.shutdown()

    def shutdown(self) -> None:
        """Gracefully shutdown both processes."""
        for name, process in [
            ("API server", self.api_process),
            ("Worker", self.worker_process),
        ]:
            if process and process.poll() is None:
                print(f"Stopping {name}...")
                process.terminate()
                try:
                    process.wait(timeout=10)
                    print(f"{name} stopped")
                except subprocess.TimeoutExpired:
                    print(f"{name} didn't stop gracefully, killing...")
                    process.kill()
                    process.wait()

    def run(self) -> int:
        """Run both processes and wait for either to exit."""
        # Register signal handlers
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        try:
            # Start both processes
            self.api_process = self.start_api_server()
            self.worker_process = self.start_worker()

            # Wait for either process to exit
            while not self.shutdown_requested:
                api_status = self.api_process.poll()
                worker_status = self.worker_process.poll()

                if api_status is not None:
                    print(f"API server exited with code {api_status}")
                    self.shutdown_requested = True
                    self.shutdown()
                    return api_status

                if worker_status is not None:
                    print(f"Worker exited with code {worker_status}")
                    self.shutdown_requested = True
                    self.shutdown()
                    return worker_status

                time.sleep(0.1)

        except Exception as e:
            print(f"Error: {e}")
            self.shutdown()
            return 1

        return 0


def main() -> int:
    """Main entry point."""
    manager = ProcessManager()
    return manager.run()


if __name__ == "__main__":
    sys.exit(main())
