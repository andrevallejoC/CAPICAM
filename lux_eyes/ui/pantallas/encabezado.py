"""
ui/pantallas/encabezado.py — EncabezadoMarca: barra superior persistente
con el capibara y el nombre "LUXeyes", visible en cualquier pantalla del
flujo (vive en VentanaPrincipal, por encima del QStackedWidget — no
dentro de él, así no hay que repetirlo en cada pantalla).

DECISIÓN de tamaño: 44px de alto fijo. La pantalla real del dispositivo
es de solo 480px de alto en total (ver PantallaCaptura, que ya usa la
mayor parte de ese presupuesto) — un encabezado más alto competiría por
espacio con el contenido real de cada pantalla. Se verificó con
QWidget.sizeHint() que las 4 pantallas siguen cabiendo con este
encabezado sumado (ver test_ui.py).
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from ..estilos import ACENTO, PRIMARIO, SUPERFICIE, BORDE

_RUTA_CAPIBARA = Path(__file__).resolve().parent.parent / "assets" / "capibara.png"
_ALTO_BARRA = 44
_ALTO_ICONO = 34


class EncabezadoMarca(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_ALTO_BARRA)
        self.setStyleSheet(
            f"background-color: {SUPERFICIE}; border-bottom: 1px solid {BORDE};"
        )

        icono = QLabel()
        pixmap = QPixmap(str(_RUTA_CAPIBARA))
        if not pixmap.isNull():
            # Un único reescalado, aquí, en la construcción — nunca en
            # cada repintado. La imagen ya viene pre-reducida en
            # assets/capibara.png (ver ui/estilos.py y la conversación de
            # diseño), esto solo la ajusta al alto exacto de la barra.
            icono.setPixmap(
                pixmap.scaledToHeight(_ALTO_ICONO, Qt.TransformationMode.SmoothTransformation)
            )
        icono.setFixedWidth(_ALTO_ICONO + 6)
        icono.setAlignment(Qt.AlignmentFlag.AlignCenter)

        nombre = QLabel("LUXeyes")
        nombre.setStyleSheet(f"color: {PRIMARIO}; font-size: 15pt; font-weight: 800;")

        subtitulo = QLabel("Tamizaje visual")
        subtitulo.setStyleSheet(f"color: {ACENTO}; font-size: 9pt; font-weight: 600;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(8)
        layout.addWidget(icono)
        layout.addWidget(nombre)
        layout.addWidget(subtitulo)
        layout.addStretch()
