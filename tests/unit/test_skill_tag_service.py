import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.skill_tag_service import SkillTagService


def test_constructor_initializes_repo(mocker, mock_db_session):
    """SkillTagService should instantiate SkillTagRepository with db."""
    mock_repo = MagicMock()
    mocker.patch("app.services.skill_tag_service.SkillTagRepository", return_value=mock_repo)

    service = SkillTagService(mock_db_session)

    assert service.repo is mock_repo


@pytest.mark.asyncio
async def test_get_all_tags_returns_list(mocker, mock_db_session):
    """get_all_tags should call repo.list_all_tags and return its value."""
    mock_repo = MagicMock()
    mock_repo.list_all_tags = AsyncMock(return_value=[{"id": "t1", "name": "tag1"}])
    mocker.patch("app.services.skill_tag_service.SkillTagRepository", return_value=mock_repo)

    service = SkillTagService(mock_db_session)

    result = await service.get_all_tags()

    assert result == [{"id": "t1", "name": "tag1"}]
    mock_repo.list_all_tags.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_all_tags_propagates_exception(mocker, mock_db_session):
    """If the repository raises, the service should propagate the exception."""
    mock_repo = MagicMock()
    mock_repo.list_all_tags = AsyncMock(side_effect=RuntimeError("db fail"))
    mocker.patch("app.services.skill_tag_service.SkillTagRepository", return_value=mock_repo)

    service = SkillTagService(mock_db_session)

    with pytest.raises(RuntimeError):
        await service.get_all_tags()
