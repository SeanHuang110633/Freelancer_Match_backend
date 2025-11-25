# app/core/redis.py (清理後)

import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool
from typing import AsyncGenerator
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self):
        self.pool = None
        # (REMOVED) 移除 pubsub_client
        # self.pubsub_client = None

    def initialize(self):
        try:
            self.pool = ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=20,
                decode_responses=False
            )
            logger.info("Redis 連線池已成功初始化。")
        except Exception as e:
            logger.error(f"Redis 連線池初始化失敗: {e}")
            raise

    async def get_redis_client(self) -> AsyncGenerator[aioredis.Redis, None]:
        """
        FastAPI Dependency: 獲取一個用於一般指令 (PUBLISH) 的 Redis 連線。
        """
        if not self.pool:
            raise RuntimeError("RedisManager 尚未初始化。")
            
        redis_client = aioredis.Redis(connection_pool=self.pool)
        try:
            yield redis_client
        finally:
            await redis_client.aclose()

    # (REMOVED) 移除 get_redis_pubsub_client
    # async def get_redis_pubsub_client(self) -> aioredis.Redis: ...

    async def close(self):
        # (REMOVED) 移除 pubsub_client 的關閉邏輯
        if self.pool:
            await self.pool.disconnect()
            logger.info("已關閉 Redis 連線池。")

# 建立全域單例
redis_manager = RedisManager()

# --- 供 FastAPI 依賴注入使用的輔助函式 ---

async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """
    FastAPI Dependency: (用於 PUBLISH)
    """
    async for client in redis_manager.get_redis_client():
        yield client

# (REMOVED) 移除 get_redis_pubsub
# async def get_redis_pubsub() -> aioredis.Redis: ...