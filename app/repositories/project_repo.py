# app/repositories/project_repo.py
# (您可以直接複製並取代整個檔案)

import logging
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from app.models.user import User
from app.models.employer_profile import EmployerProfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from sqlalchemy import func, delete 
from fastapi import HTTPException

# 匯入 Models
from app.models.project import Project, ProjectSkillTag
from app.models.user import User
from app.models.proposal import Proposal # --- (新增) --- 為了 Eager Loading

# 匯入 Schemas
from app.schemas.project_schema import ProjectCreate, ProjectUpdate

class ProjectRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
    # 建立新案件
    async def create_project(self, project_data: ProjectCreate, employer_id: str) -> Project:
        """
        建立新案件 (Project) 並同時寫入 案件-技能 (ProjectSkillTag) 關聯表
        """
        
        project_dict = project_data.model_dump(exclude={"skill_tag_ids"})
        new_project_id = str(uuid.uuid4())
        
        db_project = Project(
            **project_dict,
            project_id=new_project_id,
            employer_id=employer_id
        )
        
        db_skill_tags = []
        for tag_id in project_data.skill_tag_ids:
            db_skill_tags.append(
                ProjectSkillTag(
                    project_skill_tag_id=str(uuid.uuid4()),
                    project_id=new_project_id,
                    tag_id=tag_id
                )
            )
            
        self.db.add(db_project)
        self.db.add_all(db_skill_tags)
        
        await self.db.commit()
        
        # (修正)
        # 不要使用 refresh()，而是呼叫 get_project_by_id()
        # 它會使用 lazy="selectin" 抓取一個完整的、
        # 已預先載入 skills 和 skills.tag 的物件
        complete_project = await self.get_project_by_id(new_project_id)
        
        if complete_project is None:
            # 這種情況幾乎不可能發生，但作為防禦性程式設計
            raise HTTPException(status_code=404, detail="剛建立的案件找不到")

        return complete_project # 回傳這個 Pydantic 可以安全序列化的物件
    # 獲取單一案件 (包含技能)
    async def get_project_by_id(self, project_id: str) -> Project | None:
        """
        透過 ID 獲取單一案件 (包含技能)及雇主資訊
        
        (這個方法是正確的，因為 select(Project) 會觸發 Model 上的 lazy="selectin")
        """
        
        # (修改)
        stmt = select(Project).where(Project.project_id == project_id)
        
        # (重要：新增 Eager Loading 策略)
        # 載入 Project.employer (User)
        # 接著載入 User.employer_profile (EmployerProfile)
        stmt = stmt.options(
            joinedload(Project.employer).
            selectinload(User.employer_profile)
        )
        # (修改結束)
        
        result = await self.db.execute(stmt)
        return result.scalars().first()

    # 拿到某個案件的所有提案
    # 補上 ProposalService 需要的函式
    async def get_project_by_id_with_proposals(self, project_id: str) -> Project | None:
        """
        透過 ID 獲取單一案件，並 Eager Load (預先載入) 所有關聯的提案
        以及提案人的資訊 (用於 ProjectWithProposalsOut Schema)
        """
        stmt = select(Project).where(Project.project_id == project_id).options(
            # 1. 載入案件的提案列表 (project.proposals)
            selectinload(Project.proposals).options(
                # 2. 針對「每一個」提案，載入提案人 (proposal.freelancer)
                selectinload(Proposal.freelancer).options(
                    # 3. 針對「每一個」提案人，載入其 Profile (user.freelancer_profile)
                    selectinload(User.freelancer_profile)
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()


    # 條件搜尋案件
    async def list_projects(
        self,
        tag_ids: Optional[List[str]] = None,
        location: Optional[str] = None,
        work_type: Optional[str] = None
    ) -> List[Project]:
        """
        (核心功能) 依條件複合式搜尋案件
        1. 技能 (tag_ids): 任一標籤符合 (OR 邏輯)
        2. 地區 (location): 模糊比對
        3. 工作型態 (work_type): 精確比對
        """
        

        # 基礎查詢 (SELECT * FROM projects)
        # 我們指定 select(Project) 而非 select(Project.project_id, ...)，
        # 這樣才能觸發 Model 上的 lazy="selectin" 來自動載入 skills
        stmt = select(Project)

        # (新增) 修正 Bug 1：
        # 即使是列表查詢，也必須 Eager Load ProjectOut 所需的巢狀資料
        stmt = stmt.options(
            joinedload(Project.employer).
            selectinload(User.employer_profile)
        )
        # (新增結束)

        # 1. 處理技能標籤 (tag_ids)
        if tag_ids:
            # (重要)
            # 我們需要 JOIN 關聯表 ProjectSkillTag
            # 並且篩選 tag_id 在我們傳入的列表中
            # 這符合需求文件中的 "任一方與條件有相同標籤即匹配成功"
            # (新增日誌) 確認進入 tag_ids 邏輯
            logger.info(f"Applying tag_ids filter: {tag_ids}")
            stmt = stmt.join(
                ProjectSkillTag, Project.project_id == ProjectSkillTag.project_id
            ).where(
                ProjectSkillTag.tag_id.in_(tag_ids)
            )

        # 2. 處理地區 (location)
        if location:
            # 使用 ILIKE 進行不分大小寫的模糊比對 (e.g., "台北" 可搜到 "台北市")
            # (新增日誌) 確認進入 location 邏輯
            logger.info(f"Applying location filter: {location}")
            stmt = stmt.where(Project.location.ilike(f"%{location}%"))

        # 3. 處理工作型態 (work_type)
        if work_type:
            # 精確比對 (e.g., '遠端', '實體')
            # (新增日誌) 確認進入 work_type 邏輯
            logger.info(f"Applying work_type filter: {work_type}")
            stmt = stmt.where(Project.work_type == work_type)

        # (新增日誌) 打印最終生成的 SQL (近似)
        # 注意：這只是近似 SQL，參數可能未完全綁定，但有助於理解結構
        try:
            compiled_stmt = stmt.compile(compile_kwargs={"literal_binds": True})
            logger.info(f"Compiled SQL (approx): {compiled_stmt}")
        except Exception as e:
            logger.warning(f"Could not compile SQL for logging: {e}")
        
        # (重要) 
        # 1. 使用 distinct() 確保如果一個案件符合多個標籤，它在列表中只出現一次。
        # 2. 由於 'lazy="selectin"' 的機制，skills 會在這次查詢中被自動載入。
        result = await self.db.execute(stmt.distinct())
        
        return result.scalars().all()

    # 獲取所有「招募中」的案件 (包含技能)
    async def list_active_projects_with_skills(self) -> List[Project]:
        """
        獲取所有 '招募中' 的案件，並預先載入技能
        """
        # (重要)
        # 由於 Model 已設定 lazy="selectin"，
        # 我們只需查詢 Project 並過濾 status，
        # SQLAlchemy 會自動處理 'skills' 和 'skills.tag' 的 Eager Loading
        stmt = select(Project).where(Project.status == '招募中')

        # (重要：新增 Eager Loading 策略)
        # 這裡也必須載入 Project.employer (User)
        # 接著載入 User.employer_profile (EmployerProfile)
        stmt = stmt.options(
            joinedload(Project.employer).
            selectinload(User.employer_profile)
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    # 查看特定雇主的所有案件
    async def list_projects_by_employer_id(self, employer_id: str) -> List[Project]:
        """
        查詢特定雇主的所有案件 (包含技能)
        """
        # 依舊利用 lazy="selectin" 自動載入 skills
        stmt = select(Project).where(Project.employer_id == employer_id).order_by(Project.created_at.desc()) # 按建立時間排序

        # (重要：新增 Eager Loading 策略)
        # 這裡也必須載入 Project.employer (User)
        # 接著載入 User.employer_profile (EmployerProfile)
        stmt = stmt.options(
            joinedload(Project.employer).
            selectinload(User.employer_profile)
        )
        # (修改結束)
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    # (新增) 需求二：通用的更新方法
    async def update_project(self, project: Project) -> Project:
        """
        (U) 儲存對現有 Project 物件的變更
        """
        await self.db.commit()
        await self.db.refresh(project)
        # (重要) commit 後，我們需要重新獲取 Eager Loaded 的版本
        refreshed_project = await self.get_project_by_id(project.project_id)
        if refreshed_project is None:
             # 理論上不可能
            raise HTTPException(status_code=500, detail="Failed to re-fetch project after update")
        return refreshed_project

    # (新增) 需求二：更新案件技能標籤
    async def update_project_skills(self, project_id: str, tag_ids: List[str]):
        """
        (U) 覆蓋案件的技能標籤
        """
        # 1. 刪除舊標籤
        stmt_delete = delete(ProjectSkillTag).where(
            ProjectSkillTag.project_id == project_id
        )
        await self.db.execute(stmt_delete)
        await self.db.flush() # 確保 DELETE 執行

        # 2. 新增新標籤
        new_skill_links = []
        for tag_id in tag_ids:
            new_link = ProjectSkillTag(
                project_skill_tag_id=str(uuid.uuid4()),
                project_id=project_id,
                tag_id=tag_id
            )
            new_skill_links.append(new_link)
        
        if new_skill_links:
            self.db.add_all(new_skill_links)
        
        # (注意) commit 由上層的 update_project 執行