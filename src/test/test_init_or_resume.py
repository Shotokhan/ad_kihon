import mongomock
import time

import project_utils
from mongo_utils import get_db_manager, get_teams, get_services, insert_flag, push_stolen_flag, push_lost_flag, get_flag_by_data, NotExistentDocument
from checker_lib import gen_flag, gen_seed


config = {
    "teams": [
        {"id": 0, "host": "10.0.0.1", "name": "first", "token": "c2e192800a294acbb2ac7dd188502edb"},
        {"id": 1, "host": "10.0.0.2", "name": "second", "token": "934310005a1447b8bd52d9dcbd5c405a"}
    ],
    "services": [
        {"id": 0, "port": 7331, "name": "example_0", "checker": "volume/example/example_checker_0.py"},
        {"id": 1, "port": 7332, "name": "example_1", "checker": "volume/example/example_checker_1.py"}
    ],
    "mongo": {
        "hostname": "mock.mongodb.com", "port": 27017, "db_name": "ad_kihon", "user": "admin", "password": "admin"
    },
    "flask": {
        "port": 8080
    },
    "misc": {
        "start_time": "11 apr 2022 15:30",
        "end_time": "11 apr 2022 19:30",
        "round_time": 120,
        "flag_lifetime": 5,
        "atk_weight": 10,
        "def_weight": 10,
        "sla_weight": 80,
        "flag_header": "flag",
        "flag_body_len": 30,
        "rate_limit_seconds": 5,
        "max_flags_per_submission": 20,
        "scoreboard_cache_update_latency": 2,
        "base_score": 1000
    }
}


def util_push_attack(db, flags, index):
    if not (0 <= index <= 3):
        project_utils.log("Error: provide an index in [0, 3]")
        raise Exception
    if index <= 1:
        token = "934310005a1447b8bd52d9dcbd5c405a"
        attacked_team_id = 0
    else:
        token = "c2e192800a294acbb2ac7dd188502edb"
        attacked_team_id = 1
    timestamp = int(time.time())
    push_stolen_flag(db, token, flags[index], timestamp)
    push_lost_flag(db, attacked_team_id, flags[index], timestamp)


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def base_init_test():
    project_utils.init_or_resume_mongo(config)
    db, _ = get_db_manager(config['mongo'])
    # some basic checks
    teams = [t for t in get_teams(db)]
    config_teams = {t['id']: t for t in config['teams']}
    for team in teams:
        assert team['team_id'] in config_teams, "Team should have been written to mongo"
        assert team['name'] == config_teams[team['team_id']]['name'], "Team should have been properly written to mongo"
        assert len(team['points']) == len(config['services']), "Points should have been initialized"
    services = [s for s in get_services(db)]
    config_services = {s['id']: s for s in config['services']}
    for service in services:
        assert service['service_id'] in config_services, "Service should have been written to mongo"
        assert service['name'] == config_services[service['service_id']]['name'], \
            "Service should have been properly written to mongo"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def init_do_something_then_resume_test():
    project_utils.init_or_resume_mongo(config)
    db, _ = get_db_manager(config['mongo'])
    flags = [gen_flag(config['misc']['flag_header'], config['misc']['flag_body_len']) for _ in range(4)]
    seeds = [gen_seed() for _ in range(4)]
    i, j = 0, 0
    for flag, seed in zip(flags, seeds):
        insert_flag(db, flag, seed, round_num=0, team_id=i, service_id=j)
        i = (i + j) % 2
        j = (j + 1) % 2
    """
        flag[0] owned by team 0, service 0
        flag[1] owned by team 0, service 1
        flag[2] owned by team 1, service 0
        flag[3] owned by team 1, service 1
    """
    for i in range(2):
        util_push_attack(db, flags, i)
    project_utils.init_or_resume_mongo(config)
    # some basic checks plus some additional checks
    teams = [t for t in get_teams(db)]
    config_teams = {t['id']: t for t in config['teams']}
    for team in teams:
        assert team['team_id'] in config_teams, "Team should have been written to mongo"
        assert team['name'] == config_teams[team['team_id']]['name'], "Team should have been properly written to mongo"
        assert len(team['points']) == len(config['services']), "Points should have been initialized"
        points = team['points']
        team['points'] = {p['service_id']: p for p in points}
        if team['team_id'] == 0:
            assert len(team['lost_flags']) == 2, "Team 0 should have lost 2 flags"
            assert team['points'][0]['def_pts'] == -1, "Team 0 points on service 0 should have been resumed"
            assert team['points'][1]['def_pts'] == -1, "Team 0 points on service 1 should have been resumed"
        elif team['team_id'] == 1:
            assert len(team['stolen_flags']) == 2, "Team 0 should have stolen 2 flags"
            assert team['points'][0]['atk_pts'] == 1, "Team 1 points on service 0 should have been resumed"
            assert team['points'][1]['atk_pts'] == 1, "Team 1 points on service 1 should have been resumed"
    services = [s for s in get_services(db)]
    config_services = {s['id']: s for s in config['services']}
    for service in services:
        assert service['service_id'] in config_services, "Service should have been written to mongo"
        assert service['name'] == config_services[service['service_id']]['name'], \
            "Service should have been properly written to mongo"
    for flag in flags:
        error = False
        try:
            get_flag_by_data(db, flag)
        except NotExistentDocument:
            error = True
        assert not error, "Flag should be present in mongo"


tests = [base_init_test, init_do_something_then_resume_test]


if __name__ == "__main__":
    for test in tests:
        project_utils.log(f"Starting test: {test.__name__}")
        try:
            test()
        except AssertionError as e:
            project_utils.log(f"Test {test.__name__} failed: {e.args}")
            continue
        project_utils.log(f"Test {test.__name__} completed successfully")
