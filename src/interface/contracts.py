"""Stable contracts shared by lenses, the screen shell, and hardware adapters."""

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from time import monotonic


class TactileState(IntEnum):
    OFF = 0
    LOW = 1
    HIGH = 2


@dataclass(frozen=True)
class TactileFrame:
    """Exactly one state for each of the twenty tactile points."""

    points: tuple[TactileState, ...]

    def __post_init__(self):
        if len(self.points) != 20:
            raise ValueError("A tactile frame must contain exactly 20 points")
        normalized = tuple(TactileState(point) for point in self.points)
        object.__setattr__(self, "points", normalized)

    @classmethod
    def off(cls):
        return cls((TactileState.OFF,) * 20)


@dataclass(frozen=True)
class HandInputState:
    joystick: float = 0.0
    button_down: bool = False
    button_pressed: bool = False
    timestamp_s: float = field(default_factory=monotonic)

    def __post_init__(self):
        if not -1.0 <= self.joystick <= 1.0:
            raise ValueError("joystick must be between -1 and 1")


class SpeechCategory(str, Enum):
    """The reason a message is spoken, used by the quiet-mode policy."""

    CONTENT = "content"
    CONTEXT = "context"
    OPTION = "option"
    VALUE = "value"
    CHANGE = "change"
    CONFIRMATION = "confirmation"
    ERROR = "error"
    INSTRUCTION = "instruction"


@dataclass(frozen=True)
class SpeechRequest:
    text: str
    interrupt: bool = False
    priority: int = 0
    category: SpeechCategory = SpeechCategory.CONTENT
    instruction_text: str = ""
    clip_id: str = ""


@dataclass(frozen=True)
class LensOutput:
    tactile: TactileFrame = field(default_factory=TactileFrame.off)
    header_text: str = ""
    info_title: str = ""
    info_lines: tuple[str, ...] = ()
    view_mode: str = "map"
    speech: tuple[SpeechRequest, ...] = ()
    view_payload: object = None


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    value_type: str
    default: object
    description: str = ""
    choices: tuple[object, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choice_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class LensManifest:
    lens_id: str
    name: str
    description: str
    settings: tuple[SettingSpec, ...] = ()


class Lens:
    """Base class for a modular lens."""

    manifest = LensManifest("unnamed", "Unnamed lens", "No description")

    def start(self, context):
        pass

    def update(self, snapshot, input_state):
        return LensOutput()

    def destroy(self):
        pass
