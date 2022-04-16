import re
import threading
from functools import partial
import time
from dateutil import parser

from event_queue import *
from mongo_utils import get_db_manager, get_flag_by_data, check_stolen_flag, push_stolen_flag, push_lost_flag, \
    NotExistentDocument
from check_scheduler import CheckScheduler


class InvalidToken(Exception):
    pass


class RateLimitExceeded(Exception):
    pass


class ServiceBusy(RateLimitExceeded):
    pass


class OutOfTimeWindow(Exception):
    pass


class InitServiceError(Exception):
    pass


class SubmissionService:
    def __init__(self, eventQueue: EventQueue, config: dict, checkScheduler: CheckScheduler):
        self.eventQueue = eventQueue
        _, mongo_client = get_db_manager(config['mongo'])
        self.mongoClient = mongo_client
        self.mongoConfig = config['mongo']
        flag_regex = config['misc']['flag_header'] + r'\{[a-f0-9]{' + str(config['misc']['flag_body_len']) + r'}\}'
        self.flagPat = re.compile(flag_regex)
        self.teams = {team['token']: team for team in config['teams']}
        for team_token in self.teams.keys():
            self.teams[team_token]['rate_limit_mutex'] = threading.Lock()
            self.teams[team_token]['service_mutex'] = threading.Lock()
        self.rateLimitSeconds = config['misc']['rate_limit_seconds']
        self.roundTime = config['misc']['round_time']
        self.rateLimitTimeMutex = threading.Lock()
        self.maxFlagsPerSubmission = config['misc']['max_flags_per_submission']
        self.flagLifetime = config['misc']['flag_lifetime']
        self.startTime = int(parser.parse(config['misc']['start_time']).timestamp())
        self.endTime = int(parser.parse(config['misc']['end_time']).timestamp())
        if self.startTime >= self.endTime:
            raise InitServiceError
        # the check scheduler is here only to know current round number, which would be slow to grep from mongo
        self.checkScheduler = checkScheduler

    def getTeamMutexes(self, team_token: str):
        if team_token not in self.teams:
            raise InvalidToken
        else:
            return self.teams[team_token]['rate_limit_mutex'], self.teams[team_token]['service_mutex']

    @staticmethod
    def release(mutex: threading.Lock):
        try:
            mutex.release()
        except RuntimeError:
            pass

    def acquireMutexWithScheduledRelease(self, mutex: threading.Lock):
        # if the service time is very high, the mutex may be released before service is completed,
        # and this could result in concurrency issues; so each team should have a mutex for rate limit
        # and another mutex for service
        acquired = mutex.acquire(blocking=False)
        if not acquired:
            raise RateLimitExceeded
        else:
            release = partial(SubmissionService.release, mutex)
            rateHandler = threading.Timer(interval=self.rateLimitSeconds, function=release)
            rateHandler.start()

    def increaseRateLimit(self):
        self.rateLimitTimeMutex.acquire(blocking=True)
        self.rateLimitSeconds *= 2
        self.rateLimitTimeMutex.release()

    def decreaseRateLimit(self):
        self.rateLimitTimeMutex.acquire(blocking=True)
        self.rateLimitSeconds /= 2
        self.rateLimitTimeMutex.release()

    def acquireServiceMutex(self, mutex: threading.Lock) -> threading.Timer:
        acquired = mutex.acquire(blocking=False)
        if not acquired:
            # this is the case in which the service time is being slower than rate limit
            # so, temporary increase rate limit for this round
            self.increaseRateLimit()
            decrease = lambda service: service.decreaseRateLimit()
            decrease = partial(decrease, self)
            decreaseHandler = threading.Timer(interval=self.roundTime, function=decrease)
            decreaseHandler.start()
            raise ServiceBusy
        # also this one is scheduled after a long time, for reliability;
        # if the service goes well, it will (and must) cancel the scheduling, to avoid a spurious release
        release = partial(SubmissionService.release, mutex)
        reliabilityHandler = threading.Timer(interval=self.roundTime * 2, function=release)
        reliabilityHandler.start()
        return reliabilityHandler

    @staticmethod
    def handleFlag(db, flag, team_token, team, event_queue, flag_pat, msg, msg_mutex, round_num, flag_lifetime):
        if not re.match(flag_pat, flag):
            msg_mutex.acquire(blocking=True)
            msg['num_invalid'] += 1
            msg_mutex.release()
            return
        try:
            flag_dict = get_flag_by_data(db, flag)
        except NotExistentDocument:
            msg_mutex.acquire(blocking=True)
            msg['num_invalid'] += 1
            msg_mutex.release()
            return
        if flag_dict['team_id'] == team['id']:
            msg_mutex.acquire(blocking=True)
            msg['num_self_flags'] += 1
            msg_mutex.release()
            return
        if flag_dict['round_num'] < round_num - flag_lifetime:
            msg_mutex.acquire(blocking=True)
            msg['num_old'] += 1
            msg_mutex.release()
            return
        try:
            check_stolen_flag(db, team_token, flag)
            msg_mutex.acquire(blocking=True)
            msg['num_already_submitted'] += 1
            msg_mutex.release()
            return
        except NotExistentDocument:
            timestamp = int(time.time())
            push_stolen_flag(db, team_token, flag, timestamp)
            push_lost_flag(db, flag_dict['team_id'], flag, timestamp)
            event = {"type": EVENT_ATTACK, "team": team['id'], "service": flag_dict['service_id'],
                     "attacked_team": flag_dict['team_id'], "timestamp": timestamp}
            event_queue.put(event)
            msg_mutex.acquire(blocking=True)
            msg['num_accepted'] += 1
            msg_mutex.release()

    def submitFlags(self, team_token: str, flags: list):
        if not (self.startTime <= int(time.time()) <= self.endTime):
            raise OutOfTimeWindow
        rate_limit_mutex, service_mutex = self.getTeamMutexes(team_token)
        # for rate limiting
        self.acquireMutexWithScheduledRelease(rate_limit_mutex)
        # for other concurrency issues (when the service is slower than rate limit)
        timed_release = self.acquireServiceMutex(service_mutex)
        msg = {"num_invalid": 0, "num_accepted": 0, "num_already_submitted": 0,
               "num_self_flags": 0, "num_discarded": max(len(flags) - self.maxFlagsPerSubmission, 0),
               "num_old": 0}
        msg_mutex = threading.Lock()
        flags = flags[:self.maxFlagsPerSubmission]
        db, _ = get_db_manager(self.mongoConfig, self.mongoClient)
        team = self.teams[team_token]
        threads = []
        # a thread for each flag, join all of them, because most operations are I/O; it would be too slow otherwise
        current_flag_handler = partial(SubmissionService.handleFlag,
                                       db=db, team_token=team_token, team=team, event_queue=self.eventQueue,
                                       flag_pat=self.flagPat, msg=msg, msg_mutex=msg_mutex,
                                       round_num=self.checkScheduler.roundNum, flag_lifetime=self.flagLifetime)
        for flag in flags:
            thread_flag_handler = partial(current_flag_handler, flag=flag)
            service_thread = threading.Thread(target=thread_flag_handler)
            threads.append(service_thread)
            service_thread.start()
        for thread in threads:
            thread.join()
        if timed_release.is_alive():
            # note: if it is not alive, it means that the service took more than 2 rounds to complete;
            # it's rare, but it's still an edge case to consider, to avoid a release on an already released mutex
            self.release(service_mutex)
            timed_release.cancel()
        return msg
