"""
ui/hilo_sync.py — HiloSync: ejecuta SincronizadorWeb.ejecutar_ciclo() en su
propio QThread, disparado manualmente por el botón "Sincronizar ahora" de
VentanaPrincipal (decisión aprobada: sincronización manual, no automática
ni por proceso aparte).

Mismo patrón que hilo_orquestador.py — QObject.moveToThread(), comandos en
un QObject que vive en el hilo principal, resultado devuelto por señales
que Qt entrega de forma segura entre hilos.
"""

from __future__ import annotations

import logging

from PyQt5.QtCore import QObject, QThread, pyqtSignal as Signal, pyqtSlot as Slot

from lux_eyes.sync.sincronizador import ResumenSincronizacion, SincronizadorWeb

logger = logging.getLogger("lux_eyes.ui")


class ComandosSync(QObject):
    """Vive en el hilo principal. La UI emite esto; Qt lo entrega al hilo de sync/."""
    sincronizar_ahora = Signal()


class SenalesSync(QObject):
    """Vive en el hilo principal. El hilo de sync/ emite esto al terminar."""
    sincronizacion_iniciada = Signal()
    sincronizacion_completada = Signal(object)  # ResumenSincronizacion
    sincronizacion_fallo = Signal(str)


class SyncWorker(QObject):
    """Vive en el QThread de HiloSync. Posee la única instancia de SincronizadorWeb."""

    def __init__(self, repo, cliente, config, senales: SenalesSync):
        super().__init__()
        self._sincronizador = SincronizadorWeb(repo, cliente, config)
        self._senales = senales

    def conectar(self, comandos: ComandosSync) -> None:
        comandos.sincronizar_ahora.connect(self._sincronizar)

    @Slot()
    def _sincronizar(self) -> None:
        self._senales.sincronizacion_iniciada.emit()
        try:
            resumen: ResumenSincronizacion = self._sincronizador.ejecutar_ciclo()
            self._senales.sincronizacion_completada.emit(resumen)
        except Exception as error:
            # Cualquier fallo inesperado (no solo ErrorSincronizacion, que
            # ejecutar_ciclo() ya maneja internamente) se reporta a la UI
            # en vez de dejar el hilo de sync/ en un estado desconocido
            # para el siguiente clic del botón.
            logger.exception("Fallo inesperado durante la sincronización manual.")
            self._senales.sincronizacion_fallo.emit(str(error))


class HiloSync:
    """Empaqueta el QThread, el SyncWorker y el ComandosSync. Una sola instancia por proceso."""

    def __init__(self, repo, cliente, config):
        self._hilo = QThread()
        self._hilo.setObjectName("HiloSync")
        self.senales = SenalesSync()
        self.worker = SyncWorker(repo, cliente, config, self.senales)
        self.worker.moveToThread(self._hilo)
        self.comandos = ComandosSync()
        self.worker.conectar(self.comandos)
        self._hilo.start()

    def detener(self) -> None:
        self._hilo.quit()
        self._hilo.wait()
