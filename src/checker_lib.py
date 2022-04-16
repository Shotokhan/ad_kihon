import uuid


OK = "ok"
MUMBLE = "mumble"
CORRUPT = "corrupt"
DOWN = "down"
ERROR = "error"


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
