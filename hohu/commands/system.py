import questionary
import typer
from rich.console import Console
from rich.table import Table

from hohu import __version__
from hohu.config import CONFIG_FILE, load_config, save_config
from hohu.i18n import i18n

console = Console()
system_app = typer.Typer(help="System settings & Information")


@system_app.command("info")
def show_info():
    """View system configuration information"""
    config = load_config()

    table = Table(
        title="HoHu CLI System Configuration",
        show_header=False,
        title_style="bold magenta",
    )

    table.add_row("Version", f"[green]{__version__}[/green]")
    table.add_row("Language", f"[cyan]{config.get('language', 'auto')}[/cyan]")
    table.add_row("Config Path", f"[dim]{CONFIG_FILE}[/dim]")
    table.add_row("I18n Status", "[green]Loaded[/green]")

    console.print(table)


@system_app.command("lang")
def set_language():
    """Set the CLI interaction language"""
    choices = [
        questionary.Choice("简体中文", value="zh"),
        questionary.Choice("English", value="en"),
        questionary.Choice("Follow System (跟随系统)", value="auto"),
    ]

    selected_lang = questionary.select(i18n.t("select_lang"), choices=choices).ask()

    if selected_lang:
        config = load_config()
        config["language"] = selected_lang
        save_config(config)

        # 假设 i18n 实例有 refresh 方法
        i18n.refresh()
        console.print(f"[green]✔[/green] {i18n.t('lang_updated')}")
