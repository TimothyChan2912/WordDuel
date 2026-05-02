import threading
from models.player_match_state import PlayerMatchStateCollection


class TimeBasedMatchManager:
    def __init__(self, match_id, player_states: PlayerMatchStateCollection, time_limit: int):
        self.match_id      = match_id
        self.player_states = player_states
        self.time_limit    = time_limit          # seconds
        self.countdown_timer: threading.Timer | None = None

    def initialize_timer(self):
        # TODO: set up countdown_timer to call _on_time_up after time_limit seconds
        pass

    def start_match(self):
        # TODO: assign shared word to both players, start timer
        pass

    def compare_scores(self):
        # TODO: compare words_solved for each player, return winner_id or None (draw)
        pass

    def handle_forfeit(self, player_id):
        # TODO: cancel timer, award win to opponent, save result
        pass

    def _on_time_up(self):
        # TODO: called when timer expires — compare scores, save result
        pass
