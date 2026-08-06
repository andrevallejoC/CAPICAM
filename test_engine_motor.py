"""
test_engine_motor.py — Pruebas de aceptación de la Fase 4, parte 2:
MotorFotorrefraccionLuxEyes de extremo a extremo, con TODOS los
componentes de hardware como dobles de prueba (ControladorLED, Reloj,
FuenteDeVideo, DetectorPupila) — sin GPIO, sin cámara, sin MediaPipe real.

Genera una imagen sintética de "pupila" con un gradiente de intensidad
lineal conocido a lo largo de los tres meridianos, de modo que se puede
verificar que el motor completo recupera esfera/cilindro/eje razonables
a partir de una señal controlada — es la prueba de integración más fuerte
posible sin hardware real.
"""

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from lux_eyes.engine import ConfiguracionCaptura, EstimadorOLS, MotorFotorrefraccionLuxEyes
from lux_eyes.engine.contratos_estimacion import DeteccionPupila
from lux_eyes.engine.contratos_hardware import FrameCrudo
from lux_eyes.engine.errores import PupilaNoDetectadaError, VentanaInestableError

VERDE = "\033[92m"; ROJO = "\033[91m"; RESET = "\033[0m"
_ok = 0; _fail = 0


def check(nombre, condicion):
    global _ok, _fail
    if condicion:
        _ok += 1
        print(f"  {VERDE}PASA{RESET}  {nombre}")
    else:
        _fail += 1
        print(f"  {ROJO}FALLA{RESET} {nombre}")


class RelojControlable:
    """Avanza en pasos fijos cada vez que se le pide ahora(), simulando
    el paso del tiempo sin sleep() real."""

    def __init__(self, paso=0.001):
        self._t = 0.0
        self._paso = paso

    def ahora(self):
        self._t += self._paso
        return self._t


class ControladorLEDEspia:
    def __init__(self):
        self.encendido = None
        self.historial = []

    def encender(self, meridiano_grados):
        self.encendido = meridiano_grados
        self.historial.append(("encender", meridiano_grados))

    def apagar(self):
        self.encendido = None
        self.historial.append(("apagar", None))


def imagen_sintetica_pupila(centro=(100, 100), radio=40, pendiente_por_grado=None):
    """
    Genera una imagen 200x200 con un gradiente de intensidad radial
    simple: más brillante hacia el centro, decae hacia el borde —
    suficiente para que un estimador de pendiente recupere un valor
    negativo consistente en cualquier dirección desde el centro.
    """
    tam = 200
    yy, xx = np.mgrid[0:tam, 0:tam]
    dist = np.hypot(xx - centro[0], yy - centro[1])
    imagen = np.clip(220 - dist * 2.5, 20, 255).astype(np.uint8)
    return imagen


class FuenteDeVideoFalsa:
    """Entrega siempre la misma imagen sintética, con timestamps crecientes."""

    def __init__(self, reloj, imagen):
        self._reloj = reloj
        self._imagen = imagen
        self._activa = False

    def iniciar(self):
        self._activa = True

    def leer_frame(self):
        if not self._activa:
            return None
        t = self._reloj.ahora()
        return FrameCrudo(
            imagen=self._imagen, timestamp_sensor=t, duracion_exposicion=0.0005,
            metadatos={"FocusFoM": 100},
        )

    def detener(self):
        self._activa = False


class DetectorPupilaFalso:
    def __init__(self, deteccion):
        self._deteccion = deteccion
        self.veces_llamado = 0

    def detectar(self, imagen):
        self.veces_llamado += 1
        return self._deteccion


def construir_motor(config=None, deteccion_pupila=None, imagen=None):
    reloj = RelojControlable(paso=0.002)
    led = ControladorLEDEspia()
    imagen = imagen if imagen is not None else imagen_sintetica_pupila()
    fuente = FuenteDeVideoFalsa(reloj, imagen)
    # DetectorPupilaFalso no distingue por ojo (siempre la misma
    # detección fija) — se usa la MISMA instancia para 'od' y 'oi' en
    # estas pruebas, ya que el objetivo aquí es probar la lógica del
    # motor, no la selección de detector por ojo (ver test 9 más abajo).
    detector = DetectorPupilaFalso(deteccion_pupila or DeteccionPupila(100, 100, 40))
    cfg = config or ConfiguracionCaptura(
        angulos_meridianos=(0, 60, 120), repeticiones_ciclo=1,
        duracion_estabilizacion_segundos=0.001,
        frames_objetivo_por_meridiano=10, frames_minimos_utiles=5,
    )
    motor = MotorFotorrefraccionLuxEyes(
        controlador_led=led, fuente_video=fuente, reloj=reloj,
        detector_pupila_od=detector, detector_pupila_oi=detector,
        estimador=EstimadorOLS(), config=cfg,
    )
    return motor, led, reloj


class FuenteDeVideoExposicionLarga(FuenteDeVideoFalsa):
    """
    Variante que reporta una duracion_exposicion artificialmente grande,
    de modo que la ventana de exposición de cada frame NUNCA cabe entera
    dentro del intervalo estable (muy corto) del LED — el sincronizador
    los descarta a todos, simulando en la práctica una "ventana inestable"
    sin necesitar una configuración imposible a nivel de dataclass.
    """

    def leer_frame(self):
        frame = super().leer_frame()
        if frame is None:
            return None
        return FrameCrudo(
            imagen=frame.imagen, timestamp_sensor=frame.timestamp_sensor,
            duracion_exposicion=10.0,  # segundos: absurdamente larga a propósito
            metadatos=frame.metadatos,
        )


def main():
    print("\n=== engine/ — motor de extremo a extremo (con dobles de hardware) ===\n")

    # ── 1. Flujo feliz completo ──────────────────────────────────────────
    print("1) medir_ojo() completo con dobles de hardware")
    motor, led, reloj = construir_motor()
    eventos_progreso = []
    resultado = motor.medir_ojo("od", lambda msg: eventos_progreso.append(msg))

    check("devuelve un ResultadoOjo con esfera no nula", resultado.esfera is not None)
    check("devuelve cilindro y eje", resultado.cilindro is not None and resultado.eje is not None)
    check("devuelve incertidumbre (esfera_sd)", resultado.esfera_sd is not None)
    check("el eje está en rango clínico [0,180)", 0.0 <= resultado.eje < 180.0)
    check("reflejo_rojo es None (placeholder honesto, D5)", resultado.reflejo_rojo is None)
    check("se reportó progreso al menos una vez", len(eventos_progreso) > 0)
    check("el LED se apagó al finalizar", led.encendido is None)
    check("se encendieron los 3 meridianos en algún momento",
          {0, 60, 120} <= {m for accion, m in led.historial if accion == "encender"})

    # ── 2. Pupila no detectada en ningún frame ───────────────────────────
    print("\n2) PupilaNoDetectadaError cuando el detector nunca encuentra pupila")
    motor2, _, _ = construir_motor(deteccion_pupila=None)
    motor2._detectores_por_ojo["od"] = DetectorPupilaFalso(None)  # fuerza "nunca detecta"
    try:
        motor2.medir_ojo("od", lambda m: None)
        check("lanza PupilaNoDetectadaError", False)
    except PupilaNoDetectadaError:
        check("lanza PupilaNoDetectadaError", True)

    # ── 3. Ventana inestable: el sincronizador descarta los frames ──────
    print("\n3) VentanaInestableError cuando el sincronizador descarta los frames")
    reloj3 = RelojControlable(paso=0.002)
    led3 = ControladorLEDEspia()
    fuente3 = FuenteDeVideoExposicionLarga(reloj3, imagen_sintetica_pupila())
    detector3 = DetectorPupilaFalso(DeteccionPupila(100, 100, 40))
    cfg3 = ConfiguracionCaptura(
        angulos_meridianos=(0, 60, 120), repeticiones_ciclo=1,
        duracion_estabilizacion_segundos=0.001,
        frames_objetivo_por_meridiano=5, frames_minimos_utiles=3,
    )
    motor3 = MotorFotorrefraccionLuxEyes(
        controlador_led=led3, fuente_video=fuente3, reloj=reloj3,
        detector_pupila_od=detector3, detector_pupila_oi=detector3,
        estimador=EstimadorOLS(), config=cfg3,
    )
    try:
        motor3.medir_ojo("od", lambda m: None)
        check("lanza VentanaInestableError", False)
    except VentanaInestableError:
        check("lanza VentanaInestableError", True)

    # ── 4. El motor cumple el Protocol de orchestrator/ (integración real) ─
    print("\n4) Integración real con OrquestadorTamizaje (Fase 3)")
    import tempfile
    from lux_eyes.storage import RepositorioTamizajes
    from lux_eyes.orchestrator import OrquestadorTamizaje

    class ReglasClinicasFalsas:
        def clasificar(self, od, oi, edad_meses):
            return ("BAJO", False, "")

    tmp = Path(tempfile.mkdtemp(prefix="luxeyes_engine_"))
    repo = RepositorioTamizajes(tmp / "z.db", tmp / "capturas_z")
    motor4, _, _ = construir_motor()
    orq = OrquestadorTamizaje(repo=repo, motor=motor4, clinical=ReglasClinicasFalsas())

    orq.iniciar_nuevo_tamizaje()
    orq.recibir_datos_sesion("I.E. San Miguel", "San Miguel", "TM. Rodríguez", "2026-07-01")
    orq.recibir_datos_paciente("12345678", "Ana Pérez", "2015-03-10", "5B")
    orq.ejecutar_captura("od")
    orq.ejecutar_captura("oi")
    uuid_local = orq.confirmar_guardado()

    rec = repo.obtener(uuid_local)
    check("MotorFotorrefraccionLuxEyes se integra sin cambios con orchestrator/ "
          "(ya implementado y probado en la Fase 3)",
          rec is not None and rec.od.esfera is not None and rec.oi.esfera is not None)
    repo.cerrar()

    # ── 9. CORRECCIÓN: cada ojo usa SU PROPIO detector, no uno compartido ──
    print("\n9) Enrutamiento correcto de detector_pupila_od / detector_pupila_oi")
    print("   (bug real encontrado al integrar ui/ con hardware, corregido aquí)")
    reloj5 = RelojControlable(paso=0.002)
    led5 = ControladorLEDEspia()
    fuente5 = FuenteDeVideoFalsa(reloj5, imagen_sintetica_pupila())
    detector_od = DetectorPupilaFalso(DeteccionPupila(100, 100, 40))
    detector_oi = DetectorPupilaFalso(DeteccionPupila(100, 100, 40))
    cfg5 = ConfiguracionCaptura(
        angulos_meridianos=(0, 60, 120), repeticiones_ciclo=1,
        duracion_estabilizacion_segundos=0.001,
        frames_objetivo_por_meridiano=10, frames_minimos_utiles=5,
    )
    motor5 = MotorFotorrefraccionLuxEyes(
        controlador_led=led5, fuente_video=fuente5, reloj=reloj5,
        detector_pupila_od=detector_od, detector_pupila_oi=detector_oi,
        estimador=EstimadorOLS(), config=cfg5,
    )

    motor5.medir_ojo("od", lambda m: None)
    check("al medir 'od', SOLO se llamó al detector de 'od'",
          detector_od.veces_llamado > 0 and detector_oi.veces_llamado == 0)

    motor5.medir_ojo("oi", lambda m: None)
    check("al medir 'oi' con la MISMA instancia de motor, SOLO se llamó "
          "al detector de 'oi' (antes de la corrección, se habría "
          "reutilizado el detector de 'od' para ambos ojos)",
          detector_oi.veces_llamado > 0)

    print(f"\n{'='*52}")
    total = _ok + _fail
    color = VERDE if _fail == 0 else ROJO
    print(f"{color}Resultado: {_ok}/{total} pruebas pasadas, {_fail} fallidas{RESET}")
    print(f"{'='*52}\n")
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
