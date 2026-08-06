"""
sync/serializacion.py — Traduce un Tamizaje al payload JSON del contrato
de la API (Documento Maestro, apéndice 17.3).

Es una función pura: no hace I/O, no conoce HTTP ni storage/. Aísla el
contrato de datos externo del resto de sync/, de modo que un cambio en el
contrato (como la incorporación de uuid_local, ver más abajo) quede
contenido en este único archivo.

PRINCIPIO heredado de storage/tipos.py:
    El DNI se guarda en claro SOLO localmente. Este módulo es el único
    lugar del sistema donde el DNI se transforma antes de salir del
    dispositivo (SHA-256, nunca en claro por red). El hash se calcula al
    vuelo en cada llamada; nunca se persiste.
"""

from __future__ import annotations

import hashlib

from lux_eyes.common.tipos import Tamizaje, ResultadoOjo

from .configuracion import ConfiguracionSync


def _hash_dni(dni: str) -> str | None:
    if not dni:
        return None
    return hashlib.sha256(dni.encode("utf-8")).hexdigest()


def _resultado_ojo_a_dict(r: ResultadoOjo) -> dict:
    return {
        "esfera": r.esfera,
        "cilindro": r.cilindro,
        # [CORRECCIÓN] Confirmado por 422 real del servidor: exige "eje"
        # como entero estricto (int_from_float rechaza 90.0). El pipeline
        # de engine/ calcula el eje en punto flotante (grados con
        # precisión sub-entero), pero clínicamente el eje siempre se
        # reporta en grados enteros — redondear (no truncar) al enviar no
        # distorsiona el significado clínico, a diferencia de la decisión
        # sobre reflejo_rojo_presente (ver esa función, más abajo). El
        # valor completo, sin redondear, se sigue guardando intacto en
        # storage/ local — esta pérdida de precisión de <1° solo aplica
        # al payload que sale hacia la API.
        "eje": round(r.eje) if r.eje is not None else None,
        "reflejo_rojo_presente": _reflejo_rojo_presente_o_provisional(r.reflejo_rojo),
    }


def _reflejo_rojo_presente_o_provisional(reflejo_rojo: bool | None) -> bool:
    """
    [DECISIÓN, aprobada por Luxeyes] El backend exige reflejo_rojo_presente
    como booleano estricto (confirmado por 422 real del servidor: rechaza
    null). El dispositivo NUNCA evalúa esto todavía (deuda D5 — sin módulo
    de detección de reflejo rojo); MotorFotorrefraccionLuxEyes siempre
    devuelve reflejo_rojo=None, honestamente.

    Se decidió enviar True cuando no fue evaluado (r.reflejo_rojo is None),
    en vez de False, para no generar un falso positivo de alarma clínica
    (False implicaría "reflejo ausente", un hallazgo real que podría
    alarmar a un padre o médico sin que el dispositivo lo haya constatado).
    True, en cambio, se interpreta como "sin hallazgo anómalo reportado" —
    más cercano a "no evaluado" que a una alarma activa, aunque SIGUE
    siendo una aproximación imperfecta, no un valor clínico real.

    RESTRICCIÓN-ACTUAL: esto puede ocultar un problema real de opacidad de
    medios que el dispositivo simplemente no puede detectar todavía. La
    nota en `observaciones` (ver tamizaje_a_payload) es lo único que
    comunica esta limitación a quien lea el reporte.
    ARQUITECTURA IDEAL: implementar D5 (detección real de reflejo rojo) y
    eliminar esta función — cuando exista una medición real, r.reflejo_rojo
    nunca será None y esta coerción deja de aplicarse.
    """
    return True if reflejo_rojo is None else reflejo_rojo


_NOTA_REFLEJO_ROJO_PROVISIONAL = (
    "AVISO: reflejo rojo no evaluado (D5); enviado como true por defecto."
)

# [DECISIÓN, aprobada por Luxeyes — TEMPORAL, para destrabar la validación
# de conectividad mientras el backend no puede modificarse] Confirmado por
# 422 real del servidor: duracion_captura_segundos exige <=180. Una
# captura real puede legítimamente tomar más (reintentos por mala
# posición, etc.) — el valor real, sin recortar, sigue intacto en
# storage/ local; SOLO el payload de salida se topa aquí. Esto OCULTA
# capturas genuinamente largas ante quien lea el reporte/analítica del
# backend — no es una solución de fondo. La solución correcta es que el
# backend suba este límite o lo vuelva opcional; hablar con el equipo de
# backend antes de dar esto por definitivo.
_MAXIMO_DURACION_CAPTURA_SEGUNDOS = 179
_NOTA_DURACION_TOPADA = (
    "AVISO: duración recortada a {tope}s (real fue mayor; límite servidor=180s)."
)

# [CORRECCIÓN — confirmado contra el modelo Pydantic real del backend,
# app/models.py] TamizajePayload.observaciones tiene max_length=500 —
# nunca lo respetábamos. Con la nota clínica real (de clinical/, que ya
# puede ser larga por sí sola) más las notas PROVISIONALES que este mismo
# archivo agrega, el total supera 500 con facilidad — confirmado por un
# 422 real ("string_too_long"). Se prioriza SIEMPRE la nota clínica real
# (lo más importante para quien lea el reporte); si no alcanza el
# espacio, se recortan primero las notas técnicas PROVISIONALES, y como
# último recurso se trunca el conjunto entero con "…" — nunca se envía
# más de 500 caracteres. t.observaciones (sin tocar, completo) sigue
# intacto en storage/ local.
_MAXIMO_OBSERVACIONES = 500

# [CORRECCIÓN — mismo modelo real] TamizajePayload.riesgo_ambliopía solo
# acepta {"BAJO", "MODERADO", "ALTO"} — clinical/reglas.py.NivelRiesgo
# tiene un CUARTO nivel, SIN_RIESGO, que el backend no contempla en
# absoluto (confirmado por 422 real: "riesgo_ambliopía debe ser uno de:
# {...}. Se recibió: 'SIN_RIESGO'"). Se mapea a "BAJO" — la categoría
# menos severa que el backend sí acepta — SOLO para el payload de salida;
# storage/ local conserva "SIN_RIESGO" tal cual, ya que es una distinción
# clínicamente real y útil (un tamizaje sin ningún criterio cumplido no
# es lo mismo que uno con criterios de baja severidad) que solo el
# backend no puede representar todavía.
_MAPEO_RIESGO_A_BACKEND = {
    "SIN_RIESGO": "BAJO",
}


def _riesgo_para_payload(riesgo: str | None) -> str:
    if riesgo is None:
        # No debería ocurrir en la práctica (clinical/ siempre devuelve
        # un string), pero ante lo inesperado se usa la categoría menos
        # severa en vez de fallar o inventar un riesgo alto sin base.
        return "BAJO"
    return _MAPEO_RIESGO_A_BACKEND.get(riesgo, riesgo)


def _observaciones_para_payload(t: Tamizaje) -> str:
    """
    Igual que t.observaciones, salvo que agrega notas de advertencia
    PROVISIONALES cuando el payload de salida se desvía del dato real por
    exigencias del backend (reflejo rojo no evaluado, duración topada) —
    solo cuando de verdad aplica cada una — y garantiza no superar
    _MAXIMO_OBSERVACIONES caracteres en total (ver esa constante).
    NUNCA modifica t.observaciones en sí (eso se queda intacto en
    storage/ local).
    """
    notas = []
    if t.od.reflejo_rojo is None or t.oi.reflejo_rojo is None:
        notas.append(_NOTA_REFLEJO_ROJO_PROVISIONAL)
    if t.duracion_segundos is not None and t.duracion_segundos > _MAXIMO_DURACION_CAPTURA_SEGUNDOS:
        notas.append(_NOTA_DURACION_TOPADA.format(tope=_MAXIMO_DURACION_CAPTURA_SEGUNDOS))

    base = t.observaciones or ""
    completo = base if not notas else (f"{base} " + " ".join(notas)).strip()

    if len(completo) <= _MAXIMO_OBSERVACIONES:
        return completo

    # No cabe todo: se prioriza la nota clínica real, recortando primero
    # las notas técnicas (las de este archivo), y si aun así no alcanza,
    # se trunca el conjunto con "…" como último recurso.
    if len(base) < _MAXIMO_OBSERVACIONES:
        margen = _MAXIMO_OBSERVACIONES - len(base) - 2  # 2 = espacio + "…"
        notas_recortadas = (" ".join(notas))[:margen]
        return f"{base} {notas_recortadas}…".strip()
    return base[: _MAXIMO_OBSERVACIONES - 1] + "…"


def _duracion_captura_segundos_para_payload(duracion_segundos: float | None) -> int | None:
    """Redondea a entero y aplica el tope PROVISIONAL — ver docstring arriba."""
    if duracion_segundos is None:
        return None
    return min(round(duracion_segundos), _MAXIMO_DURACION_CAPTURA_SEGUNDOS)


def _grado_seccion_para_payload(grado_seccion: str | None) -> str | None:
    """
    [CORRECCIÓN — mismo modelo real] TamizajePayload.grado_seccion tiene
    max_length=10 — nunca lo respetábamos. No confirmado por un 422 real
    todavía (a diferencia de los demás fixes de este archivo), pero sí
    por el esquema del backend; se corrige preventivamente antes de que
    un grado/sección real más largo ("Kinder B", "Primero C", etc.)
    dispare el mismo tipo de rechazo.
    """
    if grado_seccion is None:
        return None
    return grado_seccion[:10]


def tamizaje_a_payload(t: Tamizaje, config: ConfiguracionSync) -> dict:
    """
    Construye el JSON del Paso 1 (POST /api/v1/tamizaje/sincronizar).

    DECISIÓN (aprobada, Fase 2):
        Se añade "uuid_local" al payload aunque el contrato documentado en
        17.3 no lo contempla.

        RESTRICCIÓN-ACTUAL:
            El backend actual no utiliza ni garantiza idempotencia con este
            campo (deuda D1); es razonable asumir que lo ignora sin error,
            ya que la mayoría de APIs REST descartan campos desconocidos.
        ARQUITECTURA IDEAL:
            El backend reconoce uuid_local como clave de idempotencia y
            evita duplicados ante reenvíos tras confirmaciones perdidas.
        MEJORA FUTURA:
            Ninguna acción adicional requerida en el cliente cuando el
            backend lo adopte: el campo ya viaja desde esta fase. Solo
            requiere coordinación del lado del backend.
    """
    return {
        "dispositivo_id": config.dispositivo_id,
        "version_firmware": config.version_firmware,
        "colegio_nombre": t.colegio_nombre,
        "colegio_distrito": t.colegio_distrito,
        "tecnólogo_responsable": t.tecnologo,
        "fecha_sesion": t.fecha_sesion,
        "dni_hash": _hash_dni(t.dni),
        "nombre_paciente": t.nombre_paciente,
        "fecha_nacimiento": t.fecha_nacimiento,
        "grado_seccion": _grado_seccion_para_payload(t.grado_seccion),
        "email_padre": t.email_padre,
        "telefono_padre": t.telefono_padre,
        "ojo_derecho": _resultado_ojo_a_dict(t.od),
        "ojo_izquierdo": _resultado_ojo_a_dict(t.oi),
        "riesgo_ambliopía": _riesgo_para_payload(t.riesgo),
        "requiere_derivacion": t.requiere_derivacion,
        "observaciones": _observaciones_para_payload(t),
        # [CORRECCIÓN] Igual que "eje": el backend exige entero estricto
        # (confirmado por 422 real). Además, TOPADO a 179s de forma
        # PROVISIONAL — ver _duracion_captura_segundos_para_payload().
        # t.duracion_segundos (real, completo, sin recortar) sigue
        # intacto en storage/ local.
        "duracion_captura_segundos": _duracion_captura_segundos_para_payload(
            t.duracion_segundos
        ),
        "timestamp_captura": t.timestamp_captura,
        # Campo adicional, ver docstring de esta función.
        "uuid_local": t.uuid_local,
    }
