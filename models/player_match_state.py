from database.db import get_connection


class PlayerMatchState:
    def __init__(self, match_id, player_id):
        self.match_id     = match_id
        self.player_id    = player_id
        self.hp           = 100
        self.streak_count = 0
        self.words_solved = 0
        self.score        = 0

    def increment_streak(self):
        # TODO: streak_count += 1, persist
        pass

    def reset_streak(self):
        # TODO: streak_count = 0, persist
        pass

    def record_score(self, points):
        # TODO: score += points, words_solved += 1, persist
        pass


class PlayerMatchStateCollection:
    """Holds the PlayerMatchState for both players in a match."""

    def __init__(self):
        self.player_states: list[PlayerMatchState] = []

    def add(self, state: PlayerMatchState):
        self.player_states.append(state)

    def get_by_player(self, player_id) -> PlayerMatchState | None:
        return next((s for s in self.player_states if s.player_id == player_id), None)
