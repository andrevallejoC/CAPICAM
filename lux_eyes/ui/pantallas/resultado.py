"""
ui/pantallas/resultado.py — PantallaResultado: muestra esfera/cilindro/
eje de ambos ojos, riesgo clínico y observaciones; permite guardar o
cancelar; y tras guardar, ofrece "siguiente niño (mismo colegio)" o
"cambiar de colegio" (decisión aprobada en el diseño de la Fase 5).

Esta pantalla NUNCA lee directamente del contexto del orquestador — solo
recibe los datos ya resueltos vía mostrar_resultado(), alimentados por
VentanaPrincipal a partir de los eventos de SenalesFlujo. Mantiene la
misma separación que el resto de ui/: cero acceso directo a
orchestrator/ más allá de las señales ya definidas.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal as Signal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from lux_eyes.common.tipos import ResultadoOjo

from ..estilos import ADVERTENCIA, ERROR, EXITO, TEXTO_SUAVE


def _formatear_ojo(nombre: str, r: ResultadoOjo) -> str:
    if r is None or r.esfera is None:
        return f"{nombre}: sin datos"
    partes = [f"Esfera: {r.esfera:+.2f} D"]
    if r.esfera_sd is not None:
        partes[-1] += f" (SD {r.esfera_sd:.2f})"
    if r.cilindro is not None:
        txt = f"Cilindro: {r.cilindro:+.2f} D"
        if r.cilindro_sd is not None:
            txt += f" (SD {r.cilindro_sd:.2f})"
        partes.append(txt)
    if r.eje is not None:
        txt = f"Eje: {r.eje:.0f}°"
        if r.eje_sd is not None:
            txt += f" (SD {r.eje_sd:.1f})"
        partes.append(txt)
    return f"<b>{nombre}</b><br>" + "<br>".join(partes)


# Color del banner de riesgo — pura comunicación visual, no cambia el
# significado clínico (eso lo decide clinical/, esta pantalla solo
# refleja lo que ya llegó calculado).
_COLOR_POR_RIESGO = {
    "SIN_RIESGO": EXITO,
    "BAJO": EXITO,
    "MODERADO": ADVERTENCIA,
    "ALTO": ERROR,
}


class PantallaResultado(QWidget):
    """
    Señales:
        guardar_solicitado()
        cancelar_solicitado()
        siguiente_nino_solicitado() — solo relevante tras guardar exitoso
        cambiar_colegio_solicitado() — solo relevante tras guardar exitoso
    """

    guardar_solicitado = Signal()
    cancelar_solicitado = Signal()
    siguiente_nino_solicitado = Signal()
    cambiar_colegio_solicitado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._etiqueta_od = QLabel()
        self._etiqueta_oi = QLabel()
        self._etiqueta_riesgo = QLabel()
        self._etiqueta_riesgo.setStyleSheet("font-size: 13pt; font-weight: 700;")
        self._etiqueta_observaciones = QLabel()
        self._etiqueta_observaciones.setWordWrap(True)
        self._etiqueta_observaciones.setStyleSheet(f"color: {TEXTO_SUAVE}; font-size: 9pt;")

        resultados = QHBoxLayout()
        resultados.addWidget(self._etiqueta_od)
        resultados.addWidget(self._etiqueta_oi)

        self._boton_cancelar = QPushButton("Cancelar")
        self._boton_cancelar.setProperty("secundario", True)
        self._boton_cancelar.clicked.connect(self.cancelar_solicitado.emit)
        self._boton_guardar = QPushButton("Guardar")
        self._boton_guardar.clicked.connect(self.guardar_solicitado.emit)

        self._botones_antes_de_guardar = QHBoxLayout()
        self._botones_antes_de_guardar.addWidget(self._boton_cancelar)
        self._botones_antes_de_guardar.addWidget(self._boton_guardar, stretch=1)

        self._etiqueta_guardado = QLabel()
        self._etiqueta_guardado.setStyleSheet(f"color: {EXITO}; font-weight: 700;")
        self._etiqueta_guardado.setVisible(False)

        self._boton_cambiar_colegio = QPushButton("Cambiar de colegio")
        self._boton_cambiar_colegio.setProperty("secundario", True)
        self._boton_cambiar_colegio.clicked.connect(self.cambiar_colegio_solicitado.emit)
        self._boton_siguiente_nino = QPushButton("Siguiente niño (mismo colegio)")
        self._boton_siguiente_nino.clicked.connect(self.siguiente_nino_solicitado.emit)

        self._botones_despues_de_guardar = QHBoxLayout()
        self._botones_despues_de_guardar.addWidget(self._boton_cambiar_colegio)
        self._botones_despues_de_guardar.addWidget(self._boton_siguiente_nino, stretch=1)

        titulo = QLabel("Resultado")
        titulo.setProperty("rolTitulo", True)

        layout = QVBoxLayout(self)
        layout.addWidget(titulo)
        layout.addLayout(resultados)
        layout.addWidget(self._etiqueta_riesgo)
        layout.addWidget(self._etiqueta_observaciones)
        layout.addWidget(self._etiqueta_guardado)
        layout.addLayout(self._botones_antes_de_guardar)
        layout.addLayout(self._botones_despues_de_guardar)

        self._mostrar_modo_pre_guardado()

    def _mostrar_modo_pre_guardado(self) -> None:
        self._etiqueta_guardado.setVisible(False)
        self._boton_guardar.setVisible(True)
        self._boton_cancelar.setVisible(True)
        self._boton_siguiente_nino.setVisible(False)
        self._boton_cambiar_colegio.setVisible(False)

    def _mostrar_modo_post_guardado(self, uuid_local: str) -> None:
        self._etiqueta_guardado.setText(f"Guardado correctamente (id local: {uuid_local[:8]}…)")
        self._etiqueta_guardado.setVisible(True)
        self._boton_guardar.setVisible(False)
        self._boton_cancelar.setVisible(False)
        self._boton_siguiente_nino.setVisible(True)
        self._boton_cambiar_colegio.setVisible(True)

    # ── Comandos desde VentanaPrincipal ─────────────────────────────────
    def mostrar_resultado(
        self, od: ResultadoOjo, oi: ResultadoOjo,
        riesgo: str | None, requiere_derivacion: bool | None, observaciones: str,
    ) -> None:
        self._mostrar_modo_pre_guardado()
        self._etiqueta_od.setText(_formatear_ojo("Ojo derecho", od))
        self._etiqueta_oi.setText(_formatear_ojo("Ojo izquierdo", oi))

        texto_riesgo = f"Riesgo: {riesgo or 'desconocido'}"
        if requiere_derivacion:
            texto_riesgo += " — REQUIERE DERIVACIÓN"
        color = _COLOR_POR_RIESGO.get(riesgo, TEXTO_SUAVE)
        self._etiqueta_riesgo.setStyleSheet(
            f"color: {color}; font-size: 13pt; font-weight: 700;"
        )
        self._etiqueta_riesgo.setText(texto_riesgo)
        self._etiqueta_observaciones.setText(observaciones)

    def confirmar_guardado(self, uuid_local: str) -> None:
        self._mostrar_modo_post_guardado(uuid_local)
