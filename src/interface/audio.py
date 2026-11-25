"""Asynchronous speech service used by lenses and reflected in the header."""

from queue import Empty, PriorityQueue
from threading import Event, Lock, Thread


class SpeechBackend:
    def speak(self, text):
        raise NotImplementedError


class Pyttsx3Backend(SpeechBackend):
    def __init__(self):
        self._engine = None

    def speak(self, text):
        if self._engine is None:
            import pyttsx3
            self._engine = pyttsx3.init()
        self._engine.say(text)
        self._engine.runAndWait()


class NullSpeechBackend(SpeechBackend):
    def speak(self, text):
        pass


class AudioService:
    def __init__(self, backend=None):
        if backend is None:
            try:
                backend = Pyttsx3Backend()
            except Exception:
                backend = NullSpeechBackend()
        self.backend = backend
        self.current_text = ""
        self._queue = PriorityQueue()
        self._sequence = 0
        self._lock = Lock()
        self._stop = Event()
        self._thread = Thread(target=self._run, name="lens-audio", daemon=True)
        self._thread.start()

    def speak(self, text, interrupt=False, priority=0):
        if not text:
            return
        with self._lock:
            if interrupt:
                self._queue = PriorityQueue()
            self._sequence += 1
            self._queue.put((-priority, self._sequence, text))

    def _run(self):
        while not self._stop.is_set():
            try:
                _, _, text = self._queue.get(timeout=0.1)
            except Empty:
                continue
            self.current_text = text
            try:
                self.backend.speak(text)
            except Exception:
                # Speech must never stop the lens or compute loops.
                pass
            finally:
                self._queue.task_done()

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1.0)
