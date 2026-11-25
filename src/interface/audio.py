"""Asynchronous speech service used by lenses and reflected in the header."""

from queue import Empty, PriorityQueue
from threading import Event, Lock, Thread

from .contracts import SpeechCategory
from .debug import debug

try:
    from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
    from PySide6.QtTextToSpeech import QTextToSpeech
    from PySide6.QtWidgets import QApplication
except ImportError:
    QObject = QThread = QTimer = Qt = Signal = Slot = QTextToSpeech = QApplication = None


if QObject is not None:
    class _QtSpeechBridge(QObject):
        text_requested = Signal(str)
        replacement_requested = Signal(str)
        initialized = Signal()

        def __init__(self):
            super().__init__()
            self.error_text = None
            self.speech = None
            self._pending_replacement = None
            self._waiting_for_ready = False
            self.text_requested.connect(self._say, Qt.QueuedConnection)
            self.replacement_requested.connect(self._replace, Qt.QueuedConnection)

        @Slot()
        def initialize(self):
            # This slot runs in the dedicated speech thread, keeping SAPI and
            # QTextToSpeech out of the screen application's event loop.
            self.speech = QTextToSpeech("sapi")
            debug("qt_initialize state=%s", self.speech.state())
            if self.speech.state() == QTextToSpeech.Error:
                self.error_text = self.speech.errorReason()
            else:
                self.speech.errorOccurred.connect(self._set_error)
                # Do not rely solely on this signal: some SAPI versions do
                # not consistently emit Ready after stop(). The replacement
                # path also polls from this same speech thread.
                self.speech.stateChanged.connect(self._state_changed)
            self.initialized.emit()

        @Slot(str)
        def _say(self, text):
            debug("qt_say text=%r state_before=%s", text, self.speech.state() if self.speech else None)
            if self.speech is not None and not self.error_text:
                self.speech.say(text)

        def _state_changed(self, state):
            debug("qt_state_changed state=%s pending=%r", state, self._pending_replacement)
            if state == QTextToSpeech.Ready:
                self._speak_pending()

        def _speak_pending(self):
            debug("qt_speak_pending state=%s pending=%r", self.speech.state() if self.speech else None, self._pending_replacement)
            if self.speech is None or self.speech.state() != QTextToSpeech.Ready:
                return False
            if self._pending_replacement is None:
                self._waiting_for_ready = False
                return True
            text = self._pending_replacement
            self._pending_replacement = None
            self._waiting_for_ready = False
            self.speech.say(text)
            debug("qt_say_pending text=%r", text)
            return True

        @Slot()
        def _poll_ready(self):
            debug("qt_poll_ready state=%s pending=%r", self.speech.state() if self.speech else None, self._pending_replacement)
            if self._speak_pending():
                return
            QTimer.singleShot(10, self._poll_ready)

        @Slot(str)
        def _replace(self, text):
            debug("qt_replace text=%r state_before=%s", text, self.speech.state() if self.speech else None)
            if self.speech is None or self.error_text:
                return
            self._pending_replacement = text
            if self.speech.state() == QTextToSpeech.Ready:
                self._speak_pending()
            else:
                self.speech.stop()
                debug("qt_stop_for_replacement text=%r", text)
                if not self._waiting_for_ready:
                    self._waiting_for_ready = True
                    QTimer.singleShot(10, self._poll_ready)

        def _set_error(self, reason):
            self.error_text = str(reason)
            debug("qt_error reason=%r", reason)
else:
    _QtSpeechBridge = None


class SpeechBackend:
    def speak(self, text, interrupt=False):
        raise NotImplementedError


class Pyttsx3Backend(SpeechBackend):
    def __init__(self):
        import pyttsx3
        self._engine = pyttsx3.init()
        self._engine.connect(
            "started-utterance",
            lambda name: debug("pyttsx3_started name=%r", name),
        )
        self._engine.connect(
            "finished-utterance",
            lambda name, completed: debug(
                "pyttsx3_finished name=%r completed=%s", name, completed
            ),
        )
        self._engine.connect(
            "error",
            lambda name, error: debug("pyttsx3_error name=%r error=%r", name, error),
        )

    def speak(self, text, interrupt=False):
        debug("pyttsx3_speak_start text=%r interrupt=%s", text, interrupt)
        # AudioService already removes queued stale messages. Calling
        # engine.stop() before every runAndWait() leaves the Windows SAPI
        # driver in a state where later utterances can complete silently.
        self._engine.say(text)
        self._engine.runAndWait()
        debug("pyttsx3_speak_return text=%r", text)


class QtSpeechBackend(SpeechBackend):
    """Run Qt's Windows SAPI engine on a dedicated Qt thread."""

    def __init__(self):
        if _QtSpeechBridge is None or QApplication.instance() is None:
            raise RuntimeError("Qt speech requires a running QApplication")
        self._thread = QThread()
        self._bridge = _QtSpeechBridge()
        self._ready = Event()
        self._bridge.moveToThread(self._thread)
        self._thread.started.connect(self._bridge.initialize)
        self._bridge.initialized.connect(self._ready.set, Qt.DirectConnection)
        self._thread.start()
        debug("qt_thread_started")
        if not self._ready.wait(2.0):
            self.close()
            raise RuntimeError("Qt speech thread failed to start")
        if self._bridge.error_text:
            error = str(self._bridge.error_text)
            self.close()
            raise RuntimeError(f"Qt speech initialization failed: {error}")
        debug("qt_backend_ready")

    def speak(self, text, interrupt=False):
        debug("qt_backend_speak text=%r interrupt=%s", text, interrupt)
        if interrupt:
            self._bridge.replacement_requested.emit(text)
        else:
            self._bridge.text_requested.emit(text)

    def close(self):
        if getattr(self, "_thread", None) is not None:
            self._thread.quit()
            self._thread.wait(1000)
            self._thread = None


class NullSpeechBackend(SpeechBackend):
    def speak(self, text, interrupt=False):
        pass


class AudioService:
    def __init__(self, backend=None):
        self.startup_error = None
        if backend is None:
            errors = []
            # QtSpeechBackend owns QTextToSpeech on a dedicated QThread, so
            # it avoids the GUI freeze while retaining reliable Windows SAPI
            # replacement behavior. pyttsx3 remains the fallback backend.
            for backend_type in (QtSpeechBackend, Pyttsx3Backend):
                try:
                    backend = backend_type()
                    break
                except Exception as error:
                    errors.append(str(error))
                    debug("audio_backend_failed backend=%s error=%r", backend_type.__name__, error)
            if backend is None:
                backend = NullSpeechBackend()
                self.startup_error = " | ".join(errors)
        self.backend = backend
        debug("audio_service_backend backend=%s startup_error=%r", type(backend).__name__, self.startup_error)
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

    def speak(self, text, interrupt=False, priority=0, category=SpeechCategory.CONTENT):
        if not text:
            return
        debug("audio_request text=%r interrupt=%s priority=%s category=%s", text, interrupt, priority, category)
        with self._lock:
            if interrupt:
                # Keep one queue object for the worker's entire lifetime. If
                # it has already taken an item, replacing the queue causes
                # its later task_done() to target the wrong queue and kills
                # the audio thread.
                while True:
                    try:
                        self._queue.get_nowait()
                    except Empty:
                        break
                    else:
                        self._queue.task_done()
                debug("audio_queue_interrupted")
            self._sequence += 1
            self._queue.put((-priority, self._sequence, (text, category, interrupt)))
            debug("audio_queue_put sequence=%s size=%s", self._sequence, self._queue.qsize())

    def _run(self):
        while not self._stop.is_set():
            try:
                _, _, payload = self._queue.get(timeout=0.1)
            except Empty:
                continue
            text, _category, _interrupt = payload
            self.current_text = text
            debug("audio_worker_dequeue text=%r interrupt=%s", text, _interrupt)
            try:
                # Keep backend calls on the audio worker. Interrupt handling
                # is passed to the backend as one atomic operation.
                self.backend.speak(text, interrupt=_interrupt)
                debug("audio_worker_backend_return text=%r", text)
            except Exception as error:
                # Speech must never stop the lens or compute loops, but the
                # developer UI should make backend failures visible.
                self._last_error = str(error)
                debug("audio_worker_error error=%r", error)
            finally:
                self._queue.task_done()

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1.0)
        close_backend = getattr(self.backend, "close", None)
        if close_backend is not None:
            close_backend()
        debug("audio_service_closed")
