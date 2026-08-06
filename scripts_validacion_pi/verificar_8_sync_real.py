"""
scripts_validacion_pi/verificar_8_sync_real.py — Primera conexión REAL de
sync/ contra la API externa (ambliodetect-api.onrender.com), usando un
tamizaje de PRUEBA explícito (no un paciente real) para no ensuciar la
base de datos del backend con datos falsos marcados como reales.

Ejecutar: python -m scripts_validacion_pi.verificar_8_sync_real
"""

import tempfile
from pathlib import Path

from lux_eyes.common.tipos import ResultadoOjo, Tamizaje
from lux_eyes.storage import RepositorioTamizajes
from lux_eyes.sync import ClienteAPI, ConfiguracionSync, SincronizadorWeb

# AJUSTA esto: el token real, si tu compañero ya definió uno (deuda D9).
# Si el backend todavía no valida tokens, cualquier cadena debería
# funcionar sin error — pero avísame si ves un 401/403 inesperado.
TOKEN = "token-de-prueba"

# Correo real donde SÍ quieres recibir el PDF de prueba.
CORREO_PRUEBA = "luxeyes9@gmail.com"


def main():
    config = ConfiguracionSync(
        dispositivo_id="RPi-VALIDACION-01",
        version_firmware="0.1.0",
        url_base="https://ambliodetect-api.onrender.com",
        token=TOKEN,
    )

    tmp = Path(tempfile.mkdtemp(prefix="luxeyes_sync_real_"))
    repo = RepositorioTamizajes(tmp / "sync_prueba.db", tmp / "capturas_prueba")

    tamizaje_prueba = Tamizaje(
        colegio_nombre="IE San Miguel - Prueba de conexión",
        colegio_distrito="San Miguel",
        tecnologo="Prueba de validación",
        fecha_sesion="2026-07-12",
        dni="00000000",
        nombre_paciente="Prueba Conexion Sync",
        fecha_nacimiento="2020-01-01",
        grado_seccion="Prueba",
        email_padre=CORREO_PRUEBA,
        # reflejo_rojo no se especifica (queda en None) — igual que en
        # una captura real del dispositivo (deuda D5). sync/serializacion.py
        # lo convierte automáticamente a True al construir el payload,
        # con una nota de advertencia agregada a observaciones.
        od=ResultadoOjo(esfera=-1.25, cilindro=-0.50, eje=90.0),
        oi=ResultadoOjo(esfera=-1.50, cilindro=-0.75, eje=85.0),
        riesgo="BAJO", requiere_derivacion=False,
        observaciones="Prueba de integración real desde la Raspberry Pi.",
        duracion_segundos=10.0, timestamp_captura="2026-07-12T00:00:00+00:00",
    )
    uuid_local = repo.crear_tamizaje(tamizaje_prueba)
    print(f"Tamizaje de prueba creado localmente: {uuid_local}")

    cliente = ClienteAPI(config)
    sincronizador = SincronizadorWeb(repo, cliente, config)

    print("\nEjecutando ciclo de sincronización real...")
    resumen = sincronizador.ejecutar_ciclo()
    print(f"Resumen: {resumen}")

    rec = repo.obtener(uuid_local)
    print(f"\nEstado final: {rec.estado_sync}")
    print(f"registro_id_servidor: {rec.registro_id_servidor}")

    if rec.estado_sync.value == "SINCRONIZADO":
        print(f"\n✅ Éxito. Revisa la bandeja de {CORREO_PRUEBA} en unos minutos "
              f"(el servidor puede tardar en generar y enviar el PDF).")
    else:
        print(f"\n❌ No se sincronizó. Mensaje de error real del servidor "
              f"(guardado en storage/, campo ultimo_error):\n")
        print(f"    {rec.ultimo_error}")

    repo.cerrar()


if __name__ == "__main__":
    main()
