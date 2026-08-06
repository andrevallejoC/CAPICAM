"""
ui/ventana_principal.py — VentanaPrincipal: conecta las 4 pantallas, el
HiloOrquestador y el gestor de cámara (vista previa en vivo).

DECISIÓN de arquitectura: el gestor de cámara se recibe por inyección
(gestor_camara: cualquier objeto con iniciar_vista_previa(callback) y
detener_vista_previa()) — nunca se importa GestorCamaraCompartida
directamente aquí. Esto permite probar TODA la lógica de navegación y
cableado de esta clase con un doble de prueba, sin picamera2 ni GPIO,
igual que se hizo en engine/ con los Protocols de hardware.

DECISIÓN (Fase 5, aprobada): la reutilización de datos de sesión para
"siguiente niño, mismo colegio" vive AQUÍ, no en orchestrator/ — el
orquestador nunca se modificó para esto, solo se le sigue llamando con
los mismos argumentos que ya aceptaba desde la Fase 3.
"""

from __future__ import annotations

from typing import Callable, Protocol

from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from lux_eyes.common.tipos import ResultadoOjo
from lux_eyes.orchestrator.maquina_estados import EstadoFlujo

from .estilos import hoja_de_estilos
from .hilo_orquestador import HiloOrquestador
from .hilo_sync import HiloSync
from .observador_qt import ObservadorQt
from .pantallas import (
    EncabezadoMarca, PantallaCaptura, PantallaFormularioPaciente,
    PantallaFormularioSesion, PantallaResultado,
)


class GestorCamara(Protocol):
    """Contrato mínimo que VentanaPrincipal necesita del gestor de cámara real."""

    def iniciar_vista_previa(self, callback_frame: Callable[[QImage], None]) -> None: ...
    def detener_vista_previa(self) -> None: ...


class VentanaPrincipal(QMainWindow):
    def __init__(
        self, repo, motor, clinical, gestor_camara: GestorCamara,
        cliente_sync, config_sync, parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Lux Eyes — Tamizaje visual")
        self.setStyleSheet(hoja_de_estilos())

        self._repo = repo
        self._gestor_camara = gestor_camara
        self._observador = ObservadorQt()
        self._hilo = HiloOrquestador(repo, motor, clinical, self._observador)
        self._hilo_sync = HiloSync(repo, cliente_sync, config_sync)

        self._sesion_cacheada: tuple[str, str, str, str] | None = None
        self._resultados: dict[str, ResultadoOjo] = {}
        self._riesgo: str | None = None
        self._requiere_derivacion: bool | None = None
        self._observaciones: str = ""

        self._pantalla_sesion = PantallaFormularioSesion()
        self._pantalla_paciente = PantallaFormularioPaciente()
        self._pantalla_captura = PantallaCaptura()
        self._pantalla_resultado = PantallaResultado()

        self._pila = QStackedWidget()
        self._pila.addWidget(self._pantalla_sesion)
        self._pila.addWidget(self._pantalla_paciente)
        self._pila.addWidget(self._pantalla_captura)
        self._pila.addWidget(self._pantalla_resultado)

        # Encabezado de marca (capibara + "LUXeyes") por ENCIMA de la
        # pila, no dentro de ella — así queda visible en las 4 pantallas
        # sin tener que repetirlo en cada una. Ver EncabezadoMarca para
        # el porqué del tamaño fijo (presupuesto de 480px de alto real).
        contenedor = QWidget()
        layout_contenedor = QVBoxLayout(contenedor)
        layout_contenedor.setContentsMargins(0, 0, 0, 0)
        layout_contenedor.setSpacing(0)
        layout_contenedor.addWidget(EncabezadoMarca())
        layout_contenedor.addWidget(self._pila)
        self.setCentralWidget(contenedor)

        self._crear_barra_sync()
        self._conectar_pantallas()
        self._conectar_senales_flujo()
        self._conectar_senales_sync()

        self._hilo.comandos.iniciar_nuevo_tamizaje.emit()
        self._actualizar_contador_pendientes()

    # ── Barra de sincronización (persistente, visible en cualquier pantalla) ──
    def _crear_barra_sync(self) -> None:
        """
        Vive en la barra de estado de QMainWindow — fuera del
        QStackedWidget, por eso queda visible sin importar qué pantalla
        del flujo de tamizaje esté mostrándose (decisión aprobada:
        sincronización manual, no atada a ningún paciente en particular).
        """
        self._etiqueta_pendientes = QLabel()
        self._boton_sincronizar = QPushButton("Sincronizar ahora")
        self._boton_sincronizar.clicked.connect(self._hilo_sync.comandos.sincronizar_ahora.emit)

        barra = self.statusBar()
        barra.addWidget(self._etiqueta_pendientes)
        barra.addPermanentWidget(self._boton_sincronizar)

    def _actualizar_contador_pendientes(self) -> None:
        conteos = self._repo.contar_por_estado()
        pendientes = conteos.get("PENDIENTE", 0) + conteos.get("ERROR_REINTENTABLE", 0)
        permanentes = conteos.get("ERROR_PERMANENTE", 0)
        texto = f"{pendientes} tamizaje(s) pendiente(s) de sincronizar"
        if permanentes:
            # [CORRECCIÓN — bug real reportado por un usuario] "0
            # pendientes" es ambiguo: puede significar "todo sincronizado
            # bien" O "todo terminó en error permanente, ya no se
            # reintenta". Sin esta distinción, un fallo real de
            # validación del servidor se leía como éxito silencioso.
            texto += f" — ATENCIÓN: {permanentes} con error permanente (revisar ultimo_error en storage/)"
        self._etiqueta_pendientes.setText(texto)

    def _conectar_senales_sync(self) -> None:
        s = self._hilo_sync.senales
        s.sincronizacion_iniciada.connect(self._al_sincronizacion_iniciada)
        s.sincronizacion_completada.connect(self._al_sincronizacion_completada)
        s.sincronizacion_fallo.connect(self._al_sincronizacion_fallo)

    def _al_sincronizacion_iniciada(self) -> None:
        self._boton_sincronizar.setEnabled(False)
        self._etiqueta_pendientes.setText("Sincronizando…")

    def _al_sincronizacion_completada(self, resumen) -> None:
        self._boton_sincronizar.setEnabled(True)
        self._actualizar_contador_pendientes()
        self.statusBar().showMessage(
            f"Sincronización: {resumen.sincronizados} enviados, "
            f"{resumen.reintentables} reintentables, {resumen.permanentes} con error, "
            f"{resumen.ambientales} sin conexión.",
            8000,  # ms visible antes de que la barra vuelva al contador de pendientes
        )

    def _al_sincronizacion_fallo(self, mensaje: str) -> None:
        self._boton_sincronizar.setEnabled(True)
        self.statusBar().showMessage(f"Error inesperado al sincronizar: {mensaje}", 8000)

    # ── Cableado: pantallas -> comandos del orquestador ─────────────────
    def _conectar_pantallas(self) -> None:
        self._pantalla_sesion.datos_confirmados.connect(self._al_confirmar_sesion)
        self._pantalla_paciente.datos_confirmados.connect(
            self._hilo.comandos.recibir_datos_paciente.emit
        )
        self._pantalla_paciente.atras_solicitado.connect(self._al_atras_desde_paciente)
        self._pantalla_captura.iniciar_captura_solicitada.connect(self._al_iniciar_captura)
        self._pantalla_captura.atras_solicitado.connect(self._al_atras_desde_captura)
        self._pantalla_resultado.guardar_solicitado.connect(
            self._hilo.comandos.confirmar_guardado.emit
        )
        self._pantalla_resultado.cancelar_solicitado.connect(
            self._hilo.comandos.cancelar.emit
        )
        self._pantalla_resultado.siguiente_nino_solicitado.connect(self._al_siguiente_nino)
        self._pantalla_resultado.cambiar_colegio_solicitado.connect(self._al_cambiar_colegio)

    def _al_confirmar_sesion(self, colegio, distrito, tecnologo, fecha) -> None:
        self._sesion_cacheada = (colegio, distrito, tecnologo, fecha)
        self._hilo.comandos.recibir_datos_sesion.emit(colegio, distrito, tecnologo, fecha)

    def _al_atras_desde_paciente(self) -> None:
        """
        "Atrás" desde el formulario de paciente: a diferencia de
        "cancelar" genérico (que reutiliza _sesion_cacheada para
        "siguiente niño, mismo colegio"), aquí el tecnólogo quiere
        volver a EDITAR los datos de sesión — no verlos saltados de
        nuevo. Se pre-llena PantallaFormularioSesion con lo que ya
        había escrito (no arranca en blanco) y se limpia el caché ANTES
        de cancelar, para que _al_inicio_formulario() muestre esa
        pantalla en vez de reutilizar el caché y devolver directo a
        FormularioPaciente (el bug original: "Atrás" parecía no hacer
        nada, porque el caché lo revertía inmediatamente).
        """
        if self._sesion_cacheada is not None:
            self._pantalla_sesion.prellenar(*self._sesion_cacheada)
        self._sesion_cacheada = None
        self._hilo.comandos.cancelar.emit()

    def _al_iniciar_captura(self) -> None:
        ojo = self._pantalla_captura.ojo_actual
        self._gestor_camara.detener_vista_previa()
        self._hilo.comandos.ejecutar_captura.emit(ojo)

    def _al_atras_desde_captura(self) -> None:
        """
        "Atrás" desde la pantalla de captura: libera la cámara ANTES de
        cancelar (igual que al iniciar una captura real) — si no se
        libera aquí, la vista previa seguiría corriendo sobre una cámara
        que el siguiente paso (formulario de sesión/paciente) ya no
        necesita, dejándola ocupada sin motivo.
        """
        self._gestor_camara.detener_vista_previa()
        self._hilo.comandos.cancelar.emit()

    def _al_siguiente_nino(self) -> None:
        self._resultados = {}
        self._riesgo = None
        self._requiere_derivacion = None
        self._observaciones = ""
        self._pantalla_paciente.limpiar()
        self._hilo.comandos.iniciar_nuevo_tamizaje.emit()
        if self._sesion_cacheada is not None:
            self._hilo.comandos.recibir_datos_sesion.emit(*self._sesion_cacheada)
        self._pila.setCurrentWidget(self._pantalla_paciente)

    def _al_cambiar_colegio(self) -> None:
        self._resultados = {}
        self._riesgo = None
        self._requiere_derivacion = None
        self._observaciones = ""
        self._hilo.comandos.iniciar_nuevo_tamizaje.emit()
        self._pila.setCurrentWidget(self._pantalla_sesion)

    # ── Cableado: eventos del orquestador (SenalesFlujo) -> pantallas ──
    def _conectar_senales_flujo(self) -> None:
        s = self._observador.senales
        s.cambio_de_estado.connect(self._al_cambio_de_estado)
        s.inicio_formulario.connect(self._al_inicio_formulario)
        s.captura_iniciada.connect(self._al_captura_iniciada)
        s.progreso_captura.connect(self._al_progreso_captura)
        s.captura_finalizada.connect(self._al_captura_finalizada)
        s.procesamiento_finalizado.connect(self._al_procesamiento_finalizado)
        s.resultado_listo.connect(self._al_resultado_listo)
        s.almacenamiento_completado.connect(self._al_almacenamiento_completado)
        s.error.connect(self._al_error)
        s.cancelacion.connect(self._al_cancelacion)

    def _al_cambio_de_estado(self, estado_anterior, estado_nuevo) -> None:
        """
        [CORRECCIÓN, bug real encontrado al probar en la Raspberry Pi con
        un usuario real] Cubre la ÚNICA transición del flujo que no tenía
        un evento semántico dedicado en ObservadorDeFlujo:
        FORMULARIO_SESION -> FORMULARIO_PACIENTE (a diferencia de
        captura_iniciada/resultado_listo, que sí son eventos específicos,
        recibir_datos_sesion() exitoso solo dispara en_cambio_de_estado).

        Sin este manejador, el botón "Continuar" del formulario de sesión
        parecía no hacer nada: los datos SÍ se enviaban y el orquestador
        SÍ avanzaba de estado, pero la pantalla nunca cambiaba. Las
        pruebas automatizadas no lo detectaron porque disparaban la
        señal de la pantalla de paciente directamente, sin pasar por si
        esa pantalla estaba realmente visible — ver test_ui.py, corregido
        para usar clics reales (QTest.mouseClick) en vez de emit()
        directo en los botones que el tecnólogo realmente toca.
        """
        if estado_nuevo == EstadoFlujo.FORMULARIO_PACIENTE:
            self._pila.setCurrentWidget(self._pantalla_paciente)

    def _al_cancelacion(self, estado_anterior: EstadoFlujo) -> None:
        """
        Tras cancelar desde PantallaResultado (antes de guardar), el
        orquestador queda en CANCELADO — un estado terminal sin pantalla
        propia. Se reanuda igual que "siguiente niño, mismo colegio": si
        hay una sesión cacheada, se reenvía sin mostrar el formulario de
        sesión; si no, se muestra el formulario de sesión desde cero.
        """
        self._resultados = {}
        self._riesgo = None
        self._requiere_derivacion = None
        self._observaciones = ""
        self._pantalla_paciente.limpiar()
        self._hilo.comandos.iniciar_nuevo_tamizaje.emit()
        if self._sesion_cacheada is not None:
            self._hilo.comandos.recibir_datos_sesion.emit(*self._sesion_cacheada)

    def _al_inicio_formulario(self) -> None:
        # Solo mostrar el formulario de sesión si NO hay una sesión
        # cacheada esperando a ser reenviada (flujo "siguiente niño").
        if self._sesion_cacheada is None:
            self._pila.setCurrentWidget(self._pantalla_sesion)

    def _al_captura_iniciada(self, ojo: str) -> None:
        self._pantalla_captura.preparar(ojo)
        self._pila.setCurrentWidget(self._pantalla_captura)
        self._gestor_camara.iniciar_vista_previa(self._pantalla_captura.actualizar_frame_preview)

    def _al_progreso_captura(self, ojo: str, mensaje: str) -> None:
        self._pantalla_captura.mostrar_progreso(mensaje)

    def _al_captura_finalizada(self, ojo: str, resultado: ResultadoOjo) -> None:
        self._resultados[ojo] = resultado

    def _al_procesamiento_finalizado(
        self, riesgo: str | None, requiere_derivacion: bool | None, observaciones: str
    ) -> None:
        self._riesgo = riesgo
        self._requiere_derivacion = requiere_derivacion
        self._observaciones = observaciones

    def _al_resultado_listo(self) -> None:
        self._pantalla_resultado.mostrar_resultado(
            self._resultados.get("od"), self._resultados.get("oi"),
            self._riesgo, self._requiere_derivacion, self._observaciones,
        )
        self._pila.setCurrentWidget(self._pantalla_resultado)

    def _al_almacenamiento_completado(self, uuid_local: str) -> None:
        self._pantalla_resultado.confirmar_guardado(uuid_local)
        self._actualizar_contador_pendientes()

    def _al_error(self, estado: EstadoFlujo, mensaje: str) -> None:
        if estado == EstadoFlujo.FORMULARIO_SESION:
            self._pantalla_sesion.mostrar_error(mensaje)
        elif estado == EstadoFlujo.FORMULARIO_PACIENTE:
            self._pantalla_paciente.mostrar_error(mensaje)
        elif estado in (EstadoFlujo.CAPTURA_OD, EstadoFlujo.CAPTURA_OI):
            self._pantalla_captura.mostrar_error(mensaje)
            # Fallo recuperable de captura: liberar/reiniciar la vista
            # previa para que el tecnólogo pueda reposicionar y reintentar.
            self._gestor_camara.iniciar_vista_previa(self._pantalla_captura.actualizar_frame_preview)

    def closeEvent(self, event) -> None:
        self._gestor_camara.detener_vista_previa()
        self._hilo.detener()
        self._hilo_sync.detener()
        super().closeEvent(event)
