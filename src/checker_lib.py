import uuid
import random
import hashlib


OK = "ok"
MUMBLE = "mumble"
CORRUPT = "corrupt"
DOWN = "down"
ERROR = "error"


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class CheckerUtils(metaclass=Singleton):
    def __init__(self):
        self.user_agents = None
        with open('/usr/src/app/src/useragents.txt', 'r') as f:
            self.user_agents = f.read().split('\n')
        self.usernames = None
        with open('/usr/src/app/src/usernames.txt', 'r') as f:
            self.usernames = f.read().split('\n')

    def randomUserAgent(self):
        return random.choice(self.user_agents)

    def randomUsername(self):
        return random.choice(self.usernames)

    @staticmethod
    def credentialsFromSeed(seed, length=16):
        seed = seed.encode()
        password = hashlib.sha256()
        password.update(seed)
        password = password.digest()

        username = hashlib.sha256()
        username.update(password)
        username.update(seed)
        username = username.digest()

        password = password.hex()[:length]
        username = username.hex()[:length]
        return username, password


def gen_flag(flag_header="flag", flag_body_len=32):
    # pattern: r'flag\{[a-f0-9]{32}\}' ; generate pattern for re:
    # flag_header + r'\{[a-f0-9]{' + str(flag_body_len) + r'}\}'
    flag_body = ""
    while len(flag_body) < flag_body_len:
        flag_body += uuid.uuid4().hex
    flag_body = flag_body[:flag_body_len]
    flag = flag_header + '{' + flag_body + '}'
    return flag


def gen_seed():
    return uuid.uuid4().hex
