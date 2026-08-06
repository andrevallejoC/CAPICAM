"""
ui/pantallas/formulario_sesion.py — PantallaFormularioSesion: colegio,
distrito, tecnólogo y fecha de sesión.

Solo se muestra al iniciar el dispositivo o cuando el tecnólogo elige
explícitamente "cambiar de colegio" — para la sesión de tamizaje seguido
a muchos niños del mismo colegio (decisión aprobada en el diseño de la
Fase 5), VentanaPrincipal reutiliza estos datos sin volver a mostrar
esta pantalla.
"""

from __future__ import annotations

from datetime import date

from PyQt5.QtCore import pyqtSignal as Signal
from PyQt5.QtWidgets import (
    QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..estilos import ERROR


class PantallaFormularioSesion(QWidget):
    """
    Emite datos_confirmados(colegio_nombre, colegio_distrito, tecnologo,
    fecha_sesion) cuando el tecnólogo confirma el formulario. La
    VALIDACIÓN real (que los campos no estén vacíos, formato de fecha)
    la hace orchestrator/ContextoTamizajeEnCurso — esta pantalla no
    duplica esa lógica, solo recoge texto y lo envía. Si el orquestador
    rechaza los datos, mostrar_error() lo refleja aquí.
    """

    datos_confirmados = Signal(str, str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._campo_colegio = QLineEdit()
        self._campo_distrito = QLineEdit()
        self._campo_tecnologo = QLineEdit()
        self._campo_fecha = QLineEdit(date.today().isoformat())
        self._campo_fecha.setPlaceholderText("YYYY-MM-DD")

        self._etiqueta_error = QLabel()
        self._etiqueta_error.setStyleSheet(f"color: {ERROR}; font-weight: 600;")
        self._etiqueta_error.setVisible(False)

        formulario = QFormLayout()
        formulario.addRow("Colegio:", self._campo_colegio)
        formulario.addRow("Distrito:", self._campo_distrito)
        formulario.addRow("Tecnólogo:", self._campo_tecnologo)
        formulario.addRow("Fecha de sesión:", self._campo_fecha)

        self._boton_continuar = QPushButton("Continuar")
        self._boton_continuar.clicked.connect(self._al_confirmar)

        titulo = QLabel("Datos de la sesión")
        titulo.setProperty("rolTitulo", True)

        layout = QVBoxLayout(self)
        layout.addWidget(titulo)
        layout.addLayout(formulario)
        layout.addWidget(self._etiqueta_error)
        layout.addWidget(self._boton_continuar)

    def _al_confirmar(self) -> None:
        self._etiqueta_error.setVisible(False)
        self.datos_confirmados.emit(
            self._campo_colegio.text().strip(),
            self._campo_distrito.text().strip(),
            self._campo_tecnologo.text().strip(),
            self._campo_fecha.text().strip(),
        )

    def mostrar_error(self, mensaje: str) -> None:
        self._etiqueta_error.setText(mensaje)
        self._etiqueta_error.setVisible(True)

    def prellenar(self, colegio_nombre: str, colegio_distrito: str,
                  tecnologo: str, fecha_sesion: str) -> None:
        """Usado al 'cambiar de colegio' desde una sesión previa, para no partir de campos vacíos."""
        self._campo_colegio.setText(colegio_nombre)
        self._campo_distrito.setText(colegio_distrito)
        self._campo_tecnologo.setText(tecnologo)
        self._campo_fecha.setText(fecha_sesion)
