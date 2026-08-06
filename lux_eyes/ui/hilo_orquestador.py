"""
ui/hilo_orquestador.py — HiloOrquestador: ejecuta OrquestadorTamizaje en
su propio QThread, para que sus llamadas bloqueantes (medir_ojo() puede
tardar varios segundos) nunca congelen la interfaz.

DECISIÓN de arquitectura:
    Patrón QObject.moveToThread() (no subclasear QThread y sobreescribir
    run()) — es el patrón recomendado por Qt para trabajo en segundo
    plano con señales/slots, y es el que permite que Qt entregue las
    llamadas entre hilos de forma automática y segura.

    ComandosOrquestador vive en el hilo PRINCIPAL: la UI emite sus
    señales (p. ej. "quiero iniciar un tamizaje nuevo"). OrquestadorWorker
    vive en el hilo del orquestador (dentro del QThread) y sus slots
    están conectados a esas señales. Como emisor y receptor viven en
    hilos distintos, Qt entrega la llamada en cola de forma automática
    (QueuedConnection) — no hace falta gestionar el cruce de hilos a
    mano, ni aquí ni en las pantallas.

    Las respuestas (eventos de ObservadorDeFlujo) viajan en la dirección
    contraria por SenalesFlujo (observador_qt.py), con la misma garantía
    automática de Qt.
"""

from __future__ import annotations

import logging

from PyQt5.QtCore import QObject, QThread, pyqtSignal as Signal, pyqtSlot as Slot

from lux_eyes.orchestrator.excepciones import EstadoInvalidoError
from lux_eyes.orchestrator.orquestador import OrquestadorTamizaje

logger = logging.getLogger("lux_eyes.ui")


class ComandosOrquestador(QObject):
    """
    Vive en el hilo principal. La UI emite estas señales; Qt las entrega
    de forma automática y segura al hilo del orquestador. Ningún método
    de OrquestadorTamizaje se llama nunca directamente desde la UI.
    """

    iniciar_nuevo_tamizaje = Signal()
    recibir_datos_sesion = Signal(str, str, str, str)
    recibir_datos_paciente = Signal(str, str, str, str, str, str)
    ejecutar_captura = Signal(str)
    confirmar_guardado = Signal()
    cancelar = Signal()


class OrquestadorWorker(QObject):
    """
    Vive en el QThread de HiloOrquestador. Posee la única instancia de
    OrquestadorTamizaje del proceso — nunca se construye más de una.
    """

    def __init__(self, repo, motor, clinical, observador):
        super().__init__()
        self._orquestador = OrquestadorTamizaje(
            repo=repo, motor=motor, clinical=clinical, observador=observador
        )

    def conectar(self, comandos: ComandosOrquestador) -> None:
        comandos.iniciar_nuevo_tamizaje.connect(self._iniciar_nuevo_tamizaje)
        comandos.recibir_datos_sesion.connect(self._recibir_datos_sesion)
        comandos.recibir_datos_paciente.connect(self._recibir_datos_paciente)
        comandos.ejecutar_captura.connect(self._ejecutar_captura)
        comandos.confirmar_guardado.connect(self._confirmar_guardado)
        comandos.cancelar.connect(self._cancelar)

    def _ejecutar_seguro(self, fn, *args) -> None:
        """
        EstadoInvalidoError señala un error de PROGRAMACIÓN de la UI
        (llamar a un comando en el estado equivocado) — no un error de
        flujo recuperable (esos ya los reporta ObservadorDeFlujo.en_error
        por su cuenta). Se registra por logging para diagnóstico, nunca
        deja el hilo del orquestador en un estado roto para el siguiente
        comando.
        """
        try:
            fn(*args)
        except EstadoInvalidoError:
            logger.exception(
                "Comando de UI llamado en un estado no válido del orquestador."
            )

    @Slot()
    def _iniciar_nuevo_tamizaje(self) -> None:
        self._ejecutar_seguro(self._orquestador.iniciar_nuevo_tamizaje)

    @Slot(str, str, str, str)
    def _recibir_datos_sesion(self, colegio_nombre, colegio_distrito, tecnologo, fecha_sesion) -> None:
        self._ejecutar_seguro(
            self._orquestador.recibir_datos_sesion,
            colegio_nombre, colegio_distrito, tecnologo, fecha_sesion,
        )

    @Slot(str, str, str, str, str, str)
    def _recibir_datos_paciente(
        self, dni, nombre_paciente, fecha_nacimiento, grado_seccion, email_padre, telefono_padre
    ) -> None:
        self._ejecutar_seguro(
            self._orquestador.recibir_datos_paciente,
            dni, nombre_paciente, fecha_nacimiento, grado_seccion,
            email_padre or None, telefono_padre or None,
        )

    @Slot(str)
    def _ejecutar_captura(self, ojo) -> None:
        self._ejecutar_seguro(self._orquestador.ejecutar_captura, ojo)

    @Slot()
    def _confirmar_guardado(self) -> None:
        self._ejecutar_seguro(self._orquestador.confirmar_guardado)

    @Slot()
    def _cancelar(self) -> None:
        self._ejecutar_seguro(self._orquestador.cancelar)


class HiloOrquestador:
    """
    Empaqueta el QThread, el OrquestadorWorker y el ComandosOrquestador.
    Construir UNA sola instancia por proceso (mismo principio que
    SincronizadorWeb / MotorFotorrefraccionLuxEyes en fases anteriores).
    """

    def __init__(self, repo, motor, clinical, observador):
        self._hilo = QThread()
        self._hilo.setObjectName("HiloOrquestador")
        self.worker = OrquestadorWorker(repo, motor, clinical, observador)
        self.worker.moveToThread(self._hilo)
        self.comandos = ComandosOrquestador()
        self.worker.conectar(self.comandos)
        self._hilo.start()

    def detener(self) -> None:
        """Llamar al cerrar la aplicación, para liberar el QThread limpiamente."""
        self._hilo.quit()
        self._hilo.wait()
