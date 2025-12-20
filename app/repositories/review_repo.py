# app/repositories/review_repo.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_
from typing import List, Optional, Dict

from app.models.review import Review
# (新增) 匯入快取
from app.core.cache import cached

class ReviewRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_review(self, review: Review) -> Review:
        """
        (C) 新增評價
        """
        self.db.add(review)
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def get_review_by_contract_and_reviewer(
        self, contract_id: str, reviewer_id: str
    ) -> Optional[Review]:
        """
        (R) 檢查特定使用者在該合約是否已經評價過 (防止重複評價)
        """
        stmt = select(Review).where(
            Review.contract_id == contract_id,
            Review.reviewer_id == reviewer_id
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_reviews_by_contract_id(self, contract_id: str) -> List[Review]:
        """
        (R) 獲取某合約的所有評價
        """
        stmt = select(Review).where(Review.contract_id == contract_id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def calculate_freelancer_average_rating(self, freelancer_id: str) -> float:
        """
        (Agg) 計算工作者的總體平均信譽分數 (用於更新 Profile.reputation_score)
        """
        # 1. 計算單筆評價的平均分
        single_review_avg = (
            func.coalesce(Review.rating_communication_fw, 0) +
            func.coalesce(Review.rating_professionalism_fw, 0) +
            func.coalesce(Review.rating_punctuality_fw, 0) +
            func.coalesce(Review.rating_quality_fw, 0)
        ) / 4.0

        # 2. 計算所有評價的平均
        stmt = select(func.avg(single_review_avg)).where(
            Review.reviewee_id == freelancer_id,
            Review.rating_communication_fw.isnot(None) # 確保是評給工作者的紀錄
        )
        
        result = await self.db.execute(stmt)
        average = result.scalar()
        return float(average) if average else 5.0

    # --- (新增) 計算詳細指標平均分 (加上快取) ---

    # Key: review:stats:freelancer:<hash_of_args>
    # 由於參數只有 freelancer_id，我們可以預期 Key 雖然是 Hash 過的，但對於同一個 ID 是固定的。
    # 不過為了清除方便，我們稍後在 Service 層會使用 Pattern Deletion 或其他方式。
    # 這裡設定 1 小時過期 (3600秒)
    @cached(key_prefix="review:stats:freelancer", expire=3600)
    async def get_freelancer_detailed_ratings(self, freelancer_id: str) -> Dict[str, float]:
        """
        (Agg) 取得工作者的四項詳細指標平均分 (Cached)
        """
        stmt = select(
            func.avg(Review.rating_communication_fw).label("avg_communication"),
            func.avg(Review.rating_professionalism_fw).label("avg_professionalism"),
            func.avg(Review.rating_punctuality_fw).label("avg_punctuality"),
            func.avg(Review.rating_quality_fw).label("avg_quality")
        ).where(
            Review.reviewee_id == freelancer_id,
            # 確保只計算 "雇主評工作者" 的資料 (避免混入該 User 作為雇主時收到的評價)
            Review.rating_communication_fw.isnot(None)
        )

        result = await self.db.execute(stmt)
        try:
            row = result.one()
        except Exception:
            # 處理查無資料的情況 (雖然 avg 通常會回傳 None)
            return {
                "avg_communication": 0.0,
                "avg_professionalism": 0.0,
                "avg_punctuality": 0.0,
                "avg_quality": 0.0
            }

        # 若無評價，回傳 0.0
        return {
            "avg_communication": float(row.avg_communication) if row.avg_communication else 0.0,
            "avg_professionalism": float(row.avg_professionalism) if row.avg_professionalism else 0.0,
            "avg_punctuality": float(row.avg_punctuality) if row.avg_punctuality else 0.0,
            "avg_quality": float(row.avg_quality) if row.avg_quality else 0.0
        }

    @cached(key_prefix="review:stats:employer", expire=3600)
    async def get_employer_detailed_ratings(self, employer_id: str) -> Dict[str, float]:
        """
        (Agg) 取得雇主的四項詳細指標平均分 (Cached)
        """
        stmt = select(
            func.avg(Review.rating_communication_we).label("avg_communication"),
            func.avg(Review.rating_quality_we).label("avg_quality"),
            func.avg(Review.rating_compensation_we).label("avg_compensation"),
            func.avg(Review.rating_process_we).label("avg_process")
        ).where(
            Review.reviewee_id == employer_id,
            # 確保只計算 "工作者評雇主" 的資料
            Review.rating_communication_we.isnot(None)
        )

        result = await self.db.execute(stmt)
        try:
            row = result.one()
        except Exception:
            return {
                "avg_communication": 0.0,
                "avg_quality": 0.0,
                "avg_compensation": 0.0,
                "avg_process": 0.0
            }

        return {
            "avg_communication": float(row.avg_communication) if row.avg_communication else 0.0,
            "avg_quality": float(row.avg_quality) if row.avg_quality else 0.0,
            "avg_compensation": float(row.avg_compensation) if row.avg_compensation else 0.0,
            "avg_process": float(row.avg_process) if row.avg_process else 0.0
        }