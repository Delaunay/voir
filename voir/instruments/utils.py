"""Utilities for instruments."""

import multiprocessing
import time
from threading import Thread


class Monitor(Thread):
    """Thread that calls a monitoring function every ``delay`` seconds.

    Notes
    -----

    Because of python's implementation the frequency of the call to the monitoring function
    might quite far away from the specified delay.

    For a more deterministic monitoring use MonitorProc instead.
    """

    def __init__(self, delay, func):
        super().__init__(daemon=True)
        self.stopped = False
        self.delay = delay
        self.func = func

    def run(self):
        while not self.stopped:
            time.sleep(self.delay)
            self.func()

    def stop(self):
        self.stopped = True


def _worker(state, queue, func, delay):
    while state['running']:
        queue.put(func())
        time.sleep(delay)


class MonitorProc:
    """Spawn a new process that calls a monitoring function every ``delay`` seconds.

    Notes
    -----

    Because the monitoring function is called in a new process, it might be useful
    to specify the onevent callback to save/print the monitored value inside the main process.
    """
    def __init__(self, delay, func, onevent=None, delay2=0.1):
        self.manager = multiprocessing.Manager()
        self.state = self.manager.dict()
        self.state['running'] = True
        self.results = multiprocessing.Queue()
        self.process = multiprocessing.Process(
            target=_worker,
            args=(self.state, self.results, func, delay),
        )
        self.onevent = onevent

        if onevent is not None:
            def poll():
                for event in self.poll():
                    onevent(event)

            self.monitor = Monitor(delay2, poll)

    def poll(self):
        """Fetch the available results"""
        events = []
        while not self.results.empty():
            event = self.results.get()

            if self.onevent:
                self.onevent(event)

            events.append(event)
        return events

    def start(self):
        self.process.start()

    def stop(self):
        self.monitor.stop()
        self.state['running'] = False
        self.process.join()

        # process the last events if any
        if self.onevent is not None:
            self.poll()
