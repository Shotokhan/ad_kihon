import pymongo
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from checker_lib import OK, MUMBLE, CORRUPT, DOWN, ERROR
import project_utils


class AlreadyExistentFlagOrSeed(Exception):
    pass


class NotExistentDocument(Exception):
    pass


class InvalidUpdate(Exception):
    pass


def get_db_manager(mongo_config, mongo_client=None):
    # the mongo_client implements a connection pool, so the idea is to have one instance of it where possible
    if mongo_client is None:
        mongo_client = open_client(mongo_config['hostname'], mongo_config['port'], mongo_config['user'], mongo_config['password'])
    db = get_db(mongo_client, mongo_config['db_name'])
    return db, mongo_client


def open_client(hostname, port, user, password) -> pymongo.MongoClient:
    mongo_url = f"mongodb://{user}:{password}@{hostname}"
    mongo_client = pymongo.MongoClient(mongo_url, port)
    return mongo_client


def get_db(mongo_client: pymongo.MongoClient, db_name: str) -> Database:
    return mongo_client.get_database(db_name)


def get_collection(db: Database, collection_name: str) -> Collection:
    return db.get_collection(collection_name)


def create_index(db: Database, collection_name: str, column_name: str):
    col = db.get_collection(collection_name)
    col.create_index([(column_name, pymongo.TEXT)], unique=True)


def insert_flag(db: Database, flag_data: str, seed: str, round_num: int, team_id: int, service_id: int):
    col = db.get_collection("flag")
    try:
        col.insert_one({"flag_data": flag_data, "seed": seed, "round_num": round_num,
                        "team_id": team_id, "service_id": service_id})
    except DuplicateKeyError:
        raise AlreadyExistentFlagOrSeed


def get_flag_by_data(db: Database, flag_data: str):
    col = db.get_collection("flag")
    flag = col.find_one({"flag_data": flag_data})
    if flag is None:
        raise NotExistentDocument
    return flag


def get_flag_for_round(db: Database, round_num: int, team_id: int, service_id: int):
    col = db.get_collection("flag")
    flag = col.find_one({"round_num": round_num, "team_id": team_id, "service_id": service_id})
    if flag is None:
        raise NotExistentDocument
    return flag


def insert_team_if_not_exists(db: Database, team_id: int, ip_addr: str, name: str, token: str):
    # ip_addr can also be an hostname
    col = db.get_collection("team")
    team = col.find_one({"team_id": team_id})
    if team is not None:
        return
    col.insert_one({"team_id": team_id, "ip_addr": ip_addr, "name": name, "token": token,
                    "points": [], "stolen_flags": [], "lost_flags": [], "checks": [], "last_pts_update": 0})


def get_teams(db: Database):
    col = db.get_collection("team")
    teams = col.find()
    return teams


def insert_service_if_not_exists(db: Database, service_id: int, port: int, name: str):
    col = db.get_collection("service")
    service = col.find_one({"service_id": service_id})
    if service is not None:
        return
    col.insert_one({"service_id": service_id, "port": port, "name": name})


def get_services(db: Database):
    col = db.get_collection("service")
    services = col.find()
    return services


def init_teams_points(db: Database):
    # this function silently checks if team points had already been initialized
    team_col = db.get_collection("team")
    teams = get_teams(db)
    services = [s for s in get_services(db)]
    for team in teams:
        for service in services:
            check = team_col.find_one({"team_id": team['team_id'],
                                       "points.service_id": service['service_id']})
            if check is None:
                team_col.update_one({"team_id": team['team_id']}, {"$push": {
                    "points": {"service_id": service['service_id'], "atk_pts": 0, "def_pts": 0, "sla_pts": 0}
                }})


def check_stolen_flag(db: Database, team_token: str, flag_data: str):
    # assumes that flag_data is in some flag document
    col = db.get_collection("team")
    team = col.find_one({"token": team_token, "stolen_flags.flag_data": flag_data})
    if team is None:
        raise NotExistentDocument
    return team


def push_stolen_flag(db: Database, team_token: str, flag_data: str, timestamp: int):
    # assumes that necessary checks were already made
    col = db.get_collection("team")
    col.update_one({"token": team_token}, {"$push": {
        "stolen_flags": {"flag_data": flag_data, "timestamp": timestamp}
    }})


def push_lost_flag(db: Database, team_id: int, flag_data: str, timestamp: int):
    # uses team_id because the flag submission service verifies each flag by querying it,
    # and by doing so it obtains the team_id (the team token is given by the attacker)
    col = db.get_collection("team")
    col.update_one({"team_id": team_id}, {"$push": {
        "lost_flags": {"flag_data": flag_data, "timestamp": timestamp}
    }})


def push_check(db: Database, team_id: int, service_id: int, status: str, timestamp: int):
    col = db.get_collection("team")
    col.update_one({"team_id": team_id}, {"$push": {
        "checks": {"service_id": service_id, "status": status, "timestamp": timestamp}
    }})


def update_points(db: Database, team_id: int, service_id: int, pts_type: str, increment: bool, timestamp: int):
    col = db.get_collection("team")
    if pts_type not in ["atk_pts", "def_pts", "sla_pts"]:
        raise InvalidUpdate
    if increment:
        amount = 1
    else:
        amount = -1
    col.update_one({"team_id": team_id, "points.service_id": service_id}, {"$inc": {
        f"points.$.{pts_type}": amount
    }})
    col.update_one({"team_id": team_id}, {"$set": {"last_pts_update": timestamp}})


def resume_points(db: Database):
    teams = [t for t in get_teams(db)]
    col = db.get_collection("team")
    flags = {}
    for team in teams:
        # set to 0 before making the entire computation
        for pts in team['points']:
            service_id = pts['service_id']
            col.update_one({"team_id": team['team_id'], "points.service_id": service_id},
                           {"$set": {"points.$.atk_pts": 0, "points.$.def_pts": 0, "points.$.sla_pts": 0}})
        max_timestamp = 0
        attacks = [i for i in team['stolen_flags']]
        for atk in attacks:
            if atk['flag_data'] not in flags:
                flag = get_flag_by_data(db, atk['flag_data'])
                flags[atk['flag_data']] = flag
            else:
                flag = flags[atk['flag_data']]
            service_id = flag['service_id']
            timestamp = atk['timestamp']
            if timestamp > max_timestamp:
                max_timestamp = timestamp
            update_points(db, team['team_id'], service_id, "atk_pts", True, timestamp)
        defenses = [i for i in team['lost_flags']]
        # it's called defenses but is "attacks received"
        for rcvd in defenses:
            if rcvd['flag_data'] not in flags:
                flag = get_flag_by_data(db, rcvd['flag_data'])
                flags[rcvd['flag_data']] = flag
            else:
                flag = flags[rcvd['flag_data']]
            service_id = flag['service_id']
            timestamp = rcvd['timestamp']
            if timestamp > max_timestamp:
                max_timestamp = timestamp
            update_points(db, team['team_id'], service_id, "def_pts", False, timestamp)
        checks = [i for i in team['checks']]
        for check in checks:
            if check['status'] == ERROR:
                continue
            elif check['status'] == OK:
                increment = True
            elif check['status'] in [MUMBLE, DOWN, CORRUPT]:
                increment = False
            else:
                project_utils.log(f"Found an invalid check status ( {check['status']} ) while resuming points")
                continue
            service_id = check['service_id']
            timestamp = check['timestamp']
            if timestamp > max_timestamp:
                max_timestamp = timestamp
            update_points(db, team['team_id'], service_id, "sla_pts", increment, timestamp)
        col.update_one({"team_id": team["team_id"]}, {"$set": {"last_pts_update": max_timestamp}})
