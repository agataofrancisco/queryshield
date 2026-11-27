"""A baseline insegura não abre sockets de escuta (tarefa 7.3).

O processo do runner (e todos os seus filhos) é observado com psutil durante toda a execução.
Verifica-se que:
  * nenhum socket do processo está em LISTEN (o servidor pgserver é outro processo e fica de fora);
  * o observador vê a ligação de saída do processo à base de dados (senão seria vazia).
Limitação: no Windows o pgserver escuta em 127.0.0.1; isso pertence ao servidor, não à baseline.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from tests.postgres.conftest import PgEnv

pytestmark = pytest.mark.postgres

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_baseline_process_never_listens_on_a_socket(pg_env: PgEnv, tmp_path: Path) -> None:
    env = {
        **os.environ,
        "QS_SANDBOX_ADMIN_DSN": pg_env.admin_dsn,
        "QS_BASELINE_REPORT_DIR": str(tmp_path),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "eval.run_baseline"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    # No Windows, o python de um venv é um lançador que arranca o interpretador real como filho.
    # Observa-se por isso a árvore inteira (raiz e descendentes), em cada amostra.
    root = psutil.Process(proc.pid)
    listening: list[str] = []
    outbound_seen = False
    interpreter_seen = False
    samples = 0
    deadline = time.monotonic() + 600
    while proc.poll() is None:
        if time.monotonic() > deadline:
            proc.kill()
            pytest.fail("baseline excedeu o tempo limite")
        try:
            tree = [root, *root.children(recursive=True)]
            for member in tree:
                if member.pid != proc.pid and "python" in member.name().lower():
                    interpreter_seen = True
                for conn in member.net_connections(kind="inet"):
                    if conn.status == psutil.CONN_LISTEN:
                        listening.append(f"pid {member.pid} {conn.laddr}")
                    if conn.status == psutil.CONN_ESTABLISHED and conn.raddr:
                        outbound_seen = True
        except psutil.Error:
            pass
        samples += 1
        time.sleep(0.05)
    output = proc.communicate()[0].decode("utf-8", errors="replace")
    assert proc.returncode == 0, output[-2000:]
    assert samples > 10, "amostragem insuficiente para afirmar algo"
    assert interpreter_seen, "a observação não incluiu o interpretador real (filho do lançador)"
    assert listening == [], f"a baseline abriu sockets de escuta: {listening}"
    assert outbound_seen, "o observador não viu a ligação de saída à base de dados"
    assert (tmp_path / "baseline-sandbox.json").exists()
