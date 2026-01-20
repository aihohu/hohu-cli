import typer
from rich.console import Console

from hohu import __version__
from hohu.commands.admin import admin_app
from hohu.commands.system import set_language, show_info, system_app

app = typer.Typer(name="hohu", help="HoHu CLI Tool", no_args_is_help=True)
console = Console()


def version_callback(value: bool):
    if value:
        from rich.console import Console

        console = Console()
        console.print(
            f"🚀 [bold cyan]HoHu CLI[/bold cyan] Version: [green]{__version__}[/green]"
        )
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version",
    ),
):
    """HoHu 全能开发管理工具"""
    pass


app.add_typer(admin_app, name="admin")
app.add_typer(system_app, name="system")

app.command(name="lang")(set_language)
app.command(name="info")(show_info)

if __name__ == "__main__":
    app()
