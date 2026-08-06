"""
ui/observador_qt.py — ObservadorQt: traduce los eventos de
ObservadorDeFlujo (orchestrator/contratos.py, ya definido desde la
Fase 3) a señales Qt, para que corran de forma segura entre el hilo del
orquestador (ver hilo_orquestador.py) y el hilo principal de la UI.

DECISIÓN de arquitectura:
    ObservadorDeFlujo NO es un QObject (orchestrator/ no depende de Qt,
    por diseño — sigue sin depender de ningún framework gráfico). Por
    eso ObservadorQt es un adaptador: internamente posee un QObject
    (SenalesFlujo) con las señales reales, y cada método de
    ObservadorDeFlujo simplemente emite la señal correspondiente.

    Qt garantiza que una señal emitida desde un hilo distinto al del
    receptor se entrega de forma segura (QueuedConnection automática)
    siempre que el objeto receptor viva en el hilo correcto — por eso
    SenalesFlujo debe crearse en el hilo principal (antes de mover
    HiloOrquestador a su propio QThread) y las pantallas deben conectar
    sus slots a estas señales desde el hilo principal, nunca desde
    dentro del hilo del orquestador.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal as Signal

from lux_eyes.common.tipos import ResultadoOjo
from lux_eyes.orchestrator.contratos import ObservadorDeFlujo
from lux_eyes.orchestrator.maquina_estados import EstadoFlujo


class SenalesFlujo(QObject):
    """
    Las señales Qt reales. Separado de ObservadorQt porque las señales
    deben declararse en una subclase de QObject a nivel de clase (no se
    pueden definir dinámicamente en __init__), y porque así SenalesFlujo
    puede crearse explícitamente en el hilo principal antes de que
    ObservadorQt empiece a usarse desde el hilo del orquestador.
    """

    cambio_de_estado = Signal(object, object)          # (EstadoFlujo | None, EstadoFlujo)
    inicio_formulario = Signal()
    captura_iniciada = Signal(str)                      # ojo
    progreso_captura = Signal(str, str)                  # (ojo, mensaje)
    captura_finalizada = Signal(str, object)             # (ojo, ResultadoOjo)
    procesamiento_iniciado = Signal()
    procesamiento_finalizado = Signal(object, object, str)  # (riesgo, requiere_derivacion, obs)
    resultado_listo = Signal()
    almacenamiento_completado = Signal(str)              # uuid_local
    error = Signal(object, str)                           # (EstadoFlujo, mensaje)
    cancelacion = Signal(object)                           # EstadoFlujo


class ObservadorQt(ObservadorDeFlujo):
    """
    Implementación real de ObservadorDeFlujo para la UI. Cada método
    reenvía el evento a SenalesFlujo — nunca actualiza widgets
    directamente (eso lo hacen las pantallas, conectadas a las señales,
    ya en el hilo principal).
    """

    def __init__(self, senales: SenalesFlujo | None = None):
        self.senales = senales or SenalesFlujo()

    def en_cambio_de_estado(
        self, estado_anterior: EstadoFlujo | None, estado_nuevo: EstadoFlujo
    ) -> None:
        self.senales.cambio_de_estado.emit(estado_anterior, estado_nuevo)

    def en_inicio_formulario(self) -> None:
        self.senales.inicio_formulario.emit()

    def en_captura_iniciada(self, ojo: str) -> None:
        self.senales.captura_iniciada.emit(ojo)

    def en_progreso_captura(self, ojo: str, mensaje: str) -> None:
        self.senales.progreso_captura.emit(ojo, mensaje)

    def en_captura_finalizada(self, ojo: str, resultado: ResultadoOjo) -> None:
        self.senales.captura_finalizada.emit(ojo, resultado)

    def en_procesamiento_iniciado(self) -> None:
        self.senales.procesamiento_iniciado.emit()

    def en_procesamiento_finalizado(
        self, riesgo: str | None, requiere_derivacion: bool | None, observaciones: str
    ) -> None:
        self.senales.procesamiento_finalizado.emit(riesgo, requiere_derivacion, observaciones)

    def en_resultado_listo(self) -> None:
        self.senales.resultado_listo.emit()

    def en_almacenamiento_completado(self, uuid_local: str) -> None:
        self.senales.almacenamiento_completado.emit(uuid_local)

    def en_error(self, estado: EstadoFlujo, mensaje: str) -> None:
        self.senales.error.emit(estado, mensaje)

    def en_cancelacion(self, estado_anterior: EstadoFlujo) -> None:
        self.senales.cancelacion.emit(estado_anterior)
