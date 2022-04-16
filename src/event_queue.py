import queue

EVENT_CHECK = "check"
EVENT_ATTACK = "attack"


# just a wrapper around queue.Queue, for code manageability
class EventQueue(queue.Queue):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
