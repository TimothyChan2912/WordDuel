import threading
from models.player_match_state import PlayerMatchStateCollection


class BattleMatchManager:
    def __init__(self, match_id, player_states: PlayerMatchStateCollection,
                 starting_hp: int = 100):
        self.match_id      = match_id
        self.player_states = player_states
        self.starting_hp   = starting_hp

        self.current_word  = None
        self.current_round = 1

        self.round_timer: threading.Timer | None = None

    def start_match(self):
        # TODO:
        # - initialize each player's HP
        # - reset round state
        # - generate first word
        # - notify clients match has started
        pass

    def handle_guess_complete(self):
        # TODO:
        # - check if both players finished round
        # - if yes → trigger damage calculation
        # - then either end match or start next round
        pass

    def calculate_damage(self, attempts: int):
        # TODO:
        # - convert number of attempts into damage value
        # - return int
        pass

    def apply_round_damage(self):
        # TODO:
        # - compute each player's damage
        # - subtract HP crosswise
        # - emit round results
        pass

    def check_win_condition(self):
        # TODO:
        # - return winner_id if one player's HP <= 0
        # - return None otherwise
        pass

    def handle_forfeit(self, player_id):
        # TODO:
        # - immediately end match
        # - award win to opponent
        # - apply ELO change
        # - emit game_over
        pass
