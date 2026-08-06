"""
test_storage.py — Pruebas de aceptación de la Fase 1 (almacenamiento local).

Valida los criterios de aceptación del módulo storage:
  1. Autonomía: cada tamizaje nace con uuid_local propio, sin servidor.
  2. Local-first: el dato persiste y se recupera intacto.
  3. Ciclo de vida de sincronización: transiciones de estado correctas.
  4. Cola de pendientes: listar correctamente lo que falta enviar.
  5. Idempotencia local del vínculo imagen-registro (por uuid_local).
  6. Integridad de imágenes por hash.
  7. Recuperación tras reinicio: ENVIANDO -> PENDIENTE.
  8. Persistencia real en disco (reabrir la base y encontrar el dato).
  9. Auditoría: las transiciones quedan trazadas.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lux_eyes.common import Tamizaje, ResultadoOjo, EstadoSync, EstadoImagenes
from lux_eyes.storage import RepositorioTamizajes

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
        od=ResultadoOjo(esfera=1.09, cilindro=-1.03, eje=157.0,
                        esfera_sd=0.12, cilindro_sd=0.09, eje_sd=4.1),
        oi=ResultadoOjo(esfera=0.75, cilindro=-0.50, eje=88.0),
        riesgo="MODERADO", requiere_derivacion=True,
        duracion_segundos=42.5, timestamp_captura="2026-07-01T10:15:00+00:00",
    )


def main():
    tmp = Path(tempfile.mkdtemp(prefix="luxeyes_"))
    ruta_db = tmp / "tamizaje_local.db"
    carpeta_img = tmp / "capturas"
    print(f"\nEntorno de prueba: {tmp}\n")

    repo = RepositorioTamizajes(ruta_db, carpeta_img)

    # ── 1. Autonomía: uuid_local sin servidor ──
    print("1) Autonomía del dispositivo (uuid_local propio)")
    t = tamizaje_ejemplo()
    uuid1 = repo.crear_tamizaje(t)
    check("crear_tamizaje devuelve un uuid_local no vacío", bool(uuid1))
    check("el tamizaje nace sin registro_id_servidor (offline)",
          repo.obtener(uuid1).registro_id_servidor is None)
    check("el estado inicial es PENDIENTE",
          repo.obtener(uuid1).estado_sync == EstadoSync.PENDIENTE)

    # ── 2. Local-first: dato íntegro ──
    print("\n2) Persistencia íntegra del dato")
    rec = repo.obtener(uuid1)
    check("nombre del paciente correcto", rec.nombre_paciente == "Ana Pérez")
    check("esfera OD correcta", rec.od.esfera == 1.09)
    check("incertidumbre OD correcta", rec.od.eje_sd == 4.1)
    check("reflejo_rojo es None (no evaluado, no inventado)",
          rec.od.reflejo_rojo is None)
    check("riesgo clínico correcto", rec.riesgo == "MODERADO")
    check("requiere_derivacion es True", rec.requiere_derivacion is True)

    # ── 3. Ciclo de vida de sincronización ──
    print("\n3) Ciclo de vida de sincronización")
    repo.marcar_estado_sync(uuid1, EstadoSync.ENVIANDO)
    check("transición a ENVIANDO", repo.obtener(uuid1).estado_sync == EstadoSync.ENVIANDO)
    repo.marcar_estado_sync(uuid1, EstadoSync.SINCRONIZADO,
                            registro_id_servidor="SRV-0001")
    rec = repo.obtener(uuid1)
    check("transición a SINCRONIZADO", rec.estado_sync == EstadoSync.SINCRONIZADO)
    check("registro_id_servidor asociado tras sync", rec.registro_id_servidor == "SRV-0001")
    check("uuid_local NO cambió al sincronizar", rec.uuid_local == uuid1)

    # ── 4. Cola de pendientes ──
    print("\n4) Cola de pendientes")
    t2 = tamizaje_ejemplo("Beto Quispe", "87654321")
    t3 = tamizaje_ejemplo("Carla Ruiz", "11223344")
    uuid2 = repo.crear_tamizaje(t2)
    uuid3 = repo.crear_tamizaje(t3)
    repo.marcar_estado_sync(uuid3, EstadoSync.ERROR_REINTENTABLE,
                            error="timeout", incrementar_intentos=True)
    pendientes = repo.listar_pendientes()
    uuids_pend = {p.uuid_local for p in pendientes}
    check("el SINCRONIZADO no aparece en pendientes", uuid1 not in uuids_pend)
    check("el PENDIENTE aparece", uuid2 in uuids_pend)
    check("el ERROR_REINTENTABLE aparece", uuid3 in uuids_pend)
    check("orden por antigüedad (uuid2 antes que uuid3)",
          [p.uuid_local for p in pendientes] == sorted(
              [uuid2, uuid3], key=lambda u: repo.obtener(u).creado_en))

    # ── 5 y 6. Imágenes: vínculo estable e integridad ──
    print("\n5-6) Imágenes: vínculo por uuid_local e integridad por hash")
    foto_od = tmp / "captura_od_raw.jpg"
    foto_od.write_bytes(b"IMAGEN_IR_OJO_DERECHO_datos_binarios")
    repo.adjuntar_imagen(uuid2, "od", str(foto_od))
    rec2 = repo.obtener(uuid2)
    check("ruta de imagen OD guardada", rec2.ruta_imagen_od is not None)
    check("nombre de archivo deriva del uuid_local (vínculo estable)",
          uuid2 in Path(rec2.ruta_imagen_od).name)
    check("hash de imagen OD calculado", bool(rec2.hash_imagen_od))
    check("integridad verificable (hash coincide)",
          repo.imagenes.verificar_integridad(rec2.ruta_imagen_od, rec2.hash_imagen_od))
    # Corromper el archivo y verificar que la integridad falla
    Path(rec2.ruta_imagen_od).write_bytes(b"CORRUPTO")
    check("integridad detecta corrupción",
          not repo.imagenes.verificar_integridad(rec2.ruta_imagen_od, rec2.hash_imagen_od))
    check("estado de imágenes es PENDIENTE tras adjuntar",
          rec2.estado_imagenes == EstadoImagenes.PENDIENTE)

    # ── 9. Auditoría ──
    print("\n9) Auditoría de transiciones")
    hist = repo.historial_auditoria(uuid1)
    eventos = [h["evento"] for h in hist]
    check("existe evento CREADO", "CREADO" in eventos)
    check("existen transiciones ESTADO_SYNC", "ESTADO_SYNC" in eventos)
    check("la auditoría preserva el orden", hist == sorted(hist, key=lambda h: h["creado_en"]))

    # ── 7 y 8. Reinicio: recuperación y persistencia en disco ──
    print("\n7-8) Recuperación tras reinicio y persistencia en disco")
    # Simular un envío interrumpido: uuid2 queda en ENVIANDO
    repo.marcar_estado_sync(uuid2, EstadoSync.ENVIANDO)
    repo.cerrar()  # simular apagado del dispositivo

    # Reabrir la base como si el dispositivo reiniciara
    repo2 = RepositorioTamizajes(ruta_db, carpeta_img)
    check("el dato persiste tras reabrir la base",
          repo2.obtener(uuid1) is not None and
          repo2.obtener(uuid1).nombre_paciente == "Ana Pérez")
    n_recuperados = repo2.recuperar_envios_interrumpidos()
    check("se recupera al menos 1 envío interrumpido", n_recuperados >= 1)
    check("el envío interrumpido (uuid2) vuelve a PENDIENTE",
          repo2.obtener(uuid2).estado_sync == EstadoSync.PENDIENTE)
    check("el SINCRONIZADO no se ve afectado por la recuperación",
          repo2.obtener(uuid1).estado_sync == EstadoSync.SINCRONIZADO)

    # ── Resumen de estados ──
    print("\nResumen de estados en la base:")
    for estado, n in sorted(repo2.contar_por_estado().items()):
        print(f"    {estado}: {n}")

    repo2.cerrar()

    print(f"\n{'='*52}")
    total = _ok + _fail
    color = VERDE if _fail == 0 else ROJO
    print(f"{color}Resultado: {_ok}/{total} pruebas pasadas, {_fail} fallidas{RESET}")
    print(f"{'='*52}\n")
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
