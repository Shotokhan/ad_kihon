import threading
from dateutil import parser
import datetime
from importlib import import_module
import random
import time
import schedule
import math

from event_queue import EventQueue, EVENT_CHECK
from mongo_utils import get_db_manager, push_check, insert_flag, get_flag_for_round, AlreadyExistentFlagOrSeed, NotExistentDocument
import checker_lib
from project_utils import log


class InitSchedulerError(Exception):
    pass


class CheckScheduler(threading.Thread):
    def __init__(self, eventQueue: EventQueue, config: dict):
        super().__init__()
        self.eventQueue = eventQueue
        self.roundNum = 0
        _, mongo_client = get_db_manager(config['mongo'])
        self.mongoClient = mongo_client
        self.mongoConfig = config['mongo']
        # warning: the parser tries to infer data format; use a non ambiguous format
        # see https://pypi.org/project/python-dateutil/
        self.startTime = parser.parse(config['misc']['start_time'])
        self.endTime = parser.parse(config['misc']['end_time'])
        if self.endTime <= self.startTime:
            log("Error: end time should be greater than start time")
            raise InitSchedulerError
        self.roundTime = config['misc']['round_time']
        self.maxRounds = (self.endTime - self.startTime) // datetime.timedelta(seconds=self.roundTime)
        self.flagHeader = config['misc']['flag_header']
        self.flagBodyLen = config['misc']['flag_body_len']
        self.flagLifetime = config['misc']['flag_lifetime']
        self.stopped = False
        self.teams = {team['id']: team for team in config['teams']}
        self.services = {service['id']: service for service in config['services']}
        self.checkerMods = {service_id: import_module(self.filePathToModuleName(self.services[service_id]['checker']))
                            for service_id in self.services.keys()}
        self.checkers = {team_id: {service_id: self.checkerMods[service_id].Checker(
                team=self.teams[team_id],
                service=self.services[service_id])
                for service_id in self.services.keys()} for team_id in self.teams.keys()}

    @staticmethod
    def filePathToModuleName(checkerPath: str):
        checkerPath = checkerPath.split('.py')[0]
        checkerPath = checkerPath.replace('/', '.')
        return checkerPath

    @staticmethod
    def runChecker(eventQueue: EventQueue, mongoConfig, mongoClient, checker, flag, seed, roundTime, isPrevious=False):
        timeSlice = roundTime // 3
        event = {"type": EVENT_CHECK, "status": "unset", "team": checker.team['id'], "service": checker.service['id']}
        db, _ = get_db_manager(mongoConfig, mongoClient)
        try:
            res = checker.check()
            if res != checker_lib.OK:
                timestamp = int(time.time())
                event['status'] = res
                event['timestamp'] = timestamp
                eventQueue.put(event)
                push_check(db, checker.team['id'], checker.service['id'], res, timestamp)
                return
            if not isPrevious:
                time.sleep(random.randint(0, timeSlice))
                res = checker.put(flag, seed)
                if res != checker_lib.OK:
                    timestamp = int(time.time())
                    event['status'] = res
                    event['timestamp'] = timestamp
                    eventQueue.put(event)
                    push_check(db, checker.team['id'], checker.service['id'], res, timestamp)
                    return
            time.sleep(random.randint(0, timeSlice))
            res = checker.get(flag, seed)
            timestamp = int(time.time())
            event['status'] = res
            event['timestamp'] = timestamp
            eventQueue.put(event)
            push_check(db, checker.team['id'], checker.service['id'], res, timestamp)
        except:
            timestamp = int(time.time())
            event['status'] = checker_lib.ERROR
            event['timestamp'] = timestamp
            eventQueue.put(event)
            push_check(db, checker.team['id'], checker.service['id'], checker_lib.ERROR, timestamp)

    def checkerScheduling(self):
        self.roundNum += 1
        log(f"Starting checkers' scheduling for round number: {self.roundNum}, time: {time.time()}")
        db, _ = get_db_manager(self.mongoConfig, self.mongoClient)
        for team_id in self.teams:
            for service_id in self.services:
                while True:
                    try:
                        flag = checker_lib.gen_flag(self.flagHeader, self.flagBodyLen)
                        seed = checker_lib.gen_seed()
                        insert_flag(db, flag, seed, self.roundNum, team_id, service_id)
                        break
                    except AlreadyExistentFlagOrSeed:
                        pass
                checker = self.checkers[team_id][service_id]
                checkerThread = threading.Thread(target=CheckScheduler.runChecker,
                                                 args=(self.eventQueue, self.mongoConfig, self.mongoClient,
                                                       checker, flag, seed, self.roundNum))
                checkerThread.start()
        # a flag is valid for: (current round) + (flag lifetime rounds)
        for recentRound in range(self.roundNum - 1, self.roundNum - self.flagLifetime - 1, -1):
            if recentRound <= 0:
                break
            for team_id in self.teams:
                for service_id in self.services:
                    try:
                        flag_dict = get_flag_for_round(db, recentRound, team_id, service_id)
                        flag, seed = flag_dict['flag_data'], flag_dict['seed']
                        checker = self.checkers[team_id][service_id]
                        checkerThread = threading.Thread(target=CheckScheduler.runChecker,
                                                         args=(self.eventQueue, self.mongoConfig, self.mongoClient,
                                                               checker, flag, seed, self.roundNum, True))
                        checkerThread.start()
                    except NotExistentDocument:
                        log(f"Error: flag for round {recentRound}, team {team_id} and service {service_id} doesn't exist")
        log(f"Completed checkers' scheduling for round number: {self.roundNum}, time: {time.time()}")

    def run(self) -> None:
        # calling datetime.datetime.now() multiple times to ensure the check is right
        if datetime.datetime.now() >= self.endTime:
            log("Error: trying to start after end time")
            exit(1)
        elif datetime.datetime.now() >= self.startTime:
            # resume; it works will if resume is done right after stop
            # if it is done later, it will do the scheduling such that the endTime is respected,
            # jumping over missed rounds; so, at the start it will trigger some exceptions
            # when grepping flags for old rounds
            self.roundNum = int(math.floor((datetime.datetime.now() - self.startTime) / datetime.timedelta(seconds=self.roundTime)))
            # wait until next round start
            delay = (self.startTime + (self.roundNum + 1) * datetime.timedelta(seconds=self.roundTime)) - datetime.datetime.now()
            time.sleep(delay.seconds)
        else:
            delay = self.startTime - datetime.datetime.now()
            time.sleep(delay.seconds)
        schedule.every(self.roundTime).seconds.do(self.checkerScheduling)
        while self.roundNum < self.maxRounds:
            schedule.run_pending()
            if self.stopped:
                schedule.clear()
                return
        schedule.clear()


if __name__ == "__main__":
    checker_mod_name = CheckScheduler.filePathToModuleName("volume/example/example_checker_0.py")
    checker_mod = import_module(checker_mod_name)
    checker = checker_mod.Checker(team={}, service={})
    res = checker.check()
    assert res == checker_lib.OK

    checker_mod_name = CheckScheduler.filePathToModuleName("volume/example/example_checker_1.py")
    checker_mod = import_module(checker_mod_name)
    checker = checker_mod.Checker(team={}, service={})
    res = checker.check()
    assert res == checker_lib.CORRUPT


