from controllers.backend_controller import BackendController


class ModeManager:
    def __init__(self, backend: BackendController):
        self.backend = backend

    def handle_find_match_click(self, player_id, mode_type, **kwargs):
        # TODO: add player to matchmaking queue, check for opponent, start match if found
        pass


class ModeSelector:
    def __init__(self):
        self.time_limit     = None
        self.guess_attempts = None

    def set_mode(self, mode_type: str, time_limit: int = None, guess_attempts: int = None):
        # TODO: configure mode parameters, pass to ModeManager
        self.time_limit     = time_limit
        self.guess_attempts = guess_attempts
