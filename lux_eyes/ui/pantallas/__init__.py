"""ui/pantallas/ — Widgets de cada paso del flujo de tamizaje."""

from .captura import PantallaCaptura
from .encabezado import EncabezadoMarca
from .formulario_paciente import PantallaFormularioPaciente
from .formulario_sesion import PantallaFormularioSesion
from .resultado import PantallaResultado

__all__ = [
    "PantallaFormularioSesion",
    "PantallaFormularioPaciente",
    "PantallaCaptura",
    "PantallaResultado",
    "EncabezadoMarca",
]
