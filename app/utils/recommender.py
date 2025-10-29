# app/utils/recommender.py (新檔案)
import Levenshtein
from typing import List, Dict, Set

# (輔助函式) 取得兩個字串的 Levenshtein 相似度 (0.0 ~ 1.0)
def _get_string_similarity(s1: str, s2: str) -> float:
    # Levenshtein.distance 算出的是 "編輯距離" (差多少)
    # 我們將其標準化為 "相似度" (0.0 ~ 1.0)
    # 1.0 表示完全相同
    if not s1 or not s2:
        return 0.0
    distance = Levenshtein.distance(s1.lower(), s2.lower())
    max_len = max(len(s1), len(s2))
    # 避免除以零，以及如果兩個字串都是空的，視為完全相似
    if max_len == 0:
        return 1.0
    return 1.0 - (distance / max_len)

def calculate_recommendation_scores(
    # 'source_skills' (e.g., 登入者的技能)
    source_skill_names: Set[str], 
    # 'target_items' (e.g., 所有案件 or 所有工作者)
    target_items: List[Dict] 
) -> List[Dict]:
    """
    計算來源 (Source) 與所有目標 (Target) 的推薦分數
    """
    
    recommendations = []

    if not source_skill_names:
        return []

    for item in target_items:
        item_skill_names = item.get("skill_names", set())
        if not item_skill_names:
            continue

        total_score = 0.0
        
        # 1. (標籤重疊度)
        exact_matches = source_skill_names.intersection(item_skill_names) # 
        total_score += len(exact_matches) * 1.0 
        
        # 2. (Levenshtein 相似度)
        source_fuzzy_tags = source_skill_names - exact_matches
        item_fuzzy_tags = item_skill_names - exact_matches

        for s_tag in source_fuzzy_tags:
            best_match_score = 0.0
            for i_tag in item_fuzzy_tags:
                similarity = _get_string_similarity(s_tag, i_tag)
                if similarity > 0.7: 
                    best_match_score = max(best_match_score, similarity)
            
            total_score += best_match_score

        if total_score > 0:
            recommendations.append({
                # (修正) 使用通用的 'item_id' 和 'item_object'
                "item_id": item.get("item_id"), 
                "score": total_score,
                "item_object": item.get("item_object") 
            })

   # 排序邏輯
    recommendations.sort(
        key=lambda x: (
            x["score"], # 主要排序鍵：推薦分數 (高到低)
            # 次要排序鍵：信譽分數 (高到低)
            getattr(x.get("item_object"), 'reputation_score', 0)
        ),
        reverse=True # <--- 關鍵在這裡
    )
    
    return recommendations