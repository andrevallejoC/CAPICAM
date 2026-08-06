"""
ui/pantallas/formulario_paciente.py — PantallaFormularioPaciente: DNI,
nombre, fecha de nacimiento, grado/sección, contacto de los padres
(opcional).
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal as Signal
from PyQt5.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..estilos import ERROR


class PantallaFormularioPaciente(QWidget):
    """
    Emite datos_confirmados(dni, nombre_paciente, fecha_nacimiento,
    grado_seccion, email_padre, telefono_padre). Igual que
    PantallaFormularioSesion, la validación real vive en orchestrator/ —
    esta pantalla solo recoge y envía.

    Emite atras_solicitado() cuando el tecnólogo presiona "Atrás" — quien
    escuche debe cancelar el tamizaje en curso y volver a la pantalla
    anterior (mecanismo "cancelar y reiniciar", ya existente desde antes
    de agregar este botón — ver VentanaPrincipal._al_cancelacion).
    """

    datos_confirmados = Signal(str, str, str, str, str, str)
    atras_solicitado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._campo_dni = QLineEdit()
        self._campo_nombre = QLineEdit()
        self._campo_fecha_nacimiento = QLineEdit()
        self._campo_fecha_nacimiento.setPlaceholderText("YYYY-MM-DD")
        self._campo_grado = QLineEdit()
        self._campo_email_padre = QLineEdit()
        self._campo_telefono_padre = QLineEdit()

        self._etiqueta_error = QLabel()
        self._etiqueta_error.setStyleSheet(f"color: {ERROR}; font-weight: 600;")
        self._etiqueta_error.setVisible(False)

        formulario = QFormLayout()
        formulario.addRow("DNI:", self._campo_dni)
        formulario.addRow("Nombre del paciente:", self._campo_nombre)
        formulario.addRow("Fecha de nacimiento:", self._campo_fecha_nacimiento)
        formulario.addRow("Grado y sección:", self._campo_grado)
        formulario.addRow("Email del padre/madre (opcional):", self._campo_email_padre)
        formulario.addRow("Teléfono del padre/madre (opcional):", self._campo_telefono_padre)

        self._boton_atras = QPushButton("← Atrás")
        self._boton_atras.setProperty("secundario", True)
        self._boton_atras.clicked.connect(self.atras_solicitado.emit)

        self._boton_continuar = QPushButton("Continuar")
        self._boton_continuar.clicked.connect(self._al_confirmar)

        fila_botones = QHBoxLayout()
        fila_botones.addWidget(self._boton_atras)
        fila_botones.addWidget(self._boton_continuar, stretch=1)

        titulo = QLabel("Datos del paciente")
        titulo.setProperty("rolTitulo", True)

        layout = QVBoxLayout(self)
        layout.addWidget(titulo)
        layout.addLayout(formulario)
        layout.addWidget(self._etiqueta_error)
        layout.addLayout(fila_botones)

    def _al_confirmar(self) -> None:
        self._etiqueta_error.setVisible(False)
        self.datos_confirmados.emit(
            self._campo_dni.text().strip(),
            self._campo_nombre.text().strip(),
            self._campo_fecha_nacimiento.text().strip(),
            self._campo_grado.text().strip(),
            self._campo_email_padre.text().strip(),
            self._campo_telefono_padre.text().strip(),
        )

    def mostrar_error(self, mensaje: str) -> None:
        self._etiqueta_error.setText(mensaje)
        self._etiqueta_error.setVisible(True)

    def limpiar(self) -> None:
        """Se llama antes de cada niño nuevo, para no arrastrar datos del anterior."""
        for campo in (
            self._campo_dni, self._campo_nombre, self._campo_fecha_nacimiento,
            self._campo_grado, self._campo_email_padre, self._campo_telefono_padre,
        ):
            campo.clear()
        self._etiqueta_error.setVisible(False)
