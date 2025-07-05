from rich.panel import Panel
from rich.text import Text


class Panels:
    def __init__(self, config):
        self.config = config

    def render_debug_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="left"), title=f"{title}", border_style="bright_black")

    def render_info_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="center"), title=f"{title}", border_style="bright_black")

    def render_status_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="left"), title=f"{title}", border_style=self.config.status_panel_color)

    def render_char_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="center"), title=f"{title}", border_style=self.config.character_panel_color)

    def render_response_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="left"), title=f"{title}", border_style="green")

    def render_map_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="left"), title=f"{title}", border_style=self.config.map_panel_color)

    def render_end_panel(self, title: str, message: str) -> Panel:
        return Panel(Text(message, justify="center"), title=f"{title}", border_style="red")