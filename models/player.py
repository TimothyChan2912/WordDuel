from database.db import get_connection


class Player:
    def __init__(self, id, username, email, rank, skill_level):
        self.id          = id
        self.username    = username
        self.email       = email
        self.rank        = rank
        self.skill_level = skill_level

    @staticmethod
    def find_by_username(username):
        # TODO: query players table by username
        pass

    @staticmethod
    def create(username, email, password_hash):
        # TODO: insert new player into players table
        pass

    def find_match(self, mode_type):
        # TODO: add player to matchmaking_queue
        pass

    def set_category(self, category):
        # TODO: update player's preferred category
        pass

    def make_guess(self, word):
        # TODO: validate guess against current match word
        pass
