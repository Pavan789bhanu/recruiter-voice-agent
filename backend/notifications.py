"""
Push Notifications — alerts the user's iPhone when a human recruiter calls.

Uses Firebase Cloud Messaging (FCM) which works for both iOS and Android.
Alternatively, Apple APNs directly for iOS only.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

# ── Token registry (in-memory; use DB in production) ──────────────────────────
# Maps device_id → FCM push token
_device_tokens: dict[str, str] = {}


def register_device(device_id: str, push_token: str):
    _device_tokens[device_id] = push_token
    logger.info(f"Device registered: {device_id}")


def get_all_tokens() -> list[str]:
    return list(_device_tokens.values())


async def send_push_notification(title: str, body: str, data: dict | None = None):
    """
    Send push notification to all registered devices via FCM.
    Set FIREBASE_SERVER_KEY in .env to enable.
    """
    import os
    firebase_key = os.environ.get("FIREBASE_SERVER_KEY", "")
    if not firebase_key:
        logger.warning("FIREBASE_SERVER_KEY not set — push notification skipped")
        return

    tokens = get_all_tokens()
    if not tokens:
        logger.warning("No registered devices for push notification")
        return

    payload = {
        "registration_ids": tokens,
        "notification": {
            "title": title,
            "body": body,
            "sound": "default",
        },
        "data": data or {},
        "priority": "high",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://fcm.googleapis.com/fcm/send",
            json=payload,
            headers={
                "Authorization": f"key={firebase_key}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"Push sent to {len(tokens)} devices")
        else:
            logger.error(f"Push failed: {resp.status_code} {resp.text}")
