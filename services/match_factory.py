from models.match import Match
from models.player_match_state import PlayerMatchState, PlayerMatchStateCollection


class MatchFactory:
    @staticmethod
    def create_match(mode_type, player1_id, player2_id, **kwargs):
        """
        Instantiate the correct match manager based on mode_type.
        kwargs: time_limit, guess_attempts
        """
        # TODO: create Match record in DB
        # TODO: create PlayerMatchState records for both players
        # TODO: return the appropriate manager instance
        if mode_type == 'time_based':
            pass  # return TimeBasedMatchManager(...)
        elif mode_type == 'streak':
            pass  # return StreakMatchManager(...)
        else:
            pass  # return PvPMatchManager(...)
