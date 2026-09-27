import redis.asyncio as aioredis

from app.config import settings


redis = aioredis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=True,
)


async def close_redis() -> None:
    await redis.aclose()