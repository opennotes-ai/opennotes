#!/usr/bin/env python3
"""
Standalone diagnostic script for JetStream concurrent subscription issues.

Usage:
    uv run python scripts/diagnose_jetstream.py

This script:
1. Connects to NATS and shows server version
2. Tests sequential subscriptions
3. Tests concurrent subscriptions (reproduces timeout issue)
4. Tests message delivery
"""

import asyncio
import logging
import os
import sys
import time

import nats
from nats.js.api import ConsumerConfig, RetentionPolicy, StorageType, StreamConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")
STREAM_NAME = "JETSTREAM_DIAG"


async def get_server_info(nc: nats.NATS) -> dict:
    return {
        "version": nc.connected_server_version,
        "server_id": nc.client_id,
        "server_name": str(nc.connected_url),
        "go_version": "N/A",
        "jetstream": True,
    }


async def setup_stream(js) -> None:
    try:
        await js.delete_stream(STREAM_NAME)
    except Exception:
        pass

    await js.add_stream(
        StreamConfig(
            name=STREAM_NAME,
            subjects=[f"{STREAM_NAME}.>"],
            retention=RetentionPolicy.WORK_QUEUE,
            storage=StorageType.MEMORY,
            max_age=60,
        )
    )


async def run_sequential_subscriptions(js, num_subs: int = 8) -> dict:
    logger.info(f"\n{'=' * 60}")
    logger.info("TEST: Sequential Subscriptions")
    logger.info(f"{'=' * 60}")

    results = {"success": 0, "timeout": 0, "error": 0, "times": []}
    subs = []

    for i in range(num_subs):
        subject = f"{STREAM_NAME}.seq.{i}"
        try:
            start = time.time()
            sub = await asyncio.wait_for(
                js.subscribe(subject, cb=lambda m: None, config=ConsumerConfig(max_deliver=3)),
                timeout=10.0,
            )
            elapsed = time.time() - start
            subs.append(sub)
            results["success"] += 1
            results["times"].append(elapsed)
            logger.info(f"  Sub {i}: SUCCESS in {elapsed:.3f}s")
        except TimeoutError:
            results["timeout"] += 1
            logger.error(f"  Sub {i}: TIMEOUT")
        except Exception as e:
            results["error"] += 1
            logger.error(f"  Sub {i}: ERROR - {e}")

    for sub in subs:
        await sub.unsubscribe()

    return results


async def run_high_concurrency_stress(js, num_subs: int = 50) -> dict:
    """Stress test with higher concurrency to reproduce edge cases."""
    logger.info(f"\n{'=' * 60}")
    logger.info(f"TEST: High Concurrency Stress ({num_subs} subs)")
    logger.info(f"{'=' * 60}")

    results = {"success": 0, "timeout": 0, "error": 0, "times": []}
    subs = []

    async def create_sub(idx: int):
        subject = f"{STREAM_NAME}.stress.{idx}"
        try:
            start = time.time()
            sub = await asyncio.wait_for(
                js.subscribe(subject, cb=lambda m: None, config=ConsumerConfig(max_deliver=3)),
                timeout=10.0,
            )
            elapsed = time.time() - start
            return ("success", sub, elapsed)
        except TimeoutError:
            return ("timeout", None, 10.0)
        except Exception as e:
            logger.error(f"  Sub {idx}: ERROR - {e}")
            return ("error", None, 0)

    tasks = [create_sub(i) for i in range(num_subs)]
    outcomes = await asyncio.gather(*tasks)

    for status, sub, elapsed in outcomes:
        results[status] += 1
        if elapsed and status == "success":
            results["times"].append(elapsed)
        if sub:
            subs.append(sub)

    logger.info(f"  Success: {results['success']}/{num_subs}")
    if results["timeout"] > 0:
        logger.error(f"  Timeouts: {results['timeout']}")
    if results["times"]:
        logger.info(f"  Avg time: {sum(results['times']) / len(results['times']):.3f}s")
        logger.info(f"  Max time: {max(results['times']):.3f}s")

    for sub in subs:
        await sub.unsubscribe()

    return results


async def run_concurrent_subscriptions(js, num_subs: int = 8) -> dict:
    logger.info(f"\n{'=' * 60}")
    logger.info("TEST: Concurrent Subscriptions (reproduces nats-py #437)")
    logger.info(f"{'=' * 60}")

    results = {"success": 0, "timeout": 0, "error": 0, "times": []}
    subs = []

    async def create_sub(idx: int):
        subject = f"{STREAM_NAME}.conc.{idx}"
        try:
            start = time.time()
            sub = await asyncio.wait_for(
                js.subscribe(subject, cb=lambda m: None, config=ConsumerConfig(max_deliver=3)),
                timeout=10.0,
            )
            elapsed = time.time() - start
            logger.info(f"  Sub {idx}: SUCCESS in {elapsed:.3f}s")
            return ("success", sub, elapsed)
        except TimeoutError:
            logger.error(f"  Sub {idx}: TIMEOUT after 10s")
            return ("timeout", None, 10.0)
        except Exception as e:
            logger.error(f"  Sub {idx}: ERROR - {e}")
            return ("error", None, 0)

    tasks = [create_sub(i) for i in range(num_subs)]
    outcomes = await asyncio.gather(*tasks)

    for status, sub, elapsed in outcomes:
        results[status] += 1
        if elapsed:
            results["times"].append(elapsed)
        if sub:
            subs.append(sub)

    for sub in subs:
        await sub.unsubscribe()

    return results


def log_version_info(version_str: str) -> None:
    """Log version-specific information and recommendations."""
    import re

    match = re.search(r"v?(\d+)\.(\d+)", version_str)
    if match:
        major, minor = int(match.group(1)), int(match.group(2))
        if major == 2 and minor == 9:
            logger.warning(f"\n  NATS {version_str} - Version 2.9.15 known to have issues!")
        elif major == 2 and minor == 10:
            logger.info(f"\n  NATS {version_str} - Consider upgrading to 2.12.x")
        elif major == 2 and minor >= 12:
            logger.info(f"\n  NATS {version_str} - Latest stable!")


def print_summary(results: dict, info: dict) -> bool:
    """Print summary and return True if issues were detected."""
    logger.info(f"\n{'=' * 60}")
    logger.info("SUMMARY")
    logger.info(f"{'=' * 60}")

    logger.info(f"\nNATS Server: {info['version']}")

    seq = results["sequential"]
    logger.info(
        f"\nSequential Subscriptions ({seq['success']}/{seq['success'] + seq['timeout'] + seq['error']}):"
    )
    if seq["times"]:
        logger.info(f"  Avg time: {sum(seq['times']) / len(seq['times']):.3f}s")
        logger.info(f"  Max time: {max(seq['times']):.3f}s")

    conc = results["concurrent"]
    logger.info(
        f"\nConcurrent Subscriptions ({conc['success']}/{conc['success'] + conc['timeout'] + conc['error']}):"
    )
    if conc["timeout"] > 0:
        logger.warning(f"    {conc['timeout']} TIMEOUTS - nats-py #437 confirmed!")
    if conc["times"]:
        logger.info(f"  Avg time: {sum(conc['times']) / len(conc['times']):.3f}s")
        logger.info(f"  Max time: {max(conc['times']):.3f}s")

    stress = results["stress"]
    total_stress = stress["success"] + stress["timeout"] + stress["error"]
    logger.info(f"\nHigh Concurrency Stress ({stress['success']}/{total_stress}):")
    if stress["timeout"] > 0:
        logger.warning(f"    {stress['timeout']} TIMEOUTS under stress!")
    if stress["times"]:
        logger.info(f"  Avg time: {sum(stress['times']) / len(stress['times']):.3f}s")
        logger.info(f"  Max time: {max(stress['times']):.3f}s")

    deliv = results["delivery"]
    logger.info("\nMessage Delivery:")
    logger.info(f"  Core NATS received: {deliv['core_received']}")
    logger.info(f"  JetStream received: {deliv['js_received']}")
    if deliv["js_timeout"]:
        logger.warning("    JetStream subscription timed out!")
    elif deliv["js_received"] == 0:
        logger.warning("    JetStream subscription OK but no messages received!")

    return conc["timeout"] > 0 or stress["timeout"] > 0 or deliv["js_received"] == 0


async def run_message_delivery(nc, js) -> dict:
    logger.info(f"\n{'=' * 60}")
    logger.info("TEST: Message Delivery (JetStream vs Core NATS)")
    logger.info(f"{'=' * 60}")

    results = {"js_received": 0, "core_received": 0, "js_timeout": False}
    subject = f"{STREAM_NAME}.delivery"

    received_js = []
    received_core = []

    async def js_handler(msg):
        received_js.append(msg.data.decode())
        await msg.ack()
        logger.info(f"  JetStream received: {msg.data.decode()}")

    async def core_handler(msg):
        received_core.append(msg.data.decode())
        logger.info(f"  Core NATS received: {msg.data.decode()}")

    # Core NATS subscription
    core_sub = await nc.subscribe(subject, cb=core_handler)
    logger.info("  Core NATS subscription created")

    # JetStream subscription
    try:
        js_sub = await asyncio.wait_for(
            js.subscribe(subject, cb=js_handler, config=ConsumerConfig(max_deliver=3)),
            timeout=10.0,
        )
        logger.info("  JetStream subscription created")
    except TimeoutError:
        js_sub = None
        results["js_timeout"] = True
        logger.error("  JetStream subscription TIMED OUT")

    await asyncio.sleep(0.5)

    # Publish
    await js.publish(subject, b"test_msg_1")
    logger.info("  Published via JetStream")
    await nc.publish(subject, b"test_msg_2")
    logger.info("  Published via Core NATS")

    await asyncio.sleep(2)

    results["js_received"] = len(received_js)
    results["core_received"] = len(received_core)

    if js_sub:
        await js_sub.unsubscribe()
    await core_sub.unsubscribe()

    return results


async def main():
    logger.info("=" * 60)
    logger.info("NATS JETSTREAM DIAGNOSTIC TOOL")
    logger.info("=" * 60)
    logger.info(f"Connecting to: {NATS_URL}")

    try:
        nc = await nats.connect(NATS_URL, max_reconnect_attempts=3)
        js = nc.jetstream(timeout=30.0)
    except Exception as e:
        logger.error(f"Failed to connect to NATS: {e}")
        sys.exit(1)

    # Server info
    info = await get_server_info(nc)
    logger.info("\nNATS Server Info:")
    logger.info(f"  Version: {info['version']}")
    logger.info(f"  Server Name: {info['server_name']}")
    logger.info(f"  Go Version: {info['go_version']}")
    logger.info(f"  JetStream: {info['jetstream']}")

    # Check version
    log_version_info(str(info["version"]))

    # Setup
    await setup_stream(js)
    logger.info(f"Created test stream: {STREAM_NAME}")

    # Run tests
    results = {}
    results["sequential"] = await run_sequential_subscriptions(js)
    await asyncio.sleep(1)
    results["concurrent"] = await run_concurrent_subscriptions(js)
    await asyncio.sleep(1)
    results["stress"] = await run_high_concurrency_stress(js, num_subs=50)
    await asyncio.sleep(1)
    results["delivery"] = await run_message_delivery(nc, js)

    # Summary
    has_issues = print_summary(results, info)

    # Cleanup
    try:
        await js.delete_stream(STREAM_NAME)
    except Exception:
        pass
    await nc.drain()
    await nc.close()

    logger.info(f"\n{'=' * 60}")
    logger.info("DIAGNOSIS COMPLETE")
    logger.info(f"{'=' * 60}")

    # Exit code based on results
    if has_issues:
        logger.info("\n🔴 Issues detected - see details above")
        return 1
    logger.info("\n🟢 All tests passed!")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
