class AbstractChecker:
    # you must implement this class with a class named "Checker" and specify its relative path
    # in config.json; the seed is passed because, usually, checker are stateless, but you have
    # a class for each team and for each service so you can make stateful checkers if you prefer
    def __init__(self, team: dict, service: dict):
        self.team = team
        self.service = service

    def check(self):
        raise NotImplementedError

    def put(self, flag_data: str, seed: str):
        raise NotImplementedError

    def get(self, flag_data: str, seed: str):
        raise NotImplementedError
