"""Инвалидация кэша настроек между процессами."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.redis_client import redis


logger = logging.getLogger("app.settings.pubsub")

CHANNEL = "settings:invalidate"

_RECONNECT_DELAY_SEC = 5


async def publish_invalidate() -> None:
    """Сообщить всем воркерам, что кэш настроек устарел."""
    try:
        await redis.publish(CHANNEL, "1")
    except Exception:
        logger.exception("settings invalidate publish failed")


async def subscriber_loop(
    on_message: Callable[[], Awaitable[None]],
) -> None:
    """Долгоживущий цикл подписки."""
    while True:
        try:
            await _run_subscriber(on_message)
        except asyncio.CancelledError:
            logger.info("settings subscriber cancelled")
            raise
        except Exception:
            logger.exception(
                "settings subscriber crashed, retrying in %ss",
                _RECONNECT_DELAY_SEC,
            )
            await asyncio.sleep(_RECONNECT_DELAY_SEC)


async def _run_subscriber(
    on_message: Callable[[], Awaitable[None]],
) -> None:
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(CHANNEL)
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                await on_message()
            except Exception:
                logger.exception("settings invalidate handler failed")
    finally:
        try:
            await pubsub.unsubscribe(CHANNEL)
        except Exception:
            pass
        try:
            await pubsub.aclose()  # type: ignore[attr-defined]
        except Exception:
            logger.debug("pubsub close failed", exc_info=True)