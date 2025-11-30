import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ----------------------------------------------------------------------
# 1. 匯入您的 Base 與所有 Model
# ----------------------------------------------------------------------
# 為了讓 Alembic 偵測到所有表格，必須確保所有 Model 都被匯入
from app.core.database import Base
from app.core.config import settings

# 匯入所有定義的模型 (Model)，這樣 Base.metadata 才會包含它們
from app.models.user import User
from app.models.freelancer_profile import FreelancerProfile
from app.models.employer_profile import EmployerProfile
from app.models.skill_tag import SkillTag, UserSkillTag
from app.models.project import Project, ProjectSkillTag
from app.models.proposal import Proposal
from app.models.contract import Contract
from app.models.deliverable import Deliverable
from app.models.review import Review
from app.models.message import ChatRoom, ChatRoomParticipant, Message
from app.models.notification import Notification
# 若有其他 model 請一併匯入...

# ----------------------------------------------------------------------

config = context.config

# 設定 Log
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 2. 將 target_metadata 指向您的 Base.metadata
target_metadata = Base.metadata

# 3. 覆寫資料庫 URL (優先讀取環境變數或 App Settings)
# 這樣我們就不需要在 alembic.ini 中寫死帳密
def get_url():
    return settings.DATABASE_URL

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    
    # 使用我們設定檔中的 URL
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())