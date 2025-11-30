import asyncio
import sys
import os
import uuid
from sqlalchemy.future import select

# 將專案根目錄加入 Path，確保能匯入 app.*
sys.path.append(os.getcwd())

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash

# 匯入 Models
from app.models.user import User, UserRoleEnum
from app.models.skill_tag import SkillTag, UserSkillTag
from app.models.freelancer_profile import FreelancerProfile
from app.models.employer_profile import EmployerProfile
from app.models.project import Project, ProjectSkillTag

async def seed_data():
    async with AsyncSessionLocal() as db:
        print("🌱 開始系統測試種子資料注入 (Seeding)...")

        # -----------------------------------------------------
        # 1. 建立技能標籤 (Skill Tags) - 系統基礎資料
        # -----------------------------------------------------
        print(">> 建立 Skill Tags...")
        tags_data = [
            {"name": "Python", "category": "Backend"},
            {"name": "Vue.js", "category": "Frontend"},
            {"name": "FastAPI", "category": "Backend"},
            {"name": "MySQL", "category": "Database"},
            {"name": "Docker", "category": "DevOps"},
            {"name": "UI/UX Design", "category": "Design"}
        ]
        
        tag_map = {} # name -> uuid
        
        for t in tags_data:
            # 檢查是否存在，避免重複執行報錯
            stmt = select(SkillTag).where(SkillTag.name == t["name"])
            existing = (await db.execute(stmt)).scalars().first()
            
            if not existing:
                tag_id = str(uuid.uuid4())
                new_tag = SkillTag(
                    tag_id=tag_id, 
                    name=t["name"], 
                    category=t["category"], 
                    is_managed=True
                )
                db.add(new_tag)
                tag_map[t["name"]] = tag_id
            else:
                tag_map[t["name"]] = existing.tag_id
        
        await db.flush()

        # -----------------------------------------------------
        # 2. 建立測試雇主 (Employer) - "TechStart Inc."
        # -----------------------------------------------------
        print(">> 建立雇主 (employer@test.com)...")
        emp_email = "employer@test.com"
        stmt = select(User).where(User.email == emp_email)
        existing_emp = (await db.execute(stmt)).scalars().first()

        emp_user_id = str(uuid.uuid4())

        if not existing_emp:
            employer = User(
                user_id=emp_user_id,
                email=emp_email,
                password_hash=get_password_hash("password123"),
                role=UserRoleEnum.employer,
                is_active=True
            )
            db.add(employer)
            
            # 雇主 Profile
            emp_profile = EmployerProfile(
                profile_id=str(uuid.uuid4()),
                user_id=emp_user_id,
                company_name="TechStart Inc.",
                company_bio="Leading tech startup in Taiwan.",
                contact_email="hr@techstart.com",
                contact_phone="0912345678"
            )
            db.add(emp_profile)
        else:
            emp_user_id = existing_emp.user_id

        # -----------------------------------------------------
        # 3. 建立測試工作者 (Freelancer) - "Alex Code"
        # -----------------------------------------------------
        print(">> 建立工作者 (worker@test.com)...")
        worker_email = "worker@test.com"
        stmt = select(User).where(User.email == worker_email)
        existing_worker = (await db.execute(stmt)).scalars().first()

        worker_user_id = str(uuid.uuid4())

        if not existing_worker:
            freelancer = User(
                user_id=worker_user_id,
                email=worker_email,
                password_hash=get_password_hash("password123"),
                role=UserRoleEnum.freelancer,
                is_active=True
            )
            db.add(freelancer)

            # 工作者 Profile
            free_profile = FreelancerProfile(
                profile_id=str(uuid.uuid4()),
                user_id=worker_user_id,
                full_name="Alex Code",
                bio="Full Stack Developer specialized in Python & Vue.",
                visibility="公開",
                reputation_score=5.0
            )
            db.add(free_profile)
            await db.flush() # 確保 profile_id 生成

            # 綁定技能 (Python, Vue.js, FastAPI)
            skills_to_add = ["Python", "Vue.js", "FastAPI"]
            for skill_name in skills_to_add:
                if skill_name in tag_map:
                    user_skill = UserSkillTag(
                        user_skill_tag_id=str(uuid.uuid4()),
                        profile_id=free_profile.profile_id,
                        tag_id=tag_map[skill_name],
                        familiarity_level=5
                    )
                    db.add(user_skill)
        else:
            worker_user_id = existing_worker.user_id

        # -----------------------------------------------------
        # 4. 建立預設案件 (Project) - "E-commerce Backend"
        # -----------------------------------------------------
        print(">> 建立預設案件...")
        # 檢查雇主是否已有案件
        stmt = select(Project).where(Project.employer_id == emp_user_id)
        existing_projects = (await db.execute(stmt)).scalars().all()

        if not existing_projects:
            project_id = str(uuid.uuid4())
            project = Project(
                project_id=project_id,
                employer_id=emp_user_id,
                title="E-commerce Backend API Development",
                description="Need a robust backend using FastAPI and MySQL. Must support high concurrency.",
                status="招募中",
                work_type="遠端",
                location="台北",
                budget_min=50000,
                budget_max=80000,
                required_people=1
            )
            db.add(project)
            await db.flush()

            # 案件需求技能 (Python, MySQL, Docker)
            req_skills = ["Python", "MySQL", "Docker"]
            for skill_name in req_skills:
                if skill_name in tag_map:
                    proj_skill = ProjectSkillTag(
                        project_skill_tag_id=str(uuid.uuid4()),
                        project_id=project_id,
                        tag_id=tag_map[skill_name]
                    )
                    db.add(proj_skill)
            
            print(f"   -> 案件 '{project.title}' 已建立 (ID: {project_id})")

        await db.commit()
        print("🎉 資料初始化完成！環境已準備好進行系統測試。")

if __name__ == "__main__":
    # 使用 Docker 內部的 URL 執行時，確保環境變數 DATABASE_URL 正確
    # 若在本地執行此腳本連接 Docker DB，需手動 override DATABASE_URL 指向 localhost:3308
    asyncio.run(seed_data())