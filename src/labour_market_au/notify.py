"""Slack webhook notifications for pipeline runs.

Sends success/failure messages to a Slack channel via incoming webhook.
Graceful no-op if SLACK_WEBHOOK_URL is not configured.
"""
from __future__ import annotations

import logging
import os
import traceback

import httpx

log = logging.getLogger("labour_market_au.notify")

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")


def send_slack(message: str, is_error: bool = False) -> bool:
    """Post a message to Slack via incoming webhook.

    Returns True if sent successfully, False otherwise.
    No-op (returns False) if SLACK_WEBHOOK_URL is not set.
    """
    url = SLACK_WEBHOOK_URL or os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        log.warning("SLACK_WEBHOOK_URL not set, skipping notification.")
        return False

    try:
        resp = httpx.post(url, json={"text": message}, timeout=10)
        if resp.status_code != 200:
            log.warning("Slack webhook returned %d: %s", resp.status_code, resp.text)
            return False
        return True
    except Exception as exc:
        log.warning("Failed to send Slack notification: %s", exc)
        return False


def notify_release_detected(dataset: str, data_period: str) -> bool:
    """Send notification when a due release is detected."""
    return send_slack(
        f":newspaper: JSA/DEWR release due: *{dataset}* ({data_period})"
    )


def notify_pipeline_success(dataset: str, records: int) -> bool:
    """Send a success notification with pipeline summary."""
    return send_slack(
        f":white_check_mark: *Labour Market AU pipeline complete*\n"
        f"Dataset: {dataset} | Records loaded: {records:,}"
    )


def notify_pipeline_failure(error: Exception, dataset: str = "") -> bool:
    """Send a failure notification with error details."""
    tb = traceback.format_exception_only(type(error), error)
    error_text = "".join(tb).strip()
    if len(error_text) > 500:
        error_text = error_text[:500] + "..."

    lines = [":x: *Labour Market AU pipeline failed*"]
    if dataset:
        lines.append(f"*Dataset:* {dataset}")
    lines.append(f"```{error_text}```")
    return send_slack("\n".join(lines), is_error=True)
