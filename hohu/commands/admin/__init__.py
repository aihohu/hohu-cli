import typer

from hohu.commands.admin.create import create
from hohu.commands.admin.dev import dev
from hohu.commands.admin.init import init

admin_app = typer.Typer(help="Admin commands for projects")

admin_app.command(name="create")(create)
admin_app.command(name="init")(init)
admin_app.command(name="dev")(dev)
