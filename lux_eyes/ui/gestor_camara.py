"""
ui/gestor_camara.py — GestorCamaraCompartida: dueño ÚNICO de
FuenteDeVideoPicamera2 + ControladorLEDGPIO + RelojMonotono, para que la
vista previa en vivo (antes de capturar) y MotorFotorrefraccionLuxEyes
(durante la captura real) NUNCA intenten usar la cámara al mismo tiempo
— la causa exacta del error "Device or resource busy" ya visto al
validar engine/ en hardware real.

ADVERTENCIA IMPORTANTE (mismo aviso que engine/adaptadores_picamera2.py
y adaptadores_gpio.py): este archivo NO pudo ejecutarse en el entorno
donde se escribió — picamera2/RPi.GPIO solo funcionan en una Raspberry
Pi real. Sigue la API ya validada de esos adaptadores (Fase 4), pero el
bucle de vista previa en sí (QThread + leer_frame() en bucle) DEBE
probarse en el dispositivo físico antes de confiar en él.

[PRINCIPIO CRÍTICO] heredado de engine/: reloj, LED y fuente de video son
la MISMA instancia tanto para la vista previa como para
MotorFotorrefraccionLuxEyes — construidos UNA sola vez aquí y reutilizados,
nunca duplicados.
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import QObject, QThread, pyqtSignal as Signal
from PyQt5.QtGui import QImage

from lux_eyes.engine.adaptadores_gpio import ControladorLEDGPIO, RelojMonotono
from lux_eyes.engine.adaptadores_picamera2 import FuenteDeVideoPicamera2
from lux_eyes.engine.configuracion import ConfiguracionCaptura
from lux_eyes.engine.motor import MotorFotorrefraccionLuxEyes


def _frame_a_qimage(imagen) -> QImage:
    """
    Convierte un array 2D en escala de grises (el formato que entrega
    FrameCrudo.imagen, ver engine/contratos_hardware.py) a QImage. copy()
    es necesario: QImage sobre el buffer de numpy sin copiar quedaría
    inválida en cuanto el array se libere/reutilice en el siguiente frame.
    """
    alto, ancho = imagen.shape[:2]
    return QImage(
        imagen.tobytes(), ancho, alto, ancho, QImage.Format.Format_Grayscale8
    ).copy()


class _HiloVistaPrevia(QThread):
    """
    Bucle de lectura continua de frames para la vista previa, en su
    propio hilo — leer_frame() bloquea brevemente por cada llamada real
    a la cámara; correrlo en el hilo principal congelaría la UI.
    """

    frame_listo = Signal(QImage)

    def __init__(self, fuente: FuenteDeVideoPicamera2, parent=None):
        super().__init__(parent)
        self._fuente = fuente
        self._activo = False

    def run(self) -> None:
        self._activo = True
        while self._activo:
            frame = self._fuente.leer_frame()
            if frame is not None:
                self.frame_listo.emit(_frame_a_qimage(frame.imagen))

    def detener(self) -> None:
        self._activo = False
        self.wait()


class GestorCamaraCompartida(QObject):
    """
    Implementa el contrato GestorCamara que VentanaPrincipal espera
    (iniciar_vista_previa/detener_vista_previa), y además construye
    MotorFotorrefraccionLuxEyes reutilizando la MISMA cámara/LED/reloj.

    MERIDIANO_VISTA_PREVIA: el LED que se mantiene encendido durante el
    posicionamiento, para que el reflejo sea visible (mismo criterio ya
    validado en scripts_validacion_pi/verificar_4_deteccion_pupila.py —
    sin luz IR, la escena no tiene contraste suficiente para nada).
    """

    MERIDIANO_VISTA_PREVIA = 0

    def __init__(
        self,
        pines_por_meridiano: dict[int, int],
        detector_pupila_od,
        detector_pupila_oi,
        estimador,
        config: ConfiguracionCaptura | None = None,
        rotacion_grados: int = 270,
        exposicion_us: int = 10000,
        ganancia_analoga: float = 2.0,
    ):
        """
        detector_pupila_od / detector_pupila_oi: instancias SEPARADAS —
        DetectorPupilaHaar/DetectorPupilaMediaPipe están fijas a un lado
        de la cara desde su propio constructor (ver
        engine/adaptador_haarcascade.py). Pasar la misma instancia para
        ambos ojos mediría el ojo izquierdo con el detector del derecho
        — exactamente el bug corregido en engine/motor.py al integrar
        esta clase con hardware real por primera vez.
        """
        super().__init__()
        self._config = config or ConfiguracionCaptura()
        self.reloj = RelojMonotono()
        self.led = ControladorLEDGPIO(pines_por_meridiano)
        self.fuente = FuenteDeVideoPicamera2(
            reloj=self.reloj, rotacion_grados=rotacion_grados,
            exposicion_us=exposicion_us, ganancia_analoga=ganancia_analoga,
        )
        self._detector_pupila_od = detector_pupila_od
        self._detector_pupila_oi = detector_pupila_oi
        self._estimador = estimador
        self._hilo_preview: _HiloVistaPrevia | None = None

    def construir_motor(self) -> MotorFotorrefraccionLuxEyes:
        """
        Construye el motor reutilizando la MISMA cámara/LED/reloj de este
        gestor. Llamar UNA sola vez; el motor resultante se pasa a
        VentanaPrincipal/OrquestadorTamizaje y se reutiliza durante toda
        la sesión del dispositivo.
        """
        return MotorFotorrefraccionLuxEyes(
            controlador_led=self.led, fuente_video=self.fuente, reloj=self.reloj,
            detector_pupila_od=self._detector_pupila_od,
            detector_pupila_oi=self._detector_pupila_oi,
            estimador=self._estimador, config=self._config,
        )

    # ── Contrato GestorCamara (ver ventana_principal.py) ────────────────
    def iniciar_vista_previa(self, callback_frame: Callable[[QImage], None]) -> None:
        self.led.encender(self.MERIDIANO_VISTA_PREVIA)
        self.fuente.iniciar()
        self._hilo_preview = _HiloVistaPrevia(self.fuente)
        self._hilo_preview.frame_listo.connect(callback_frame)
        self._hilo_preview.start()

    def detener_vista_previa(self) -> None:
        if self._hilo_preview is not None:
            self._hilo_preview.detener()
            self._hilo_preview = None
        self.fuente.detener()
        self.led.apagar()

    def liberar(self) -> None:
        """Llamar al cerrar la aplicación."""
        self.detener_vista_previa()
        self.led.liberar()
