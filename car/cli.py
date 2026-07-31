"""Interactive startup prompt: which Connection Card is on each device."""

import legoeducation as le
from rich.prompt import Prompt

from car.settings import ConnectionCard
from car.ui import console

CARD_COLORS: dict[str, int] = {
    "green": le.LEGO_COLOR_GREEN,
    "blue": le.LEGO_COLOR_BLUE,
    "red": le.LEGO_COLOR_RED,
    "orange": le.LEGO_COLOR_ORANGE,
    "yellow": le.LEGO_COLOR_YELLOW,
    "azure": le.LEGO_COLOR_AZURE,
    "purple": le.LEGO_COLOR_PURPLE,
    "magenta": le.LEGO_COLOR_MAGENTA,
}


def prompt_connection_card(device_label: str) -> ConnectionCard:
    """Asks for the Card color and serial number."""
    console.print(f"[bold]Which Connection Card is on your {device_label}?[/bold]")
    color_name = Prompt.ask(
        "Card color",
        choices=sorted(CARD_COLORS),
        case_sensitive=False,
    )

    serial = Prompt.ask("Card serial number").strip()
    while not serial:
        serial = Prompt.ask("Card serial number (must not be empty)").strip()

    return ConnectionCard(color_name=color_name, serial=serial)


def get_connection_card(device_label: str, saved: ConnectionCard | None) -> ConnectionCard:
    """Returns the Connection Card saved in settings.json, or asks for it once if not known yet."""
    if saved is not None:
        console.print(f"[bold]{device_label}[/bold] Connection Card: {saved.color_name} / {saved.serial} (saved)")
        return saved
    return prompt_connection_card(device_label)
