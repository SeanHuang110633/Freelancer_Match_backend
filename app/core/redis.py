# app/core/redis.py

import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool
from typing import AsyncGenerator, Optional, List
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self):
        self.pool: Optional[ConnectionPool] = None

    def initialize(self):
        try:
            # 建立連線池
            self.pool = ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_POOL_SIZE,
                decode_responses=True # (關鍵修改) 設為 True，讓 Redis 直接回傳 str，省去手動 decode
            )
            logger.info(f"Redis 連線池已成功初始化 (Max Conns: {settings.REDIS_POOL_SIZE})。")
        except Exception as e:
            logger.error(f"Redis 連線池初始化失敗: {e}")
            raise

    async def get_redis_client(self) -> AsyncGenerator[aioredis.Redis, None]:
        """
        FastAPI Dependency: 獲取一個用於一般指令 (如 Pub/Sub) 的 Redis 連線。
        """
        if not self.pool:
            raise RuntimeError("RedisManager 尚未初始化。")
            
        # 從 Pool 建立一個 Client 實例
        redis_client = aioredis.Redis(connection_pool=self.pool)
        try:
            yield redis_client
        finally:
            # 關閉這個 Client 實例 (不會關閉 Pool)
            await redis_client.aclose()

    async def close(self):
        if self.pool:
            await self.pool.disconnect()
            logger.info("已關閉 Redis 連線池。")

    # --- (新增) 供 Decorator 使用的直接存取方法 ---

    async def get_value(self, key: str) -> Optional[str]:
        """從 Redis 獲取字串值 (Decorator 用)"""
        if not self.pool:
            return None
        
        # 建立臨時 Client
        client = aioredis.Redis(connection_pool=self.pool)
        try:
            return await client.get(key)
        except Exception as e:
            logger.error(f"Redis GET failed for {key}: {e}")
            return None
        finally:
            await client.aclose()

    async def set_value(self, key: str, value: str, expire: int = 300):
        """寫入字串值到 Redis (Decorator 用)"""
        if not self.pool:
            return
        
        client = aioredis.Redis(connection_pool=self.pool)
        try:
            await client.set(key, value, ex=expire)
        except Exception as e:
            logger.error(f"Redis SET failed for {key}: {e}")
        finally:
            await client.aclose()

    async def delete_key(self, key: str):
        """刪除指定的 Key"""
        if not self.pool:
            return
        
        client = aioredis.Redis(connection_pool=self.pool)
        try:
            await client.delete(key)
        except Exception as e:
            logger.error(f"Redis DELETE failed for {key}: {e}")
        finally:
            await client.aclose()

    async def delete_keys_by_pattern(self, pattern: str):
        """
        依 Pattern 批量刪除 Key (例如 'project:123:*')
        使用 SCAN 指令避免阻塞 Redis
        """
        if not self.pool:
            return
        
        client = aioredis.Redis(connection_pool=self.pool)
        try:
            keys_to_delete = []
            # 使用 scan_iter 進行非阻塞遍歷
            async for key in client.scan_iter(match=pattern):
                keys_to_delete.append(key)
            
            if keys_to_delete:
                await client.delete(*keys_to_delete)
                logger.info(f"Deleted {len(keys_to_delete)} keys matching pattern: {pattern}")
        except Exception as e:
            logger.error(f"Redis Pattern DELETE failed for {pattern}: {e}")
        finally:
            await client.aclose()

# 建立全域單例
redis_manager = RedisManager()

# --- 供 FastAPI 依賴注入使用的輔助函式 ---

async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """
    FastAPI Dependency: (主要用於 Router/Service 層的 PUBLISH 或其他操作)
    """
    async for client in redis_manager.get_redis_client():
        yield client