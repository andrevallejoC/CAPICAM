"""
engine/adaptadores_picamera2.py — Implementación REAL de FuenteDeVideo
para Raspberry Pi (Picamera2 + Camera Module 3 NoIR).

ADVERTENCIA IMPORTANTE:
    Igual que adaptadores_gpio.py: este archivo NO pudo ejecutarse ni
    probarse en el entorno donde se escribió. `picamera2` ni siquiera
    instala fuera de una Raspberry Pi (depende de libcamera del sistema
    operativo). Está escrito siguiendo la API pública documentada de
    Picamera2, pero DEBE validarse en el dispositivo físico. La lógica
    científica del resto de engine/ sí se probó de forma exhaustiva y
    automática; esto no.

DECISIÓN de arquitectura: no lleva NINGUNA lógica de interpretación —
solo traduce capture_array()/metadata de Picamera2 al contrato FrameCrudo
(imagen, timestamp_sensor, duracion_exposicion, metadatos). Toda la
lógica de qué hacer con esos frames vive en synchronizer.py, ya probado.

[PRINCIPIO CRÍTICO] (7.3, "reloj monótono común"): esta clase usa el
MISMO objeto Reloj que se le pasa a illumination.SecuenciadorIluminacion
para marcar cada frame — NUNCA el SensorTimestamp propio de libcamera.
Quien construya el motor DEBE pasar la MISMA instancia de Reloj a
FuenteDeVideoPicamera2 y a MotorFotorrefraccionLuxEyes; si se usan dos
relojes distintos (p. ej. uno RelojMonotono y otro derivado de
SensorTimestamp), la asignación frame->meridiano de synchronizer.py
compara tiempos de bases distintas y el criterio de aceptación del Paso 1
("0 frames mal asignados") no puede cumplirse aunque el hardware funcione
perfectamente. Esto se detectó y corrigió al escribir el script de
validación 03_verificar_sincronizacion.py — no estaba cubierto por las
pruebas automáticas porque los dobles de prueba de FuenteDeVideo ya
usaban el reloj compartido por construcción, sin que hiciera falta
imponerlo explícitamente como aquí.

RESTRICCIÓN-ACTUAL:
    Usar reloj.ahora() en el momento en que leer_frame() devuelve el
    array introduce una pequeña latencia respecto al instante real de
    exposición del sensor (el tiempo que tarda picamera2 en entregar el
    frame a Python), no capturada por el SensorTimestamp de hardware.
ARQUITECTURA IDEAL:
    Calibrar una única vez, al iniciar(), el offset entre el reloj propio
    del sensor (SensorTimestamp) y el Reloj compartido, y aplicar ese
    offset a cada SensorTimestamp posterior — conservando la precisión de
    hardware sin perder la base de tiempo común. Requiere validar en el
    dispositivo real que ambos relojes no derivan entre sí de forma
    significativa durante una sesión de captura (segundos).
MEJORA FUTURA:
    Implementar esa calibración de offset si la latencia de
    reloj.ahora() resulta insuficiente en la práctica (validar con
    03_verificar_sincronizacion.py: si "frames mal asignados" no da 0 de
    forma consistente, esta es la primera causa a revisar).

[DECISIÓN] (17.6, "RECOMENDADO"): modo binned 2304x1296 (~56fps) en vez
de la resolución completa 4608x2592 usada en la implementación previa —
mejor framerate para adquisición continua, a costa de resolución (que
sigue siendo más que suficiente para el análisis del gradiente pupilar).
Configurable por si se decide lo contrario tras validación experimental.

CALIBRACIÓN EMPÍRICA (exposicion_us=10000, ganancia_analoga=2.0):
    Los valores por defecto de exposición y ganancia se recalibraron tras
    validar en hardware real. Con los valores iniciales (20000/4.0,
    heredados del régimen PWM 100Hz/53% de la implementación anterior)
    y LED en DC continuo (D4, ~1.9x más brillo promedio), la imagen
    quedaba sobreexpuesta: el reflejo de Purkinje se veía artificialmente
    grande (efecto de "blooming" del sensor al saturar), llegando a
    cubrir buena parte de la pupila en las imágenes de diagnóstico.

    RESTRICCIÓN-ACTUAL:
        Estos valores están calibrados para ESTE circuito específico (9
        LEDs IR en paralelo por meridiano, 181Ω por rama, ~19mA por LED,
        alimentación 5V — ver la conversación de validación de hardware)
        y esta distancia de trabajo (~50cm). Un cambio de LED, de
        corriente, o de distancia de trabajo invalida esta calibración.
    ARQUITECTURA IDEAL:
        Auto-exposición ejecutada UNA vez al inicio de cada sesión (no
        continua, para no romper el principio 5.1 de parámetros fijos
        durante la captura), que fije exposición/ganancia según las
        condiciones del momento y las bloquee para el resto de la sesión.
    MEJORA FUTURA:
        Si se cambia el hardware de iluminación, repetir la calibración
        empírica: reducir exposicion_us/ganancia_analoga hasta que el
        reflejo de Purkinje se vea como un punto compacto en las imágenes
        de diagnóstico (scripts_validacion_pi/verificar_5_mascara_reflejo.py),
        no una mancha grande.

[PRINCIPIO] (5.1, etapas 1-3; 17.6): parámetros de captura FIJOS y
verificados — exposición, ganancia, balance de blancos y enfoque
manuales, para fotometría comparable entre los tres meridianos. Este
adaptador nunca activa autoexposición ni autoenfoque continuos.

RESTRICCIÓN-ACTUAL:
    El bloqueo de enfoque (LensPosition) se fija UNA vez al iniciar() y no
    se re-verifica durante la sesión. Si el paciente se mueve
    significativamente entre OD y OI, el plano focal podría no ser
    idéntico para ambos ojos (5.1, etapa 1).
ARQUITECTURA IDEAL:
    Verificar LensPosition antes de cada ojo y re-bloquear si es
    necesario, o exponer una advertencia al orquestador si el enfoque
    derivó más allá de un umbral.
MEJORA FUTURA:
    Añadir esa verificación cuando se disponga de datos reales de cuánto
    deriva el enfoque entre OD y OI en la práctica (requiere el
    dispositivo físico para caracterizarlo).
"""

from __future__ import annotations

from .contratos_hardware import FrameCrudo
from .errores import FalloHardwareError

# np.rot90(imagen, k=-1) = 90° horario; k=1 = 90° antihorario; k=2 = 180°
# (da igual el sentido). Verificado empíricamente (no asumido) antes de
# usarse aquí — ver docstring de FuenteDeVideoPicamera2.rotacion_grados
# para cómo confirmar el valor correcto en tu montaje físico.
_K_ROT90_POR_GRADOS = {0: 0, 90: -1, 180: 2, 270: 1}


class FuenteDeVideoPicamera2:
    """
    Implementación real de FuenteDeVideo sobre Picamera2.

    canal_ir: 'R' por defecto (17.6: "canal=R"), correcto para el sensor
    IMX708 sin filtro de corte IR de la Camera Module 3 NoIR.

    rotacion_grados: corrige la orientación FÍSICA de montaje de la
    cámara en el dispositivo (detectado en la práctica: en este diseño
    la cámara está montada rotada 90° respecto a la orientación vertical
    esperada). Acepta 0, 90, 180 o 270 — el ángulo, en sentido HORARIO,
    que hay que aplicarle a la imagen cruda del sensor para que quede
    orientada como la ve un observador de frente al dispositivo (mismo
    sistema de referencia que geometry.trazar_meridiano() asume: 0° =
    eje vertical de la imagen).

    IMPORTANTE: la dirección correcta (90 vs 270) depende de CÓMO está
    orientado el sensor en tu montaje físico exacto, no se puede adivinar
    desde el código. Verifícala así: corre
    scripts_validacion_pi/verificar_2_camara.py con rotacion_grados=90 y
    revisa la imagen guardada — si sale con la orientación correcta SIN
    que tengas que girar tú la cámara/tu cuerpo al capturar, es el valor
    correcto. Si sale rotada 180° respecto a lo esperado, usa 270 en su
    lugar (nunca "más o menos 90", son las únicas dos opciones posibles
    para un desalineamiento de un cuarto de vuelta).
    """

    def __init__(
        self,
        reloj,
        resolucion: tuple[int, int] = (2304, 1296),
        exposicion_us: int = 10000,
        ganancia_analoga: float = 2.0,
        rotacion_grados: int = 180,
        canal_ir: str = "R",
    ):
        """
        reloj: la MISMA instancia de contratos_hardware.Reloj (típicamente
        adaptadores_gpio.RelojMonotono en la Pi real) que se le pasará a
        SecuenciadorIluminacion y a MotorFotorrefraccionLuxEyes. Ver
        [PRINCIPIO CRÍTICO] en el docstring del módulo — NO es opcional
        para que la sincronización LED-frame tenga sentido.
        """
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise FalloHardwareError(
                "No se pudo importar picamera2. Este adaptador solo "
                "funciona sobre una Raspberry Pi real con la cámara "
                "conectada y picamera2 instalado (requiere libcamera del "
                "sistema, no solo el paquete de pip)."
            ) from exc

        self._Picamera2 = Picamera2
        self._reloj = reloj
        self._resolucion = resolucion
        self._exposicion_us = exposicion_us
        self._ganancia = ganancia_analoga
        self._rotacion = rotacion_grados
        self._canal_ir = canal_ir
        self._camara = None

    def iniciar(self) -> None:
        self._camara = self._Picamera2()
        config = self._camara.create_video_configuration(
            main={"size": self._resolucion, "format": "RGB888"},
        )
        self._camara.configure(config)

        # Parámetros manuales fijos: AE/AWB OFF, enfoque bloqueado (5.1).
        # AfMode=0 (manual) es el valor documentado de libcamera para
        # deshabilitar autoenfoque continuo; se fija ANTES de start().
        self._camara.set_controls({
            "AeEnable": False,
            "AwbEnable": False,
            "ExposureTime": self._exposicion_us,
            "AnalogueGain": self._ganancia,
            "AfMode": 0,
        })

        self._camara.start()

    def leer_frame(self) -> FrameCrudo | None:
        if self._camara is None:
            raise FalloHardwareError("leer_frame() llamado antes de iniciar().")

        import numpy as np

        # CORRECCIÓN (detectada al validar en hardware real, ver
        # scripts_validacion_pi/): capture_array() y capture_metadata()
        # como llamadas SEPARADAS cada una espera de forma independiente
        # al siguiente frame disponible — además de costar ~2x el tiempo
        # de espera (framerate efectivo medido: ~15fps sobre un modo
        # nativo de 56fps), pueden terminar devolviendo imagen y
        # metadatos de frames DISTINTOS. capture_request() devuelve una
        # única petición ya completada; extraer ambos de ahí garantiza
        # que pertenecen al mismo frame físico.
        peticion = self._camara.capture_request()
        try:
            arreglo = peticion.make_array("main")
            metadatos = peticion.get_metadata()
        finally:
            peticion.release()

        # Selección del canal IR (17.6: "canal=R") sin descartar los
        # demás canales de metadatos ya capturados.
        indice_canal = {"R": 0, "G": 1, "B": 2}[self._canal_ir]
        imagen = arreglo[:, :, indice_canal] if arreglo.ndim == 3 else arreglo

        # Ver _K_ROT90_POR_GRADOS al inicio del módulo.
        k = _K_ROT90_POR_GRADOS.get(self._rotacion)
        if k is None:
            raise ValueError(
                f"rotacion_grados debe ser 0, 90, 180 o 270, no {self._rotacion!r}."
            )
        if k != 0:
            imagen = np.rot90(imagen, k)

        # [PRINCIPIO CRÍTICO] (7.3, ver docstring del módulo): el timestamp
        # del frame se toma del RELOJ COMPARTIDO con illumination, nunca
        # del SensorTimestamp propio de libcamera (bases de tiempo
        # distintas, no comparables entre sí).
        timestamp_segundos = self._reloj.ahora()

        duracion_exposicion_us = metadatos.get("ExposureTime", self._exposicion_us)

        return FrameCrudo(
            imagen=imagen,
            timestamp_sensor=timestamp_segundos,
            duracion_exposicion=duracion_exposicion_us / 1e6,
            metadatos={
                "FocusFoM": metadatos.get("FocusFoM"),
                "LensPosition": metadatos.get("LensPosition"),
                "AnalogueGain": metadatos.get("AnalogueGain"),
                # Diagnóstico únicamente: NO usar para sincronización (ver
                # RESTRICCIÓN-ACTUAL / MEJORA FUTURA en el docstring).
                "SensorTimestampHardware": metadatos.get("SensorTimestamp"),
            },
        )

    def detener(self) -> None:
        if self._camara is not None:
            self._camara.stop()
            self._camara.close()
            self._camara = None
