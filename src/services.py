from event_queue import EventQueue
from event_dispatcher import EventDispatcher
from check_scheduler import CheckScheduler
from submission_service import SubmissionService
from scoreboard_cache import ScoreboardCache


class Services:
    def __init__(self, config):
        self.eventQueue = EventQueue()
        self.eventDispatcher = EventDispatcher(self.eventQueue, config)
        self.checkScheduler = CheckScheduler(self.eventQueue, config)
        self.submissionService = SubmissionService(self.eventQueue, config, self.checkScheduler)
        self.scoreboardCache = ScoreboardCache(config)
        self.eventDispatcher.start()
        self.checkScheduler.start()

    def stop(self):
        self.eventDispatcher.stopped = True
        self.checkScheduler.stopped = True
        self.eventDispatcher.join()
        if 1 <= self.checkScheduler.roundNum < self.checkScheduler.maxRounds:
            self.checkScheduler.join(timeout=self.checkScheduler.roundTime)


if __name__ == "__main__":
    # just to check that there aren't import errors
    pass
