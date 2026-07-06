"""roles.py — Menu de seleção de função (role) do jogador (camada ui).

A fonte de tecla é INJETÁVEL (`read_key`) para permitir testes automatizados;
o default real é msvcrt.getch(), então em produção o comportamento não muda.
"""

from __future__ import annotations

from collections.abc import Callable

from owpick.infra import storage

MAPPING = {
    "1": "ALL",  # Fila Aberta
    "2": "TANK",  # Tanque
    "3": "SUP",  # Suporte
    "4": "DPS",  # DPS
}


def _default_read_key() -> bytes:
    import msvcrt

    return msvcrt.getch()


def _decode(key) -> str:
    """Normaliza a tecla lida (bytes do msvcrt ou str de um stub) para str."""
    if isinstance(key, bytes):
        try:
            return key.decode()
        except UnicodeDecodeError:
            return ""
    return str(key)


def executar(read_key: Callable[[], object] = _default_read_key) -> str | None:
    """Lê a role escolhida (1..4), grava em Roles.txt e retorna-a."""
    print("1=Fila Aberta  2=Tanque  3=Suporte  4=DPS")
    print("Pressione 1, 2, 3 ou 4...")

    while True:
        key = _decode(read_key())
        if key in MAPPING:
            role = MAPPING[key]
            storage.write_role(role)
            print("Escolhido:", role)
            return role


if __name__ == "__main__":
    executar()
