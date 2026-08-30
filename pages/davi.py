"""Página mobile do motorista, disponível em /davi."""

from pathlib import Path
import runpy


runpy.run_path(
    str(Path(__file__).parents[1] / "app.py"),
    run_name="__main__",
    init_globals={"APROAR_DAVI_MODE": True},
)
