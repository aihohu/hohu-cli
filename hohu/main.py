import typer
from rich.console import Console

from hohu import __version__
from hohu.commands.admin.build import build
from hohu.commands.admin.create import create
from hohu.commands.admin.deploy import deploy_app
from hohu.commands.admin.dev import dev
from hohu.commands.admin.init import init
from hohu.commands.admin.migrate import migrate
from hohu.commands.admin.monitoring import monitoring_app
from hohu.commands.system import set_language, show_info, system_app
from hohu.i18n import i18n

app = typer.Typer(name="hohu", help=i18n.t("cli_help"), no_args_is_help=True)
console = Console()


def version_callback(value: bool):
    if value:
        from rich.console import Console

        console = Console()
        console.print(
            f"🚀 [bold cyan]HoHu CLI[/bold cyan] Version: [green]{__version__}[/green]"
        )
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help=i18n.t("version_help"),
    ),
):
    pass


app.command(name="create", help=i18n.t("create_help"))(create)
app.command(name="init", help=i18n.t("init_help"))(init)
app.command(name="dev", help=i18n.t("dev_help"))(dev)
app.command(name="build", help=i18n.t("build_help"))(build)
app.command(name="migrate", help=i18n.t("migrate_help"))(migrate)

app.add_typer(deploy_app, name="deploy")
app.add_typer(monitoring_app, name="monitoring")
app.add_typer(system_app, name="system")

app.command(name="lang", help=i18n.t("system_lang_help"))(set_language)
app.command(name="info", help=i18n.t("system_info_help"))(show_info)

if __name__ == "__main__":
    app()
