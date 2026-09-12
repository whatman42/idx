from __future__ import annotations
import typer
app = typer.Typer()
@app.command()
def main(out_dir: str = typer.Option("models/candidates"),
         min_oos_accuracy: float = typer.Option(0.0),
         promote: bool = typer.Option(False)):
    print({"status": "ok", "promote": promote, "out_dir": out_dir})
if __name__ == "__main__":
    app()
