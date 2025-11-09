# app/services/contract_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from datetime import datetime
from typing import List
import logging

# 匯入 M7
from app.models.contract import Contract # (M7) 已在 Phase 1 更新 Enum
from app.schemas.contract_schema import ContractCreate, ContractUpdate, ContractStatusUpdate
from app.repositories.contract_repo import ContractRepository

# 匯入 M6 (提案)
from app.repositories.proposal_repo import ProposalRepository
from app.models.proposal import Proposal

# 匯入 M4 (案件)
from app.models.project import Project

# 匯入 M2/M3 (Profile)
from app.repositories.profile_repo import ProfileRepository

# 匯入 M1 (User)
from app.models.user import User

# (M8.3 新增)
from app.services.notification_service import NotificationService 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ContractService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.contract_repo = ContractRepository(db)
        self.proposal_repo = ProposalRepository(db)
        self.profile_repo = ProfileRepository(db)
        # (修正) 我們在上次偵錯中已確認需要 UserRepo
        from app.repositories.user_repo import UserRepository
        self.user_repo = UserRepository(db)
        self.notification_service = NotificationService(db) # (M8.3 新增)


    # ... _generate_contract_template (保持不變) ...
    def _generate_contract_template(
        self, 
        project: Project, 
        proposal: Proposal,
        employer: User,
        freelancer: User
    ) -> str:
        amount = project.budget_max or project.budget_min or 0.0
        end_date_str = project.completion_deadline.strftime('%Y-%m-%d') if project.completion_deadline else "未指定"
        template = f"""
# 專案合約草案 (v1)

## 一、 案件資訊
* **合約標題**: {project.title}
* **案件編號**: {project.project_id}
* **工作型態**: {project.work_type}
* **履約金額**: TWD {amount:,.0f}
* **履約期限**: 預計於 {end_date_str} 前完成

## 二、 雙方資訊
* **甲方 (雇主)**: {employer.email} (User ID: {employer.user_id})
* **乙方 (工作者)**: {freelancer.email} (User ID: {freelancer.user_id})

## 三、 工作內容
(此處由甲方(雇主)填寫，預設帶入案件描述)

{project.description}

## 四、 交付方式
(此處由甲方(雇主)填寫)

...

## 五、 其他附帶條件
(此處由甲方(雇主)填寫)

...

---
(本合約由系統於 {datetime.now().strftime('%Y-%m-%d %H:%M')} 自動產生，甲方(雇主)可於「協商中」狀態下修改)
"""
        return template.strip()


    # --- ( M8.3 執行順序修正 ) ---
    async def create_contract_from_proposal(
        self, 
        contract_data: ContractCreate, 
        employer: User
    ) -> Contract:
        proposal = await self.proposal_repo.get_proposal_by_id_with_project_and_freelancer(
            contract_data.proposal_id
        )
        if not proposal:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "提案不存在")
        if proposal.project.employer_id != employer.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "你無權操作此提案")
        if proposal.status != "已接受":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "此提案狀態不符 (非 '已接受')")
        exists = await self.contract_repo.check_contract_exists_by_proposal(
            contract_data.proposal_id
        )
        if exists:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "此提案已建立合約")
        
        project = proposal.project
        freelancer = proposal.freelancer
        
        content = self._generate_contract_template(
            project=project,
            proposal=proposal,
            employer=employer,
            freelancer=freelancer
        )
        
        # 步驟 1: 建立合約物件
        new_contract = Contract(
            project_id=project.project_id,
            proposal_id=proposal.proposal_id,
            employer_id=employer.user_id,
            freelancer_id=freelancer.user_id,
            title=project.title,
            content=content,
            amount=project.budget_max or project.budget_min or 0.0,
            start_date=datetime.now(),
            end_date=project.completion_deadline or datetime.now(),
            status="協商中"
        )
        
        # 步驟 2: (修正) 先將合約寫入 Repo 以取得 contract_id
        # (我們假設 repo.create_contract 不會 commit)
        created_contract = await self.contract_repo.create_contract(new_contract)

        # 步驟 3: (修正) 在 Repo 儲存後，*立即* 呼叫通知
        # 這樣 notification 和 contract 都在同一個 session 中
        await self.notification_service.create_notification(
            user_id=created_contract.freelancer_id, # 接收方：工作者
            title=f"雇主已建立合約草案「{created_contract.title}」",
            message="請檢視合約內容並確認簽署。",
            link_url=f"/contracts/{created_contract.contract_id}" # 現在我們有 ID
        )

        # 步驟 4: (修正) 最後才讀取 Eager Loaded 的物件並回傳
        # (這將在 Service 函式結束後由 FastAPI 統一 commit)
        fully_loaded_contract = await self.contract_repo.get_contract_by_id(
            created_contract.contract_id
        )
        
        if not fully_loaded_contract:
            # 這種情況理論上不應發生，除非 session 有問題
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "建立合約後無法讀取")

        return fully_loaded_contract
    # --- ( M8.3 修正結束 ) ---

    # ... get_contract_details (保持不變) ...
    async def get_contract_details(self, contract_id: str, user: User) -> Contract:
        contract = await self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "合約不存在")
        if contract.employer_id != user.user_id and contract.freelancer_id != user.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "你無權檢視此合約")
        return contract

    # ... get_my_contracts (保持不變) ...
    async def get_my_contracts(self, user: User) -> List[Contract]:
        return await self.contract_repo.list_contracts_by_user(user.user_id)

    # ... update_draft_contract (保持不變) ...
    async def update_draft_contract(
        self, 
        contract_id: str, 
        data: ContractUpdate, 
        user: User
    ) -> Contract:
        contract = await self.get_contract_details(contract_id, user)
        if contract.employer_id != user.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "只有雇主可以修改合約草案")
        if contract.status != "協商中":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "合約已簽訂，無法修改")
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(contract, key, value)
        contract.version += 1
        contract.updated_at = datetime.now()
        
        # (TODO: M8.3) 在這裡也應該加入通知，通知工作者「雇主修改了協商中的合約」
        
        await self.contract_repo.update_contract(contract)
        return await self.contract_repo.get_contract_by_id(contract.contract_id)
        
    # ... delete_draft_contract (保持不變) ...
    async def delete_draft_contract(self, contract_id: str, user: User) -> None:
        contract = await self.get_contract_details(contract_id, user)
        if contract.employer_id != user.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "只有雇主可以刪除合約草案")
        if contract.status != "協商中":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "合約已簽訂，無法刪除")
        
        # (TODO: M8.3) 在刪除前發送通知
        # await self.notification_service.create_notification(
        #     user_id=contract.freelancer_id,
        #     title=f"雇主已撤銷合約草案「{contract.title}」",
        #     link_url="/my-contracts"
        # )
        
        await self.contract_repo.delete_contract(contract)
        return

    # --- ( M7 狀態機重構 ) ---
    async def update_contract_status(
        self, 
        contract_id: str, 
        data: ContractStatusUpdate, 
        user: User
    ) -> Contract:
        """
        (M7.4, M7.5) 重構後的合約狀態流轉 (雙方)
        """
        contract = await self.get_contract_details(contract_id, user)
        
        current_status = contract.status
        new_status = data.status
        role = user.role.value # 使用 .value (e.g., "雇主")

        allowed_transitions = {
            # 1. (工作者) 同意合約 -> 進行中
            ("協商中", "進行中"): ["自由工作者"],
            
            # 2. (雇主) 請求修改
            ("進行中", "雇主請求修改"): ["雇主"],
            # 3. (工作者) 回應雇主修改
            ("雇主請求修改", "協商中"): ["自由工作者"], # 同意修改
            ("雇主請求修改", "進行中"): ["自由工作者"], # 拒絕修改
            
            # 4. (工作者) 請求修改
            ("進行中", "工作者請求修改"): ["自由工作者"],
            # 5. (雇主) 回應工作者修改
            ("工作者請求修改", "協商中"): ["雇主"], # 同意修改
            ("工作者請求修改", "進行中"): ["雇主"], # 拒絕修改

            # 6. (雇主) 請求終止
            ("進行中", "雇主請求終止"): ["雇主"],
            # 7. (工作者) 回應雇主終止
            ("雇主請求終止", "終止"): ["自由工作者"], # 同意終止
            ("雇主請求終止", "進行中"): ["自由工作者"], # 拒絕終止

            # 8. (工作者) 請求終止
            ("進行中", "工作者請求終止"): ["自由工作者"],
            # 9. (雇主) 回應工作者終止
            ("工作者請求終止", "終止"): ["雇主"], # 同意終止
            ("工作者請求終止", "進行中"): ["雇主"], # 拒絕終止

            # 10. (工作者) 請求驗收
            ("進行中", "工作者要求驗收"): ["自由工作者"],
            # 11. (雇主) 回應驗收
            ("工作者要求驗收", "已完成"): ["雇主"], # 驗收通過
            ("工作者要求驗收", "進行中"): ["雇主"], # 驗收退回

            # 12. (雇主) 直接完成 (適用於不需驗收的任務)
            ("進行中", "已完成"): ["雇主"],
            
            # 13. (雙方) 在協商中終止
            ("協商中", "終止"): ["雇主", "自由工作者"],
        }
        
        transition = (current_status, new_status)
        
        if transition not in allowed_transitions:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, 
                f"不合法的狀態轉移: {current_status} -> {new_status}"
            )
            
        if role not in allowed_transitions[transition]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"你的角色 ({role}) 無權執行此狀態轉移"
            )

        # --- (M8.3 觸發點：*完整* 邏輯修正) ---
        notification_title = ""
        notification_user_id = None
        link_url = f"/contracts/{contract.contract_id}"
        content_name = f"「{contract.title}」" # 輔助變數

        # 依 transition 決定接收方和標題
        # --- 協商/簽約 ---
        if transition == ("協商中", "進行中"):
            notification_title = f"工作者已簽署合約 {content_name}"
            notification_user_id = contract.employer_id # 通知雇主
        
        elif transition == ("協商中", "終止"):
            # 通知對方
            notification_user_id = contract.employer_id if role == "自由工作者" else contract.freelancer_id
            notification_title = f"合約 {content_name} 已在協商中被 {role} 終止"

        # --- 雇主請求修改 (E: 雇主, F: 工作者) ---
        elif transition == ("進行中", "雇主請求修改"):
            notification_title = f"雇主請求修改合約 {content_name}"
            notification_user_id = contract.freelancer_id # 通知 F
        elif transition == ("雇主請求修改", "協商中"):
            notification_title = f"工作者同意修改合約 {content_name} (返回協商)"
            notification_user_id = contract.employer_id # 通知 E
        elif transition == ("雇主請求修改", "進行中"):
            notification_title = f"工作者拒絕修改合約 {content_name} (恢復進行)"
            notification_user_id = contract.employer_id # 通知 E

        # --- 工作者請求修改 (E: 雇主, F: 工作者) ---
        elif transition == ("進行中", "工作者請求修改"):
            notification_title = f"工作者請求修改合約 {content_name}"
            notification_user_id = contract.employer_id # 通知 E
        elif transition == ("工作者請求修改", "協商中"):
            notification_title = f"雇主同意修改合約 {content_name} (返回協商)"
            notification_user_id = contract.freelancer_id # 通知 F
        elif transition == ("工作者請求修改", "進行中"):
            notification_title = f"雇主拒絕修改合約 {content_name} (恢復進行)"
            notification_user_id = contract.freelancer_id # 通知 F

        # --- 雇主請求終止 (E: 雇主, F: 工作者) ---
        elif transition == ("進行中", "雇主請求終止"):
            notification_title = f"雇主請求終止合約 {content_name}"
            notification_user_id = contract.freelancer_id # 通知 F
        elif transition == ("雇主請求終止", "終止"):
            notification_title = f"工作者同意終止合約 {content_name}"
            notification_user_id = contract.employer_id # 通知 E
        elif transition == ("雇主請求終止", "進行中"):
            notification_title = f"工作者拒絕終止合約 {content_name} (恢復進行)"
            notification_user_id = contract.employer_id # 通知 E

        # --- 工作者請求終止 (E: 雇主, F: 工作者) ---
        elif transition == ("進行中", "工作者請求終止"):
            notification_title = f"工作者請求終止合約 {content_name}"
            notification_user_id = contract.employer_id # 通知 E
        elif transition == ("工作者請求終止", "終止"):
            notification_title = f"雇主同意終止合約 {content_name}"
            notification_user_id = contract.freelancer_id # 通知 F
        elif transition == ("工作者請求終止", "進行中"):
            notification_title = f"雇主拒絕終止合約 {content_name} (恢復進行)"
            notification_user_id = contract.freelancer_id # 通知 F
            
        # --- 驗收流程 (E: 雇主, F: 工作者) ---
        elif transition == ("進行中", "工作者要求驗收"):
            notification_title = f"工作者已提交 {content_name} 的驗收請求"
            notification_user_id = contract.employer_id # 通知 E
        elif transition == ("工作者要求驗收", "已完成"):
            notification_title = f"雇主已驗收通過 {content_name}"
            notification_user_id = contract.freelancer_id # 通知 F
        elif transition == ("工作者要求驗收", "進行中"):
            notification_title = f"雇主退回了 {content_name} 的驗收 (恢復進行)"
            notification_user_id = contract.freelancer_id # 通知 F
            
        # --- 雇主直接完成 ---
        elif transition == ("進行中", "已完成"):
            notification_title = f"雇主已將合約 {content_name} 標記為完成"
            notification_user_id = contract.freelancer_id # 通知 F
        
        # --- (M8.3 觸發點：執行通知) ---
        # (修正) 我們將執行點移到 DB 更新 *之前*，以匹配成功的模式
        logging.info(f"準備發送通知給 User ID: {notification_user_id}，標題: {notification_title}")
        if notification_user_id and notification_title:
            await self.notification_service.create_notification(
                user_id=notification_user_id,
                title=notification_title,
                link_url=link_url
            )
        # --- (M8.3 結束) ---
        
        # 更新狀態
        contract.status = new_status
        contract.updated_at = datetime.now()
        
        # --- ( M7 狀態機重構 ) ---
        if transition == ("協商中", "進行中"):
            if contract.project:
                contract.project.status = "已成案"
        # --- ( M7 修正結束 ) ---
        
        # (TODO: M9) 如果 new_status == "已完成"，觸發 M9 (評價) 模組
        
        # (修正) DB 更新是最後一步
        await self.contract_repo.update_contract(contract)
        
        # (修正) 同樣，更新後也需要回傳 Eager Loaded 的物件
        return await self.contract_repo.get_contract_by_id(contract.contract_id)