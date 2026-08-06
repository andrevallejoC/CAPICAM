"""
engine/ — Motor de fotorrefracción (Fase 4).

Implementa el Protocol MotorFotorrefraccion ya definido en
orchestrator/contratos.py desde la Fase 3.

DECISIÓN de arquitectura (importación diferida / lazy):
    Este __init__.py NO importa MotorFotorrefraccionLuxEyes ni los
    estimadores de pendiente (EstimadorOLS/Huber/TheilSen/RANSAC) de
    forma ansiosa en el top-level, porque esos arrastran numpy,
    scikit-learn y opencv como dependencias transitivas
    (motor.py -> slope_estimator.py -> sklearn; motor.py ->
    reflex_mask.py -> cv2). En la práctica, esto significaba que un
    script que solo necesita ControladorLEDGPIO (sin ninguna relación
    con scikit-learn) igual exigía tener scikit-learn instalado, solo
    por importar el paquete engine — fricción real e innecesaria en la
    Raspberry Pi, donde instalar ese stack científico completo es
    costoso (detectado al validar hardware real, ver
    scripts_validacion_pi/).

    Los símbolos "pesados" (ver _SIMBOLOS_DIFERIDOS) se cargan solo la
    primera vez que se accede a ellos, vía __getattr__ de módulo (PEP
    562). Los símbolos "livianos" (dataclasses, Protocols, excepciones,
    fórmulas basadas solo en `math`) se siguen importando de forma
    directa arriba: no cuesta nada y mantiene el autocompletado normal
    para quien sí los use.

    Regla práctica para quien agregue un submódulo nuevo: si importa
    numpy, scikit-learn, opencv o mediapipe en su nivel superior,
    regístralo en _SIMBOLOS_DIFERIDOS, no en los imports directos de
    abajo.
"""

import importlib

# ── Livianos: sin numpy/sklearn/opencv/mediapipe, se importan directo ──
from .configuracion import ConfiguracionCaptura
from .contratos_estimacion import DeteccionPupila, DetectorPupila, EstimadorPendiente, ResultadoPendiente
from .contratos_hardware import ControladorLED, FrameCrudo, FuenteDeVideo, Reloj
from .errores import ErrorMotor, FalloHardwareError, PupilaNoDetectadaError, VentanaInestableError
from .refraction import CalibracionRefraccion

# ── Pesados: se resuelven solo si de verdad se usan (ver __getattr__) ──
_SIMBOLOS_DIFERIDOS = {
    "MotorFotorrefraccionLuxEyes": ".motor",          # arrastra sklearn + cv2
    "EstimadorOLS": ".slope_estimator",                # arrastra sklearn
    "EstimadorHuber": ".slope_estimator",
    "EstimadorTheilSen": ".slope_estimator",
    "EstimadorRANSAC": ".slope_estimator",
}


def __getattr__(nombre: str):
    modulo_relativo = _SIMBOLOS_DIFERIDOS.get(nombre)
    if modulo_relativo is None:
        raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")
    modulo = importlib.import_module(modulo_relativo, __name__)
    valor = getattr(modulo, nombre)
    globals()[nombre] = valor  # cachea: la próxima vez no vuelve a importar
    return valor


def __dir__():
    return sorted(list(globals().keys()) + list(_SIMBOLOS_DIFERIDOS.keys()))


__all__ = [
    "MotorFotorrefraccionLuxEyes",
    "ConfiguracionCaptura",
    "CalibracionRefraccion",
    "EstimadorOLS",
    "EstimadorHuber",
    "EstimadorTheilSen",
    "EstimadorRANSAC",
    "ControladorLED",
    "FuenteDeVideo",
    "Reloj",
    "FrameCrudo",
    "DetectorPupila",
    "DeteccionPupila",
    "EstimadorPendiente",
    "ResultadoPendiente",
    "ErrorMotor",
    "PupilaNoDetectadaError",
    "VentanaInestableError",
    "FalloHardwareError",
]
