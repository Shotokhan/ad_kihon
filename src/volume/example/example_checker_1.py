from checker import AbstractChecker
from checker_lib import *


class Checker(AbstractChecker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def check(self):
        return CORRUPT

    def put(self, flag_data: str, seed: str):
        return CORRUPT

    def get(self, flag_data: str, seed: str):
        return CORRUPT
