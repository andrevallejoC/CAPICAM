"""
ui/pantallas/captura.py — PantallaCaptura: vista previa en vivo antes de
capturar, progreso durante la captura real. Se reutiliza la MISMA
instancia para 'od' y 'oi' — VentanaPrincipal llama a preparar(ojo) antes
de mostrarla cada vez.

DECISIÓN de arquitectura (Fase 5, aprobada): esta pantalla NUNCA toca la
cámara directamente — no importa FuenteDeVideoPicamera2 ni
ControladorLEDGPIO. Solo expone actualizar_frame_preview(QImage), que
quien la use (VentanaPrincipal, coordinando con GestorCamaraCompartida)
llama con cada frame ya convertido. Esto mantiene la pantalla 100%
probable sin hardware — igual que el resto de ui/.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal as Signal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..estilos import ERROR

# Dimensión del recuadro de vista previa. Calibrado para caber en la
# pantalla táctil real del dispositivo (800x480, ver docstring de la
# clase) — NO usar un valor más grande sin volver a medir con
# sizeHint() contra 800x480, como se hizo aquí (ver test_ui.py).
_LADO_VISTA_PREVIA_PX = 300


class PantallaCaptura(QWidget):
    """
    Señales:
        iniciar_captura_solicitada() — el tecnólogo presionó "Iniciar
            captura" (o "Reintentar" tras un error). Quien escuche debe
            detener la vista previa y disparar ejecutar_captura(ojo).
        atras_solicitado() — cancela el tamizaje en curso y vuelve a la
            pantalla anterior (mismo mecanismo de "cancelar y reiniciar"
            que el resto de botones "Atrás"). Seguro de presionar incluso
            a mitad de una medición: el comando queda en cola hasta que
            el intento actual de medir_ojo() termine, sin condiciones de
            carrera — ver HiloOrquestador.

    Slots públicos (llamados desde VentanaPrincipal, conectado a
    SenalesFlujo / al gestor de cámara):
        preparar(ojo) — antes de mostrar la pantalla para un ojo nuevo.
        actualizar_frame_preview(QImage) — nuevo frame de la vista previa.
        mostrar_progreso(mensaje) — evento en_progreso_captura /
            en_captura_iniciada del orquestador.
        mostrar_error(mensaje) — evento en_error: reactiva el botón como
            "Reintentar" y vuelve a mostrar la vista previa.

    DECISIÓN de diseño (corregida tras validar en la pantalla táctil
    real): la primera versión apilaba título + vista previa (480x480) +
    progreso + error + botón EN VERTICAL, pidiendo 598px de alto — más
    de lo que existen en la pantalla real (800x480, solo 480px de alto
    disponibles). Se rediseñó a un layout HORIZONTAL (vista previa a la
    izquierda, controles a la derecha), aprovechando que la pantalla es
    ancha (800px) aunque baja (480px). Verificado con
    QWidget.sizeHint() contra el límite real antes de dar esto por
    resuelto — no solo "se ve razonable". El recuadro se redujo de
    340 a 300px al agregar el encabezado de marca (EncabezadoMarca),
    que también compite por el mismo presupuesto de 480px — vuelto a
    verificar con sizeHint(), no solo asumido.
    """

    iniciar_captura_solicitada = Signal()
    atras_solicitado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ojo_actual: str | None = None

        self._titulo = QLabel()
        self._titulo.setProperty("rolTitulo", True)

        self._vista = QLabel()
        self._vista.setFixedSize(_LADO_VISTA_PREVIA_PX, _LADO_VISTA_PREVIA_PX)
        self._vista.setStyleSheet("background-color: black; border-radius: 8px;")
        self._vista.setScaledContents(True)

        self._etiqueta_progreso = QLabel("")
        self._etiqueta_progreso.setWordWrap(True)
        self._etiqueta_error = QLabel("")
        self._etiqueta_error.setWordWrap(True)
        self._etiqueta_error.setStyleSheet(f"color: {ERROR}; font-weight: bold;")
        self._etiqueta_error.setVisible(False)

        self._boton_atras = QPushButton("← Atrás")
        self._boton_atras.setProperty("secundario", True)
        self._boton_atras.clicked.connect(self.atras_solicitado.emit)

        self._boton_iniciar = QPushButton("Iniciar captura")
        self._boton_iniciar.clicked.connect(self.iniciar_captura_solicitada.emit)
        self._boton_iniciar.setMinimumHeight(44)  # más fácil de tocar en pantalla táctil

        fila_botones = QHBoxLayout()
        fila_botones.addWidget(self._boton_atras)
        fila_botones.addWidget(self._boton_iniciar, stretch=1)

        panel_derecho = QVBoxLayout()
        panel_derecho.addWidget(self._etiqueta_progreso)
        panel_derecho.addWidget(self._etiqueta_error)
        panel_derecho.addStretch()
        panel_derecho.addLayout(fila_botones)

        fila_principal = QHBoxLayout()
        fila_principal.addWidget(self._vista)
        fila_principal.addLayout(panel_derecho, stretch=1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._titulo)
        layout.addLayout(fila_principal)

    # ── Comandos desde VentanaPrincipal ─────────────────────────────────
    def preparar(self, ojo: str) -> None:
        """Reinicia la pantalla para capturar el ojo indicado ('od' u 'oi')."""
        self._ojo_actual = ojo
        nombre_legible = "ojo derecho" if ojo == "od" else "ojo izquierdo"
        self._titulo.setText(f"Captura — {nombre_legible}")
        self._etiqueta_progreso.setText("Posiciona al paciente y presiona 'Iniciar captura'.")
        self._etiqueta_error.setVisible(False)
        self._boton_iniciar.setText("Iniciar captura")
        self._boton_iniciar.setEnabled(True)

    def actualizar_frame_preview(self, imagen: QImage) -> None:
        self._vista.setPixmap(QPixmap.fromImage(imagen))

    def mostrar_progreso(self, mensaje: str) -> None:
        self._etiqueta_progreso.setText(mensaje)
        self._boton_iniciar.setEnabled(False)

    def mostrar_error(self, mensaje: str) -> None:
        self._etiqueta_error.setText(mensaje)
        self._etiqueta_error.setVisible(True)
        self._etiqueta_progreso.setText("")
        self._boton_iniciar.setText("Reintentar")
        self._boton_iniciar.setEnabled(True)

    @property
    def ojo_actual(self) -> str | None:
        return self._ojo_actual
