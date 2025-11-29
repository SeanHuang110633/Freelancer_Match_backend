import pytest
from types import SimpleNamespace
from app.utils.recommender import calculate_recommendation_scores

# 建立一個簡單的假物件來模擬 User/Project，具備 reputation_score 屬性
def mock_item(id, score=5.0):
    return SimpleNamespace(id=id, reputation_score=score)

def test_exact_match_score():
    """測試：完全匹配的標籤應該獲得 1.0 分"""
    source_skills = {"python", "fastapi"}
    target_items = [
        {
            "item_id": "p1",
            "skill_names": {"python"}, # 重疊 1 個
            "item_object": mock_item("p1")
        }
    ]
    
    results = calculate_recommendation_scores(source_skills, target_items)
    
    assert len(results) == 1
    assert results[0]["score"] == 1.0

def test_fuzzy_match_score():
    """測試：模糊匹配 (Levenshtein) 應該獲得 0.0 ~ 1.0 之間的分數"""
    source_skills = {"python"}
    # "pytho" 與 "python" 非常相似，應該會被匹配到
    target_items = [
        {
            "item_id": "p1", 
            "skill_names": {"pytho"}, 
            "item_object": mock_item("p1")
        }
    ]
    
    results = calculate_recommendation_scores(source_skills, target_items)
    
    assert len(results) == 1
    # 相似度肯定大於 0.7，但小於 1.0
    assert 0.7 < results[0]["score"] < 1.0

def test_sorting_logic_priority_and_reputation():
    """
    測試排序邏輯：
    1. 分數 (Score) 高的在前面
    2. 分數相同時，信譽 (Reputation) 高的在前面
    """
    source_skills = {"java", "sql"}
    
    targets = [
        # 專案 A: 命中 1 個標籤 (Score 1.0), 信譽 3.0
        {
            "item_id": "A", 
            "skill_names": {"java"}, 
            "item_object": mock_item("A", score=3.0)
        },
        # 專案 B: 命中 2 個標籤 (Score 2.0), 信譽 5.0 -> 最高分
        {
            "item_id": "B", 
            "skill_names": {"java", "sql"}, 
            "item_object": mock_item("B", score=5.0)
        },
        # 專案 C: 命中 1 個標籤 (Score 1.0), 信譽 5.0 -> 跟 A 同分，但信譽比 A 高
        {
            "item_id": "C", 
            "skill_names": {"sql"}, 
            "item_object": mock_item("C", score=5.0)
        }
    ]
    
    results = calculate_recommendation_scores(source_skills, targets)
    
    # 預期順序：
    # 1. B (2.0分)
    # 2. C (1.0分, 信譽 5.0)
    # 3. A (1.0分, 信譽 3.0)
    
    assert len(results) == 3
    assert results[0]["item_id"] == "B"
    assert results[1]["item_id"] == "C"
    assert results[2]["item_id"] == "A"

def test_empty_input():
    """測試：沒有輸入技能時回傳空列表"""
    assert calculate_recommendation_scores(set(), []) == []