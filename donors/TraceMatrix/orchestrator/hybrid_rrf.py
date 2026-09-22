
def reciprocal_rank_fusion(ranked_lists, k=10, weight=60):
    scores = {}
    for lst in ranked_lists:
        for rank, item in enumerate(lst, start=1):
            key = item if isinstance(item, str) else item.get('url') or item.get('id')
            scores[key] = scores.get(key, 0) + 1.0 / (weight + rank)
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [k for k,v in ordered][:k]
