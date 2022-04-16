import mongomock
import time
import datetime

from services import Services
import project_utils
from checker_lib import OK, CORRUPT
from mongo_utils import get_db_manager, get_flag_for_round


config = {
    "teams": [
        {"id": 0, "host": "10.0.0.1", "name": "first", "token": "c2e192800a294acbb2ac7dd188502edb"},
        {"id": 1, "host": "10.0.0.2", "name": "second", "token": "934310005a1447b8bd52d9dcbd5c405a"}
    ],
    "services": [
        {"id": 0, "port": 7331, "name": "example_0", "checker": "volume/example/example_checker_0.py"},
        {"id": 1, "port": 7332, "name": "example_1", "checker": "volume/example/example_checker_1.py"},
        {"id": 2, "port": 7333, "name": "example_2", "checker": "volume/example/example_checker_0.py"}
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
        "base_score": 1000,
        "dispatch_frequency": 2
    }
}


def to_time_str(timestamp: int):
    fmt = "%d %b %Y %H:%M:%S"
    return datetime.datetime.fromtimestamp(timestamp).strftime(fmt)


def check_team_stats(team, round_num, expected_overall_score, n_checks: list):
    # this function is to make some refactoring among different tests, it doesn't check all the stats
    i = round_num
    for service_name in team['service_status']:
        if service_name == 'example_0' or service_name == 'example_2':
            assert team['service_status'][service_name] == OK, \
                f"Incorrect service status for team {team['name']}, service {service_name} at round {i}"
            assert team['points'][service_name]['sla_pts'] == n_checks[i], \
                f"Incorrect sla_pts for team {team['name']}, service {service_name} at round {i}"
        elif service_name == 'example_1':
            assert team['service_status'][service_name] == CORRUPT, \
                f"Incorrect service status for team {team['name']}, service {service_name} at round {i}"
            assert team['points'][service_name]['sla_pts'] == -1 * n_checks[i], \
                f"Incorrect sla_pts for team {team['name']}, service {service_name} at round {i}"
    assert team['overall_score'] == expected_overall_score, \
        f"Incorrect overall score for team {team['name']} at round {i}"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def only_checkers_test():
    config['misc']['start_time'] = to_time_str(int(time.time()) + 3)
    config['misc']['end_time'] = to_time_str(int(time.time()) + 35)
    config['misc']['round_time'] = 9
    config['misc']['dispatch_frequency'] = 0.01
    project_utils.init_or_resume_mongo(config)
    adServices = Services(config)
    assert adServices.checkScheduler.maxRounds == 3, "Incorrect computation of number of rounds"
    teams = adServices.scoreboardCache.getStats()
    for team in teams:
        assert team['overall_score'] == adServices.scoreboardCache.baseScore, \
            f"At start, all scores should be equal to base score"
        assert len(team['service_status']) == 0, "At start, services should not have any status"
    time.sleep(3)
    n_checks = [0, 1, 3, 6]
    for i in range(1, 4):
        time.sleep(10)
        teams = adServices.scoreboardCache.getStats()
        for team in teams:
            # 2 OK and 1 CORRUPT for each round, plus the rounds in flagLifetime window
            expected_overall_score = n_checks[i] * adServices.scoreboardCache.slaWeight
            expected_overall_score += adServices.scoreboardCache.baseScore
            check_team_stats(team, round_num=i, expected_overall_score=expected_overall_score, n_checks=n_checks)
    time.sleep(1)
    assert not adServices.checkScheduler.is_alive(), "Check scheduler should have terminated"
    adServices.stop()


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def check_and_flag_submit_test():
    config['misc']['start_time'] = to_time_str(int(time.time()) + 3)
    config['misc']['end_time'] = to_time_str(int(time.time()) + 35)
    config['misc']['round_time'] = 9
    config['misc']['dispatch_frequency'] = 0.01
    project_utils.init_or_resume_mongo(config)
    db, _ = get_db_manager(config['mongo'])
    token = "c2e192800a294acbb2ac7dd188502edb"
    adServices = Services(config)
    assert adServices.checkScheduler.maxRounds == 3, "Incorrect computation of number of rounds"
    teams = adServices.scoreboardCache.getStats()
    for team in teams:
        assert team['overall_score'] == adServices.scoreboardCache.baseScore, \
            f"At start, all scores should be equal to base score"
        assert len(team['service_status']) == 0, "At start, services should not have any status"
    time.sleep(3)
    n_checks = [0, 1, 3, 6]
    for i in range(1, 4):
        time.sleep(9)
        flag = get_flag_for_round(db, round_num=i, team_id=1, service_id=0)['flag_data']
        adServices.submissionService.submitFlags(team_token=token, flags=[flag])
        time.sleep(1)
        teams = adServices.scoreboardCache.getStats()
        for team in teams:
            sla_score = n_checks[i] * adServices.scoreboardCache.slaWeight
            atk_score = i * adServices.scoreboardCache.atkWeight if team['name'] == 'first' else 0
            def_score = -i * adServices.scoreboardCache.defWeight if team['name'] == 'second' else 0
            expected_overall_score = sla_score + atk_score + def_score
            expected_overall_score += adServices.scoreboardCache.baseScore
            check_team_stats(team, round_num=i, expected_overall_score=expected_overall_score, n_checks=n_checks)
            if team['name'] == 'first':
                assert team['points']['example_0']['atk_pts'] == i, \
                    f"Incorrect atk pts for team {team['name']} on example_0"
                assert team['points']['example_1']['atk_pts'] == 0, \
                    f"Incorrect atk pts for team {team['name']} on example_1"
            elif team['name'] == 'second':
                assert team['points']['example_0']['def_pts'] == -i, \
                    f"Incorrect def pts for team {team['name']} on example_0"
                assert team['points']['example_1']['def_pts'] == 0, \
                    f"Incorrect def pts for team {team['name']} on example_1"
    time.sleep(1)
    assert not adServices.checkScheduler.is_alive(), "Check scheduler should have terminated"
    adServices.stop()


tests = [only_checkers_test, check_and_flag_submit_test]


if __name__ == "__main__":
    for test in tests:
        project_utils.log(f"Starting test: {test.__name__}")
        try:
            test()
        except AssertionError as e:
            project_utils.log(f"Test {test.__name__} failed: {e.args}")
            # in this case I have to break, because otherwise threads will continue their execution
            break
        project_utils.log(f"Test {test.__name__} completed successfully")
