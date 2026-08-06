"""
test_clinical.py — Pruebas de aceptación del módulo clinical/
(ReglasClinicasAAPOS), con los criterios reales validados por Luxeyes.

Cubre los 4 criterios (miopía, hipermetropía, astigmatismo,
anisometropía), la estratificación por edad (corte en 48 meses), los
valores límite exactos de cada umbral, y que la nota de limitación
(estrabismo/opacidad de medios no evaluados) esté SIEMPRE presente.

DECISIÓN de la prueba: para aislar cada criterio de forma limpia, los
tests de miopía/hipermetropía/astigmatismo aplican el MISMO valor a
ambos ojos (od y oi) — así el meridiano_menor coincide entre ambos y
anisometropía nunca se dispara por accidente, contaminando el resultado.
Anisometropía se prueba aparte, con ojos deliberadamente distintos.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lux_eyes.common.tipos import ResultadoOjo
from lux_eyes.clinical import NivelRiesgo, ReglasClinicasAAPOS, UmbralesRiesgo

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


def ojo(esfera=0.0, cilindro=0.0, eje=90.0):
    return ResultadoOjo(esfera=esfera, cilindro=cilindro, eje=eje)


def par_simetrico(esfera=0.0, cilindro=0.0):
    """Mismos valores en ambos ojos: aísla el criterio bajo prueba sin
    disparar anisometropía por accidente."""
    return ojo(esfera, cilindro), ojo(esfera, cilindro)


def main():
    print("\n=== clinical/ — ReglasClinicasAAPOS ===\n")
    reglas = ReglasClinicasAAPOS()

    # ── 1. Sin ningún criterio: SIN_RIESGO ───────────────────────────────
    print("1) Ojos sanos, sin ningún criterio")
    od, oi = par_simetrico(0.0, 0.0)
    riesgo, derivar, obs = reglas.clasificar(od, oi, edad_meses=60)
    check("riesgo = SIN_RIESGO", riesgo == NivelRiesgo.SIN_RIESGO.value)
    check("requiere_derivacion = False", derivar is False)
    check("la nota de limitación SIEMPRE está presente, incluso sin riesgo",
          "estrabismo" in obs and "opacidad de medios" in obs)

    # ── 2. Hipermetropía (sin estratificar por edad) ─────────────────────
    print("\n2) Hipermetropía (umbral único >4.00D, sin estratificar; ambos ojos iguales)")
    od, oi = par_simetrico(4.01, 0.0)
    r, d, o = reglas.clasificar(od, oi, edad_meses=24)
    check("4.01D (ambos ojos) a 24 meses SÍ dispara hipermetropía", d is True)
    check("riesgo = MODERADO", r == NivelRiesgo.MODERADO.value)
    check("'hipermetropía' aparece en observaciones", "hipermetropía" in o)

    od, oi = par_simetrico(4.00, 0.0)
    r, d, o = reglas.clasificar(od, oi, edad_meses=24)
    check("exactamente 4.00D (ambos ojos) NO dispara (umbral es estrictamente '>')",
          d is False)

    od, oi = par_simetrico(4.01, 0.0)
    r, d, o = reglas.clasificar(od, oi, edad_meses=70)
    check("4.01D a 70 meses (>48) TAMBIÉN dispara (sin estratificar)", d is True)

    # ── 3. Miopía: estratificada, corte en 48 meses ──────────────────────
    print("\n3) Miopía (estratificada: <48m umbral -3.00D, >=48m umbral -2.00D; ambos ojos iguales)")
    od, oi = par_simetrico(-3.01, 0.0)
    r, d, o = reglas.clasificar(od, oi, edad_meses=47.9)
    check("-3.01D a 47.9 meses (<48) SÍ dispara miopía", d is True)

    od, oi = par_simetrico(-3.00, 0.0)
    r, d, o = reglas.clasificar(od, oi, edad_meses=47.9)
    check("exactamente -3.00D a 47.9 meses NO dispara (umbral estricto)", d is False)

    od, oi = par_simetrico(-2.50, 0.0)
    r, d, o = reglas.clasificar(od, oi, edad_meses=47.9)
    check("-2.50D a 47.9 meses (entre -2.00 y -3.00) NO dispara con el "
          "umbral de menores de 48 meses (-3.00)", d is False)

    od, oi = par_simetrico(-2.01, 0.0)
    r, d, o = reglas.clasificar(od, oi, edad_meses=48.0)
    check("-2.01D exactamente a 48 meses (corte incluido en '>=') usa el "
          "umbral de mayores: SÍ dispara", d is True)

    od, oi = par_simetrico(-2.00, 0.0)
    r, d, o = reglas.clasificar(od, oi, edad_meses=48.0)
    check("exactamente -2.00D a 48 meses NO dispara (umbral estricto)", d is False)

    od, oi = par_simetrico(-2.50, 0.0)
    r, d, o = reglas.clasificar(od, oi, edad_meses=60)
    check("riesgo = BAJO para miopía sola", r == NivelRiesgo.BAJO.value)

    # ── 4. Astigmatismo: estratificado, sobre |cilindro| ─────────────────
    print("\n4) Astigmatismo (estratificado: <48m umbral 3.00D, >=48m umbral 1.75D; ambos ojos iguales)")
    od, oi = par_simetrico(0.0, -3.01)
    r, d, o = reglas.clasificar(od, oi, edad_meses=36)
    check("|cilindro|=3.01D a 36 meses (<48) SÍ dispara astigmatismo", d is True)

    od, oi = par_simetrico(0.0, -3.00)
    r, d, o = reglas.clasificar(od, oi, edad_meses=36)
    check("exactamente |cilindro|=3.00D a 36 meses NO dispara", d is False)

    od, oi = par_simetrico(0.0, -1.76)
    r, d, o = reglas.clasificar(od, oi, edad_meses=60)
    check("|cilindro|=1.76D a 60 meses (>=48) SÍ dispara astigmatismo", d is True)

    od, oi = par_simetrico(0.0, -1.75)
    r, d, o = reglas.clasificar(od, oi, edad_meses=60)
    check("exactamente |cilindro|=1.75D a 60 meses NO dispara", d is False)

    od_neg, oi_neg = par_simetrico(0.0, -2.0)
    od_pos, oi_pos = par_simetrico(0.0, 2.0)
    check("el signo del cilindro no importa (se usa valor absoluto)",
          reglas.clasificar(od_neg, oi_neg, edad_meses=60)[1]
          == reglas.clasificar(od_pos, oi_pos, edad_meses=60)[1])

    # ── 5. Anisometropía: sobre meridiano menor (esfera+cilindro), ambos ojos ──
    print("\n5) Anisometropía (umbral 1.25D sobre |meridiano_menor_OD - meridiano_menor_OI|)")
    # meridiano_menor = esfera + cilindro
    od = ojo(esfera=0.0, cilindro=0.0)     # meridiano_menor = 0.0
    oi = ojo(esfera=1.26, cilindro=0.0)    # meridiano_menor = 1.26
    r, d, o = reglas.clasificar(od, oi, edad_meses=60)
    check("diferencia de 1.26D entre meridianos menores SÍ dispara anisometropía",
          d is True)
    check("riesgo = ALTO para anisometropía (máxima severidad)",
          r == NivelRiesgo.ALTO.value)

    od = ojo(esfera=0.0, cilindro=0.0)
    oi = ojo(esfera=1.25, cilindro=0.0)
    r, d, o = reglas.clasificar(od, oi, edad_meses=60)
    check("diferencia de exactamente 1.25D NO dispara (umbral estricto)", d is False)

    # Caso donde esfera sola no lo detectaría, pero meridiano_menor sí:
    # dos ojos con la misma esfera pero cilindros distintos.
    od = ojo(esfera=1.0, cilindro=0.0)      # meridiano_menor = 1.0
    oi = ojo(esfera=1.0, cilindro=-1.50)    # meridiano_menor = -0.5
    r, d, o = reglas.clasificar(od, oi, edad_meses=60)
    check("con esferas IGUALES pero cilindros distintos, la anisometropía "
          "por meridiano menor SÍ se detecta (diferencia = 1.5D) — "
          "confirma que no se usa solo esfera",
          d is True)
    check("'anisometropía' aparece en observaciones", "anisometropía" in o)

    od_a = ojo(0.0, 0.0)
    oi_a = ojo(1.26, 0.0)
    check("anisometropía NO se estratifica por edad (mismo umbral a 24 y 60 meses)",
          reglas.clasificar(od_a, oi_a, edad_meses=24)[1]
          == reglas.clasificar(od_a, oi_a, edad_meses=60)[1]
          == True)

    # ── 6. Múltiples criterios a la vez: reporta el nivel más alto ──────
    print("\n6) Múltiples criterios cumplidos simultáneamente")
    od_hiperopia = ojo(esfera=5.0, cilindro=0.0)       # hipermetropía
    oi_anisometropia = ojo(esfera=7.0, cilindro=0.0)   # + anisometropía (dif=2.0 > 1.25)
    r, d, o = reglas.clasificar(od_hiperopia, oi_anisometropia, edad_meses=60)
    check("con hipermetropía Y anisometropía a la vez, prevalece ALTO "
          "(el criterio más severo, no el primero evaluado)",
          r == NivelRiesgo.ALTO.value)
    check("ambos criterios aparecen listados en observaciones",
          "hipermetropía" in o and "anisometropía" in o)

    # ── 7. Datos faltantes (None): nunca lanza, simplemente no dispara ──
    print("\n7) Robustez ante datos faltantes (esfera/cilindro en None)")
    od_incompleto = ResultadoOjo(esfera=None, cilindro=None, eje=None)
    oi_sano = ojo(0.0, 0.0)
    try:
        r, d, o = reglas.clasificar(od_incompleto, oi_sano, edad_meses=60)
        check("no lanza excepción con esfera/cilindro en None", True)
        check("con datos faltantes en un ojo, ese criterio simplemente no "
              "se marca como cumplido (no revienta ni asume peor caso)",
              d is False)
    except Exception as e:
        check(f"no lanza excepción con esfera/cilindro en None ({e})", False)

    # ── 8. Umbrales inyectables (no cableados) ───────────────────────────
    print("\n8) UmbralesRiesgo es inyectable (no está cableado en reglas.py)")
    umbrales_estrictos = UmbralesRiesgo(hiperopia_dioptrias=1.0)
    reglas_estrictas = ReglasClinicasAAPOS(umbrales_estrictos)
    od_e, oi_e = par_simetrico(1.5, 0.0)
    r, d, o = reglas_estrictas.clasificar(od_e, oi_e, edad_meses=60)
    check("con un umbral inyectado más estricto (1.0D), 1.5D SÍ dispara "
          "(confirma que los umbrales no están cableados en la lógica)",
          d is True)
    r, d, o = reglas.clasificar(od_e, oi_e, edad_meses=60)
    check("con los umbrales por defecto (4.0D), el mismo 1.5D NO dispara",
          d is False)

    probar_integracion_con_orchestrator()

    print(f"\n{'='*52}")
    total = _ok + _fail
    color = VERDE if _fail == 0 else ROJO
    print(f"{color}Resultado: {_ok}/{total} pruebas pasadas, {_fail} fallidas{RESET}")
    print(f"{'='*52}\n")
    return 0 if _fail == 0 else 1


def probar_integracion_con_orchestrator():
    """
    Integración real (no con dobles falsos): OrquestadorTamizaje +
    ReglasClinicasAAPOS de verdad, cerrando el ciclo del cambio de
    contrato (edad_meses agregado a ReglasClinicas.clasificar en la
    Fase 3). Hasta ahora orchestrator/ solo se había probado con
    ReglasFalsas; esto confirma que la implementación real encaja sin
    fricciones con el resto del flujo ya construido y probado.
    """
    print("\n=== Integración real: orchestrator/ + clinical/ ===\n")
    import tempfile

    from lux_eyes.storage import RepositorioTamizajes
    from lux_eyes.orchestrator import OrquestadorTamizaje

    class MotorFalso:
        def medir_ojo(self, ojo, reportar_progreso):
            # Valores que disparan hipermetropía (>4.00D) a propósito,
            # para confirmar que el riesgo real se propaga hasta storage/.
            return ResultadoOjo(esfera=4.5, cilindro=0.0, eje=90.0)

    tmp = Path(tempfile.mkdtemp(prefix="luxeyes_clinical_integracion_"))
    repo = RepositorioTamizajes(tmp / "z.db", tmp / "capturas_z")
    orq = OrquestadorTamizaje(repo=repo, motor=MotorFalso(), clinical=ReglasClinicasAAPOS())

    orq.iniciar_nuevo_tamizaje()
    orq.recibir_datos_sesion("I.E. San Miguel", "San Miguel", "TM. Rodríguez", "2026-07-01")
    # Paciente de 5 años exactos (60 meses) para que la estratificación
    # por edad use el bracket de "mayores de 48 meses".
    orq.recibir_datos_paciente("12345678", "Ana Pérez", "2021-07-01", "5B")
    orq.ejecutar_captura("od")
    orq.ejecutar_captura("oi")
    uuid_local = orq.confirmar_guardado()

    rec = repo.obtener(uuid_local)
    check("el riesgo real (no un doble falso) llegó hasta storage/",
          rec.riesgo == NivelRiesgo.MODERADO.value)
    check("requiere_derivacion real llegó hasta storage/",
          rec.requiere_derivacion is True)
    check("la nota de limitación real llegó hasta storage/ en observaciones",
          "estrabismo" in rec.observaciones)
    repo.cerrar()


if __name__ == "__main__":
    sys.exit(main())
