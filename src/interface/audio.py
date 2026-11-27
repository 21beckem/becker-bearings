"""Asynchronous speech service used by lenses and reflected in the header."""

import json
from pathlib import Path
from threading import Event, Lock, Thread

from .audio_queue import AudioQueue
from .contracts import SpeechCategory, SpeechPart, SpeechRequest
from .debug import debug

try:
    from PySide6.QtCore import QObject, QThread, QTimer, Qt, QUrl, Signal, Slot
    from PySide6.QtMultimedia import QSoundEffect
    from PySide6.QtTextToSpeech import QTextToSpeech
    from PySide6.QtWidgets import QApplication
except ImportError:
    (QObject, QThread, QTimer, Qt, QUrl, Signal, Slot, QSoundEffect,
     QTextToSpeech, QApplication) = (None,) * 10


if QObject is not None:
    class _QtClipPlayer(QObject):
        """Preload generated WAV clips and play them through Qt."""

        play_requested = Signal(str, bool)
        stop_requested = Signal()

        def __init__(self, manifest_path):
            super().__init__()
            self._effects = {}
            self._text_to_clip = {}
            self._clip_waiters = {}
            self._clip_waiters_lock = Lock()
            self.play_requested.connect(self._play, Qt.QueuedConnection)
            self.stop_requested.connect(self._stop, Qt.QueuedConnection)
            self._load_manifest(Path(manifest_path))

        def _load_manifest(self, manifest_path):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                debug("clip_manifest_failed path=%s error=%r", manifest_path, error)
                return
            for phrase in manifest.get("phrases", ()):
                clip_id = phrase.get("id")
                filename = phrase.get("file")
                if not clip_id or not filename:
                    continue
                source = manifest_path.parent / filename
                if not source.is_file():
                    debug("clip_missing id=%s path=%s", clip_id, source)
                    continue
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(source.resolve())))
                effect.setVolume(1.0)
                effect.playingChanged.connect(
                    lambda clip_id=clip_id, effect=effect:
                    self._playing_changed(clip_id, effect.isPlaying())
                )
                self._effects[clip_id] = effect
                if phrase.get("text"):
                    self._text_to_clip[phrase["text"]] = clip_id
            debug("clips_loaded count=%s path=%s", len(self._effects), manifest_path)

        def clip_for_text(self, text):
            return self._text_to_clip.get(text)

        def play_clip(self, clip_id, interrupt=True):
            if clip_id not in self._effects:
                return False
            waiter = Event()
            with self._clip_waiters_lock:
                self._clip_waiters[clip_id] = waiter
            self.play_requested.emit(clip_id, interrupt)
            waiter.wait(120.0)
            return True

        def stop(self):
            self.stop_requested.emit()

        @Slot(str, bool)
        def _play(self, clip_id, interrupt):
            if interrupt:
                self._stop()
            effect = self._effects.get(clip_id)
            if effect is not None:
                debug("clip_play id=%s interrupt=%s", clip_id, interrupt)
                effect.play()

        @Slot()
        def _stop(self):
            for effect in self._effects.values():
                if effect.isPlaying():
                    effect.stop()
            with self._clip_waiters_lock:
                waiters = tuple(self._clip_waiters.values())
                self._clip_waiters.clear()
            for waiter in waiters:
                waiter.set()

        def _playing_changed(self, clip_id, playing):
            if playing:
                return
            with self._clip_waiters_lock:
                waiter = self._clip_waiters.pop(clip_id, None)
            if waiter is not None:
                waiter.set()

        def close(self):
            self.stop()


    def _default_clip_player():
        if QApplication.instance() is None:
            return None
        manifest_path = (
            Path(__file__).resolve().parents[1] / "assets" / "audio" / "manifest.json"
        )
        if not manifest_path.is_file():
            return None
        return _QtClipPlayer(manifest_path)


    class _QtSpeechBridge(QObject):
        text_requested = Signal(str)
        replacement_requested = Signal(str)
        stop_requested = Signal()
        initialized = Signal()

        def __init__(self):
            super().__init__()
            self.error_text = None
            self.speech = None
            self._pending_replacement = None
            self._waiting_for_ready = False
            self.text_requested.connect(self._say, Qt.QueuedConnection)
            self.replacement_requested.connect(self._replace, Qt.QueuedConnection)
            self.stop_requested.connect(self._stop, Qt.QueuedConnection)

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

        @Slot()
        def _stop(self):
            if self.speech is not None:
                self.speech.stop()
else:
    _QtSpeechBridge = None
    _default_clip_player = lambda: None


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

    def stop(self):
        if getattr(self, "_bridge", None) is not None:
            self._bridge.stop_requested.emit()

    def close(self):
        if getattr(self, "_thread", None) is not None:
            self._thread.quit()
            self._thread.wait(1000)
            self._thread = None


class NullSpeechBackend(SpeechBackend):
    def speak(self, text, interrupt=False):
        pass


class AudioService:
    def __init__(self, backend=None, clip_player=None):
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
        self.clip_player = (
            _default_clip_player() if clip_player is None else clip_player
        )
        debug("audio_service_backend backend=%s startup_error=%r", type(backend).__name__, self.startup_error)
        self.current_text = ""
        self._last_error = self.startup_error
        self._queue = AudioQueue()
        self._lock = Lock()
        self._stop = Event()
        self._thread = Thread(target=self._run, name="lens-audio", daemon=True)
        self._thread.start()

    @property
    def last_error(self):
        backend_error = getattr(self.backend, "error_text", None)
        return backend_error or self._last_error

    def has_message(self, message_id):
        """Return whether a message is currently playing or queued."""
        with self._lock:
            return self._queue.contains(message_id)

    def speak(self, text, interrupt=False, priority=0,
              category=SpeechCategory.CONTENT, clip_id="", message_id="",
              message_type=None, lens_id="", error_key="",
              play_after_instructions=False, audio_parts=()):
        if isinstance(text, SpeechRequest):
            request = text
        else:
            if not text:
                return
            request = SpeechRequest(
                text=text,
                category=category,
                clip_id=clip_id,
                message_id=message_id,
                message_type=message_type,
                lens_id=lens_id,
                error_key=error_key,
                play_after_instructions=play_after_instructions,
                audio_parts=audio_parts,
            )
        if not request.text:
            return
        debug(
            "audio_request text=%r type=%s id=%s lens=%s clip_id=%s",
            request.text, request.message_type, request.message_id,
            request.lens_id, request.clip_id,
        )
        with self._lock:
            decision = self._queue.submit(request)
            queued_count = len(self._queue.queued)
        if decision.interrupt_current:
            self._stop_backend()
        debug("audio_queue_submit interrupt=%s queued=%s",
              decision.interrupt_current, queued_count)

    def _run(self):
        while not self._stop.is_set():
            with self._lock:
                message = self._queue.begin_next()
            if message is None:
                self._stop.wait(0.1)
                continue
            self.current_text = message.text
            debug("audio_worker_dequeue text=%r type=%s id=%s",
                  message.text, message.message_type, message.message_id)
            try:
                parts = message.audio_parts or (
                    SpeechPart(message.text, message.clip_id),
                )
                for part in parts:
                    clip_id = part.clip_id or getattr(
                        self.clip_player, "clip_for_text", lambda _: None
                    )(part.text)
                    if (clip_id and self.clip_player is not None and
                            self.clip_player.play_clip(clip_id, False)):
                        continue
                    if not part.allow_tts:
                        debug("audio_clip_required_missing clip_id=%s text=%r",
                              clip_id, part.text)
                        continue
                    self.backend.speak(part.text, interrupt=False)
                debug("audio_worker_backend_return text=%r", message.text)
            except Exception as error:
                # Speech must never stop the lens or compute loops, but the
                # developer UI should make backend failures visible.
                self._last_error = str(error)
                debug("audio_worker_error error=%r", error)
            finally:
                with self._lock:
                    self._queue.finish(message)

    def _stop_backend(self):
        stop_backend = getattr(self.backend, "stop", None)
        if stop_backend is not None:
            try:
                stop_backend()
            except Exception as error:
                debug("audio_backend_stop_error error=%r", error)
        stop_clips = getattr(self.clip_player, "stop", None)
        if stop_clips is not None:
            try:
                stop_clips()
            except Exception as error:
                debug("audio_clip_stop_error error=%r", error)

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1.0)
        close_backend = getattr(self.backend, "close", None)
        if close_backend is not None:
            close_backend()
        close_clips = getattr(self.clip_player, "close", None)
        if close_clips is not None:
            close_clips()
        debug("audio_service_closed")
