import threading
import time

from event_queue import *
from mongo_utils import get_db_manager, update_points
from project_utils import log
from checker_lib import *

"""
Event formats:
{"type": EVENT_CHECK, "status": Union(OK, DOWN, MUMBLE, CORRUPT, ERROR), "team": team_id, "service": service_id, "timestamp": int_timestamp}
{"type": EVENT_ATTACK, "team": team_id, "service": service_id, "attacked_team": attacked_team_id, "timestamp": int_timestamp}
"""


class EventDispatcher(threading.Thread):
    def __init__(self, eventQueue: EventQueue, config: dict):
        super().__init__()
        self.eventQueue = eventQueue
        _, mongo_client = get_db_manager(config['mongo'])
        self.mongoClient = mongo_client
        self.mongoConfig = config['mongo']
        self.stopped = False
        self.dispatchFrequency = config['misc']['dispatch_frequency']

    @staticmethod
    def updatePoints(mongoClient, mongoConfig, event):
        # timestamp is passed in the event to have consistency between stolen_flags, lost_flags and checks'
        # timestamps and last_pts_update timestamp; silently take current time as timestamp if it is not present
        if 'timestamp' in event:
            timestamp = event['timestamp']
        else:
            timestamp = int(time.time())
        db, _ = get_db_manager(mongoConfig, mongoClient)
        if event['type'] == EVENT_CHECK:
            pts_type = "sla_pts"
            status = event['status']
            if status == ERROR:
                # nothing to do: checker error
                return
            elif status == OK:
                increment = True
            elif status in [MUMBLE, CORRUPT, DOWN]:
                increment = False
            else:
                log(f"Error: {status} is an invalid event status")
                return
            update_points(db, event['team'], event['service'], pts_type, increment, timestamp)
        elif event['type'] == EVENT_ATTACK:
            atk_type = "atk_pts"
            def_type = "def_pts"
            team, service, attacked_team = event['team'], event['service'], event['attacked_team']
            update_points(db, team, service, pts_type=atk_type, increment=True, timestamp=timestamp)
            update_points(db, attacked_team, service, pts_type=def_type, increment=False, timestamp=timestamp)
        else:
            log(f"Error: {event['type']} is an invalid event type")

    def run(self) -> None:
        while True:
            time.sleep(self.dispatchFrequency)
            new_events = []
            empty = False
            while not empty:
                try:
                    new_events.append(self.eventQueue.get(block=False))
                except queue.Empty:
                    empty = True
            for event in new_events:
                updateThread = threading.Thread(target=EventDispatcher.updatePoints,
                                                args=(self.mongoClient, self.mongoConfig, event))
                updateThread.start()
            if self.stopped:
                return
