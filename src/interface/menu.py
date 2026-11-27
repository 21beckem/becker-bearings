"""Reusable joystick-and-tactile option navigation."""

from dataclasses import dataclass
from time import monotonic

from .contracts import (
    LensOutput, SpeechCategory, SpeechMessageType, SpeechRequest,
    TactileFrame, TactileState,
)
from .debug import debug


MENU_COLUMNS = 4
MENU_ROWS = 5
MENU_TACTILE_MODES = {
    "trinary_ancestors_low",
    "binary_ancestors_high",
    "current_only",
}


@dataclass
class MenuItem:
    key: str
    label: str
    description: str = ""
    value_provider: object = None
    select: object = None
    tactile_state: TactileState = TactileState.OFF
    audio_parts_provider: object = None
    value_prefix: str = "Current value:"

    def value_text(self):
        if self.value_provider is None:
            return ""
        value = self.value_provider() if callable(self.value_provider) else self.value_provider
        return "" if value in (None, "") else str(value)

    def audio_parts(self):
        if self.audio_parts_provider is None:
            return ()
        parts = self.audio_parts_provider()
        return tuple(parts or ())


@dataclass(frozen=True)
class MenuResult:
    speech: tuple[SpeechRequest, ...] = ()
    selected: MenuItem | None = None
    moved: bool = False


class MenuNavigator:
    """A menu whose focused item is represented by one tactile point."""

    def __init__(self, title, items, instructions=(), initial_index=0,
                 instruction_id="menu.instructions"):
        if not items:
            raise ValueError("a menu requires at least one item")
        self.title = title
        self.items = list(items)
        self.instructions = tuple(instructions)
        self.instruction_id = instruction_id
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
        result = result or MenuResult()
        return LensOutput(
            tactile=MenuStack((self,)).frame(),
            header_text=header_text or f"{self.title}: {self.current.label}",
            info_title=self.title,
            info_lines=tuple(self._info_lines()) + tuple(extra_info),
            speech=result.speech,
            menu_layers=(self,),
        )

    def _info_lines(self):
        item = self.current
        lines = [item.label]
        if item.value_text():
            lines.append(self._value_phrase(item))
        if item.description:
            lines.append(item.description)
        return lines

    def _speech_for_current(self, include_instructions=False):
        item = self.current
        text = item.label
        if item.value_text():
            separator = " " if item.value_prefix == "currently" else ". "
            text += separator + self._value_phrase(item)
        if include_instructions:
            requests = list(self.instruction_speech())
            requests.append(SpeechRequest(
                text,
                category=SpeechCategory.OPTION,
                message_id=f"menu.option.{item.key}",
                message_type=SpeechMessageType.MENU_OPTION,
                play_after_instructions=True,
                audio_parts=item.audio_parts(),
            ))
            return tuple(requests)
        requests = [SpeechRequest(
            text,
            category=SpeechCategory.OPTION,
            message_id=f"menu.option.{item.key}",
            message_type=SpeechMessageType.MENU_OPTION,
            audio_parts=item.audio_parts(),
        )]
        return tuple(requests)

    @staticmethod
    def _value_phrase(item):
        return f"{item.value_prefix} {item.value_text()}"

    def instruction_speech(self):
        return (SpeechRequest(
            " ".join(self.instructions),
            category=SpeechCategory.INSTRUCTION,
            message_id=self.instruction_id,
            message_type=SpeechMessageType.INSTRUCTION,
        ),)

    @staticmethod
    def _direction(input_state):
        value = input_state.joystick
        if abs(value) < 0.55:
            return 0
        return 1 if value > 0 else -1


class MenuStack:
    """Compose logical menu layers into the grip's four tactile columns."""

    def __init__(self, layers=(), tactile_mode="trinary_ancestors_low"):
        self.layers = tuple(layers)
        self.tactile_mode = (
            tactile_mode if tactile_mode in MENU_TACTILE_MODES
            else "trinary_ancestors_low"
        )

    def frame(self):
        points = [TactileState.OFF] * 20
        visible = self.layers[-MENU_COLUMNS:]
        first_visible = len(self.layers) - len(visible)
        for visible_index, navigator in enumerate(visible):
            depth = first_visible + visible_index
            if visible_index == len(visible) - 1:
                state = TactileState.HIGH
            elif self.tactile_mode == "trinary_ancestors_low":
                state = TactileState.LOW
            elif self.tactile_mode == "binary_ancestors_high":
                state = TactileState.HIGH
            else:
                state = TactileState.OFF
            self._write_layer(points, navigator, depth, state)
        return TactileFrame(tuple(points))

    @staticmethod
    def _write_layer(points, navigator, depth, selected_state):
        column = min(depth, MENU_COLUMNS - 1)
        page_start = (navigator.index // MENU_ROWS) * MENU_ROWS
        for page_offset, item_index in enumerate(
                range(page_start, min(page_start + MENU_ROWS, len(navigator.items)))):
            item = navigator.items[item_index]
            point_index = column * MENU_ROWS + page_offset
            if item_index == navigator.index:
                points[point_index] = selected_state
            elif item.tactile_state != TactileState.OFF:
                points[point_index] = item.tactile_state
