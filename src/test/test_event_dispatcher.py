import mongomock

from event_dispatcher import *
from mongo_utils import insert_team_if_not_exists, insert_service_if_not_exists, init_teams_points, get_teams

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
        "dispatch_frequency": 2
    }
}


def prepare_test():
    db, _ = get_db_manager(config['mongo'])
    for team in config['teams']:
        insert_team_if_not_exists(db, team['id'], team['host'], team['name'], team['token'])
    for service in config['services']:
        insert_service_if_not_exists(db, service['id'], service['port'], service['name'])
    init_teams_points(db)
    eventQueue = EventQueue()
    return db, eventQueue


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def only_sla_test():
    db, eventQueue = prepare_test()
    eventDispatcher = EventDispatcher(eventQueue, config)
    eventDispatcher.start()
    events = [{'type': EVENT_CHECK, 'status': OK, 'team': 0, 'service': 0},
              {'type': EVENT_CHECK, 'status': DOWN, 'team': 0, 'service': 0},
              {'type': EVENT_CHECK, 'status': CORRUPT, 'team': 0, 'service': 0},
              {'type': EVENT_CHECK, 'status': MUMBLE, 'team': 0, 'service': 0},
              {'type': EVENT_CHECK, 'status': ERROR, 'team': 0, 'service': 0},
              {'type': EVENT_CHECK, 'status': OK, 'team': 1, 'service': 1}]
    for event in events:
        event['timestamp'] = int(time.time())
        eventQueue.put(event)
    time.sleep(5)
    assert eventQueue.empty(), "Events should have been consumed"
    teams = sorted([t for t in get_teams(db)], key=lambda t: t['team_id'])
    team_0_points = sorted(teams[0]['points'], key=lambda p: p['service_id'])
    team_0_service_0_points = team_0_points[0]
    assert team_0_service_0_points['sla_pts'] == -2, "Incorrect update of sla pts for team 0, service 0"
    team_1_points = sorted(teams[1]['points'], key=lambda p: p['service_id'])
    team_1_service_1_points = team_1_points[1]
    assert team_1_service_1_points['sla_pts'] == 1, "Incorrect update of sla pts for team 1, service 1"
    assert teams[0]['last_pts_update'] <= teams[1]['last_pts_update'], \
        "Team 0 should have been last updated before team 1"
    eventDispatcher.stopped = True


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def invalid_status_test():
    db, eventQueue = prepare_test()
    eventDispatcher = EventDispatcher(eventQueue, config)
    eventDispatcher.start()
    events = [{'type': EVENT_CHECK, 'status': "invalid", 'team': 0, 'service': 0},
              {'type': EVENT_CHECK, 'status': OK, 'team': 0, 'service': 0}]
    for event in events:
        event['timestamp'] = int(time.time())
        eventQueue.put(event)
    time.sleep(5)
    assert eventQueue.empty(), "Events should have been consumed"
    teams = sorted([t for t in get_teams(db)], key=lambda t: t['team_id'])
    team_0_points = sorted(teams[0]['points'], key=lambda p: p['service_id'])
    team_0_service_0_points = team_0_points[0]
    assert team_0_service_0_points['sla_pts'] == 1, "Incorrect update of sla pts for team 0, service 0"
    eventDispatcher.stopped = True


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def invalid_event_test():
    db, eventQueue = prepare_test()
    eventDispatcher = EventDispatcher(eventQueue, config)
    eventDispatcher.start()
    events = [{'type': "event", 'status': OK, 'team': 0, 'service': 0},
              {'type': EVENT_CHECK, 'status': OK, 'team': 0, 'service': 0}]
    for event in events:
        event['timestamp'] = int(time.time())
        eventQueue.put(event)
    time.sleep(5)
    assert eventQueue.empty(), "Events should have been consumed"
    teams = sorted([t for t in get_teams(db)], key=lambda t: t['team_id'])
    team_0_points = sorted(teams[0]['points'], key=lambda p: p['service_id'])
    team_0_service_0_points = team_0_points[0]
    assert team_0_service_0_points['sla_pts'] == 1, "Incorrect update of sla pts for team 0, service 0"
    eventDispatcher.stopped = True


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def attack_test():
    db, eventQueue = prepare_test()
    eventDispatcher = EventDispatcher(eventQueue, config)
    eventDispatcher.start()
    events = [{'type': EVENT_ATTACK, 'team': 0, 'service': 0, 'attacked_team': 1}]
    for event in events:
        event['timestamp'] = int(time.time())
        eventQueue.put(event)
    time.sleep(5)
    assert eventQueue.empty(), "Events should have been consumed"
    teams = sorted([t for t in get_teams(db)], key=lambda t: t['team_id'])
    team_0_points = sorted(teams[0]['points'], key=lambda p: p['service_id'])
    team_0_service_0_points = team_0_points[0]
    assert team_0_service_0_points['atk_pts'] == 1, "Incorrect update of atk pts for team 0, service 0"
    team_1_points = sorted(teams[1]['points'], key=lambda p: p['service_id'])
    team_1_service_0_points = team_1_points[0]
    assert team_1_service_0_points['def_pts'] == -1, "Incorrect update of def pts for team 1, service 0"
    eventDispatcher.stopped = True


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def no_timestamp_test():
    db, eventQueue = prepare_test()
    eventDispatcher = EventDispatcher(eventQueue, config)
    eventDispatcher.start()
    events = [{'type': EVENT_ATTACK, 'team': 0, 'service': 0, 'attacked_team': 1}]
    for event in events:
        eventQueue.put(event)
    time.sleep(5)
    assert eventQueue.empty(), "Events should have been consumed"
    teams = sorted([t for t in get_teams(db)], key=lambda t: t['team_id'])
    team_0_points = sorted(teams[0]['points'], key=lambda p: p['service_id'])
    team_0_service_0_points = team_0_points[0]
    assert team_0_service_0_points['atk_pts'] == 1, "Incorrect update of atk pts for team 0, service 0"
    team_1_points = sorted(teams[1]['points'], key=lambda p: p['service_id'])
    team_1_service_0_points = team_1_points[0]
    assert team_1_service_0_points['def_pts'] == -1, "Incorrect update of def pts for team 1, service 0"
    eventDispatcher.stopped = True


@mongomock.patch(servers=(('mock.mongodb.com', 27017),))
def mixed_test():
    db, eventQueue = prepare_test()
    eventDispatcher = EventDispatcher(eventQueue, config)
    eventDispatcher.start()
    events = [{'type': EVENT_ATTACK, 'team': 0, 'service': 0, 'attacked_team': 1},
              {'type': EVENT_CHECK, 'status': OK, 'team': 0, 'service': 0},
              {'type': EVENT_CHECK, 'status': DOWN, 'team': 0, 'service': 0},
              {'type': EVENT_CHECK, 'status': CORRUPT, 'team': 0, 'service': 0},
              {'type': EVENT_CHECK, 'status': MUMBLE, 'team': 0, 'service': 0},
              {'type': EVENT_CHECK, 'status': ERROR, 'team': 0, 'service': 0},
              {'type': EVENT_CHECK, 'status': OK, 'team': 1, 'service': 1}]
    for event in events:
        event['timestamp'] = int(time.time())
        eventQueue.put(event)
    time.sleep(5)
    assert eventQueue.empty(), "Events should have been consumed"
    teams = sorted([t for t in get_teams(db)], key=lambda t: t['team_id'])
    team_0_points = sorted(teams[0]['points'], key=lambda p: p['service_id'])
    team_0_service_0_points = team_0_points[0]
    assert team_0_service_0_points['atk_pts'] == 1, "Incorrect update of atk pts for team 0, service 0"
    assert team_0_service_0_points['def_pts'] == 0, "Spurious update of def pts for team 0, service 0"
    assert team_0_service_0_points['sla_pts'] == -2, "Incorrect update of sla pts for team 0, service 0"
    team_0_service_1_points = team_0_points[1]
    assert team_0_service_1_points['atk_pts'] == 0, "Spurious update of atk pts for team 0, service 1"
    assert team_0_service_1_points['def_pts'] == 0, "Spurious update of def pts for team 0, service 1"
    assert team_0_service_1_points['sla_pts'] == 0, "Spurious update of sla pts for team 0, service 1"
    team_1_points = sorted(teams[1]['points'], key=lambda p: p['service_id'])
    team_1_service_0_points = team_1_points[0]
    assert team_1_service_0_points['atk_pts'] == 0, "Spurious update of atk pts for team 1, service 0"
    assert team_1_service_0_points['def_pts'] == -1, "Incorrect update of def pts for team 1, service 0"
    assert team_1_service_0_points['sla_pts'] == 0, "Spurious update of sla pts for team 1, service 0"
    team_1_service_1_points = team_1_points[1]
    assert team_1_service_1_points['atk_pts'] == 0, "Spurious update of atk pts for team 1, service 1"
    assert team_1_service_1_points['def_pts'] == 0, "Spurious update of def pts for team 1, service 1"
    assert team_1_service_1_points['sla_pts'] == 1, "Incorrect update of sla pts for team 1, service 1"
    assert teams[0]['last_pts_update'] <= teams[1]['last_pts_update'], \
        "Team 0 should have been last updated before team 1"
    eventDispatcher.stopped = True


tests = [only_sla_test, invalid_status_test, invalid_event_test, attack_test, no_timestamp_test, mixed_test]

if __name__ == "__main__":
    for test in tests:
        log(f"Starting test: {test.__name__}")
        try:
            test()
        except AssertionError as e:
            log(f"Test {test.__name__} failed: {e.args}")
            continue
        log(f"Test {test.__name__} completed successfully")
