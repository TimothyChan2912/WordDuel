from services.match_factory import MatchFactory
from services.word_service import WordService
from database.db import get_connection


class BackendController:
    def __init__(self):
        self.queue_ref = {}   # player_id -> queue entry
        self.match_ref = {}   # match_id  -> match manager instance

    def handle_guess_check(self, player_id, match_id, guess):
        # TODO: validate guess, update PlayerMatchState, return feedback
        pass

    def start_new_game(self, player1_id, player2_id, mode_type, **kwargs):
        # TODO: use MatchFactory to create match, store in match_ref
        pass

    def handle_match_result(self, match_id, winner_id):
        # TODO: persist result, update player stats/rank
        pass
