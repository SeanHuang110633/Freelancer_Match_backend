import os
import sys
import types

# Ensure backend package (freelancer_match_backend) is on sys.path for imports during tests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.recommender import calculate_recommendation_scores


def make_item(item_id, skill_names, reputation_score=0):
    return {
        "item_id": item_id,
        "skill_names": set(skill_names),
        "item_object": types.SimpleNamespace(reputation_score=reputation_score)
    }


def test_empty_source_returns_empty():
    res = calculate_recommendation_scores(set(), [make_item("1", ["python"])])
    assert res == []


def test_exact_matches_score():
    source = {"python", "django"}
    items = [make_item("1", ["python", "flask"]) , make_item("2", ["javascript"]) ]
    scored = calculate_recommendation_scores(source, items)
    # only item 1 has one exact match => score >=1
    assert any(item["item_id"] == "1" for item in scored)
    assert all(item["score"] >= 1.0 for item in scored if item["item_id"] == "1")


def test_fuzzy_matches_score():
    source = {"reactjs"}
    # fuzzy match: 'react' should be similar
    items = [make_item("1", ["react"]), make_item("2", ["angular"]) ]
    scored = calculate_recommendation_scores(source, items)
    # expect item 1 to have a score > 0, item 2 likely 0
    ids = [s["item_id"] for s in scored]
    assert "1" in ids
    assert "2" not in ids


def test_sorting_and_reputation_tiebreaker():
    source = {"python"}
    # two items with same score but different reputation
    item_a = make_item("a", ["python"], reputation_score=3.0)
    item_b = make_item("b", ["python"], reputation_score=5.0)
    scored = calculate_recommendation_scores(source, [item_a, item_b])
    # first item should be b (higher reputation)
    assert scored[0]["item_id"] == "b"
    assert scored[1]["item_id"] == "a"
