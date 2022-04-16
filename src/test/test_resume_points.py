import mongomock
import time

from mongo_utils import *
from checker_lib import gen_flag, gen_seed, OK, ERROR, DOWN, MUMBLE, CORRUPT


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
        "flag_body_len": 30
    }
}


def prepare_test():
    db, _ = get_db_manager(config['mongo'])
    for team in config['teams']:
        insert_team_if_not_exists(db, team['id'], team['host'], team['name'], team['token'])
    for service in config['services']:
        insert_service_if_not_exists(db, service['id'], service['port'], service['name'])
    init_teams_points(db)
    return db


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def no_queue_dispatcher_resume_pts():
    db = prepare_test()
    flags = [gen_flag(config['misc']['flag_header'], config['misc']['flag_body_len']) for _ in range(4)]
    seeds = [gen_seed() for _ in range(4)]
    get_ts = lambda: int(time.time())
    # to simulate a non-0 initial situation
    update_points(db, team_id=0, service_id=0, pts_type='atk_pts', increment=True, timestamp=get_ts())
    update_points(db, team_id=1, service_id=0, pts_type='def_pts', increment=True, timestamp=get_ts())
    update_points(db, team_id=0, service_id=1, pts_type='sla_pts', increment=True, timestamp=get_ts())
    time.sleep(1)
    push_check(db, team_id=0, service_id=0, status=OK, timestamp=get_ts())
    push_check(db, team_id=0, service_id=0, status=ERROR, timestamp=get_ts())
    push_check(db, team_id=0, service_id=1, status=MUMBLE, timestamp=get_ts())
    push_check(db, team_id=1, service_id=0, status=CORRUPT, timestamp=get_ts())
    push_check(db, team_id=1, service_id=1, status=DOWN, timestamp=get_ts())
    push_check(db, team_id=1, service_id=1, status="invalid", timestamp=get_ts())
    i, j = 0, 0
    for flag, seed in zip(flags, seeds):
        insert_flag(db, flag, seed, round_num=0, team_id=i, service_id=j)
        i = (i + j) % 2
        j = (j + 1) % 2
    time.sleep(1)
    push_stolen_flag(db, team_token="c2e192800a294acbb2ac7dd188502edb", flag_data=flags[2], timestamp=get_ts())
    push_lost_flag(db, team_id=1, flag_data=flags[2], timestamp=get_ts())
    time.sleep(1)
    push_stolen_flag(db, team_token="c2e192800a294acbb2ac7dd188502edb", flag_data=flags[3], timestamp=get_ts())
    push_lost_flag(db, team_id=1, flag_data=flags[3], timestamp=get_ts())

    time.sleep(1)
    push_stolen_flag(db, team_token="934310005a1447b8bd52d9dcbd5c405a", flag_data=flags[0], timestamp=get_ts())
    push_lost_flag(db, team_id=0, flag_data=flags[0], timestamp=get_ts())
    time.sleep(1)
    push_stolen_flag(db, team_token="934310005a1447b8bd52d9dcbd5c405a", flag_data=flags[1], timestamp=get_ts())
    push_lost_flag(db, team_id=0, flag_data=flags[1], timestamp=get_ts())

    # simulate different last update time
    time.sleep(1)
    push_check(db, team_id=0, service_id=0, status=OK, timestamp=get_ts())

    resume_points(db)
    teams = sorted([t for t in get_teams(db)], key=lambda t: t['team_id'])
    for team in teams:
        points = {service_points['service_id']: service_points for service_points in team['points']}
        team['points'] = points
    assert teams[0]['points'][0]['sla_pts'] == 2, "An OK, an ERROR and a later OK should result in 2 points"
    assert teams[0]['points'][1]['sla_pts'] == -1, "A MUMBLE should result in -1 point"
    assert teams[1]['points'][0]['sla_pts'] == -1, "A CORRUPT should result in -1 point"
    assert teams[1]['points'][1]['sla_pts'] == -1, "A DOWN status and an invalid status should result in -1 point"
    assert teams[0]['points'][0]['atk_pts'] == 1, "A flag stolen on service 0 by team 0 should result in 1 point"
    assert teams[0]['points'][1]['atk_pts'] == 1, "A flag stolen on service 1 by team 0 should result in 1 point"
    assert teams[1]['points'][0]['atk_pts'] == 1, "A flag stolen on service 0 by team 1 should result in 1 point"
    assert teams[1]['points'][1]['atk_pts'] == 1, "A flag stolen on service 1 by team 1 should result in 1 point"
    assert teams[0]['points'][0]['def_pts'] == -1, "A flag lost on service 0 by team 0 should result in -1 point"
    assert teams[0]['points'][1]['def_pts'] == -1, "A flag lost on service 1 by team 0 should result in -1 point"
    assert teams[1]['points'][0]['def_pts'] == -1, "A flag lost on service 0 by team 1 should result in -1 point"
    assert teams[1]['points'][1]['def_pts'] == -1, "A flag lost on service 1 by team 1 should result in -1 point"
    assert teams[0]['last_pts_update'] > teams[1]['last_pts_update'], \
        f"Team 0 should have received the last pts update: {teams[0]['last_pts_update']}, {teams[1]['last_pts_update']}"


tests = [no_queue_dispatcher_resume_pts]


if __name__ == "__main__":
    for test in tests:
        log(f"Starting test: {test.__name__}")
        try:
            test()
        except AssertionError as e:
            log(f"Test {test.__name__} failed: {e.args}")
            continue
        log(f"Test {test.__name__} completed successfully")
