"""Top-level tactile menu."""

from interface.contracts import Lens, LensManifest
from interface.menu import MenuItem, MenuNavigator


class MainMenuLens(Lens):
    manifest = LensManifest(
        lens_id="main_menu",
        name="Main Menu",
        description="Selects a lens or opens system settings.",
    )

    def __init__(self):
        self.menu = None

    def start(self, context):
        items = []
        controller = context.controller
        for lens_id in sorted(controller._factories):
            if lens_id in ("main_menu", "system_settings"):
                continue
            manifest = controller._factories[lens_id]().manifest
            items.append(MenuItem(
                lens_id, manifest.name, manifest.description,
                select=lambda lens_id=lens_id: controller.start(lens_id),
            ))
        items.append(MenuItem(
            "settings", "Settings", "Edit overall device settings.",
            select=lambda: controller.start(
                "system_settings", menu_prefix=(self.menu,)
            ),
        ))
        items.append(MenuItem(
            "help", "Help", "Repeat menu instructions.",
        ))
        self.menu = MenuNavigator(
            self.manifest.name,
            items,
            instructions=(
                "Move the joystick to slide through menu options.",
                "Press the button to select.",
            ),
        )

    def update(self, snapshot, input_state):
        result = self.menu.update(input_state)
        if result.selected is not None and result.selected.select:
            result.selected.select()
        if result.selected is not None and result.selected.key == "help":
            result = type(result)(
                speech=result.speech + self.menu.instruction_speech(),
                moved=result.moved,
            )
        return self.menu.output(result)
