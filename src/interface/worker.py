"""Background compute worker with a one-snapshot handoff."""

from threading import Event, Lock, Thread

from compute.module.latest_camera_feed import LatestCameraFeed


class ComputeWorker:
    def __init__(self, runtime, camera_feed_class, camera_config):
        self.runtime = runtime
        self.camera_feed_class = camera_feed_class
        self.camera_config = camera_config
        self._latest = None
        self._lock = Lock()
        self._stop = Event()
        self.error = None
        self.finished = False
        self._thread = Thread(target=self._run, name="compute-runtime", daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        try:
            with LatestCameraFeed(self.camera_feed_class, self.camera_config) as feed:
                while not self._stop.is_set():
                    with self.runtime.benchmark.measure("capture"):
                        left, right, timestamp_s = feed.read()
                    snapshot = self.runtime.process(left, right, timestamp_s)
                    with self._lock:
                        self._latest = snapshot
        except RuntimeError as error:
            if str(error) != "End of stereo recording" and not self._stop.is_set():
                self.error = error
        except Exception as error:
            if not self._stop.is_set():
                self.error = error
        finally:
            self.finished = True

    def latest(self):
        with self._lock:
            snapshot = self._latest
            self._latest = None
            return snapshot

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2.0)
