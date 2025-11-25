# app/services/review_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.user import User
from app.models.review import Review
from app.models.freelancer_profile import FreelancerProfile
from app.repositories.review_repo import ReviewRepository
from app.repositories.contract_repo import ContractRepository
from app.repositories.profile_repo import ProfileRepository # 用於更新分數
from app.schemas.review_schema import ReviewCreate

class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ReviewRepository(db)
        self.contract_repo = ContractRepository(db)
        self.profile_repo = ProfileRepository(db)

    async def create_review(self, review_data: ReviewCreate, reviewer: User) -> Review:
        """
        提交評價 (One-off action, cannot be edited/deleted)
        """
        # 1. 驗證合約存在
        contract = await self.contract_repo.get_contract_by_id(review_data.contract_id)
        if not contract:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "合約不存在")

        # 2. 驗證合約狀態 (必須是 '已完成')
        if contract.status != "已完成":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "合約尚未完成，無法進行評價")

        # 3. 驗證評價者身分 (必須是合約當事人)
        if reviewer.user_id == contract.employer_id:
            # 評價者是雇主 -> 被評者是工作者
            reviewee_id = contract.freelancer_id
            role_mode = "employer_reviewing"
        elif reviewer.user_id == contract.freelancer_id:
            # 評價者是工作者 -> 被評者是雇主
            reviewee_id = contract.employer_id
            role_mode = "freelancer_reviewing"
        else:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "您無權對此合約進行評價")

        # 4. 驗證是否重複評價 (一人僅限一次，不可修改)
        existing_review = await self.repo.get_review_by_contract_and_reviewer(
            contract.contract_id, reviewer.user_id
        )
        if existing_review:
            raise HTTPException(status.HTTP_409_CONFLICT, "您已對此合約提交過評價，無法修改或再次評價。")

        # 5. 欄位驗證與資料對應
        # 根據角色，檢查對應的評分欄位是否有值
        new_review = Review(
            contract_id=contract.contract_id,
            reviewer_id=reviewer.user_id,
            reviewee_id=reviewee_id,
            comment=review_data.comment
        )

        if role_mode == "employer_reviewing":
            # 雇主評分：必須填寫 _fw 系列欄位
            if not all([
                review_data.rating_communication_fw,
                review_data.rating_professionalism_fw,
                review_data.rating_punctuality_fw,
                review_data.rating_quality_fw
            ]):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "請完整填寫對工作者的四項評分")
            
            new_review.rating_communication_fw = review_data.rating_communication_fw
            new_review.rating_professionalism_fw = review_data.rating_professionalism_fw
            new_review.rating_punctuality_fw = review_data.rating_punctuality_fw
            new_review.rating_quality_fw = review_data.rating_quality_fw

        else:
            # 工作者評分：必須填寫 _we 系列欄位
            if not all([
                review_data.rating_communication_we,
                review_data.rating_quality_we,
                review_data.rating_compensation_we,
                review_data.rating_process_we
            ]):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "請完整填寫對雇主的四項評分")

            new_review.rating_communication_we = review_data.rating_communication_we
            new_review.rating_quality_we = review_data.rating_quality_we
            new_review.rating_compensation_we = review_data.rating_compensation_we
            new_review.rating_process_we = review_data.rating_process_we

        # 6. 儲存評價
        saved_review = await self.repo.create_review(new_review)

        # 7. (關鍵) 觸發信譽更新
        # 目前系統僅 FreelancerProfile 有 reputation_score 欄位
        if role_mode == "employer_reviewing":
            # 重新計算工作者的平均分
            new_avg_score = await self.repo.calculate_freelancer_average_rating(reviewee_id)
            
            # 更新 Profile
            profile = await self.profile_repo.get_freelancer_profile_by_user_id(reviewee_id)
            if profile:
                profile.reputation_score = new_avg_score
                # 這裡我們直接複用 repo 的 update 方法 (需確保該方法支援 partial update 或我們手動 commit)
                # 由於 profile_repo.update_freelancer_profile 需要 Pydantic schema，
                # 這裡我們直接操作 ORM 物件並 commit 比較快
                self.db.add(profile)
                await self.db.commit()

        return saved_review

    async def get_reviews_for_contract(self, contract_id: str, user: User):
        """
        獲取該合約的評價列表
        """
        # 權限檢查
        contract = await self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "合約不存在")
            
        if user.user_id != contract.employer_id and user.user_id != contract.freelancer_id:
             raise HTTPException(status.HTTP_403_FORBIDDEN, "無權查看")

        return await self.repo.get_reviews_by_contract_id(contract_id)