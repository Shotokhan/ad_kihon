import mongomock
import datetime

from submission_service import *
from mongo_utils import get_db_manager, insert_team_if_not_exists, insert_service_if_not_exists, insert_flag, \
    check_stolen_flag
from event_queue import EventQueue, EVENT_ATTACK
from checker_lib import gen_flag, gen_seed
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
        "max_flags_per_submission": 20
    }
}

FIRST_ROUND = 1


def to_time_str(timestamp: int):
    fmt = "%d %b %Y %H:%M:%S"
    return datetime.datetime.fromtimestamp(timestamp).strftime(fmt)


def prepare_test():
    db, _ = get_db_manager(config['mongo'])
    for team in config['teams']:
        insert_team_if_not_exists(db, team['id'], team['host'], team['name'], team['token'])
    for service in config['services']:
        insert_service_if_not_exists(db, service['id'], service['port'], service['name'])
    flags = [gen_flag(config['misc']['flag_header'], config['misc']['flag_body_len']) for _ in range(4)]
    seeds = [gen_seed() for _ in range(4)]
    i, j = 0, 0
    for flag, seed in zip(flags, seeds):
        insert_flag(db, flag, seed, round_num=FIRST_ROUND, team_id=i, service_id=j)
        i = (i + j) % 2
        j = (j + 1) % 2
    """
    flag[0] owned by team 0, service 0
    flag[1] owned by team 0, service 1
    flag[2] owned by team 1, service 0
    flag[3] owned by team 1, service 1
    """
    eventQueue = EventQueue()
    config['misc']['start_time'] = to_time_str(int(time.time()))
    config['misc']['end_time'] = to_time_str(int(time.time()) + 300)
    return db, eventQueue, flags


def check_lost_flag(db, team_id, flag_data):
    # assumes that flag_data is in some flag document
    col = db.get_collection("team")
    team = col.find_one({"team_id": team_id, "lost_flags.flag_data": flag_data})
    if team is None:
        raise NotExistentDocument
    return team


class MockCheckScheduler:
    def __init__(self, round_num):
        self.roundNum = round_num


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def invalid_token_test():
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    token = "invalid"
    error = False
    try:
        submissionService.submitFlags(token, flags)
    except InvalidToken:
        error = True
    assert error, "InvalidToken exception should have been thrown"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def common_flags_test():
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    token = "c2e192800a294acbb2ac7dd188502edb"
    msg = submissionService.submitFlags(token, flags)
    assert msg['num_accepted'] == 2, "There should be 2 accepted flags"
    assert msg['num_self_flags'] == 2, "There should be 2 self flags"
    assert msg['num_invalid'] == 0, "All flags should be valid"
    assert msg['num_already_submitted'] == 0, "There shouldn't be already submitted flags"
    assert msg['num_discarded'] == 0, "Flag list limit shouldn't have been exceeded"
    assert msg['num_old'] == 0, "All flags should be new"
    events = []
    while not eventQueue.empty():
        event = eventQueue.get()
        assert event['type'] == EVENT_ATTACK, "Each event should be an attack"
        assert event['team'] == 0, "Submitter team should have id 0"
        assert event['attacked_team'] == 1, "Attacked team should have id 1"
        assert event['service'] in [0, 1], "Service id should be among [0, 1]"
        events.append(event)
    assert len(events) == 2, "There should be 2 events"
    for i in range(2):
        error = False
        try:
            check_stolen_flag(db, token, flags[i])
        except NotExistentDocument:
            error = True
        assert error, f"Flag {i} should not have been stolen"
        error = False
        try:
            check_lost_flag(db, team_id=1, flag_data=flags[i])
        except NotExistentDocument:
            error = True
        assert error, f"Flag {i} should not have been lost"
    check_stolen_flag(db, token, flags[2])
    check_stolen_flag(db, token, flags[3])
    check_lost_flag(db, team_id=1, flag_data=flags[2])
    check_lost_flag(db, team_id=1, flag_data=flags[3])
    _, service_mutex = submissionService.getTeamMutexes(token)
    assert not service_mutex.locked(), f"Service mutex for team with token {token} should have been released"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def not_existent_flag_test():
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    token = "c2e192800a294acbb2ac7dd188502edb"
    sub_flags = [gen_flag(config['misc']['flag_header'], config['misc']['flag_body_len'])]
    msg = submissionService.submitFlags(token, sub_flags)
    assert msg['num_invalid'] == 1, "Submitted flag should be invalid"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def invalid_flag_pattern_test():
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    token = "c2e192800a294acbb2ac7dd188502edb"
    sub_flags = ['{"$eq": flag_data}']
    msg = submissionService.submitFlags(token, sub_flags)
    assert msg['num_invalid'] == 1, "Submitted flag should be invalid"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def old_flag_test():
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=config['misc']['flag_lifetime']+FIRST_ROUND+1)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    token = "c2e192800a294acbb2ac7dd188502edb"
    sub_flags = [flags[2]]
    msg = submissionService.submitFlags(token, sub_flags)
    assert msg['num_old'] == 1, "Submitted flag should be old"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def already_submitted_flag_test():
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    token = "c2e192800a294acbb2ac7dd188502edb"
    sub_flags = [flags[2]]
    msg = submissionService.submitFlags(token, sub_flags)
    assert msg['num_accepted'] == 1, "Submitted flag should have been accepted"
    # this also tests the release of the rate limit mutex
    time.sleep(config['misc']['rate_limit_seconds'])
    msg = submissionService.submitFlags(token, sub_flags)
    assert msg['num_already_submitted'] == 1, "Submitted flag should have been rejected because already submitted"
    assert msg['num_accepted'] == 0, "Number of accepted flags should be 0"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def rate_limit_test():
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    token = "c2e192800a294acbb2ac7dd188502edb"
    sub_flags = [flags[2]]
    submissionService.submitFlags(token, sub_flags)
    error = False
    try:
        submissionService.submitFlags(token, sub_flags)
    except RateLimitExceeded:
        error = True
    assert error, "Rate limit should block the submission"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def multiple_teams_with_rate_limit_test():
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    tokens = ["c2e192800a294acbb2ac7dd188502edb", "934310005a1447b8bd52d9dcbd5c405a"]
    for token in tokens:
        msg = submissionService.submitFlags(token, flags)
        assert msg['num_accepted'] == 2, f"There should be 2 accepted flags for team with token {token}"
        error = False
        try:
            submissionService.submitFlags(token, flags)
        except RateLimitExceeded:
            error = True
        assert error, f"Rate limit should block the submission of team with token {token}"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def service_mutex_dynamic_rate_limit_test():
    # it would be good to also test stacked increase/decrease, but it's hard because of thread scheduling
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    # you may have to tune the following parameters on your system to make the test pass,
    # it is not deterministic (because of thread scheduling)
    rate_sec = 0.0000001
    sleep_time_rate_limit_mutex_release = 0.01
    submissionService.rateLimitSeconds = rate_sec
    submissionService.roundTime = 5
    submissionService.maxFlagsPerSubmission = 300
    token = "c2e192800a294acbb2ac7dd188502edb"
    sub_flags = [flags[2]] + [gen_flag(config['misc']['flag_header'], config['misc']['flag_body_len'])
                              for _ in range(submissionService.maxFlagsPerSubmission)]
    backgroundSubmit = threading.Thread(target=submissionService.submitFlags, args=(token, sub_flags))
    backgroundSubmit.start()
    time.sleep(sleep_time_rate_limit_mutex_release)
    error = False
    try:
        submissionService.submitFlags(token, sub_flags)
    except ServiceBusy:
        error = True
    assert error, "Rate limit should block the submission, thanks to service mutex"
    time.sleep(1)
    assert submissionService.rateLimitSeconds == rate_sec * 2, "Rate limit seconds should have been temporary increased"
    time.sleep(submissionService.roundTime)
    assert submissionService.rateLimitSeconds == rate_sec, "Rate limit seconds should have been decreased"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def reliability_handler_test():
    # this test is about the scheduled release of the service mutex, in case the thread crashes
    # we're not able to reproduce a thread crash here, so we'll use acquireServiceMutex method
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    round_time = 1
    submissionService.roundTime = round_time
    token = "c2e192800a294acbb2ac7dd188502edb"
    _, service_mutex = submissionService.getTeamMutexes(token)
    reliability_handler: threading.Timer = submissionService.acquireServiceMutex(service_mutex)
    assert service_mutex.locked(), "Service mutex should be locked"
    assert reliability_handler.is_alive(), "Reliability handler should be alive"
    time.sleep(round_time * 2)
    assert not service_mutex.locked(), "Service mutex should have been automatically unlocked"
    assert not reliability_handler.is_alive(), "Reliability handler should have terminated its job"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def discard_flags_test():
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    submissionService.maxFlagsPerSubmission = 1
    token = "c2e192800a294acbb2ac7dd188502edb"
    msg = submissionService.submitFlags(token, flags)
    assert msg['num_discarded'] == 3, "3 flags should have been discarded"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def submit_before_start_test():
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    config['misc']['start_time'] = to_time_str(int(time.time()) + 60)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    submissionService.maxFlagsPerSubmission = 1
    token = "c2e192800a294acbb2ac7dd188502edb"
    error = False
    try:
        submissionService.submitFlags(token, flags)
    except OutOfTimeWindow:
        error = True
    assert error, "Submission before start time should be rejected"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def submit_after_end_test():
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    config['misc']['start_time'] = to_time_str(int(time.time()) - 30)
    config['misc']['end_time'] = to_time_str(int(time.time()) - 10)
    submissionService = SubmissionService(eventQueue, config, checkScheduler)
    submissionService.maxFlagsPerSubmission = 1
    token = "c2e192800a294acbb2ac7dd188502edb"
    error = False
    try:
        submissionService.submitFlags(token, flags)
    except OutOfTimeWindow:
        error = True
    assert error, "Submission after end time should be rejected"


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def start_after_end_test():
    db, eventQueue, flags = prepare_test()
    checkScheduler = MockCheckScheduler(round_num=FIRST_ROUND)
    config['misc']['start_time'] = to_time_str(int(time.time()))
    config['misc']['end_time'] = to_time_str(int(time.time()) - 10)
    error = False
    try:
        SubmissionService(eventQueue, config, checkScheduler)
    except InitServiceError:
        error = True
    assert error, "Submission service should throw error if start time is after end time"


tests = [invalid_token_test, common_flags_test, not_existent_flag_test, invalid_flag_pattern_test, old_flag_test,
         already_submitted_flag_test, rate_limit_test, multiple_teams_with_rate_limit_test,
         service_mutex_dynamic_rate_limit_test, reliability_handler_test, discard_flags_test,
         submit_before_start_test, submit_after_end_test, start_after_end_test]


if __name__ == "__main__":
    for test in tests:
        log(f"Starting test: {test.__name__}")
        try:
            test()
        except AssertionError as e:
            log(f"Test {test.__name__} failed: {e.args}")
            continue
        log(f"Test {test.__name__} completed successfully")
