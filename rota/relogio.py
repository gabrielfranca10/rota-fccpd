"""Relógio injetável. Horário de Brasília = UTC-3 fixo (sem horário de verão desde 2019).

Usamos offset fixo em vez de zoneinfo para funcionar no Windows sem o pacote tzdata.
"""
import threading
from datetime import date, datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3), "BRT")


class Relogio:
    def agora(self) -> datetime:
        return datetime.now(BRT)

    def hoje(self) -> date:
        return self.agora().date()


class RelogioSimulado(Relogio):
    """Relógio controlável (testes e demonstração: 'avançar o tempo')."""

    def __init__(self, inicio: datetime) -> None:
        self._lock = threading.Lock()
        self._agora = inicio

    def agora(self) -> datetime:
        with self._lock:
            return self._agora

    def avancar(self, **delta) -> datetime:
        with self._lock:
            self._agora += timedelta(**delta)
            return self._agora
