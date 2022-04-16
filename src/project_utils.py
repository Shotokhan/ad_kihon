from sys import stderr
import json
from functools import wraps
from flask import Response

# not "from mongo_utils import .." because it gives import error in other modules
import mongo_utils


def log(message: str):
    print(f"[+] {message}", file=stderr)


def read_config():
    with open("volume/config.json", 'r') as f:
        config = json.load(f)
    return config


def json_response(msg_dict, status_code):
    res = Response(json.dumps(msg_dict), status=status_code, mimetype='application/json')
    return res


def init_or_resume_mongo(config):
    # all these operations are safe, i.e. they are silently okay if db is being resumed
    db, _ = mongo_utils.get_db_manager(config['mongo'])
    for team in config['teams']:
        mongo_utils.insert_team_if_not_exists(db, team['id'], team['host'], team['name'], team['token'])
    for service in config['services']:
        mongo_utils.insert_service_if_not_exists(db, service['id'], service['port'], service['name'])
    mongo_utils.init_teams_points(db)
    mongo_utils.create_index(db, collection_name='flag', column_name='flag_data')
    mongo_utils.resume_points(db)


def catch_error(func):
    @wraps(func)
    def exceptionLogger(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            err_log = "Exception in {}: {} {}\n".format(func.__name__, e.__class__.__name__, str(e))
            log(err_log)
            msg = {"error": "Generic error"}
            return json_response(msg, 500)
    return exceptionLogger
