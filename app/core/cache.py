# app/core/cache.py

import hashlib
import json
import logging
import inspect
from functools import wraps
from typing import Any, Optional

from pydantic import TypeAdapter
from app.core.redis import redis_manager
from fastapi.encoders import jsonable_encoder

# 確保 logger 等級是 INFO
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cached(
    key_prefix: str,
    expire: int = 300,
    model: Optional[Any] = None,
    namespace: Optional[str] = None # 新增：讓我們可以用 project_id 當作 Key 的主體
):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # 1. 產生 Key
                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                arg_dict = {k: v for k, v in bound_args.arguments.items() if k != 'self'}
                # --- 根除問題的核心邏輯 ---
                # 如果我們明確知道要用哪個參數當 Key (例如 project_id)
                if namespace and namespace in arg_dict:
                    # 直接產出 project:view:123 這種清爽的 Key，完全不用 MD5
                    cache_key = f"{key_prefix}:{arg_dict[namespace]}"
                else:
                    # 原有的 MD5 邏輯做為「通用/保險」方案
                    arg_str = json.dumps(jsonable_encoder(arg_dict), sort_keys=True)
                    arg_hash = hashlib.md5(arg_str.encode('utf-8')).hexdigest()
                    cache_key = f"{key_prefix}:{arg_hash}"
                    
            except Exception as e:
                logger.warning(f"[Cache] Key gen failed: {e}")
                return await func(*args, **kwargs)

            # 2. 嘗試讀取 Redis
            try:
                cached_data = await redis_manager.get_value(cache_key)
                if cached_data:
                    # ==========================================
                    # (新增) 這行 Log 證明快取生效！
                    # ==========================================
                    logger.info(f"✅ [Cache HIT] Key: {cache_key}") 
                    
                    if model:
                        if isinstance(model, TypeAdapter):
                            return model.validate_json(cached_data)
                        else:
                            return model.model_validate_json(cached_data)
                    else:
                        return json.loads(cached_data)
                else:
                    # (新增) 記錄 Miss
                    logger.info(f"⚠️ [Cache MISS] Key: {cache_key} - Fetching from DB...")

            except Exception as e:
                logger.error(f"[Cache] Read failed: {e}")

            # 3. 執行原函式 (Cache Miss)
            result = await func(*args, **kwargs)

            # 4. 寫入 Redis
            if result is not None:
                try:
                    data_to_cache = jsonable_encoder(result)
                    json_str = json.dumps(data_to_cache)
                    await redis_manager.set_value(cache_key, json_str, expire=expire)
                    # (新增) 記錄寫入
                    logger.info(f"💾 [Cache SET] Key: {cache_key} saved.")
                except Exception as e:
                    logger.error(f"[Cache] Write failed: {e}")

            return result
            
        return wrapper
    return decorator