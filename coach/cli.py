import typer
from coach.commands import assess, log, plan, report, setup, status

app = typer.Typer(name="coach", help="Exercise Coach — Apple Notes fitness CLI")
app.add_typer(setup.app, name="setup")
app.command("plan")(plan.run)
app.command("assess")(assess.run)
app.command("log")(log.run)
app.command("report")(report.run)
app.command("status")(status.run)
