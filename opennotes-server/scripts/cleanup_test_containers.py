#!/usr/bin/env python3

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

try:
    import docker
    import psutil
except ImportError as e:
    print(f"Error: Required packages not installed: {e}")
    print("Install with: uv pip install docker psutil")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

OPENNOTES_TEST_LABEL = "opennotes.test.session_id"
STATE_DIR = Path.home() / ".opennotes"
STATE_FILE = STATE_DIR / "test_containers.json"
GRACE_PERIOD_MINUTES = 10
DEFAULT_AGE_THRESHOLD_HOURS = 1


def ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_state():
    ensure_state_dir()
    if not STATE_FILE.exists():
        return {"sessions": []}
    try:
        with STATE_FILE.open() as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load state file: {e}")
        return {"sessions": []}


def save_state(state):
    ensure_state_dir()
    try:
        with STATE_FILE.open("w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Could not save state file: {e}")


def get_docker_client():
    try:
        return docker.from_env()
    except Exception as e:
        logger.error(f"Could not connect to Docker: {e}")
        sys.exit(1)


def is_process_running(pid):
    try:
        process = psutil.Process(int(pid))
        cmdline = " ".join(process.cmdline()).lower()
        return "pytest" in cmdline or "python" in cmdline
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return False


def is_container_orphaned(container, age_threshold_hours=DEFAULT_AGE_THRESHOLD_HOURS):
    labels = container.labels or {}

    session_id = labels.get(OPENNOTES_TEST_LABEL)
    if not session_id:
        return False

    pid = labels.get("opennotes.test.pid")
    timestamp_str = labels.get("opennotes.test.timestamp")

    if not timestamp_str:
        return True

    try:
        container_start_time = datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        return True

    # Ensure both datetimes are timezone-aware for comparison
    if container_start_time.tzinfo:
        now = datetime.now(container_start_time.tzinfo)
    else:
        now = datetime.now(UTC)
    container_age = now - container_start_time

    grace_period = timedelta(minutes=GRACE_PERIOD_MINUTES)
    if container_age < grace_period:
        logger.debug(
            f"Container {container.name} is younger than grace period ({GRACE_PERIOD_MINUTES} min), skipping"
        )
        return False

    if pid and is_process_running(pid):
        logger.debug(f"Container {container.name}: Process {pid} still running, skipping")
        return False

    age_threshold = timedelta(hours=age_threshold_hours)
    is_old = container_age > age_threshold
    if is_old:
        logger.debug(
            f"Container {container.name}: Older than threshold ({age_threshold_hours}h), marking for removal"
        )
    return is_old


def get_test_containers(client):
    try:
        filters = {"label": OPENNOTES_TEST_LABEL, "status": "running"}
        return client.containers.list(filters=filters)
    except Exception as e:
        logger.error(f"Error listing containers: {e}")
        return []


def cleanup_orphaned_containers(
    client, dry_run=False, age_threshold_hours=DEFAULT_AGE_THRESHOLD_HOURS, verbose=False
):
    containers = get_test_containers(client)

    if not containers:
        print("✓ No test containers found")
        return 0, 0

    orphaned = [c for c in containers if is_container_orphaned(c, age_threshold_hours)]

    if not orphaned:
        print(f"✓ All {len(containers)} test container(s) are still active")
        return 0, 0

    removed_count = 0
    failed_count = 0

    print(f"\nFound {len(orphaned)} orphaned container(s):")
    for container in orphaned:
        labels = container.labels or {}
        session_id = labels.get(OPENNOTES_TEST_LABEL, "unknown")
        pid = labels.get("opennotes.test.pid", "unknown")
        timestamp = labels.get("opennotes.test.timestamp", "unknown")

        print(f"  - {container.name}")
        if verbose:
            print(f"    Session ID: {session_id}")
            print(f"    PID: {pid}")
            print(f"    Started: {timestamp}")

    if dry_run:
        print(f"\n[DRY RUN] Would remove {len(orphaned)} container(s)")
        return len(orphaned), 0

    print(f"\nRemoving {len(orphaned)} orphaned container(s)...")
    for container in orphaned:
        try:
            container.stop(timeout=10)
            container.remove()
            removed_count += 1
            logger.info(f"✓ Removed container: {container.name}")
        except Exception as e:
            failed_count += 1
            logger.error(f"✗ Failed to remove container {container.name}: {e}")

    return removed_count, failed_count


def update_session_state(client, session_id, status="running"):
    state = load_state()

    existing = next((s for s in state["sessions"] if s.get("id") == session_id), None)

    containers = []
    try:
        filters = {"label": f"{OPENNOTES_TEST_LABEL}={session_id}"}
        containers = client.containers.list(filters=filters)
    except Exception as e:
        logger.warning(f"Could not list containers for session {session_id}: {e}")

    session_data = {
        "id": session_id,
        "pid": os.getpid(),
        "started": datetime.now(UTC).isoformat(),
        "containers": [c.name for c in containers],
        "status": status,
    }

    if existing:
        state["sessions"] = [
            s if s.get("id") != session_id else session_data for s in state["sessions"]
        ]
    else:
        state["sessions"].append(session_data)

    save_state(state)


def main():
    parser = argparse.ArgumentParser(
        description="Clean up orphaned test containers from interrupted test runs"
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be cleaned without removing containers",
    )
    parser.add_argument(
        "--age-hours",
        "-a",
        type=int,
        default=DEFAULT_AGE_THRESHOLD_HOURS,
        help=f"Remove containers older than this many hours (default: {DEFAULT_AGE_THRESHOLD_HOURS})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed information about containers",
    )
    parser.add_argument(
        "--update-state",
        action="store_true",
        help="Update session state file (used by test fixture)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        help="Session ID for state update",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    client = get_docker_client()

    if args.update_state:
        if not args.session_id:
            logger.error("--session-id required for --update-state")
            sys.exit(1)
        update_session_state(client, args.session_id)
        logger.info(f"Updated session state for {args.session_id}")
        return

    removed, failed = cleanup_orphaned_containers(
        client,
        dry_run=args.dry_run,
        age_threshold_hours=args.age_hours,
        verbose=args.verbose,
    )

    if args.dry_run:
        return

    if failed > 0:
        print(f"\n✓ Removed: {removed} | ✗ Failed: {failed}")
        sys.exit(1)

    if removed > 0:
        print(f"\n✓ Successfully removed {removed} orphaned container(s)")


if __name__ == "__main__":
    main()
