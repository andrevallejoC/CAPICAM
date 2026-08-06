"""
test_orchestrator.py — Pruebas de aceptación de la Fase 3 (orquestador +
contrato de UI mínimo).

Sigue la misma disciplina que test_storage.py y test_sync.py: dobles de
prueba (MotorFalso, ReglasFalsas, ObservadorEspia) que implementan los
contratos de contratos.py, inyectados en OrquestadorTamizaje en lugar de
engine/ y clinical/ reales (que no existen todavía) y de una futura ui/
PySide6.

Cubre los criterios de aceptación exigidos por el MANIFEST para esta fase
("Flujo de uso y máquina de estados con UI mínima de prueba contra el
contrato abstracto"):
  1. Flujo feliz completo, de FORMULARIO_SESION a COMPLETADO.
  2. Validación estructural: datos de sesión/paciente inválidos no avanzan
     el flujo y no llaman a storage/.
  3. Reintento de captura: un fallo del motor no pierde sesión/paciente ya
     ingresados y permite reintentar el mismo ojo.
  4. Reglas clínicas: se invoca clinical/ con ambos ResultadoOjo y el
     resultado queda reflejado en el Tamizaje final.
  5. confirmar_guardado() es el único punto de contacto con storage/, y
     nunca se llama a crear_tamizaje() antes de MOSTRAR_RESULTADO.
  6. Cancelación en distintas etapas: nunca deja un registro en storage/,
     y permite iniciar un tamizaje nuevo después.
  7. Máquina de estados: operaciones fuera de su estado válido lanzan
     EstadoInvalidoError.
  8. Eventos: el observador recibe los eventos de alto nivel esperados,
     en el orden esperado, y un observador que lanza excepciones no
     interrumpe el flujo.
  9. No se llama a sync/ en ningún momento (el orquestador es agnóstico
     de sincronización).
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lux_eyes.common import EstadoSync, ResultadoOjo
from lux_eyes.storage import RepositorioTamizajes
from lux_eyes.orchestrator import (
    EstadoFlujo,
    EstadoInvalidoError,
    ObservadorDeFlujo,
    OrquestadorTamizaje,
)

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


# ── Dobles de prueba ─────────────────────────────────────────────────────
class MotorFalso:
    """Implementa MotorFotorrefraccion sin cámara ni GPIO reales."""

    def __init__(self):
        self.guiones: dict[str, list] = {"od": [], "oi": []}
        self.llamadas: list[str] = []
        self.demora_segundos: float = 0.0  # simula tiempo activo real del dispositivo

    def programar(self, ojo: str, *resultados):
        """Cada resultado es un ResultadoOjo (éxito) o una excepción."""
        self.guiones[ojo] = list(resultados)

    def medir_ojo(self, ojo, reportar_progreso):
        self.llamadas.append(ojo)
        if self.demora_segundos:
            import time
            time.sleep(self.demora_segundos)
        reportar_progreso(f"capturando meridiano 1 ({ojo})")
        reportar_progreso(f"capturando meridiano 2 ({ojo})")
        guion = self.guiones.get(ojo, [])
        resultado = guion.pop(0) if guion else ResultadoOjo(esfera=0.0, cilindro=0.0, eje=0.0)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


class ReglasFalsas:
    """Implementa ReglasClinicas sin umbrales médicos reales."""

    def __init__(self, riesgo="BAJO", requiere_derivacion=False, observaciones=""):
        self._respuesta = (riesgo, requiere_derivacion, observaciones)
        self.llamadas = 0
        self.ultima_edad_meses = None

    def clasificar(self, od, oi, edad_meses):
        self.llamadas += 1
        self.ultima_edad_meses = edad_meses
        return self._respuesta


class ObservadorEspia(ObservadorDeFlujo):
    """Graba cada evento recibido, en orden, para poder inspeccionarlo."""

    def __init__(self, lanzar_en: str | None = None):
        self.eventos: list[tuple] = []
        # Nombre de un evento en el que esta implementación debe lanzar
        # una excepción a propósito, para probar que el orquestador la
        # atrapa sin interrumpir el flujo.
        self._lanzar_en = lanzar_en

    def _registrar(self, nombre, *datos):
        self.eventos.append((nombre, *datos))
        if nombre == self._lanzar_en:
            raise RuntimeError(f"fallo simulado del observador en {nombre}")

    def en_cambio_de_estado(self, estado_anterior, estado_nuevo):
        self._registrar("cambio_de_estado", estado_anterior, estado_nuevo)

    def en_inicio_formulario(self):
        self._registrar("inicio_formulario")

    def en_captura_iniciada(self, ojo):
        self._registrar("captura_iniciada", ojo)

    def en_progreso_captura(self, ojo, mensaje):
        self._registrar("progreso_captura", ojo, mensaje)

    def en_captura_finalizada(self, ojo, resultado):
        self._registrar("captura_finalizada", ojo, resultado)

    def en_procesamiento_iniciado(self):
        self._registrar("procesamiento_iniciado")

    def en_procesamiento_finalizado(self, riesgo, requiere_derivacion, observaciones):
        self._registrar("procesamiento_finalizado", riesgo, requiere_derivacion)

    def en_resultado_listo(self):
        self._registrar("resultado_listo")

    def en_almacenamiento_completado(self, uuid_local):
        self._registrar("almacenamiento_completado", uuid_local)

    def en_error(self, estado, mensaje):
        self._registrar("error", estado, mensaje)

    def en_cancelacion(self, estado_anterior):
        self._registrar("cancelacion", estado_anterior)

    def nombres(self) -> list[str]:
        return [e[0] for e in self.eventos]


def construir_orquestador(repo, motor=None, clinical=None, observador=None):
    return OrquestadorTamizaje(
        repo=repo,
        motor=motor or MotorFalso(),
        clinical=clinical or ReglasFalsas(),
        observador=observador,
    )


def avanzar_hasta_resultado(orq: OrquestadorTamizaje) -> None:
    """Atajo para pruebas que no se enfocan en cada paso individual."""
    orq.iniciar_nuevo_tamizaje()
    orq.recibir_datos_sesion("I.E. San Miguel", "San Miguel", "TM. Rodríguez", "2026-07-01")
    orq.recibir_datos_paciente("12345678", "Ana Pérez", "2015-03-10", "5B")
    orq.ejecutar_captura("od")
    orq.ejecutar_captura("oi")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="luxeyes_orch_"))
    print(f"\nEntorno de prueba: {tmp}\n")

    # ── 1. Flujo feliz completo ──────────────────────────────────────────
    print("1) Flujo feliz completo (FORMULARIO_SESION -> COMPLETADO)")
    repo = RepositorioTamizajes(tmp / "a.db", tmp / "capturas_a")
    motor = MotorFalso()
    motor.programar("od", ResultadoOjo(esfera=1.0, cilindro=-0.5, eje=90.0))
    motor.programar("oi", ResultadoOjo(esfera=0.75, cilindro=-0.25, eje=80.0))
    clinical = ReglasFalsas(riesgo="MODERADO", requiere_derivacion=True)
    espia = ObservadorEspia()
    orq = construir_orquestador(repo, motor, clinical, espia)

    avanzar_hasta_resultado(orq)
    check("tras ambas capturas el estado es MOSTRAR_RESULTADO",
          orq.estado == EstadoFlujo.MOSTRAR_RESULTADO)
    check("clinical/ fue invocado exactamente una vez", clinical.llamadas == 1)
    check("el orquestador calculó edad_meses a partir de fecha_nacimiento/"
          "fecha_sesion y la pasó a clinical.clasificar() (paciente nacido "
          "2015-03-10, sesión 2026-07-01: ~135.7 meses)",
          clinical.ultima_edad_meses is not None
          and abs(clinical.ultima_edad_meses - 135.72) < 0.1)

    uuid_local = orq.confirmar_guardado()
    check("confirmar_guardado devuelve un uuid_local", bool(uuid_local))
    check("el estado final es COMPLETADO", orq.estado == EstadoFlujo.COMPLETADO)

    rec = repo.obtener(uuid_local)
    check("el tamizaje quedó persistido en storage/", rec is not None)
    check("los datos de sesión/paciente coinciden", rec.nombre_paciente == "Ana Pérez")

    # ── CORRECCIÓN: duracion_segundos/timestamp_captura ya no quedan en None ──
    print("\n1b) duracion_segundos y timestamp_captura se llenan de verdad "
          "(bug real: quedaban en None, causaba 422 real en el servidor)")
    check("duracion_segundos NO es None (antes del fix, siempre lo era en "
          "el flujo real, solo se llenaba a mano en fixtures de prueba)",
          rec.duracion_segundos is not None)
    check("duracion_segundos es un número positivo razonable "
          "(mide tiempo real transcurrido, no un valor inventado)",
          isinstance(rec.duracion_segundos, float) and rec.duracion_segundos >= 0)
    check("timestamp_captura NO es None y tiene forma de fecha/hora ISO",
          rec.timestamp_captura is not None and "T" in rec.timestamp_captura)

    # ── CORRECCIÓN 2: la espera humana ENTRE ojos NO cuenta en duracion_segundos ──
    print("\n1c) duracion_segundos excluye la espera humana entre ojos")
    print("    (segundo bug real: un tamizaje real dio 254s por incluir esa")
    print("    espera; el servidor exige <=180s. Ahora solo se cuenta el")
    print("    tiempo real dentro de motor.medir_ojo(), ambos ojos.)")
    import time as _time
    repo2c = RepositorioTamizajes(tmp / "b.db", tmp / "capturas_b")
    motor2c = MotorFalso()
    motor2c.demora_segundos = 0.05  # simula tiempo activo real del dispositivo
    motor2c.programar("od", ResultadoOjo(esfera=1.0, cilindro=0.0, eje=90.0))
    motor2c.programar("oi", ResultadoOjo(esfera=1.0, cilindro=0.0, eje=90.0))
    clinical2c = ReglasFalsas()
    orq2c = construir_orquestador(repo2c, motor2c, clinical2c, ObservadorEspia())

    orq2c.iniciar_nuevo_tamizaje()
    orq2c.recibir_datos_sesion("I.E. San Miguel", "San Miguel", "TM. Rodríguez", "2026-07-01")
    orq2c.recibir_datos_paciente("12345678", "Ana Pérez", "2015-03-10", "5B")
    orq2c.ejecutar_captura("od")
    _time.sleep(0.5)  # simula al tecnólogo reposicionando al paciente para el otro ojo
    orq2c.ejecutar_captura("oi")
    uuid2c = orq2c.confirmar_guardado()

    rec2c = repo2c.obtener(uuid2c)
    check("duracion_segundos NO incluye la pausa de 0.5s entre ojos "
          f"(debería rondar 2x0.05=0.1s, no ~0.6s; valor real: "
          f"{rec2c.duracion_segundos:.3f}s)",
          rec2c.duracion_segundos < 0.3)
    repo2c.cerrar()
    check("los resultados OD/OI coinciden", rec.od.esfera == 1.0 and rec.oi.esfera == 0.75)
    check("la clasificación clínica quedó reflejada", rec.riesgo == "MODERADO")
    check("el tamizaje nace PENDIENTE (orchestrator no llama a sync/)",
          rec.estado_sync == EstadoSync.PENDIENTE)
    repo.cerrar()

    # ── 2. Validación estructural ────────────────────────────────────────
    print("\n2) Validación estructural (nunca clínica)")
    repo2 = RepositorioTamizajes(tmp / "b.db", tmp / "capturas_b")
    espia2 = ObservadorEspia()
    orq2 = construir_orquestador(repo2, observador=espia2)
    orq2.iniciar_nuevo_tamizaje()
    orq2.recibir_datos_sesion("", "San Miguel", "TM. Rodríguez", "fecha-invalida")

    check("con datos de sesión inválidos, el flujo NO avanza",
          orq2.estado == EstadoFlujo.FORMULARIO_SESION)
    check("se emitió un evento de error", "error" in espia2.nombres())

    orq2.recibir_datos_sesion("I.E. San Miguel", "San Miguel", "TM. Rodríguez", "2026-07-01")
    check("con datos válidos, ahora sí avanza",
          orq2.estado == EstadoFlujo.FORMULARIO_PACIENTE)

    orq2.recibir_datos_paciente("", "", "no-es-fecha", "5B")
    check("con datos de paciente inválidos, el flujo NO avanza",
          orq2.estado == EstadoFlujo.FORMULARIO_PACIENTE)
    repo2.cerrar()

    # ── 3. Reintento de captura sin pérdida de datos ────────────────────
    print("\n3) Reintento de captura tras fallo del motor")
    repo3 = RepositorioTamizajes(tmp / "c.db", tmp / "capturas_c")
    motor3 = MotorFalso()
    motor3.programar("od", RuntimeError("pupila no detectada"),
                      ResultadoOjo(esfera=2.0, cilindro=0.0, eje=0.0))
    espia3 = ObservadorEspia()
    orq3 = construir_orquestador(repo3, motor3, observador=espia3)
    orq3.iniciar_nuevo_tamizaje()
    orq3.recibir_datos_sesion("I.E. San Miguel", "San Miguel", "TM. Rodríguez", "2026-07-01")
    orq3.recibir_datos_paciente("12345678", "Ana Pérez", "2015-03-10", "5B")

    orq3.ejecutar_captura("od")  # primer intento: falla
    check("tras el primer fallo, sigue en CAPTURA_OD (reintentable)",
          orq3.estado == EstadoFlujo.CAPTURA_OD)
    check("se emitió un evento de error de captura", "error" in espia3.nombres())

    orq3.ejecutar_captura("od")  # segundo intento: éxito
    check("tras el reintento exitoso, avanza a CAPTURA_OI",
          orq3.estado == EstadoFlujo.CAPTURA_OI)
    check("motor.medir_ojo se llamó 2 veces para 'od' (el reintento)",
          motor3.llamadas.count("od") == 2)
    repo3.cerrar()

    # ── 4. confirmar_guardado es el único contacto con storage/ ─────────
    print("\n4) storage/ nunca se toca antes de MOSTRAR_RESULTADO")
    repo4 = RepositorioTamizajes(tmp / "d.db", tmp / "capturas_d")
    orq4 = construir_orquestador(repo4)
    avanzar_hasta_resultado(orq4)
    conteo_antes = repo4.contar_por_estado()
    check("antes de confirmar_guardado, storage/ sigue vacío",
          sum(conteo_antes.values()) == 0)
    orq4.confirmar_guardado()
    conteo_despues = repo4.contar_por_estado()
    check("después de confirmar_guardado, hay exactamente 1 registro",
          sum(conteo_despues.values()) == 1)
    repo4.cerrar()

    # ── 6. Cancelación en distintas etapas ───────────────────────────────
    print("\n6) Cancelación no deja registros inconsistentes")
    repo6 = RepositorioTamizajes(tmp / "e.db", tmp / "capturas_e")

    # 6a. Cancelar a mitad del formulario
    espia6a = ObservadorEspia()
    orq6a = construir_orquestador(repo6, observador=espia6a)
    orq6a.iniciar_nuevo_tamizaje()
    orq6a.recibir_datos_sesion("I.E. San Miguel", "San Miguel", "TM. Rodríguez", "2026-07-01")
    orq6a.cancelar()
    check("cancelar en FORMULARIO_PACIENTE deja el estado en CANCELADO",
          orq6a.estado == EstadoFlujo.CANCELADO)
    check("se emitió el evento de cancelación", "cancelacion" in espia6a.nombres())
    check("storage/ sigue vacío tras cancelar antes de guardar",
          sum(repo6.contar_por_estado().values()) == 0)

    # 6b. Cancelar a mitad de captura
    orq6a.iniciar_nuevo_tamizaje()
    check("tras cancelar, se puede iniciar un tamizaje nuevo",
          orq6a.estado == EstadoFlujo.FORMULARIO_SESION)
    orq6a.recibir_datos_sesion("I.E. San Miguel", "San Miguel", "TM. Rodríguez", "2026-07-01")
    orq6a.recibir_datos_paciente("12345678", "Ana Pérez", "2015-03-10", "5B")
    orq6a.cancelar()
    check("cancelar durante CAPTURA_OD también es válido",
          orq6a.estado == EstadoFlujo.CANCELADO)
    check("storage/ sigue vacío tras la segunda cancelación",
          sum(repo6.contar_por_estado().values()) == 0)

    # 6c. No se puede cancelar un flujo ya completado
    avanzar_hasta_resultado(orq6a)  # ya llama a iniciar_nuevo_tamizaje() por su cuenta
    orq6a.confirmar_guardado()
    try:
        orq6a.cancelar()
        check("cancelar() tras COMPLETADO lanza EstadoInvalidoError", False)
    except EstadoInvalidoError:
        check("cancelar() tras COMPLETADO lanza EstadoInvalidoError", True)
    repo6.cerrar()

    # ── 7. Máquina de estados: operaciones fuera de estado ───────────────
    print("\n7) Operaciones fuera de su estado válido lanzan EstadoInvalidoError")
    repo7 = RepositorioTamizajes(tmp / "f.db", tmp / "capturas_f")
    orq7 = construir_orquestador(repo7)
    try:
        orq7.recibir_datos_sesion("x", "y", "z", "2026-01-01")
        check("recibir_datos_sesion() sin iniciar_nuevo_tamizaje() lanza error", False)
    except EstadoInvalidoError:
        check("recibir_datos_sesion() sin iniciar_nuevo_tamizaje() lanza error", True)

    orq7.iniciar_nuevo_tamizaje()
    try:
        orq7.ejecutar_captura("od")
        check("ejecutar_captura() antes del paciente lanza error", False)
    except EstadoInvalidoError:
        check("ejecutar_captura() antes del paciente lanza error", True)

    try:
        orq7.confirmar_guardado()
        check("confirmar_guardado() antes de MOSTRAR_RESULTADO lanza error", False)
    except EstadoInvalidoError:
        check("confirmar_guardado() antes de MOSTRAR_RESULTADO lanza error", True)
    repo7.cerrar()

    # ── 8. Eventos: orden esperado y robustez ante observador que falla ─
    print("\n8) Eventos de alto nivel: orden y robustez")
    repo8 = RepositorioTamizajes(tmp / "g.db", tmp / "capturas_g")
    espia8 = ObservadorEspia()
    orq8 = construir_orquestador(repo8, observador=espia8)
    avanzar_hasta_resultado(orq8)
    orq8.confirmar_guardado()

    nombres = espia8.nombres()
    orden_esperado = [
        "cambio_de_estado", "inicio_formulario",  # -> FORMULARIO_SESION
        "cambio_de_estado",  # -> FORMULARIO_PACIENTE
        "cambio_de_estado", "captura_iniciada",  # -> CAPTURA_OD
        "progreso_captura", "progreso_captura", "captura_finalizada",
        "cambio_de_estado", "captura_iniciada",  # -> CAPTURA_OI
        "progreso_captura", "progreso_captura", "captura_finalizada",
        "cambio_de_estado",  # -> REGLAS_CLINICAS
        "procesamiento_iniciado", "procesamiento_finalizado",
        "cambio_de_estado", "resultado_listo",  # -> MOSTRAR_RESULTADO
        "cambio_de_estado",  # -> GUARDAR_LOCAL
        "almacenamiento_completado",
        "cambio_de_estado",  # -> COMPLETADO
    ]
    check("la secuencia de eventos coincide con la esperada",
          nombres == orden_esperado)

    # Observador que falla a propósito en un evento intermedio
    repo8b = RepositorioTamizajes(tmp / "h.db", tmp / "capturas_h")
    espia_rota = ObservadorEspia(lanzar_en="captura_finalizada")
    orq8b = construir_orquestador(repo8b, observador=espia_rota)
    orq8b.iniciar_nuevo_tamizaje()
    orq8b.recibir_datos_sesion("I.E. San Miguel", "San Miguel", "TM. Rodríguez", "2026-07-01")
    orq8b.recibir_datos_paciente("12345678", "Ana Pérez", "2015-03-10", "5B")
    orq8b.ejecutar_captura("od")  # el observador lanza aquí adentro
    check("un observador que lanza excepción no interrumpe el flujo",
          orq8b.estado == EstadoFlujo.CAPTURA_OI)
    repo8.cerrar(); repo8b.cerrar()

    # ── 9. El orquestador nunca importa ni usa sync/ ────────────────────
    print("\n9) orchestrator/ no depende de sync/")
    import ast
    codigo = Path("lux_eyes/orchestrator/orquestador.py").read_text(encoding="utf-8")
    arbol = ast.parse(codigo)
    importa_sync = any(
        "sync" in (getattr(n, "module", "") or "")
        for n in ast.walk(arbol)
        if isinstance(n, (ast.Import, ast.ImportFrom))
    )
    check("orquestador.py no importa lux_eyes.sync", not importa_sync)

    print(f"\n{'='*52}")
    total = _ok + _fail
    color = VERDE if _fail == 0 else ROJO
    print(f"{color}Resultado: {_ok}/{total} pruebas pasadas, {_fail} fallidas{RESET}")
    print(f"{'='*52}\n")
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
