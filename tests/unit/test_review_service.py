import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from app.services.review_service import ReviewService
from app.schemas.review_schema import ReviewCreate
from app.models.contract import Contract
from app.models.review import Review
from app.models.freelancer_profile import FreelancerProfile
from app.models.user import User

# ==========================================
# Part 1: 成功評價流程 (Happy Path)
# ==========================================

@pytest.mark.asyncio
async def test_create_review_employer_to_freelancer_success(mock_db_session, mock_user_employer, mocker):
    """
    測試：雇主評價工作者 (最重要場景)
    驗證重點：
    1. 評價寫入 DB。
    2. [Side Effect] 重新計算並更新工作者的 reputation_score。
    """
    # 1. Arrange
    service = ReviewService(mock_db_session)
    contract_id = "c_completed"
    freelancer_id = "worker_1"
    
    # 模擬合約 (必須是 '已完成')
    mock_contract = Contract(
        contract_id=contract_id,
        status="已完成",
        employer_id=mock_user_employer.user_id,
        freelancer_id=freelancer_id
    )
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    
    # 模擬尚未評價過
    mocker.patch.object(service.repo, 'get_review_by_contract_and_reviewer', return_value=None)
    
    # 模擬寫入評價成功
    mock_saved_review = Review(review_id="r1")
    mocker.patch.object(service.repo, 'create_review', return_value=mock_saved_review)

    # [關鍵] 模擬信譽更新相關依賴
    # 1. 模擬計算出的新平均分
    mocker.patch.object(service.repo, 'calculate_freelancer_average_rating', return_value=4.8)
    # 2. 模擬找到工作者 Profile
    mock_profile = FreelancerProfile(profile_id="fp1", user_id=freelancer_id, reputation_score=5.0)
    mocker.patch.object(service.profile_repo, 'get_freelancer_profile_by_user_id', return_value=mock_profile)

    # 準備輸入資料 (雇主評分欄位 _fw)
    review_data = ReviewCreate(
        contract_id=contract_id,
        comment="Good job",
        rating_communication_fw=5.0,
        rating_professionalism_fw=4.0,
        rating_punctuality_fw=5.0,
        rating_quality_fw=5.0
    )

    # 2. Act
    result = await service.create_review(review_data, mock_user_employer)

    # 3. Assert
    assert result.review_id == "r1"
    
    # 驗證 create_review 被呼叫，且參數正確帶入
    service.repo.create_review.assert_called_once()
    
    # 驗證 Side Effect: Profile 分數被更新
    service.repo.calculate_freelancer_average_rating.assert_called_once_with(freelancer_id)
    service.profile_repo.get_freelancer_profile_by_user_id.assert_called_once_with(freelancer_id)
    assert mock_profile.reputation_score == 4.8
    # 驗證有執行 db.add(profile) 和 commit
    mock_db_session.add.assert_called_with(mock_profile)
    mock_db_session.commit.assert_called()

@pytest.mark.asyncio
async def test_create_review_freelancer_to_employer_success(mock_db_session, mock_user_freelancer, mocker):
    """
    測試：工作者評價雇主
    驗證重點：
    1. 評價寫入 DB。
    2. 不會觸發 FreelancerProfile 更新 (雇主沒有信譽分欄位，或邏輯不同)。
    """
    # Arrange
    service = ReviewService(mock_db_session)
    contract_id = "c_completed"
    
    mock_contract = Contract(
        contract_id=contract_id,
        status="已完成",
        employer_id="boss_1",
        freelancer_id=mock_user_freelancer.user_id
    )
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    mocker.patch.object(service.repo, 'get_review_by_contract_and_reviewer', return_value=None)
    mocker.patch.object(service.repo, 'create_review', return_value=Review(review_id="r2"))
    
    # Spy calculation (確認不應該被呼叫)
    mock_calc = mocker.patch.object(service.repo, 'calculate_freelancer_average_rating')

    # 輸入資料 (工作者評分欄位 _we)
    review_data = ReviewCreate(
        contract_id=contract_id,
        rating_communication_we=5.0,
        rating_quality_we=5.0,
        rating_compensation_we=5.0,
        rating_process_we=5.0
    )

    # Act
    await service.create_review(review_data, mock_user_freelancer)

    # Assert
    service.repo.create_review.assert_called_once()
    mock_calc.assert_not_called() # 雇主沒有信譽分更新邏輯

# ==========================================
# Part 2: 異常處理與驗證 (Validation & Error Handling)
# ==========================================

@pytest.mark.asyncio
async def test_create_review_fail_contract_not_found(mock_db_session, mock_user_employer, mocker):
    """測試：合約不存在 (404)"""
    service = ReviewService(mock_db_session)
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=None)
    
    with pytest.raises(HTTPException) as exc:
        await service.create_review(ReviewCreate(contract_id="404"), mock_user_employer)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_create_review_fail_wrong_status(mock_db_session, mock_user_employer, mocker):
    """測試：合約未完成不可評價 (400)"""
    service = ReviewService(mock_db_session)
    mock_contract = Contract(status="進行中") # 非 '已完成'
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    
    with pytest.raises(HTTPException) as exc:
        await service.create_review(ReviewCreate(contract_id="c1"), mock_user_employer)
    assert exc.value.status_code == 400
    assert "合約尚未完成" in exc.value.detail

@pytest.mark.asyncio
async def test_create_review_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：非合約當事人不可評價 (403)"""
    service = ReviewService(mock_db_session)
    mock_contract = Contract(
        status="已完成",
        employer_id="other_boss",
        freelancer_id="other_worker"
    )
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    
    with pytest.raises(HTTPException) as exc:
        await service.create_review(ReviewCreate(contract_id="c1"), mock_user_employer)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_create_review_fail_duplicate(mock_db_session, mock_user_employer, mocker):
    """測試：重複評價 (409)"""
    service = ReviewService(mock_db_session)
    mock_contract = Contract(status="已完成", employer_id=mock_user_employer.user_id, freelancer_id="w1")
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    
    # 模擬已找到存在的評價
    mocker.patch.object(service.repo, 'get_review_by_contract_and_reviewer', return_value=Review())
    
    with pytest.raises(HTTPException) as exc:
        await service.create_review(ReviewCreate(contract_id="c1"), mock_user_employer)
    assert exc.value.status_code == 409
    assert "已對此合約提交過評價" in exc.value.detail

@pytest.mark.asyncio
async def test_create_review_fail_missing_fields(mock_db_session, mock_user_employer, mocker):
    """測試：雇主評價漏填欄位 (400)"""
    service = ReviewService(mock_db_session)
    mock_contract = Contract(status="已完成", employer_id=mock_user_employer.user_id, freelancer_id="w1")
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    mocker.patch.object(service.repo, 'get_review_by_contract_and_reviewer', return_value=None)
    
    # 漏填 rating_quality_fw
    bad_data = ReviewCreate(
        contract_id="c1",
        rating_communication_fw=5.0
        # 缺其他三個
    )
    
    with pytest.raises(HTTPException) as exc:
        await service.create_review(bad_data, mock_user_employer)
    assert exc.value.status_code == 400
    assert "請完整填寫" in exc.value.detail

# ==========================================
# Part 3: 查詢評價 (Read)
# ==========================================

@pytest.mark.asyncio
async def test_get_reviews_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：非當事人無法查看合約評價 (403)"""
    service = ReviewService(mock_db_session)
    mock_contract = Contract(employer_id="other", freelancer_id="other")
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    
    with pytest.raises(HTTPException) as exc:
        await service.get_reviews_for_contract("c1", mock_user_employer)
    assert exc.value.status_code == 403