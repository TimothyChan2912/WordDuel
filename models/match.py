from database.db import get_connection


class Match:
    def __init__(self, id, mode_type, status, time_limit=None, guess_attempts=None):
        self.id             = id
        self.mode_type      = mode_type   # 'pvp' | 'time_based' | 'streak'
        self.status         = status
        self.time_limit     = time_limit
        self.guess_attempts = guess_attempts

    @staticmethod
    def create(mode_type, time_limit=None, guess_attempts=None):
        # TODO: insert into matches table, return Match instance
        pass

    @staticmethod
    def find_by_id(match_id):
        # TODO: query matches table
        pass

    def save_result(self, winner_id):
        # TODO: insert into match_results, set status = 'completed'
        pass
