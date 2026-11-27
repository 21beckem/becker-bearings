"""Self-describing, immediately-committed settings menus."""

from dataclasses import dataclass, replace

from .contracts import (
    Lens, LensManifest, LensOutput, SettingSpec, SpeechCategory,
    SpeechMessageType, SpeechPart, SpeechRequest,
)
from .menu import MenuItem, MenuNavigator


_VALUE_AUDIO_KEYS = {
    "on": "settings.value.on",
    "off": "settings.value.off",
    "0.5": "settings.value.0_5",
    "1": "settings.value.1",
    "2": "settings.value.2",
    "3": "settings.value.3",
}

def _value_audio_part(spec, value, allow_tts=True):
    spoken = SettingsEditor._format(spec, value)
    normalized = spoken.rstrip(".").lower()
    clip_id = _VALUE_AUDIO_KEYS.get(normalized, "")
    text = spoken if spoken.endswith(".") else f"{spoken}."
    return SpeechPart(text, clip_id, allow_tts=allow_tts)


def _action_audio_parts(spec, action, value):
    action_text = {
        "leave": "Leave",
        "keep": "Keep",
        "turn": "Turn",
        "set_to": "Set to",
    }[action]
    normalized = SettingsEditor._format(spec, value).rstrip(".").lower()
    normalized = normalized.replace(".", "_").replace(" ", "_")
    clip_id = f"settings.action.{action}.{normalized}"
    return (SpeechPart(
        f"{action_text} {SettingsEditor._format(spec, value)}",
        clip_id,
        allow_tts=False,
    ),)


def _setting_audio_parts(spec, value, include_current=True):
    parts = [SpeechPart(spec.label, spec.label_audio_key)]
    if include_current:
        parts.append(SpeechPart("currently", "settings.current_value"))
    parts.append(_value_audio_part(spec, value))
    return tuple(parts)


def _setting_clip_id(scope_id, suffix, key):
    return f"settings.info.{scope_id}.{key}.{suffix}"


def _value_token(spec, value):
    token = SettingsEditor._format(spec, value).rstrip(".").lower()
    return token.replace(".", "_").replace(" ", "_")


def _apply_audio_part(scope_id, spec, value):
    return SpeechPart(
        f"Apply change: {spec.label.lower()} "
        f"{SettingsEditor._format(spec, value)}",
        f"settings.confirm.apply.{scope_id}.{spec.key}.{_value_token(spec, value)}",
        allow_tts=False,
    )


def _result_audio_parts(result_clip_id):
    return (SpeechPart(
        "Setting updated." if result_clip_id == "settings.updated"
        else "Edit canceled.",
        result_clip_id,
        allow_tts=False,
    ),)


@dataclass
class SettingsTarget:
    scope_id: str
    title: str
    registry: object
    on_commit: object = None
    on_leave: object = None


class SettingsEditor:
    LIST = "list"
    EDIT = "edit"
    CONFIRM = "confirm"

    def __init__(self, target):
        self.target = target
        self.state = self.LIST
        self.active_spec = None
        self.original_value = None
        self.pending_value = None
        self._confirm_layers = ()
        self._transition_speech = ()
        self._restore_feedback_before_announcement = False
        self._build_list()

    def _build_list(self):
        items = []
        for spec in self.target.registry.specs(self.target.scope_id):
            items.append(MenuItem(
                spec.key,
                spec.label,
                spec.description,
                value_provider=lambda spec=spec: self._format(
                    spec, self.target.registry.get(self.target.scope_id, spec.key)
                ),
                select=lambda spec=spec: self._open_setting(spec),
                audio_parts_provider=lambda spec=spec: _setting_audio_parts(
                    spec, self.target.registry.get(self.target.scope_id, spec.key)
                ),
                value_prefix="currently",
            ))
        items.append(MenuItem(
            "reset_defaults",
            "Reset all settings to defaults",
            "Restore every setting in this group.",
            select=self._begin_reset,
        ))
        items.append(MenuItem(
            "help", "Repeat menu instructions", "Speak the menu controls again.",
        ))
        if self.target.on_leave:
            items.append(MenuItem(
                "back", "Back", "Leave settings and return to the previous menu.",
                select=self.target.on_leave,
            ))
        self.menu = MenuNavigator(
            self.target.title,
            items,
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
            if result.selected is not None and result.selected.key == "help":
                result = type(result)(
                    speech=result.speech + self.menu.instruction_speech(),
                    moved=result.moved,
                )
            if self._restore_feedback_before_announcement:
                self._restore_feedback_before_announcement = False
                if not result.moved and result.selected is None:
                    self.menu._announce = True
                    result = type(result)(speech=(), moved=result.moved)
            if self.state == self.LIST:
                output = self.menu.output(
                    MenuResultCompat(result.speech + self._take_transition_speech())
                )
            else:
                output = self._output_after_transition()
        elif self.state == self.EDIT:
            result = self.edit_menu.update(input_state)
            if result.selected is not None and result.selected.select is not None:
                result.selected.select()
            if self.state == self.EDIT:
                output = self._edit_output(
                    result.speech + self._take_transition_speech()
                )
            else:
                output = self._output_after_transition()
        else:
            result = self.confirm_menu.update(input_state)
            if result.selected is not None and result.selected.select is not None:
                result.selected.select()
            if self.state == self.CONFIRM:
                output = self._confirm_output(
                    result.speech + self._take_transition_speech()
                )
            else:
                output = self._output_after_transition()
        self._last_output = output
        return output

    def _open_setting(self, spec):
        self.active_spec = spec
        self.original_value = self.target.registry.get(self.target.scope_id, spec.key)
        values = self._candidate_values(spec, self.original_value)
        actions = [MenuItem(
            "keep",
            self._keep_label(spec, self.original_value),
            select=self._cancel_setting,
            audio_parts_provider=lambda spec=spec: _action_audio_parts(
                spec,
                "leave" if spec.value_type == "bool" else "keep",
                self.original_value,
            ),
        )]
        for value in values:
            if value == self.original_value:
                continue
            actions.append(MenuItem(
                f"set.{value}",
                self._change_label(spec, value),
                select=lambda value=value: self._begin_setting_confirmation(value),
                audio_parts_provider=lambda value=value, spec=spec: _action_audio_parts(
                    spec,
                    "turn" if spec.value_type == "bool" else "set_to",
                    value,
                ),
            ))
        if spec.description:
            actions.append(MenuItem(
                "info",
                f"Hear what {spec.label.lower()} does",
                description=spec.description,
                select=self._play_info,
                audio_parts_provider=lambda: (
                    SpeechPart(
                        f"Hear what {spec.label.lower()} does.",
                        _setting_clip_id(
                            self.target.scope_id, "option", spec.key
                        ),
                        allow_tts=False,
                    ),
                ),
            ))
        self.edit_menu = MenuNavigator(spec.label, actions, instructions=())
        self._prime_menu(self.edit_menu)
        self.state = self.EDIT
        self._transition_speech = (
            SpeechRequest(
                f"{spec.label}. Choose an action.",
                category=SpeechCategory.CONTEXT,
                message_id=f"settings.{spec.key}.edit",
                message_type=SpeechMessageType.MENU_OPTION,
            ),
            *self.edit_menu._speech_for_current(),
        )

    def _begin_setting_confirmation(self, value):
        spec = self.active_spec
        self.pending_value = value
        self.confirm_menu = MenuNavigator(
            spec.label,
            [
                MenuItem(
                    "cancel",
                    "Cancel this change",
                    select=self._cancel_setting,
                    audio_parts_provider=lambda: (
                        SpeechPart(
                            "Cancel this change",
                            "settings.confirm.cancel_change",
                            allow_tts=False,
                        ),
                    ),
                ),
                MenuItem(
                    "apply",
                    f"Apply change: {spec.label.lower()} "
                    f"{self._format(spec, value)}",
                    select=self._apply_setting,
                    audio_parts_provider=lambda: (_apply_audio_part(
                        self.target.scope_id, spec, value
                    ),),
                ),
            ],
            instructions=(),
        )
        self.confirm_menu.index = 1
        self._prime_menu(self.confirm_menu)
        self._confirm_layers = (self.menu, self.edit_menu, self.confirm_menu)
        self.state = self.CONFIRM
        self._transition_speech = (
            SpeechRequest(
                f"Change {spec.label.lower()} from "
                f"{self._format(spec, self.original_value)} to "
                f"{self._format(spec, value)}?",
                category=SpeechCategory.CONFIRMATION,
                message_id=f"settings.{spec.key}.confirm",
                message_type=SpeechMessageType.MENU_OPTION,
            ),
            *self.confirm_menu._speech_for_current(),
        )

    def _begin_reset(self):
        self.confirm_menu = MenuNavigator(
            "Reset settings",
            [
                MenuItem("cancel", "Cancel reset", select=self._cancel_reset),
                MenuItem("apply", "Apply reset", select=self._apply_reset),
            ],
            instructions=(),
        )
        self._prime_menu(self.confirm_menu)
        self._confirm_layers = (self.menu, self.confirm_menu)
        self.state = self.CONFIRM
        self._transition_speech = (
            SpeechRequest(
                "Reset all settings to defaults?",
                category=SpeechCategory.CONFIRMATION,
                message_id="settings.reset.confirm",
                message_type=SpeechMessageType.MENU_OPTION,
            ),
            *self.confirm_menu._speech_for_current(),
        )

    def _play_info(self):
        spec = self.active_spec
        self._transition_speech = (SpeechRequest(
            spec.description,
            category=SpeechCategory.CONTENT,
            message_id=f"settings.{spec.key}.info",
            message_type=SpeechMessageType.MENU_OPTION,
            audio_parts=(SpeechPart(
                spec.description,
                _setting_clip_id(self.target.scope_id, "description", spec.key),
                allow_tts=False,
            ),),
        ),)

    def _cancel_setting(self):
        spec = self.active_spec
        self.state = self.LIST
        # Release the grip first, then announce the selected list item on the
        # following update.
        self.menu._announce = True
        self._restore_feedback_before_announcement = True
        self._transition_speech = (SpeechRequest(
            f"Edit canceled. {spec.label} currently "
            f"{self._format(spec, self.original_value)}.",
            category=SpeechCategory.CHANGE,
            message_id=f"settings.{spec.key}.canceled",
            message_type=SpeechMessageType.MENU_OPTION,
            blocks_tactile=True,
            audio_parts=_result_audio_parts("settings.edit_canceled"),
        ),)

    def _apply_setting(self):
        spec = self.active_spec
        old_value = self.original_value
        new_value = self.pending_value
        values = self.target.registry.values(self.target.scope_id)
        values[spec.key] = new_value
        self.target.registry.commit(self.target.scope_id, values)
        if self.target.on_commit:
            self.target.on_commit()
        self.state = self.LIST
        # Release the grip first, then announce the selected list item on the
        # following update.
        self.menu._announce = True
        self._restore_feedback_before_announcement = True
        self._transition_speech = (SpeechRequest(
            f"{spec.label} changed from {self._format(spec, old_value)} "
            f"to {self._format(spec, new_value)}.",
            category=SpeechCategory.CHANGE,
            message_id=f"settings.{spec.key}.changed",
            message_type=SpeechMessageType.MENU_OPTION,
            blocks_tactile=True,
            audio_parts=_result_audio_parts("settings.updated"),
        ),)

    def _cancel_reset(self):
        self.state = self.LIST
        self.menu._announce = True
        self._transition_speech = (SpeechRequest(
            "Reset canceled.",
            category=SpeechCategory.CHANGE,
            message_id="settings.reset.canceled",
            message_type=SpeechMessageType.MENU_OPTION,
        ),)

    def _apply_reset(self):
        self.target.registry.commit_defaults(self.target.scope_id)
        if self.target.on_commit:
            self.target.on_commit()
        self.state = self.LIST
        self.menu._announce = True
        self._transition_speech = (SpeechRequest(
            "All settings reset to defaults.",
            category=SpeechCategory.CHANGE,
            message_id="settings.reset.applied",
            message_type=SpeechMessageType.MENU_OPTION,
        ),)

    def _output_after_transition(self):
        speech = self._take_transition_speech()
        if self.state == self.EDIT:
            return self._edit_output(speech)
        if self.state == self.CONFIRM:
            return self._confirm_output(speech)
        return self.menu.output(MenuResultCompat(speech))

    def _edit_output(self, speech):
        output = self.edit_menu.output(
            MenuResultCompat(speech), header_text=self.menu.title
        )
        return replace(output, menu_layers=(self.menu, self.edit_menu))

    def _confirm_output(self, speech):
        output = self.confirm_menu.output(
            MenuResultCompat(speech), header_text=self.menu.title
        )
        return replace(output, menu_layers=self._confirm_layers)

    def _take_transition_speech(self):
        speech = self._transition_speech
        self._transition_speech = ()
        return speech

    @staticmethod
    def _prime_menu(menu):
        menu.enter()
        menu._entered = True
        menu._announce = False

    @staticmethod
    def _keep_label(spec, value):
        verb = "Leave" if spec.value_type == "bool" else "Keep"
        return f"{verb} {SettingsEditor._format(spec, value)}"

    @staticmethod
    def _change_label(spec, value):
        formatted = SettingsEditor._format(spec, value)
        if spec.value_type == "bool":
            return f"Turn {formatted}"
        return f"Set to {formatted}"

    @staticmethod
    def _candidate_values(spec, current):
        if spec.choices:
            return tuple(spec.choices)
        if spec.value_type == "bool":
            return (False, True)
        if spec.value_type not in ("int", "float"):
            return ()
        step = spec.step or 1
        values = []
        for direction in (-1, 1):
            value = current + direction * step
            if spec.minimum is not None:
                value = max(spec.minimum, value)
            if spec.maximum is not None:
                value = min(spec.maximum, value)
            if value != current and value not in values:
                values.append(value)
        return tuple(values)

    @staticmethod
    def _format(spec, value):
        if isinstance(value, bool):
            return "on" if value else "off"
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
