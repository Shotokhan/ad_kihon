import mongomock

from check_scheduler import *
from mongo_utils import insert_team_if_not_exists, insert_service_if_not_exists, get_teams, get_services
from checker_lib import *

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
    queue = EventQueue()
    return db, queue


def sanity_check(db, checkScheduler, queue):
    # test on teams
    time.sleep(checkScheduler.roundTime)
    n_checks_for_service = sum([i+1 for i in range(checkScheduler.flagLifetime)]) + \
                           (checkScheduler.flagLifetime + 1) * (checkScheduler.maxRounds - checkScheduler.flagLifetime)
    possible_status = [OK, MUMBLE, CORRUPT, DOWN, ERROR]
    teams = get_teams(db)
    services = get_services(db)
    for team in teams:
        for service in services:
            checks_team_i_service_j = [i for i in
                                       filter(lambda c: c['service_id'] == service['service_id'], team['checks'])]
            assert len(checks_team_i_service_j) == n_checks_for_service, \
                f"Each team should have received {n_checks_for_service} checks for each service"
            for check in checks_team_i_service_j:
                assert check['status'] in possible_status, "Check status should be among valid statuses"
    # test on events
    events = []
    while not queue.empty():
        events.append(queue.get())
    for team in teams:
        for service in services:
            events_team_i_service_j = [i for i in filter(
                lambda e: e['team'] == team['team_id'] and e['service'] == service['service_id'], events)]
            assert len(events_team_i_service_j) == n_checks_for_service, \
                f"There should be {n_checks_for_service} check events for each service and for each team"
            for event in events_team_i_service_j:
                assert event['status'] in possible_status, "Event status should be among valid statuses"
                assert event['type'] == EVENT_CHECK, "Event type should be EVENT_CHECK"
    # test on flags
    n_flags = checkScheduler.maxRounds * len(checkScheduler.teams) * len(checkScheduler.services)
    col = db.get_collection("flag")
    flags = [f for f in col.find()]
    for round_num in range(1, checkScheduler.maxRounds + 1):
        for team in teams:
            team_id = team['team_id']
            for service in services:
                service_id = service['service_id']
                flags_round_i_team_j_service_k = [i for i in filter(
                    lambda f: f['round_num'] == round_num and f['team_id'] == team_id and f['service_id'] == service_id,
                    flags
                )]
                assert len(flags_round_i_team_j_service_k) == 1, \
                    f"There should be 1 flag for team {team_id}, service {service_id} at round {round_num}"
    assert len(flags) == n_flags, f"Total num of flags should be {n_flags}"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def common_test():
    db, queue = prepare_test()
    now = datetime.datetime.now()
    fmt = "%d %b %Y %H:%M:%S"
    config['misc']['start_time'] = (now + datetime.timedelta(seconds=10)).strftime(fmt)
    config['misc']['end_time'] = (now + datetime.timedelta(seconds=100)).strftime(fmt)
    # note: roundTime=9 is too fast for a real game
    config['misc']['round_time'] = 9
    checkScheduler = CheckScheduler(queue, config)
    checkScheduler.start()
    checkScheduler.join()
    sanity_check(db, checkScheduler, queue)


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def resume_test():
    # note: this test assumes that the check scheduler and the checkers have completed all pending operations
    # before being stopped; it also assumes that the resume is immediate
    db, queue = prepare_test()
    now = datetime.datetime.now()
    fmt = "%d %b %Y %H:%M:%S"
    config['misc']['start_time'] = (now + datetime.timedelta(seconds=10)).strftime(fmt)
    config['misc']['end_time'] = (now + datetime.timedelta(seconds=100)).strftime(fmt)
    # note: roundTime=9 is too fast for a real game
    config['misc']['round_time'] = 9
    checkScheduler = CheckScheduler(queue, config)
    checkScheduler.start()
    time.sleep(35)
    checkScheduler.stopped = True
    checkScheduler.join()
    resumeScheduler = CheckScheduler(queue, config)
    resumeScheduler.start()
    resumeScheduler.join()
    sanity_check(db, resumeScheduler, queue)


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def after_end_test():
    db, queue = prepare_test()
    now = datetime.datetime.now()
    fmt = "%d %b %Y %H:%M:%S"
    config['misc']['start_time'] = (now - datetime.timedelta(seconds=100)).strftime(fmt)
    config['misc']['end_time'] = (now - datetime.timedelta(seconds=10)).strftime(fmt)
    config['misc']['round_time'] = 9
    checkScheduler = CheckScheduler(queue, config)
    checkScheduler.start()
    time.sleep(1)
    assert checkScheduler.is_alive() is False, "The scheduler should not be alive"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def start_time_after_end_time_test():
    db, queue = prepare_test()
    now = datetime.datetime.now()
    fmt = "%d %b %Y %H:%M:%S"
    config['misc']['start_time'] = (now + datetime.timedelta(seconds=100)).strftime(fmt)
    config['misc']['end_time'] = (now + datetime.timedelta(seconds=10)).strftime(fmt)
    config['misc']['round_time'] = 9
    exception = False
    try:
        checkScheduler = CheckScheduler(queue, config)
        checkScheduler.start()
        checkScheduler.join()
    except InitSchedulerError:
        exception = True
    assert exception, "The scheduler should not start"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def stop_test():
    db, queue = prepare_test()
    now = datetime.datetime.now()
    fmt = "%d %b %Y %H:%M:%S"
    config['misc']['start_time'] = (now + datetime.timedelta(seconds=10)).strftime(fmt)
    config['misc']['end_time'] = (now + datetime.timedelta(seconds=100)).strftime(fmt)
    # note: roundTime=9 is too fast for a real game
    config['misc']['round_time'] = 9
    checkScheduler = CheckScheduler(queue, config)
    checkScheduler.start()
    time.sleep(30)
    checkScheduler.stopped = True
    checkScheduler.join()
    assert checkScheduler.roundNum == 2, "The scheduler should run the pending job, then stop itself"


tests = [common_test, resume_test, after_end_test, start_time_after_end_time_test, stop_test]

if __name__ == "__main__":
    for test in tests:
        log(f"Starting test: {test.__name__}")
        try:
            test()
        except AssertionError as e:
            log(f"Test {test.__name__} failed: {e.args}")
            continue
        log(f"Test {test.__name__} completed successfully")
