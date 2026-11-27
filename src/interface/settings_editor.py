"""Reusable settings editor built on the tactile menu navigator."""

from dataclasses import dataclass, replace

from .contracts import (
    Lens, LensManifest, LensOutput, SettingSpec, SpeechCategory,
    SpeechMessageType, SpeechPart, SpeechRequest,
)
from .menu import MenuItem, MenuNavigator


_VALUE_AUDIO_KEYS = {
    "on": "settings.value.on",
    "off": "settings.value.off",
    "true": "settings.value.true",
    "false": "settings.value.false",
}


def _value_audio_part(spec, value):
    spoken = SettingsEditor._format(spec, value)
    normalized = spoken.rstrip(".").lower()
    clip_id = _VALUE_AUDIO_KEYS.get(normalized, "")
    text = spoken if spoken.endswith(".") else f"{spoken}."
    return SpeechPart(text, clip_id)


def _setting_audio_parts(spec, value, include_current=True):
    parts = [SpeechPart(spec.label, spec.label_audio_key)]
    if include_current:
        parts.append(SpeechPart("Current value", "settings.current_value"))
    parts.append(_value_audio_part(spec, value))
    return tuple(parts)


@dataclass
class SettingsTarget:
    scope_id: str
    title: str
    registry: object
    on_commit: object = None
    on_leave: object = None


class SettingsEditor:
    LIST = "list"
    VALUE = "value"
    REVIEW = "review"

    def __init__(self, target):
        self.target = target
        self.transaction = target.registry.transaction(target.scope_id)
        self.state = self.LIST
        self.active_spec = None
        self._build_list()
        self._last_output = LensOutput()
        self._review_summary_pending = False

    def _build_list(self):
        items = []
        for spec in self.target.registry.specs(self.target.scope_id):
            items.append(MenuItem(
                spec.key, spec.label, spec.description,
                value_provider=lambda spec=spec: self._format(spec, self.transaction.get(spec.key)),
                select=lambda spec=spec: self._open_value(spec),
                audio_parts_provider=lambda spec=spec: _setting_audio_parts(
                    spec, self.transaction.get(spec.key)
                ),
            ))
        items.append(MenuItem(
            "reset_defaults", "Reset all settings to defaults",
            "Restore every setting in this group.", select=self._reset_all,
        ))
        items.append(MenuItem(
            "finish", "Finish settings", select=self._begin_review,
        ))
        items.append(MenuItem(
            "help", "Repeat menu instructions", "Speak the menu controls again.",
        ))
        if self.target.on_leave:
            items.append(MenuItem(
                "back", "Back", "Leave settings without changing the current screen.",
                select=self.target.on_leave,
            ))
        self.menu = MenuNavigator(
            self.target.title, items,
            instructions=(
                "Move the joystick to slide through options.",
                "Press the button to select.",
            ),
            instruction_id="settings.instructions",
        )

    def update(self, snapshot, input_state):
        if self.state == self.LIST:
            result = self.menu.update(input_state)
            if result.selected is not None and result.selected.select is not None:
                result.selected.select()
            speech = result.speech
            if result.selected is not None and result.selected.key == "help":
                speech += self.menu.instruction_speech()
            if self.state == self.LIST:
                output = self.menu.output(MenuResultCompat(speech))
            else:
                output = self._last_output
        elif self.state == self.VALUE:
            output = self._update_value(input_state)
        else:
            output = self._update_review(input_state)
        self._last_output = output
        return output

    def _open_value(self, spec):
        self.active_spec = spec
        if spec.value_type in ("bool", "choice") or spec.choices:
            values = spec.choices or (False, True)
            labels = spec.choice_labels or tuple(self._format(spec, value) for value in values)
            self.value_menu = MenuNavigator(
                spec.label,
                [MenuItem(
                    str(value), label,
                    value_provider=lambda value=value: self._format(spec, value),
                    select=lambda value=value: self._choose_value(value),
                    audio_parts_provider=lambda value=value: _setting_audio_parts(
                        spec, value
                    ),
                )
                 for value, label in zip(values, labels)],
                instructions=("Move the joystick to choose a value.", "Press the button to accept."),
                instruction_id="settings.value.instructions",
            )
            self.value_menu.index = max(0, list(values).index(self.transaction.get(spec.key)))
            self.value_menu.enter()
            self.state = self.VALUE
        else:
            self.value_menu = MenuNavigator(
                spec.label,
                [MenuItem(
                    "value", spec.label,
                    value_provider=lambda: self._format(
                        spec, self.transaction.get(spec.key)
                    ),
                )],
                instructions=(
                    "Move the joystick to choose a value.",
                    "Press the button to accept.",
                ),
                instruction_id="settings.value.instructions",
            )
            self.state = self.VALUE

    def _choose_value(self, value):
        self.transaction.set(self.active_spec.key, value)
        self._accepted_speech = (SpeechRequest(
            f"{self.active_spec.label}. {self._format(self.active_spec, value)} accepted.",
            category=SpeechCategory.CHANGE,
            message_id=f"settings.{self.active_spec.key}.accepted",
            message_type=SpeechMessageType.MENU_OPTION,
            audio_parts=(
                SpeechPart(self.active_spec.label, self.active_spec.label_audio_key),
                _value_audio_part(self.active_spec, value),
                SpeechPart("accepted.", "settings.accepted"),
            ),
        ),)
        self.state = self.LIST
        self.menu._announce = True

    def _update_value(self, input_state):
        spec = self.active_spec
        if hasattr(self, "value_menu") and (spec.value_type in ("bool", "choice") or spec.choices):
            result = self.value_menu.update(input_state)
            if result.selected is not None and result.selected.select:
                result.selected.select()
            if self.state == self.LIST:
                speech = getattr(self, "_accepted_speech", ())
                self._accepted_speech = ()
                return self.menu.output(MenuResultCompat(speech), header_text=self.menu.title)
            output = self.value_menu.output(result)
            return replace(output, menu_layers=(self.menu, self.value_menu))

        direction = self.menu._direction(input_state)
        if direction:
            step = spec.step or 1
            value = self.transaction.get(spec.key) + direction * step
            if spec.minimum is not None:
                value = max(spec.minimum, value)
            if spec.maximum is not None:
                value = min(spec.maximum, value)
            self.transaction.set(spec.key, value)
            speech = (SpeechRequest(
                f"{spec.label}. {self._format(spec, value)}",
                category=SpeechCategory.CHANGE,
                message_id=f"settings.{spec.key}.changed",
                message_type=SpeechMessageType.MENU_OPTION,
                audio_parts=(
                    SpeechPart(spec.label, spec.label_audio_key),
                    _value_audio_part(spec, value),
                ),
            ),)
        else:
            speech = ()
        if input_state.button_pressed:
            self.state = self.LIST
            self.menu._announce = True
        output = self.menu.output(MenuResultCompat(speech), header_text=spec.label)
        return replace(output, menu_layers=(self.menu, self.value_menu))

    def _reset_all(self):
        self.transaction.reset()
        self.menu._announce = True

    def _begin_review(self):
        self.review_menu = MenuNavigator(
            "Review changes",
            [
                MenuItem("save", "Save and leave", select=self._save),
                MenuItem("continue", "Continue editing", select=self._continue_editing),
                MenuItem("discard", "Discard changes", select=self._discard),
            ],
            instructions=("Choose what to do with the changes.", "Press the button to select."),
            instruction_id="settings.review.instructions",
        )
        self._review_summary_pending = True
        self.state = self.REVIEW

    def _update_review(self, input_state):
        result = self.review_menu.update(input_state)
        speech = result.speech
        if self._review_summary_pending:
            speech = (SpeechRequest(
                self._change_summary(),
                category=SpeechCategory.CONFIRMATION,
                message_id="settings.review.summary",
                message_type=SpeechMessageType.INSTRUCTION,
            ),) + speech
            self._review_summary_pending = False
        if result.selected is not None and result.selected.select:
            result.selected.select()
        if self.state == self.REVIEW:
            output = self.review_menu.output(
                MenuResultCompat(speech), header_text="Review changes"
            )
            return replace(output, menu_layers=(self.menu, self.review_menu))
        return self._last_output

    def _change_summary(self):
        parts = []
        for spec in self.target.registry.specs(self.target.scope_id):
            if spec.key in self.transaction.changed():
                old, new = self.transaction.changed()[spec.key]
                parts.append(f"{spec.label}: {self._format(spec, old)} to {self._format(spec, new)}")
        return "You are saving " + str(len(parts)) + " change(s). " + "; ".join(parts)

    def _save(self):
        self.transaction.commit()
        if self.target.on_commit:
            self.target.on_commit()
        self.state = self.LIST
        self.menu._announce = True
        if self.target.on_leave:
            self.target.on_leave()

    def _continue_editing(self):
        self.state = self.LIST
        self.menu._announce = True

    def _discard(self):
        self.transaction = self.target.registry.transaction(self.target.scope_id)
        self.state = self.LIST
        self.menu._announce = True
        if self.target.on_leave:
            self.target.on_leave()

    @staticmethod
    def _format(spec, value):
        if spec.choice_labels and spec.choices and value in spec.choices:
            return spec.choice_labels[list(spec.choices).index(value)]
        if isinstance(value, float):
            return f"{value:g}"
        return str(value)


class MenuResultCompat:
    def __init__(self, speech):
        self.speech = speech
        self.selected = None


class SettingsLens(Lens):
    manifest = LensManifest(
        "system_settings", "System Settings", "Edit overall device settings."
    )

    def start(self, context):
        target = SettingsTarget(
            "system", "System Settings", context.settings,
            on_leave=lambda: context.controller.start("main_menu"),
        )
        self.editor = SettingsEditor(target)

    def update(self, snapshot, input_state):
        return self.editor.update(snapshot, input_state)

    def destroy(self):
        self.editor = None
