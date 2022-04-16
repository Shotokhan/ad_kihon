import mongomock
import time
import threading

from scoreboard_cache import ScoreboardCache, ConcurrentUpdateException
from mongo_utils import get_db_manager, insert_team_if_not_exists, insert_service_if_not_exists, init_teams_points, \
    insert_flag, push_stolen_flag, push_lost_flag, push_check, resume_points
from checker_lib import gen_flag, gen_seed, OK, CORRUPT
from project_utils import log

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


def prepare_test():
    db, _ = get_db_manager(config['mongo'])
    for team in config['teams']:
        insert_team_if_not_exists(db, team['id'], team['host'], team['name'], team['token'])
    for service in config['services']:
        insert_service_if_not_exists(db, service['id'], service['port'], service['name'])
    init_teams_points(db)
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
    return db, flags


def util_push_attack(db, flags, index):
    if not (0 <= index <= 3):
        log("Error: provide an index in [0, 3]")
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
def zero_pts_anti_leak_test():
    db, flags = prepare_test()
    scoreboardCache = ScoreboardCache(config)
    resume_points(db)
    teams = scoreboardCache.getStats()
    for team in teams:
        assert team['overall_score'] == scoreboardCache.baseScore, "Each team's score should be equal to base score"
        assert len(team['service_status']) == 0, "There shouldn't be any check yet"
        assert team['points']['example_0']['atk_pts'] == 0, "atk_pts should be 0"
        assert team['points']['example_0']['def_pts'] == 0, "def_pts should be 0"
        assert team['points']['example_0']['sla_pts'] == 0, "sla_pts should be 0"
        assert 'stolen_flags' not in team, "Stats should not include stolen flags"
        assert 'lost_flags' not in team, "Stats should not include lost flags"
        assert 'checks' not in team, "Stats should not include checks"
        assert 'team_id' not in team, "Stats should not include team id"
        assert 'token' not in team, "Stats should not include token"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def update_latency_test():
    db, flags = prepare_test()
    scoreboardCache = ScoreboardCache(config)
    get_ts = lambda: int(time.time())
    push_check(db, team_id=0, service_id=0, status=OK, timestamp=get_ts())
    push_check(db, team_id=0, service_id=1, status=OK, timestamp=get_ts())
    push_check(db, team_id=1, service_id=0, status=CORRUPT, timestamp=get_ts())
    push_check(db, team_id=1, service_id=1, status=CORRUPT, timestamp=get_ts())
    resume_points(db)
    teams = scoreboardCache.getStats()
    for team in teams:
        assert team['overall_score'] == scoreboardCache.baseScore, "Each team's score should still be base score"
        assert len(team['service_status']) == 0, "Service status should not have been updated yet"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def sla_pts_and_status_test():
    db, flags = prepare_test()
    scoreboardCache = ScoreboardCache(config)
    get_ts = lambda: int(time.time())
    push_check(db, team_id=0, service_id=0, status=OK, timestamp=get_ts())
    push_check(db, team_id=0, service_id=1, status=OK, timestamp=get_ts())
    push_check(db, team_id=1, service_id=0, status=CORRUPT, timestamp=get_ts())
    push_check(db, team_id=1, service_id=1, status=CORRUPT, timestamp=get_ts())
    resume_points(db)
    time.sleep(scoreboardCache.updateLatency)
    teams = scoreboardCache.getStats()
    for team in teams:
        if team['name'] == 'first':
            assert team['overall_score'] == scoreboardCache.baseScore + 2 * scoreboardCache.slaWeight, \
                f"First team overall score is {team['overall_score']}, but should be {2 * scoreboardCache.slaWeight}"
            assert team['points']['example_0']['sla_pts'] == 1, "sla_pts of service 0 should be 1"
            assert team['points']['example_1']['sla_pts'] == 1, "sla_pts of service 1 should be 1"
            assert team['service_status']['example_0'] == OK, "Service status should be OK"
            assert team['service_status']['example_1'] == OK, "Service status should be OK"
        elif team['name'] == 'second':
            assert team['overall_score'] == scoreboardCache.baseScore - 2 * scoreboardCache.slaWeight, \
                f"Second team overall score is {team['overall_score']}, but should be {-2 * scoreboardCache.slaWeight}"
            assert team['points']['example_0']['sla_pts'] == -1, "sla_pts of service 0 should be -1"
            assert team['points']['example_1']['sla_pts'] == -1, "sla_pts of service 1 should be -1"
            assert team['service_status']['example_0'] == CORRUPT, "Service status should be CORRUPT"
            assert team['service_status']['example_1'] == CORRUPT, "Service status should be CORRUPT"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def atk_and_def_pts_test():
    db, flags = prepare_test()
    scoreboardCache = ScoreboardCache(config)
    for i in range(2):
        util_push_attack(db, flags, i)
    resume_points(db)
    time.sleep(scoreboardCache.updateLatency)
    teams = scoreboardCache.getStats()
    for team in teams:
        if team['name'] == 'first':
            assert team['overall_score'] == scoreboardCache.baseScore - 2 * scoreboardCache.defWeight, \
                f"First team overall score is {team['overall_score']}, but should be {-2 * scoreboardCache.defWeight}"
            assert team['points']['example_0']['def_pts'] == -1, "def_pts of service 0 should be -1"
            assert team['points']['example_1']['def_pts'] == -1, "def_pts of service 1 should be -1"
        elif team['name'] == 'second':
            assert team['overall_score'] == scoreboardCache.baseScore + 2 * scoreboardCache.atkWeight, \
                f"First team overall score is {team['overall_score']}, but should be {2 * scoreboardCache.atkWeight}"
            assert team['points']['example_0']['atk_pts'] == 1, "atk_pts of service 0 should be 1"
            assert team['points']['example_1']['atk_pts'] == 1, "atk_pts of service 1 should be 1"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def mixed_pts_test():
    db, flags = prepare_test()
    scoreboardCache = ScoreboardCache(config)
    for i in range(2):
        util_push_attack(db, flags, i)
    get_ts = lambda: int(time.time())
    push_check(db, team_id=0, service_id=0, status=OK, timestamp=get_ts())
    push_check(db, team_id=0, service_id=1, status=OK, timestamp=get_ts())
    push_check(db, team_id=1, service_id=0, status=CORRUPT, timestamp=get_ts())
    push_check(db, team_id=1, service_id=1, status=CORRUPT, timestamp=get_ts())
    resume_points(db)
    time.sleep(scoreboardCache.updateLatency)
    teams = scoreboardCache.getStats()
    for team in teams:
        if team['name'] == 'first':
            expected_score = scoreboardCache.baseScore + 2 * scoreboardCache.slaWeight - 2 * scoreboardCache.defWeight
            assert team['overall_score'] == expected_score, \
                f"First team overall score is {team['overall_score']}, but should be {expected_score}"
            assert team['points']['example_0']['sla_pts'] == 1, "sla_pts of service 0 should be 1"
            assert team['points']['example_1']['sla_pts'] == 1, "sla_pts of service 1 should be 1"
            assert team['points']['example_0']['def_pts'] == -1, "def_pts of service 0 should be -1"
            assert team['points']['example_1']['def_pts'] == -1, "def_pts of service 1 should be -1"
            assert team['service_status']['example_0'] == OK, "Service status should be OK"
            assert team['service_status']['example_1'] == OK, "Service status should be OK"
        elif team['name'] == 'second':
            expected_score = scoreboardCache.baseScore - 2 * scoreboardCache.slaWeight + 2 * scoreboardCache.atkWeight
            assert team['overall_score'] == expected_score, \
                f"Second team overall score is {team['overall_score']}, but should be {expected_score}"
            assert team['points']['example_0']['sla_pts'] == -1, "sla_pts of service 0 should be -1"
            assert team['points']['example_1']['sla_pts'] == -1, "sla_pts of service 1 should be -1"
            assert team['points']['example_0']['atk_pts'] == 1, "atk_pts of service 0 should be 1"
            assert team['points']['example_1']['atk_pts'] == 1, "atk_pts of service 1 should be 1"
            assert team['service_status']['example_0'] == CORRUPT, "Service status should be CORRUPT"
            assert team['service_status']['example_1'] == CORRUPT, "Service status should be CORRUPT"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def concurrent_get_stats_test():
    db, flags = prepare_test()
    scoreboardCache = ScoreboardCache(config)
    n_checks = 100
    timestamp = int(time.time())
    for i in range(n_checks):
        push_check(db, team_id=0, service_id=0, status=OK, timestamp=timestamp + i)
    resume_points(db)
    time.sleep(scoreboardCache.updateLatency)
    backgroundGetStats = threading.Thread(target=scoreboardCache.getStats)
    backgroundGetStats.start()
    error = False
    try:
        scoreboardCache.getStats(wait=False)
    except ConcurrentUpdateException:
        error = True
    assert error or not scoreboardCache.mutex.locked(), \
        "The concurrent update with 'wait' set to False should throw an exception, or the mutex should be unlocked"
    while scoreboardCache.mutex.locked():
        pass
    teams = scoreboardCache.getStats(wait=False)
    for team in teams:
        if team['name'] == 'first':
            expected_score = scoreboardCache.baseScore + n_checks * scoreboardCache.slaWeight
            assert team['overall_score'] == expected_score, \
                f"First team overall score is {team['overall_score']}, but should be {expected_score}"
        elif team['name'] == 'second':
            assert team['overall_score'] == scoreboardCache.baseScore, \
                f"First team overall score is {team['overall_score']}, but should be equal to base score"


tests = [zero_pts_anti_leak_test, update_latency_test, sla_pts_and_status_test, atk_and_def_pts_test,
         mixed_pts_test, concurrent_get_stats_test]

if __name__ == "__main__":
    for test in tests:
        log(f"Starting test: {test.__name__}")
        try:
            test()
        except AssertionError as e:
            log(f"Test {test.__name__} failed: {e.args}")
            continue
        log(f"Test {test.__name__} completed successfully")
