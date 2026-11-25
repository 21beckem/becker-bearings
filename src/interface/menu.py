"""Reusable joystick-and-tactile option navigation."""

from dataclasses import dataclass
from time import monotonic

from .contracts import (
    LensOutput, SpeechCategory, SpeechRequest, TactileFrame, TactileState,
)
from .debug import debug


@dataclass
class MenuItem:
    key: str
    label: str
    description: str = ""
    value_provider: object = None
    select: object = None
    tactile_state: TactileState = TactileState.OFF

    def value_text(self):
        if self.value_provider is None:
            return ""
        value = self.value_provider() if callable(self.value_provider) else self.value_provider
        return "" if value in (None, "") else str(value)


@dataclass(frozen=True)
class MenuResult:
    speech: tuple[SpeechRequest, ...] = ()
    selected: MenuItem | None = None
    moved: bool = False
    back: bool = False


class MenuNavigator:
    """A menu whose focused item is represented by one tactile point."""

    def __init__(self, title, items, instructions=(), initial_index=0,
                 allow_back=True):
        if not items:
            raise ValueError("a menu requires at least one item")
        self.title = title
        self.items = list(items)
        self.instructions = tuple(instructions)
        self.allow_back = allow_back
        self.index = max(0, min(initial_index, len(self.items) - 1))
        self._announce = True
        self._entered = False
        self._last_direction = 0
        self._next_repeat_s = 0.0

    @property
    def current(self):
        return self.items[self.index]

    def set_items(self, items):
        if not items:
            raise ValueError("a menu requires at least one item")
        self.items = list(items)
        self.index = min(self.index, len(self.items) - 1)
        self._announce = True

    def enter(self):
        self._announce = True
        self._entered = False
        return self._speech_for_current(include_instructions=True)

    def update(self, input_state):
        now = getattr(input_state, "timestamp_s", monotonic())
        if (self.allow_back and abs(input_state.joystick_x) > 0.55 and
                abs(input_state.joystick_x) > abs(input_state.joystick_y) and
                input_state.joystick_x < 0):
            self._last_direction = 0
            return MenuResult(back=True)
        direction = self._direction(input_state)
        moved = False
        if direction == 0:
            self._last_direction = 0
        elif direction != self._last_direction or now >= self._next_repeat_s:
            first_move = direction != self._last_direction
            self.index = (self.index + direction) % len(self.items)
            self._last_direction = direction
            self._next_repeat_s = now + (0.45 if first_move else 0.22)
            self._announce = True
            moved = True
            debug("menu_move title=%s index=%s key=%s direction=%s", self.title, self.index, self.current.key, direction)

        speech = (
            self._speech_for_current(include_instructions=not self._entered)
            if self._announce else ()
        )
        self._entered = True
        self._announce = False
        selected = self.current if getattr(input_state, "button_pressed", False) else None
        if selected is not None:
            debug("menu_select title=%s index=%s key=%s", self.title, self.index, selected.key)
        return MenuResult(speech=speech, selected=selected, moved=moved)

    def output(self, result=None, header_text=None, extra_info=()):
        points = [TactileState.OFF] * 20
        for index, item in enumerate(self.items):
            if index % 20 == self.index % 20:
                points[index % 20] = TactileState.HIGH
            elif item.tactile_state != TactileState.OFF:
                points[index % 20] = item.tactile_state
        result = result or MenuResult()
        return LensOutput(
            tactile=TactileFrame(tuple(points)),
            header_text=header_text or f"{self.title}: {self.current.label}",
            info_title=self.title,
            info_lines=tuple(self._info_lines()) + tuple(extra_info),
            speech=result.speech,
        )

    def _info_lines(self):
        item = self.current
        lines = [item.label]
        if item.value_text():
            lines.append(f"Current value: {item.value_text()}")
        if item.description:
            lines.append(item.description)
        return lines

    def _speech_for_current(self, include_instructions=False):
        item = self.current
        text = item.label
        if item.value_text():
            text += f". Current value: {item.value_text()}"
        # The menu name is required on entry, but repeating it on every
        # focus change makes rapid tactile navigation unnecessarily verbose.
        required_text = f"{self.title}. {text}" if not self._entered else text
        instruction_text = " ".join(self.instructions) if include_instructions else ""
        return (SpeechRequest(
            required_text,
            interrupt=True,
            category=SpeechCategory.CONTEXT,
            instruction_text=instruction_text,
        ),)

    def instruction_speech(self):
        return (SpeechRequest(
            "Menu instructions.",
            interrupt=True,
            category=SpeechCategory.INSTRUCTION,
            instruction_text=" ".join(self.instructions),
        ),)

    @staticmethod
    def _direction(input_state):
        x = input_state.joystick_x
        y = input_state.joystick_y
        if max(abs(x), abs(y)) < 0.55:
            return 0
        if abs(y) >= abs(x):
            return 1 if y > 0 else -1
        return 1 if x > 0 else -1
