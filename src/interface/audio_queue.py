"""Deterministic queue policy for complete spoken messages."""

from dataclasses import dataclass

from .contracts import SpeechCategory, SpeechMessageType, SpeechRequest


_PRIORITY = {
    SpeechMessageType.LENS_ENTRY: 2,
    SpeechMessageType.MENU_OPTION: 1,
    SpeechMessageType.INSTRUCTION: 0,
    SpeechMessageType.ERROR: 0,
}


@dataclass(frozen=True)
class AudioMessage:
    text: str
    message_id: str
    message_type: SpeechMessageType
    lens_id: str = ""
    error_key: str = ""
    clip_id: str = ""
    play_after_instructions: bool = False
    sequence: int = 0

    @property
    def priority(self):
        if self.play_after_instructions:
            return 0
        return _PRIORITY[self.message_type]

    @classmethod
    def from_request(cls, request, *, sequence=0):
        if isinstance(request, SpeechRequest):
            message_type = request.message_type or _type_from_legacy(request)
            return cls(
                request.text,
                request.message_id or request.clip_id or request.text,
                message_type,
                request.lens_id,
                request.error_key,
                request.clip_id,
                request.play_after_instructions,
                sequence,
            )
        raise TypeError("audio queue requires a SpeechRequest")


@dataclass(frozen=True)
class QueueDecision:
    interrupt_current: bool = False


def _type_from_legacy(request):
    """Keep old callers usable while producers migrate to explicit types."""
    if request.category == SpeechCategory.ERROR:
        return SpeechMessageType.ERROR
    if request.category == SpeechCategory.INSTRUCTION:
        return SpeechMessageType.INSTRUCTION
    if request.category == SpeechCategory.CONTEXT:
        return SpeechMessageType.LENS_ENTRY
    return SpeechMessageType.MENU_OPTION


class AudioQueue:
    """Thread-safe-by-owner queue policy.

    AudioService serializes calls to this object with its lock. The class is
    deliberately independent from speech backends so its transitions can be
    tested without Qt, SAPI, or audio files.
    """

    def __init__(self):
        self._queued = []
        self._current = None
        self._sequence = 0
        self._known_errors = set()

    @property
    def current(self):
        return self._current

    @property
    def queued(self):
        return tuple(self._queued)

    def submit(self, request):
        self._sequence += 1
        message = AudioMessage.from_request(request, sequence=self._sequence)
        if message.message_type == SpeechMessageType.ERROR:
            key = message.error_key or message.message_id
            if key in self._known_errors:
                return QueueDecision()
            self._known_errors.add(key)
            self._insert(message)
            return QueueDecision()

        if message.message_type == SpeechMessageType.LENS_ENTRY:
            interrupt = self._current is not None and self._current.message_type != SpeechMessageType.ERROR
            self._queued = [
                item for item in self._queued
                if item.message_type == SpeechMessageType.ERROR
            ]
            self._insert(message, before_errors=True)
            return QueueDecision(interrupt_current=interrupt)

        if message.message_type == SpeechMessageType.MENU_OPTION:
            interrupt = False
            interrupted_instruction = None
            if self._current is not None:
                if self._current.message_type == SpeechMessageType.MENU_OPTION:
                    interrupt = True
                elif self._current.message_type == SpeechMessageType.INSTRUCTION:
                    interrupt = True
                    interrupted_instruction = self._current
            self._queued = [
                item for item in self._queued
                if item.message_type != SpeechMessageType.MENU_OPTION
            ]
            self._insert(message)
            if interrupted_instruction is not None:
                self._insert_instruction_front(interrupted_instruction)
            return QueueDecision(interrupt_current=interrupt)

        # Instructions are latest-wins while queued. An instruction that was
        # interrupted by a MenuOption is reinserted explicitly by that rule.
        self._queued = [
            item for item in self._queued
            if item.message_type != SpeechMessageType.INSTRUCTION
        ]
        self._insert(message)
        return QueueDecision()

    def begin_next(self):
        if self._current is not None or not self._queued:
            return None
        best_index = min(
            range(len(self._queued)),
            key=lambda index: (-self._queued[index].priority,
                               self._queued[index].sequence),
        )
        self._current = self._queued.pop(best_index)
        return self._current

    def finish(self, message):
        if self._current == message:
            self._current = None

    def _insert(self, message, *, before_errors=False):
        if before_errors and message.message_type == SpeechMessageType.LENS_ENTRY:
            error_index = next(
                (index for index, item in enumerate(self._queued)
                 if item.message_type == SpeechMessageType.ERROR),
                len(self._queued),
            )
            self._queued.insert(error_index, message)
            return
        self._queued.append(message)

    def _insert_instruction_front(self, message):
        instruction_index = next(
            (index for index, item in enumerate(self._queued)
             if item.message_type == SpeechMessageType.INSTRUCTION),
            len(self._queued),
        )
        self._queued.insert(instruction_index, message)
