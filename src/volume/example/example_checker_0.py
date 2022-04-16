from checker import AbstractChecker
from checker_lib import *


class Checker(AbstractChecker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def check(self):
        return OK

    def put(self, flag_data: str, seed: str):
        return OK

    def get(self, flag_data: str, seed: str):
        return OK
