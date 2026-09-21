"""Lock de leitores-escritores com preferência para escritores.

Muitas threads podem LER ao mesmo tempo (calcular hora limite com o estado de trânsito),
mas quem ESCREVE (declara uma janela de pico/bloqueio) precisa de acesso exclusivo.

Preferência para escritores: quando um escritor está esperando, novos leitores aguardam.
Sem isso, um fluxo contínuo de leitores (ingestão em massa) poderia deixar a atualização
do trânsito esperando para sempre (starvation do escritor).
"""
import threading
from contextlib import contextmanager


class RWLock:
    def __init__(self) -> None:
        self._cond = threading.Condition(threading.Lock())
        self._leitores_ativos = 0
        self._escritor_ativo = False
        self._escritores_esperando = 0

    def acquire_read(self) -> None:
        with self._cond:
            while self._escritor_ativo or self._escritores_esperando > 0:
                self._cond.wait()
            self._leitores_ativos += 1

    def release_read(self) -> None:
        with self._cond:
            self._leitores_ativos -= 1
            if self._leitores_ativos == 0:
                self._cond.notify_all()

    def acquire_write(self) -> None:
        with self._cond:
            self._escritores_esperando += 1
            try:
                while self._escritor_ativo or self._leitores_ativos > 0:
                    self._cond.wait()
            finally:
                self._escritores_esperando -= 1
            self._escritor_ativo = True

    def release_write(self) -> None:
        with self._cond:
            self._escritor_ativo = False
            self._cond.notify_all()

    @contextmanager
    def leitura(self):
        self.acquire_read()
        try:
            yield
        finally:
            self.release_read()

    @contextmanager
    def escrita(self):
        self.acquire_write()
        try:
            yield
        finally:
            self.release_write()
