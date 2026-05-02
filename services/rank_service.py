def get_rank_info(elo):
    ranks = [
        ("Bronze", 0),
        ("Silver", 900),
        ("Gold", 1000),
        ("Platinum", 1200),
        ("Diamond", 1500),
    ]

    current = ranks[0]
    next_rank = None

    for i, rank in enumerate(ranks):
        if elo >= rank[1]:
            current = rank
            next_rank = ranks[i + 1] if i + 1 < len(ranks) else None

    if not next_rank:
        return {
            "rank": current[0],
            "elo": elo,
            "next_rank": None,
            "next_elo": None,
            "progress": 100,
        }

    prev_elo = current[1]
    next_elo = next_rank[1]
    progress = int(((elo - prev_elo) / (next_elo - prev_elo)) * 100)

    return {
        "rank": current[0],
        "elo": elo,
        "next_rank": next_rank[0],
        "next_elo": next_elo,
        "progress": progress,
    }

def get_rank_progress(elo):
    ranks = [
        ("Bronze", 0),
        ("Silver", 900),
        ("Gold", 1000),
        ("Platinum", 1200),
        ("Diamond", 1500),
    ]

    current = ranks[0]
    next_rank = None

    for i, rank in enumerate(ranks):
        if elo >= rank[1]:
            current = rank
            next_rank = ranks[i + 1] if i + 1 < len(ranks) else None

    if not next_rank:
        return {
            "rank": current[0],
            "next_rank": None,
            "next_elo": None,
            "progress": 100,
        }

    progress = int(((elo - current[1]) / (next_rank[1] - current[1])) * 100)

    return {
        "rank": current[0],
        "next_rank": next_rank[0],
        "next_elo": next_rank[1],
        "progress": progress,
    }