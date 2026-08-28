"""Rota limpa /davi para o App do Motorista da Aproar.

Este arquivo deve ficar em pages/davi.py no mesmo repositório do app.py.
Ele reaproveita exatamente o mesmo código/estado do app principal, apenas ativando
o modo do motorista sem expor ?davi=true na URL.
"""
from pathlib import Path
import runpy

APP_PRINCIPAL = Path(__file__).resolve().parents[1] / "app.py"

runpy.run_path(
    str(APP_PRINCIPAL),
    init_globals={"APROAR_DAVI_MODE": True},
    run_name="__main__",
)
