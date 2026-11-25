"""Asynchronous speech service used by lenses and reflected in the header."""

from queue import Empty, PriorityQueue
from threading import Event, Lock, Thread

try:
    from PySide6.QtCore import QObject, Qt, Signal
    from PySide6.QtTextToSpeech import QTextToSpeech
    from PySide6.QtWidgets import QApplication
except ImportError:
    QObject = Qt = Signal = QTextToSpeech = QApplication = None


if QObject is not None:
    class _QtSpeechBridge(QObject):
        text_requested = Signal(str)

        def __init__(self):
            super().__init__()
            self.error_text = None
            self.speech = QTextToSpeech("sapi")
            if self.speech.state() == QTextToSpeech.Error:
                raise RuntimeError(
                    f"Qt speech initialization failed: {self.speech.errorReason()}"
                )
            self.text_requested.connect(self.speech.say, Qt.QueuedConnection)
            self.speech.errorOccurred.connect(self._set_error)

        def _set_error(self, reason):
            self.error_text = str(reason)
else:
    _QtSpeechBridge = None


class SpeechBackend:
    def speak(self, text):
        raise NotImplementedError


class Pyttsx3Backend(SpeechBackend):
    def __init__(self):
        import pyttsx3
        self._engine = pyttsx3.init()

    def speak(self, text):
        self._engine.say(text)
        self._engine.runAndWait()


class QtSpeechBackend(SpeechBackend):
    """Queue speech onto Qt's Windows SAPI engine from the audio worker."""

    def __init__(self):
        if _QtSpeechBridge is None or QApplication.instance() is None:
            raise RuntimeError("Qt speech requires a running QApplication")
        self._bridge = _QtSpeechBridge()

    def speak(self, text):
        self._bridge.text_requested.emit(text)


class NullSpeechBackend(SpeechBackend):
    def speak(self, text):
        pass


class AudioService:
    def __init__(self, backend=None):
        self.startup_error = None
        if backend is None:
            errors = []
            for backend_type in (QtSpeechBackend, Pyttsx3Backend):
                try:
                    backend = backend_type()
                    break
                except Exception as error:
                    errors.append(str(error))
            if backend is None:
                backend = NullSpeechBackend()
                self.startup_error = " | ".join(errors)
        self.backend = backend
        self.current_text = ""
        self._last_error = self.startup_error
        self._queue = PriorityQueue()
        self._sequence = 0
        self._lock = Lock()
        self._stop = Event()
        self._thread = Thread(target=self._run, name="lens-audio", daemon=True)
        self._thread.start()

    @property
    def last_error(self):
        backend_error = getattr(self.backend, "error_text", None)
        return backend_error or self._last_error

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
            except Exception as error:
                # Speech must never stop the lens or compute loops, but the
                # developer UI should make backend failures visible.
                self._last_error = str(error)
            finally:
                self._queue.task_done()

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1.0)
