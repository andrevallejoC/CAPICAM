"""
test_sync.py — Pruebas de aceptación de la Fase 2 (sincronización web).

Sigue la misma disciplina que test_storage.py: un backend simulado en
proceso (ClienteFalso), inyectado en SincronizadorWeb en lugar del cliente
HTTP real, permite probar cada rama de la clasificación de errores de
forma determinista, sin red real.

Cubre los criterios de aceptación acordados en el diseño de la Fase 2:
  1. La cola se respeta en orden (antigüedad) y solo toca lo que storage/
     ya considera pendiente.
  2. Un envío exitoso pasa a SINCRONIZADO con registro_id_servidor.
  3. El DNI nunca aparece en claro en el payload enviado; uuid_local sí
     viaja en el payload (decisión aprobada de la Fase 2).
  4. Un error de conectividad (ambiental) NO incrementa intentos_sync.
  5. Un error de servidor (5xx) SÍ incrementa intentos_sync y programa
     backoff; el registro no vuelve a intentarse antes de tiempo.
  6. Un error 400/422 pasa directo a ERROR_PERMANENTE sin agotar intentos.
  7. Un 401/403 aborta el ciclo completo sin penalizar registros
     individuales ya procesados en ciclos anteriores ni los restantes del
     ciclo actual.
  8. Superar max_intentos tras ERROR_REINTENTABLE deja el registro fuera
     de listar_pendientes() (ya resuelto por storage/, se confirma aquí
     de extremo a extremo).
  9. Un fallo en imágenes/PDF (best-effort) no revierte SINCRONIZADO.
 10. Reutilizar la misma instancia de SincronizadorWeb entre ciclos
     conserva el backoff en memoria (principio de uso documentado).
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lux_eyes.common import EstadoImagenes, EstadoSync, ResultadoOjo, Tamizaje
from lux_eyes.storage import RepositorioTamizajes
from lux_eyes.sync import ConfiguracionSync, SincronizadorWeb
from lux_eyes.sync.excepciones import (
    ErrorAutenticacion, ErrorConectividad, ErrorPermanente, ErrorServidor,
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


def tamizaje_ejemplo(nombre="Ana Pérez", dni="12345678") -> Tamizaje:
    return Tamizaje(
        colegio_nombre="I.E. San Miguel", colegio_distrito="San Miguel",
        tecnologo="TM. Rodríguez", fecha_sesion="2026-07-01",
        dni=dni, nombre_paciente=nombre, fecha_nacimiento="2015-03-10",
        grado_seccion="5B", email_padre="tutor@ejemplo.com",
        od=ResultadoOjo(esfera=1.09, cilindro=-1.03, eje=157.0),
        oi=ResultadoOjo(esfera=0.75, cilindro=-0.50, eje=88.0),
        riesgo="MODERADO", requiere_derivacion=True,
        duracion_segundos=42.5, timestamp_captura="2026-07-01T10:15:00+00:00",
    )


class ClienteFalso:
    """
    Doble de prueba de ClienteAPI. Implementa la misma interfaz pública
    (enviar_datos, subir_imagenes, generar_pdf) pero sin red real: el
    comportamiento se programa desde la prueba mediante `guiones`, un
    diccionario {uuid_local: [excepcion_o_None, excepcion_o_None, ...]}
    que se consume en orden en cada llamada a enviar_datos.

    Guarda además cada payload recibido, para poder inspeccionarlo (p. ej.
    verificar que el DNI nunca viaja en claro).
    """

    def __init__(self):
        self.guiones: dict[str, list] = {}
        self.payloads_recibidos: list[dict] = []
        self.imagenes_deben_fallar = False
        self.pdf_debe_fallar = False
        self.ultima_llamada_pdf = None
        self._contador_registro_id = 0

    def programar(self, uuid_local: str, *resultados):
        """resultados: cada uno es None (éxito) o una excepción a lanzar."""
        self.guiones[uuid_local] = list(resultados)

    def enviar_datos(self, payload: dict) -> str:
        self.payloads_recibidos.append(payload)
        uuid_local = payload["uuid_local"]
        guion = self.guiones.get(uuid_local, [None])
        resultado = guion.pop(0) if guion else None
        if isinstance(resultado, Exception):
            raise resultado
        self._contador_registro_id += 1
        return f"SRV-{self._contador_registro_id:04d}"

    def subir_imagenes(self, registro_id, ruta_od, ruta_oi):
        if self.imagenes_deben_fallar:
            raise ErrorServidor("fallo simulado al subir imágenes")

    def generar_pdf(self, registro_id, colegio_nombre, dispositivo_id, correo_padre):
        self.ultima_llamada_pdf = {
            "registro_id": registro_id, "colegio_nombre": colegio_nombre,
            "dispositivo_id": dispositivo_id, "correo_padre": correo_padre,
        }
        if self.pdf_debe_fallar:
            raise ErrorServidor("fallo simulado al generar PDF")


def nueva_config(**overrides) -> ConfiguracionSync:
    base = dict(
        dispositivo_id="RPi-AMBLIO-001", version_firmware="1.0.0",
        url_base="https://ambliodetect-api.onrender.com", token="token-de-prueba",
        max_intentos=3,
        backoff_base_segundos=1000.0,  # alto a propósito: ver prueba 5
        backoff_factor=2.0, backoff_max_segundos=5000.0, backoff_jitter_segundos=0.0,
    )
    base.update(overrides)
    return ConfiguracionSync(**base)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="luxeyes_sync_"))
    ruta_db = tmp / "tamizaje_local.db"
    carpeta_img = tmp / "capturas"
    print(f"\nEntorno de prueba: {tmp}\n")

    repo = RepositorioTamizajes(ruta_db, carpeta_img)
    config = nueva_config()

    # ── 1-3. Cola, éxito, payload sin DNI en claro, uuid_local presente ──
    print("1-3) Cola de pendientes, sincronización exitosa y payload")
    t1 = tamizaje_ejemplo("Ana Pérez", dni="12345678")
    t2 = tamizaje_ejemplo("Beto Quispe", dni="87654321")
    uuid1 = repo.crear_tamizaje(t1)
    uuid2 = repo.crear_tamizaje(t2)

    cliente = ClienteFalso()
    sync = SincronizadorWeb(repo, cliente, config)
    resumen = sync.ejecutar_ciclo()

    check("ambos tamizajes se sincronizaron", resumen.sincronizados == 2)
    check("ninguno quedó reintentable ni permanente",
          resumen.reintentables == 0 and resumen.permanentes == 0)
    check("estado final es SINCRONIZADO",
          repo.obtener(uuid1).estado_sync == EstadoSync.SINCRONIZADO)
    check("registro_id_servidor fue asignado",
          repo.obtener(uuid1).registro_id_servidor is not None)

    payload1 = next(p for p in cliente.payloads_recibidos if p["uuid_local"] == uuid1)
    check("el DNI en claro NUNCA aparece en el payload",
          "12345678" not in str(payload1))
    check("el payload trae dni_hash en su lugar", bool(payload1.get("dni_hash")))
    check("uuid_local viaja en el payload (decisión Fase 2)",
          payload1["uuid_local"] == uuid1)
    check("el payload trae dispositivo_id y version_firmware de la config",
          payload1["dispositivo_id"] == "RPi-AMBLIO-001"
          and payload1["version_firmware"] == "1.0.0")

    # ── CORRECCIÓN: reflejo_rojo=None se envía como True (decisión de Luxeyes) ──
    print("\n(payload) reflejo_rojo_presente: None se coerciona a True (backend exige bool)")
    check("reflejo_rojo=None en ambos ojos (comportamiento real de D5, sin "
          "detección implementada) se envía como True, no None ni False",
          payload1["ojo_derecho"]["reflejo_rojo_presente"] is True
          and payload1["ojo_izquierdo"]["reflejo_rojo_presente"] is True)
    check("se agregó la nota de advertencia a observaciones DEL PAYLOAD",
          "AVISO" in payload1["observaciones"])
    check("t1.observaciones (el objeto original, storage/ local) NO fue modificado",
          "AVISO" not in t1.observaciones)

    # Caso con reflejo_rojo ya evaluado de verdad (el día que D5 exista):
    # no debe coercionarse ni agregar la nota.
    t1b = tamizaje_ejemplo("Con Reflejo Evaluado", dni="11223344")
    t1b.od.reflejo_rojo = True
    t1b.oi.reflejo_rojo = False
    uuid1b = repo.crear_tamizaje(t1b)
    sync1b = SincronizadorWeb(repo, cliente, config)
    sync1b.ejecutar_ciclo()
    payload1b = next(p for p in cliente.payloads_recibidos if p["uuid_local"] == uuid1b)
    check("con reflejo_rojo YA evaluado (no None), se envía tal cual, sin coercionar",
          payload1b["ojo_derecho"]["reflejo_rojo_presente"] is True
          and payload1b["ojo_izquierdo"]["reflejo_rojo_presente"] is False)
    check("sin coerción, NO se agrega la nota de advertencia",
          "AVISO" not in payload1b["observaciones"])

    # ── CORRECCIÓN: eje se redondea a entero (backend exige int estricto) ──
    print("\n(payload) eje: se redondea a entero, el backend rechaza float (422 real)")
    t1c = tamizaje_ejemplo("Con Eje Fraccional", dni="22334455")
    t1c.od.eje = 89.6   # debe redondear a 90, no truncar a 89
    t1c.oi.eje = 45.2   # debe redondear a 45
    uuid1c = repo.crear_tamizaje(t1c)
    sync1c = SincronizadorWeb(repo, cliente, config)
    sync1c.ejecutar_ciclo()
    payload1c = next(p for p in cliente.payloads_recibidos if p["uuid_local"] == uuid1c)
    check("89.6° se redondea a 90 (no trunca a 89)",
          payload1c["ojo_derecho"]["eje"] == 90)
    check("45.2° se redondea a 45",
          payload1c["ojo_izquierdo"]["eje"] == 45)
    check("el tipo enviado es int de verdad, no float (90.0 sigue siendo "
          "rechazado por el backend aunque el VALOR sea correcto)",
          isinstance(payload1c["ojo_derecho"]["eje"], int)
          and not isinstance(payload1c["ojo_derecho"]["eje"], bool))
    check("el objeto original en memoria/storage NO se modificó (89.6 intacto, "
          "el redondeo es SOLO para el payload de salida)",
          t1c.od.eje == 89.6)

    # ── CORRECCIÓN: duracion_captura_segundos también se redondea a entero ──
    print("\n(payload) duracion_captura_segundos: se redondea a entero "
          "(mismo criterio que eje, backend exige int estricto)")
    t1d = tamizaje_ejemplo("Con Duracion Fraccional", dni="55667788")
    t1d.duracion_segundos = 47.8
    uuid1d = repo.crear_tamizaje(t1d)
    sync1d = SincronizadorWeb(repo, cliente, config)
    sync1d.ejecutar_ciclo()
    payload1d = next(p for p in cliente.payloads_recibidos if p["uuid_local"] == uuid1d)
    check("47.8 segundos se redondea a 48",
          payload1d["duracion_captura_segundos"] == 48)
    check("el tipo enviado es int, no float",
          isinstance(payload1d["duracion_captura_segundos"], int))

    # ── CORRECCIÓN: duración real >180s se topa PROVISIONALMENTE ────────
    print("\n(payload) duracion_captura_segundos >180s se topa (backend rechaza >180)")
    t1e = tamizaje_ejemplo("Con Duracion Larga", dni="66778899")
    t1e.duracion_segundos = 254.0  # el caso real reportado
    uuid1e = repo.crear_tamizaje(t1e)
    sync1e = SincronizadorWeb(repo, cliente, config)
    sync1e.ejecutar_ciclo()
    payload1e = next(p for p in cliente.payloads_recibidos if p["uuid_local"] == uuid1e)
    check("254s se topa a 179 (por debajo del límite de 180 del servidor)",
          payload1e["duracion_captura_segundos"] == 179)
    check("se agrega la nota de advertencia PROVISIONAL a observaciones "
          "DEL PAYLOAD (para que quede rastro de que no es el valor real)",
          "AVISO" in payload1e["observaciones"]
          and "180" in payload1e["observaciones"])
    check("t1e.observaciones (el objeto original, storage/ local) NO fue modificado",
          "AVISO" not in t1e.observaciones)
    check("el valor REAL (254.0) sigue intacto en el objeto/storage local, "
          "solo el payload de salida está topado",
          t1e.duracion_segundos == 254.0)

    t1f = tamizaje_ejemplo("Con Duracion Normal", dni="77889900")
    t1f.duracion_segundos = 45.0  # bajo el límite: no debe topar ni agregar nota
    uuid1f = repo.crear_tamizaje(t1f)
    sync1f = SincronizadorWeb(repo, cliente, config)
    sync1f.ejecutar_ciclo()
    payload1f = next(p for p in cliente.payloads_recibidos if p["uuid_local"] == uuid1f)
    check("con duración normal (45s, bajo el límite), NO se topa y NO se "
          "agrega la nota de duración (aunque SÍ puede llevar la nota de "
          "reflejo_rojo, que es independiente — tamizaje_ejemplo() no fija "
          "reflejo_rojo, así que esa sí aplica siempre en estas pruebas)",
          payload1f["duracion_captura_segundos"] == 45
          and "duración recortada" not in payload1f["observaciones"])

    # ── CORRECCIÓN: riesgo_ambliopía — el backend no acepta SIN_RIESGO ──
    print("\n(payload) riesgo_ambliopía: SIN_RIESGO se mapea a BAJO "
          "(confirmado contra el modelo Pydantic real del backend)")
    t1g = tamizaje_ejemplo("Sin Ningun Riesgo", dni="11112222")
    t1g.riesgo = "SIN_RIESGO"
    uuid1g = repo.crear_tamizaje(t1g)
    sync1g = SincronizadorWeb(repo, cliente, config)
    sync1g.ejecutar_ciclo()
    payload1g = next(p for p in cliente.payloads_recibidos if p["uuid_local"] == uuid1g)
    check("SIN_RIESGO se envía como BAJO (el backend solo acepta BAJO/"
          "MODERADO/ALTO, no tiene noción de 'sin riesgo')",
          payload1g["riesgo_ambliopía"] == "BAJO")
    check("t1g.riesgo (el objeto original, storage/ local) sigue siendo "
          "SIN_RIESGO — la distinción clínica real no se pierde localmente, "
          "solo el backend no puede representarla",
          t1g.riesgo == "SIN_RIESGO")

    for nivel_real in ("BAJO", "MODERADO", "ALTO"):
        t_nivel = tamizaje_ejemplo(f"Riesgo {nivel_real}", dni=f"3{nivel_real[:3]}0000")
        t_nivel.riesgo = nivel_real
        uuid_nivel = repo.crear_tamizaje(t_nivel)
        SincronizadorWeb(repo, cliente, config).ejecutar_ciclo()
        payload_nivel = next(
            p for p in cliente.payloads_recibidos if p["uuid_local"] == uuid_nivel
        )
        check(f"{nivel_real} (ya válido para el backend) viaja SIN cambios",
              payload_nivel["riesgo_ambliopía"] == nivel_real)

    # ── CORRECCIÓN: observaciones nunca supera 500 caracteres ───────────
    print("\n(payload) observaciones: nunca supera 500 caracteres "
          "(confirmado por 422 real: 'string_too_long')")
    t1h = tamizaje_ejemplo("Observaciones Muy Largas", dni="99990000")
    t1h.observaciones = "X" * 480  # ya cerca del límite por sí sola
    t1h.od.reflejo_rojo = None  # fuerza la nota de reflejo_rojo también
    t1h.duracion_segundos = 300.0  # fuerza la nota de duración también
    uuid1h = repo.crear_tamizaje(t1h)
    SincronizadorWeb(repo, cliente, config).ejecutar_ciclo()
    payload1h = next(p for p in cliente.payloads_recibidos if p["uuid_local"] == uuid1h)
    check("con observaciones ya casi al límite MÁS dos notas de advertencia, "
          f"el payload final NUNCA supera 500 caracteres (real: "
          f"{len(payload1h['observaciones'])})",
          len(payload1h["observaciones"]) <= 500)
    check("la nota clínica real (t.observaciones) se prioriza — el inicio "
          "del texto original SIGUE presente, no se descartó por completo",
          payload1h["observaciones"].startswith("X" * 50))
    check("t1h.observaciones (el objeto original, storage/ local) sigue "
          "teniendo sus 480 caracteres originales, sin truncar",
          len(t1h.observaciones) == 480)

    # ── PREVENTIVO: grado_seccion (max_length=10 en el modelo real) ─────
    print("\n(payload) grado_seccion: truncado preventivo a 10 caracteres "
          "(confirmado por el esquema real, aún no por un 422 en producción)")
    t1i = tamizaje_ejemplo("Grado Largo", dni="44445555")
    t1i.grado_seccion = "Quinto Grado B"  # 14 caracteres, más de 10
    uuid1i = repo.crear_tamizaje(t1i)
    SincronizadorWeb(repo, cliente, config).ejecutar_ciclo()
    payload1i = next(p for p in cliente.payloads_recibidos if p["uuid_local"] == uuid1i)
    check("grado_seccion se trunca a 10 caracteres exactos",
          payload1i["grado_seccion"] == "Quinto Gra"
          and len(payload1i["grado_seccion"]) == 10)
    check("t1i.grado_seccion (storage/ local) sigue completo, sin truncar",
          t1i.grado_seccion == "Quinto Grado B")

    # ── 4. Error de conectividad no incrementa intentos_sync ──
    print("\n4) Error de conectividad (ambiental)")
    t3 = tamizaje_ejemplo("Carla Ruiz", dni="11223344")
    uuid3 = repo.crear_tamizaje(t3)
    cliente.programar(uuid3, ErrorConectividad("timeout simulado"))
    resumen = sync.ejecutar_ciclo()

    rec3 = repo.obtener(uuid3)
    check("el ciclo reporta 1 fallo ambiental", resumen.ambientales == 1)
    check("vuelve a PENDIENTE (no ERROR_REINTENTABLE)",
          rec3.estado_sync == EstadoSync.PENDIENTE)
    check("intentos_sync NO se incrementó por un fallo de conectividad",
          rec3.intentos_sync == 0)

    # ── 5. Error de servidor: incrementa intentos y programa backoff ──
    print("\n5) Error de servidor (5xx) y backoff")
    t4 = tamizaje_ejemplo("Diego Torres", dni="55667788")
    uuid4 = repo.crear_tamizaje(t4)
    cliente.programar(uuid4, ErrorServidor("500 simulado"))
    resumen = sync.ejecutar_ciclo()

    rec4 = repo.obtener(uuid4)
    check("el ciclo reporta 1 reintentable", resumen.reintentables == 1)
    check("pasa a ERROR_REINTENTABLE", rec4.estado_sync == EstadoSync.ERROR_REINTENTABLE)
    check("intentos_sync SÍ se incrementó", rec4.intentos_sync == 1)

    # backoff_base=1000s garantiza que el siguiente ciclo, inmediato, lo salte
    resumen_inmediato = sync.ejecutar_ciclo()
    check("con backoff activo, el siguiente ciclo lo salta (no lo reintenta ya)",
          uuid4 not in [p["uuid_local"] for p in cliente.payloads_recibidos[-1:]]
          or resumen_inmediato.saltados_por_backoff >= 1)

    # ── 6. Error permanente (400/422) ──
    print("\n6) Error permanente (payload rechazado)")
    t5 = tamizaje_ejemplo("Elena Vidal", dni="99887766")
    uuid5 = repo.crear_tamizaje(t5)
    cliente.programar(uuid5, ErrorPermanente("422 simulado"))
    resumen = sync.ejecutar_ciclo()

    rec5 = repo.obtener(uuid5)
    check("el ciclo reporta 1 permanente", resumen.permanentes == 1)
    check("pasa directo a ERROR_PERMANENTE", rec5.estado_sync == EstadoSync.ERROR_PERMANENTE)
    check("no se le siguen agotando intentos innecesariamente",
          rec5.intentos_sync == 0)
    pendientes_tras_permanente = repo.listar_pendientes(max_intentos=config.max_intentos)
    check("ya no aparece en listar_pendientes()",
          uuid5 not in [p.uuid_local for p in pendientes_tras_permanente])

    # ── 7. Error de autenticación aborta el ciclo completo ──
    print("\n7) Error de autenticación (401/403) aborta el ciclo")
    t6 = tamizaje_ejemplo("Fabio Leon", dni="10293847")
    t7 = tamizaje_ejemplo("Gina Paredes", dni="19283746")
    uuid6 = repo.crear_tamizaje(t6)
    uuid7 = repo.crear_tamizaje(t7)
    cliente2 = ClienteFalso()
    cliente2.programar(uuid6, ErrorAutenticacion("401 simulado"))
    sync2 = SincronizadorWeb(repo, cliente2, config)
    resumen = sync2.ejecutar_ciclo()

    check("el resumen marca el ciclo como abortado por autenticación",
          resumen.ciclo_abortado_por_autenticacion is True)
    check("el tamizaje que disparó el 401 vuelve a PENDIENTE (no colgado en ENVIANDO)",
          repo.obtener(uuid6).estado_sync == EstadoSync.PENDIENTE)
    check("su intentos_sync NO se penalizó por el fallo de autenticación",
          repo.obtener(uuid6).intentos_sync == 0)
    check("el siguiente tamizaje del ciclo (uuid7) NUNCA se llegó a intentar",
          uuid7 not in [p["uuid_local"] for p in cliente2.payloads_recibidos])
    check("uuid7 sigue en PENDIENTE, intacto",
          repo.obtener(uuid7).estado_sync == EstadoSync.PENDIENTE)

    # ── 8. Agotar max_intentos deja el registro fuera de la cola ──
    print("\n8) Agotar max_intentos (ERROR_PERMANENTE por límite)")
    t8 = tamizaje_ejemplo("Hugo Vera", dni="30201020")
    uuid8 = repo.crear_tamizaje(t8)
    cliente3 = ClienteFalso()
    config_sin_backoff = nueva_config(
        max_intentos=3, backoff_base_segundos=0.0, backoff_jitter_segundos=0.0,
    )
    sync3 = SincronizadorWeb(repo, cliente3, config_sin_backoff)
    for _ in range(3):
        cliente3.programar(uuid8, ErrorServidor("500 simulado"))
        sync3.ejecutar_ciclo()

    rec8 = repo.obtener(uuid8)
    pendientes_final = repo.listar_pendientes(max_intentos=config_sin_backoff.max_intentos)
    check("tras 3 fallos de servidor con max_intentos=3, ya no está pendiente",
          uuid8 not in [p.uuid_local for p in pendientes_final])
    check("intentos_sync alcanzó el límite", rec8.intentos_sync == 3)

    # ── 9. Fallo en imágenes/PDF no revierte SINCRONIZADO ──
    print("\n9) Fallo best-effort en imágenes/PDF no revierte SINCRONIZADO")
    t9 = tamizaje_ejemplo("Ines Salas", dni="40506070")
    uuid9 = repo.crear_tamizaje(t9)
    foto = tmp / "captura_od.jpg"
    foto.write_bytes(b"IMAGEN_IR_DATOS")
    repo.adjuntar_imagen(uuid9, "od", str(foto))

    cliente4 = ClienteFalso()
    cliente4.imagenes_deben_fallar = True
    cliente4.pdf_debe_fallar = True
    sync4 = SincronizadorWeb(repo, cliente4, config)
    sync4.ejecutar_ciclo()

    rec9 = repo.obtener(uuid9)
    check("el tamizaje queda SINCRONIZADO pese al fallo de imágenes/PDF",
          rec9.estado_sync == EstadoSync.SINCRONIZADO)
    check("el estado de imágenes refleja el fallo (ERROR), sin afectar estado_sync",
          rec9.estado_imagenes == EstadoImagenes.ERROR)

    # ── 9b. CORRECCIÓN: generar_pdf recibe colegio/dispositivo/correo reales ──
    print("\n9b) generar_pdf recibe colegio_nombre, dispositivo_id y correo_padre reales")
    print("    (bug real: la versión anterior no enviaba ningún parámetro al Paso 3,")
    print("    confirmado al comparar contra el script de referencia del backend)")
    t9b = tamizaje_ejemplo("Rosa Chuquimia", dni="70809010")
    repo.crear_tamizaje(t9b)
    cliente6 = ClienteFalso()
    sync6 = SincronizadorWeb(repo, cliente6, config)
    sync6.ejecutar_ciclo()

    check("generar_pdf() SÍ fue llamado", cliente6.ultima_llamada_pdf is not None)
    check("colegio_nombre llega correcto (no vacío/None)",
          cliente6.ultima_llamada_pdf["colegio_nombre"] == "I.E. San Miguel")
    check("dispositivo_id llega desde ConfiguracionSync, no del Tamizaje",
          cliente6.ultima_llamada_pdf["dispositivo_id"] == config.dispositivo_id)
    check("correo_padre llega correcto",
          cliente6.ultima_llamada_pdf["correo_padre"] == "tutor@ejemplo.com")

    # ── 10. Reutilizar la instancia conserva el backoff en memoria ──
    print("\n10) Backoff se conserva al reutilizar la misma instancia")
    t10 = tamizaje_ejemplo("Julio Nina", dni="60708090")
    uuid10 = repo.crear_tamizaje(t10)
    cliente5 = ClienteFalso()
    config_backoff_largo = nueva_config(backoff_base_segundos=9999.0)
    sync5 = SincronizadorWeb(repo, cliente5, config_backoff_largo)

    cliente5.programar(uuid10, ErrorServidor("500 simulado"))
    sync5.ejecutar_ciclo()  # primer intento: falla, backoff programado
    intentos_llamada_1 = len(cliente5.payloads_recibidos)

    sync5.ejecutar_ciclo()  # segundo ciclo, misma instancia: debe saltarlo
    intentos_llamada_2 = len(cliente5.payloads_recibidos)
    check("con la misma instancia, el segundo ciclo NO reintenta antes de tiempo",
          intentos_llamada_2 == intentos_llamada_1)

    # Una instancia NUEVA no conoce el backoff anterior (documentado como
    # restricción actual, no un bug): confirma el comportamiento esperado.
    sync5_nueva_instancia = SincronizadorWeb(repo, cliente5, config_backoff_largo)
    sync5_nueva_instancia.ejecutar_ciclo()
    intentos_llamada_3 = len(cliente5.payloads_recibidos)
    check("una instancia NUEVA sí reintenta de inmediato (restricción documentada)",
          intentos_llamada_3 == intentos_llamada_2 + 1)

    repo.cerrar()

    print(f"\n{'='*52}")
    total = _ok + _fail
    color = VERDE if _fail == 0 else ROJO
    print(f"{color}Resultado: {_ok}/{total} pruebas pasadas, {_fail} fallidas{RESET}")
    print(f"{'='*52}\n")
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
