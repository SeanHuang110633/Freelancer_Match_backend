import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from app.services.recommendation_service import RecommendationService
from app.models.user import User


@pytest.mark.asyncio
async def test_get_job_recommendations_forbidden_role(mock_db_session, mock_user_employer):
    service = RecommendationService(mock_db_session)
    # employer is not allowed to get job recs
    with pytest.raises(HTTPException) as exc:
        await service.get_job_recommendations(mock_user_employer)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_job_recommendations_no_profile_or_no_skills(mock_db_session, mock_user_freelancer, mocker):
    service = RecommendationService(mock_db_session)
    # profile missing -> empty result
    service.profile_repo = MagicMock()
    service.profile_repo.get_freelancer_profile_by_user_id = AsyncMock(return_value=None)

    result = await service.get_job_recommendations(mock_user_freelancer)
    assert result == {"items": [], "total": 0}

    # profile exists but no skills
    profile = MagicMock()
    profile.skills = []
    service.profile_repo.get_freelancer_profile_by_user_id = AsyncMock(return_value=profile)

    result = await service.get_job_recommendations(mock_user_freelancer)
    assert result == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_get_job_recommendations_success_filters_own_and_formats_scores(mock_db_session, mock_user_freelancer, mocker):
    service = RecommendationService(mock_db_session)

    # Mock profile with skills
    tag = MagicMock()
    tag.name = "Python"
    user_skill = MagicMock()
    user_skill.tag = tag
    profile = MagicMock()
    profile.skills = [user_skill]
    service.profile_repo = MagicMock()
    service.profile_repo.get_freelancer_profile_by_user_id = AsyncMock(return_value=profile)

    # Projects: one belongs to same user (should be skipped), one valid
    proj1 = MagicMock()
    proj1.project_id = "p_self"
    proj1.employer_id = mock_user_freelancer.user_id
    proj1.skills = []

    proj2 = MagicMock()
    proj2.project_id = "p_other"
    proj2.employer_id = "other"
    skill2 = MagicMock(); skill2.tag = MagicMock(); skill2.tag.name = "python"
    proj2.skills = [skill2]

    service.project_repo = MagicMock()
    service.project_repo.list_active_projects_with_skills = AsyncMock(return_value=[proj1, proj2])

    # mock scoring function to return scored list
    mock_scored = [
        {"item_object": proj2, "score": 0.876},
    ]
    mocker.patch("app.services.recommendation_service.calculate_recommendation_scores", return_value=mock_scored)

    res = await service.get_job_recommendations(mock_user_freelancer, limit=10, offset=0)
    assert res["total"] == 1
    assert res["items"][0]["project"] is proj2
    assert isinstance(res["items"][0]["recommendation_score"], float)


@pytest.mark.asyncio
async def test_get_freelancer_recommendations_forbidden_role(mock_db_session, mock_user_freelancer):
    service = RecommendationService(mock_db_session)
    with pytest.raises(HTTPException) as exc:
        await service.get_freelancer_recommendations(mock_user_freelancer)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_freelancer_recommendations_no_employer_skills_returns_empty(mock_db_session, mock_user_employer, mocker):
    service = RecommendationService(mock_db_session)
    # simulate db.execute returning no projects
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    service.db = AsyncMock()
    service.db.execute = AsyncMock(return_value=mock_result)

    service.profile_repo = MagicMock()
    res = await service.get_freelancer_recommendations(mock_user_employer)
    assert res == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_get_freelancer_recommendations_success_calls_algorithm_and_formats(mock_db_session, mock_user_employer, mocker):
    service = RecommendationService(mock_db_session)

    # create one employer project with skills
    proj_skill = MagicMock(); proj_skill.tag = MagicMock(); proj_skill.tag.name = "django"
    project = MagicMock(); project.skills = [proj_skill]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [project]
    service.db = AsyncMock()
    service.db.execute = AsyncMock(return_value=mock_result)

    # public freelancers
    prof = MagicMock(); prof.profile_id = "pf1"; prof.user_id = "u1"
    p_skill = MagicMock(); p_skill.tag = MagicMock(); p_skill.tag.name = "django"
    prof.skills = [p_skill]

    service.profile_repo = MagicMock()
    service.profile_repo.list_public_freelancer_profiles_with_skills = AsyncMock(return_value=[prof])

    # mock scoring
    scored = [{"item_object": prof, "score": 0.5}]
    mocker.patch("app.services.recommendation_service.calculate_recommendation_scores", return_value=scored)

    res = await service.get_freelancer_recommendations(mock_user_employer, limit=10, offset=0)
    assert res["total"] == 1
    assert res["items"][0]["profile"] is prof
    assert res["items"][0]["recommendation_score"] == round(0.5, 2)
