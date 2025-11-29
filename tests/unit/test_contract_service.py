import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from datetime import datetime

from app.services.contract_service import ContractService
from app.schemas.contract_schema import ContractStatusUpdate, ContractCreate, ContractUpdate
from app.models.contract import Contract
from app.models.project import Project
from app.models.proposal import Proposal
from app.models.user import User, UserRoleEnum

# ==========================================
# Part 1: 狀態機測試 (State Machine) - 原有 P0 核心
# ==========================================

@pytest.mark.asyncio
async def test_freelancer_accept_contract_success(mock_db_session, mock_user_freelancer, mocker):
    """測試正常流程：自由工作者同意合約 (協商中 -> 進行中)"""
    # 1. Arrange
    service = ContractService(mock_db_session)
    contract_id = "c1"
    
    mock_contract = Contract(
        contract_id=contract_id,
        status="協商中",
        employer_id="employer_123",
        freelancer_id=mock_user_freelancer.user_id,
        project=Project(status="招募中")
    )
    
    # Mock Repo
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    mock_update = mocker.patch.object(service.contract_repo, 'update_contract', return_value=mock_contract)
    
    update_data = ContractStatusUpdate(status="進行中")

    # 2. Act
    await service.update_contract_status(contract_id, update_data, mock_user_freelancer)

    # 3. Assert
    assert mock_contract.status == "進行中"
    assert mock_contract.project.status == "已成案"
    mock_update.assert_called_once_with(mock_contract)

@pytest.mark.asyncio
async def test_invalid_status_transition(mock_db_session, mock_user_employer, mocker):
    """測試非法狀態轉移：已完成 -> 進行中 (應失敗)"""
    service = ContractService(mock_db_session)
    contract_id = "c2"
    
    mock_contract = Contract(
        contract_id=contract_id,
        status="已完成",
        employer_id=mock_user_employer.user_id,
        freelancer_id="worker_123"
    )
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    
    with pytest.raises(HTTPException) as exc:
        await service.update_contract_status(contract_id, ContractStatusUpdate(status="進行中"), mock_user_employer)
    
    assert exc.value.status_code == 400
    assert "不合法的狀態轉移" in exc.value.detail

@pytest.mark.asyncio
async def test_permission_denied_wrong_role(mock_db_session, mock_user_employer, mocker):
    """測試權限邊界：雇主嘗試執行工作者的動作 (應失敗)"""
    service = ContractService(mock_db_session)
    contract_id = "c3"
    
    mock_contract = Contract(
        contract_id=contract_id,
        status="進行中",
        employer_id=mock_user_employer.user_id,
        freelancer_id="worker_123"
    )
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    
    with pytest.raises(HTTPException) as exc:
        await service.update_contract_status(contract_id, ContractStatusUpdate(status="工作者要求驗收"), mock_user_employer)
    
    assert exc.value.status_code == 403
    assert "無權執行此狀態轉移" in exc.value.detail

# ==========================================
# Part 2: 合約建立邏輯 (Creation) - 新增 P0
# ==========================================

@pytest.mark.asyncio
async def test_create_contract_success(mock_db_session, mock_user_employer, mocker):
    """測試：從提案建立合約 (Happy Path)"""
    service = ContractService(mock_db_session)
    
    # 模擬關聯資料
    mock_project = Project(
        project_id="p1", 
        employer_id=mock_user_employer.user_id, 
        title="網站開發",
        description="做一個網站",
        budget_max=50000,
        work_type="遠端",
        completion_deadline=datetime(2025, 12, 31)
    )
    mock_freelancer = User(user_id="worker_1", email="worker@test.com")
    
    mock_proposal = Proposal(
        proposal_id="prop_1",
        project=mock_project,
        freelancer=mock_freelancer,
        status="已接受"
    )

    # Mock Repo
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_project_and_freelancer', return_value=mock_proposal)
    mocker.patch.object(service.contract_repo, 'check_contract_exists_by_proposal', return_value=False)
    
    # Mock create return
    mock_created_contract = Contract(contract_id="new_c1")
    mocker.patch.object(service.contract_repo, 'create_contract', return_value=mock_created_contract)
    # 模擬 create 後重新讀取完整物件
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_created_contract)

    contract_data = ContractCreate(proposal_id="prop_1")

    # Act
    result = await service.create_contract_from_proposal(contract_data, mock_user_employer)

    # Assert
    assert result.contract_id == "new_c1"
    
    # 驗證 create_contract 參數是否正確帶入 Proposal/Project 資訊
    service.contract_repo.create_contract.assert_called_once()
    call_args = service.contract_repo.create_contract.call_args[0][0]
    assert call_args.amount == 50000
    assert call_args.employer_id == mock_user_employer.user_id
    assert call_args.freelancer_id == "worker_1"
    assert call_args.status == "協商中"
    assert "網站開發" in call_args.content # 驗證樣板生成邏輯

@pytest.mark.asyncio
async def test_create_contract_fail_wrong_employer(mock_db_session, mock_user_employer, mocker):
    """測試：非該案件雇主嘗試建立合約 (權限錯誤)"""
    service = ContractService(mock_db_session)
    mock_proposal = Proposal(
        project=Project(employer_id="other_boss"), # 雇主不同
        freelancer=User(user_id="w1"),
        status="已接受"
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_project_and_freelancer', return_value=mock_proposal)

    with pytest.raises(HTTPException) as exc:
        await service.create_contract_from_proposal(ContractCreate(proposal_id="p1"), mock_user_employer)
    
    assert exc.value.status_code == 403
    assert "無權操作此提案" in exc.value.detail

@pytest.mark.asyncio
async def test_create_contract_fail_if_not_accepted(mock_db_session, mock_user_employer, mocker):
    """測試：提案狀態非 '已接受'"""
    service = ContractService(mock_db_session)
    mock_proposal = Proposal(
        status="已提交", # 狀態錯誤
        project=Project(employer_id=mock_user_employer.user_id),
        freelancer=User(user_id="w1")
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_project_and_freelancer', return_value=mock_proposal)

    with pytest.raises(HTTPException) as exc:
        await service.create_contract_from_proposal(ContractCreate(proposal_id="p1"), mock_user_employer)
    
    assert exc.value.status_code == 400
    assert "狀態不符" in exc.value.detail

@pytest.mark.asyncio
async def test_create_contract_fail_if_duplicate(mock_db_session, mock_user_employer, mocker):
    """測試：重複建立合約"""
    service = ContractService(mock_db_session)
    mock_proposal = Proposal(
        status="已接受",
        project=Project(employer_id=mock_user_employer.user_id),
        freelancer=User(user_id="w1")
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_project_and_freelancer', return_value=mock_proposal)
    mocker.patch.object(service.contract_repo, 'check_contract_exists_by_proposal', return_value=True) # 已存在

    with pytest.raises(HTTPException) as exc:
        await service.create_contract_from_proposal(ContractCreate(proposal_id="p1"), mock_user_employer)
    
    assert exc.value.status_code == 400
    assert "已建立合約" in exc.value.detail

# ==========================================
# Part 3: 草案管理與查詢 (Draft & CRUD) - 新增 P0/P1
# ==========================================

@pytest.mark.asyncio
async def test_get_my_contracts(mock_db_session, mock_user_employer, mocker):
    """測試：獲取我的合約列表"""
    service = ContractService(mock_db_session)
    mock_list = [Contract(contract_id="c1"), Contract(contract_id="c2")]
    mocker.patch.object(service.contract_repo, 'list_contracts_by_user', return_value=mock_list)

    result = await service.get_my_contracts(mock_user_employer)
    
    assert len(result) == 2
    service.contract_repo.list_contracts_by_user.assert_called_once_with(mock_user_employer.user_id)

@pytest.mark.asyncio
async def test_get_contract_details_permission(mock_db_session, mock_user_employer, mocker):
    """測試：檢視合約詳情權限 (必須是當事人)"""
    service = ContractService(mock_db_session)
    
    # 這個合約跟 mock_user_employer 無關
    mock_contract = Contract(
        contract_id="c1",
        employer_id="other_boss",
        freelancer_id="other_worker"
    )
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)

    with pytest.raises(HTTPException) as exc:
        await service.get_contract_details("c1", mock_user_employer)
    
    assert exc.value.status_code == 403
    assert "無權檢視" in exc.value.detail

@pytest.mark.asyncio
async def test_update_draft_contract_success(mock_db_session, mock_user_employer, mocker):
    """測試：雇主修改 '協商中' 的合約草案"""
    service = ContractService(mock_db_session)
    
    mock_contract = Contract(
        contract_id="c1",
        status="協商中",
        employer_id=mock_user_employer.user_id,
        version=1
    )
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    mocker.patch.object(service.contract_repo, 'update_contract', return_value=mock_contract)

    update_data = ContractUpdate(amount=60000, title="新標題")

    await service.update_draft_contract("c1", update_data, mock_user_employer)

    assert mock_contract.amount == 60000
    assert mock_contract.title == "新標題"
    assert mock_contract.version == 2 # 驗證版本號增加

@pytest.mark.asyncio
async def test_delete_draft_fail_permission(mock_db_session, mock_user_employer, mocker):
    """測試：非雇主嘗試刪除草案 (403)"""
    service = ContractService(mock_db_session)
    mock_contract = Contract(contract_id="c1", employer_id="other_boss", status="協商中")
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    
    with pytest.raises(HTTPException) as exc:
        await service.delete_draft_contract("c1", mock_user_employer)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_delete_draft_fail_wrong_status(mock_db_session, mock_user_employer, mocker):
    """測試：狀態非協商中嘗試刪除 (400) - 專門覆蓋 Line 201"""
    service = ContractService(mock_db_session)
    # 狀態是 "進行中"，應該報錯
    mock_contract = Contract(contract_id="c2", employer_id=mock_user_employer.user_id, status="進行中")
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    
    with pytest.raises(HTTPException) as exc:
        await service.delete_draft_contract("c2", mock_user_employer)
    assert exc.value.status_code == 400

@pytest.mark.asyncio
async def test_update_draft_fail_if_signed(mock_db_session, mock_user_employer, mocker):
    """測試：已簽訂(非協商中) 的合約不可修改"""
    service = ContractService(mock_db_session)
    mock_contract = Contract(
        contract_id="c1",
        status="進行中", # 狀態不對
        employer_id=mock_user_employer.user_id
    )
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)

    with pytest.raises(HTTPException) as exc:
        await service.update_draft_contract("c1", ContractUpdate(amount=100), mock_user_employer)
    
    assert exc.value.status_code == 400
    assert "無法修改" in exc.value.detail

@pytest.mark.asyncio
async def test_delete_draft_contract_success(mock_db_session, mock_user_employer, mocker):
    """測試：雇主刪除/撤銷草案"""
    service = ContractService(mock_db_session)
    mock_contract = Contract(
        contract_id="c1",
        status="協商中",
        employer_id=mock_user_employer.user_id
    )
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    mock_delete = mocker.patch.object(service.contract_repo, 'delete_contract', new_callable=AsyncMock)

    await service.delete_draft_contract("c1", mock_user_employer)

    mock_delete.assert_called_once_with(mock_contract)

# ... (保留原本的所有測試代碼) ...

# ==========================================
# Part 4: 補強異常處理 (Error Handling) - 修復 Line 100, 156, 165
# ==========================================

@pytest.mark.asyncio
async def test_create_contract_fail_proposal_not_found(mock_db_session, mock_user_employer, mocker):
    """測試：找不到提案時應報錯 (Line 100)"""
    service = ContractService(mock_db_session)
    # 模擬 Repo 回傳 None
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_project_and_freelancer', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.create_contract_from_proposal(ContractCreate(proposal_id="non_exist"), mock_user_employer)
    
    assert exc.value.status_code == 404
    assert "提案不存在" in exc.value.detail

@pytest.mark.asyncio
async def test_create_contract_fail_db_read_error(mock_db_session, mock_user_employer, mocker):
    """測試：建立後無法讀取 (防禦性程式碼 Line 156)"""
    service = ContractService(mock_db_session)
    
    # 1. 提案存在
    mock_proposal = Proposal(
        status="已接受",
        project=Project(employer_id=mock_user_employer.user_id),
        freelancer=User(user_id="w1")
    )
    mocker.patch.object(service.proposal_repo, 'get_proposal_by_id_with_project_and_freelancer', return_value=mock_proposal)
    mocker.patch.object(service.contract_repo, 'check_contract_exists_by_proposal', return_value=False)
    
    # 2. 建立成功
    mocker.patch.object(service.contract_repo, 'create_contract', return_value=Contract(contract_id="c1"))
    
    # 3. [關鍵] 但重新讀取時回傳 None (模擬 DB 異常)
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.create_contract_from_proposal(ContractCreate(proposal_id="p1"), mock_user_employer)
    
    assert exc.value.status_code == 500
    assert "無法讀取" in exc.value.detail

@pytest.mark.asyncio
async def test_get_contract_not_found(mock_db_session, mock_user_employer, mocker):
    """測試：合約不存在 (Line 165)"""
    service = ContractService(mock_db_session)
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=None)

    with pytest.raises(HTTPException) as exc:
        await service.get_contract_details("c_404", mock_user_employer)
    
    assert exc.value.status_code == 404

# ==========================================
# Part 5: 補強刪除草案邏輯 - 修復 Line 201, 203
# ==========================================

@pytest.mark.asyncio
async def test_delete_draft_fail_permission_and_status(mock_db_session, mock_user_employer, mock_user_freelancer, mocker):
    """測試：刪除草案的權限與狀態檢查"""
    service = ContractService(mock_db_session)
    
    # Case 1: 非雇主嘗試刪除
    mock_contract_1 = Contract(contract_id="c1", employer_id="other_boss", status="協商中")
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract_1)
    
    with pytest.raises(HTTPException) as exc:
        await service.delete_draft_contract("c1", mock_user_employer)
    assert exc.value.status_code == 403

    # Case 2: 狀態非協商中
    mock_contract_2 = Contract(contract_id="c2", employer_id=mock_user_employer.user_id, status="進行中")
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract_2)
    
    with pytest.raises(HTTPException) as exc:
        await service.delete_draft_contract("c2", mock_user_employer)
    assert exc.value.status_code == 400

# ==========================================
# Part 6: 狀態機參數化測試 - 修復 Line 298-361
# ==========================================

@pytest.mark.parametrize("current_status, new_status, actor_role_str", [
    # --- 發起請求 (原本已測) ---
    ("進行中", "雇主請求修改", "雇主"),
    ("進行中", "工作者請求修改", "自由工作者"),
    ("進行中", "雇主請求終止", "雇主"),
    ("進行中", "工作者請求終止", "自由工作者"),
    ("進行中", "工作者要求驗收", "自由工作者"),
    ("進行中", "已完成", "雇主"), # 直接完成 (不需要驗收的案子)
    ("協商中", "終止", "雇主"),   # 撤案
    ("協商中", "終止", "自由工作者"), # 工作者不想接了

    # --- (新增) 回應請求：修改 ---
    ("雇主請求修改", "協商中", "自由工作者"), # 同意修改 -> 回到協商
    ("雇主請求修改", "進行中", "自由工作者"), # 拒絕修改 -> 回到進行
    ("工作者請求修改", "協商中", "雇主"),     # 同意修改
    ("工作者請求修改", "進行中", "雇主"),     # 拒絕修改

    # --- (新增) 回應請求：終止 ---
    ("雇主請求終止", "終止", "自由工作者"),   # 同意終止
    ("雇主請求終止", "進行中", "自由工作者"), # 拒絕終止
    ("工作者請求終止", "終止", "雇主"),       # 同意終止
    ("工作者請求終止", "進行中", "雇主"),     # 拒絕終止

    # --- (新增) 回應請求：驗收 ---
    ("工作者要求驗收", "已完成", "雇主"),     # 驗收通過
    ("工作者要求驗收", "進行中", "雇主"),     # 驗收退回 (退回修改)
])
@pytest.mark.asyncio
async def test_valid_status_transitions_parameterized(
    mock_db_session, mocker, current_status, new_status, actor_role_str
):
    """
    參數化測試：覆蓋 allowed_transitions 字典中的所有 18 條路徑。
    """
    service = ContractService(mock_db_session)
    contract_id = "c_param"
    
    # 轉換 Role 字串為 Enum
    if actor_role_str == "雇主":
        role_enum = UserRoleEnum.employer
    else:
        role_enum = UserRoleEnum.freelancer

    mock_actor = User(user_id="actor_1", role=role_enum)
    
    # 模擬合約
    mock_contract = Contract(
        contract_id=contract_id,
        status=current_status,
        # 讓 actor 永遠是合約的當事人
        employer_id="actor_1" if actor_role_str == "雇主" else "other",
        freelancer_id="actor_1" if actor_role_str == "自由工作者" else "other",
        project=Project()
    )
    
    mocker.patch.object(service.contract_repo, 'get_contract_by_id', return_value=mock_contract)
    mock_update = mocker.patch.object(service.contract_repo, 'update_contract', return_value=mock_contract)

    # Act
    await service.update_contract_status(contract_id, ContractStatusUpdate(status=new_status), mock_actor)

    # Assert
    assert mock_contract.status == new_status
    mock_update.assert_called_once()