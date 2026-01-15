#!/usr/bin/env python
"""
OpenNotes CLI - Command line interface for server management.

Usage:
    uv run opennotes-cli [COMMAND] [OPTIONS]

    Or via direct script invocation (legacy):
    uv run python opennotes_cli.py [COMMAND] [OPTIONS]

Examples:
    uv run opennotes-cli fact-check candidates import fact-check-bureau
    uv run opennotes-cli fact-check candidates scrape-content --wait
    uv run opennotes-cli fact-check candidates promote --batch-size 100
"""

from src.cli import main

if __name__ == "__main__":
    main()
