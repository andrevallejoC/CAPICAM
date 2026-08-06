"""
storage/repositorio.py — API pública del subsistema de almacenamiento local.

Es la ÚNICA puerta de entrada al almacenamiento. El orquestador y el sincronizador
hablan con esta clase; ninguno conoce SQLite ni el sistema de archivos. Si mañana
se cambiara SQLite por otra base, solo cambiaría este archivo.

Principios que implementa:
  - Local-first: crear_tamizaje persiste ANTES de cualquier intento de red.
  - Autonomía: cada tamizaje nace con uuid_local propio; registro_id_servidor
    se asocia después.
  - Auditoría: toda transición de estado queda registrada.
  - Fuente de verdad local mientras no haya sincronización.

[CORRECCIÓN — condición de carrera real, detectada al conectar ui/ con
sync/ (Fase 5→2)] Con check_same_thread=False, sqlite3 deja de LANZAR una
excepción cuando la conexión se usa desde varios hilos — pero NO hace que
la conexión sea segura para acceso concurrente real. Mientras solo
HiloOrquestador tocaba storage/, esto nunca se manifestó (un único hilo
además del principal). Al agregar HiloSync (que escribe desde OTRO hilo,
simultáneamente), aparecieron fallos intermitentes y difíciles de
reproducir: estados que quedaban a medio actualizar, lecturas que no
reflejaban escrituras recién hechas por otro hilo. Se agrega un
threading.RLock() que serializa TODO acceso a self._conn — el comentario
original ("cada uno abre su propia conexión") documentaba una intención
de diseño que nunca se implementó; el candado es la solución más simple
y menos invasiva dado que ya existe una única conexión compartida.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from lux_eyes.common.tipos import (
    Tamizaje, ResultadoOjo, EstadoSync, EstadoImagenes, ahora_utc_iso,
)
from .esquema import inicializar_esquema
from .imagenes import GestorImagenes


def _bool_a_int(v: Optional[bool]) -> Optional[int]:
    return None if v is None else (1 if v else 0)


def _int_a_bool(v) -> Optional[bool]:
    return None if v is None else bool(v)


class RepositorioTamizajes:
    """Acceso transaccional a los tamizajes almacenados localmente."""

    def __init__(self, ruta_db: str | Path, carpeta_imagenes: str | Path):
        self.ruta_db = str(ruta_db)
        # check_same_thread=False: HiloOrquestador y HiloSync (ui/) corren
        # en hilos distintos, ambos tocan esta misma conexión. self._lock
        # (RLock, no Lock simple: _auditar() se llama desde DENTRO de
        # métodos que ya sostienen el candado, y RLock permite que el
        # MISMO hilo lo vuelva a tomar sin bloquearse a sí mismo) serializa
        # todo acceso real — ver docstring del módulo.
        self._conn = sqlite3.connect(self.ruta_db, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            inicializar_esquema(self._conn)
        self.imagenes = GestorImagenes(carpeta_imagenes)

    # ── Escritura ────────────────────────────────────────────────────────────
    def crear_tamizaje(self, t: Tamizaje) -> str:
        """
        Persiste un tamizaje nuevo. Devuelve su uuid_local.
        Esta es la operación que materializa el principio local-first: tras
        retornar, el dato está a salvo en disco independientemente de la red.
        """
        t.actualizado_en = ahora_utc_iso()
        with self._lock:
            with self._conn:  # transacción atómica
                self._conn.execute(
                    """
                    INSERT INTO tamizajes (
                        uuid_local, registro_id_servidor,
                        colegio_nombre, colegio_distrito, tecnologo, fecha_sesion,
                        dni, nombre_paciente, fecha_nacimiento, grado_seccion,
                        email_padre, telefono_padre,
                        od_esfera, od_cilindro, od_eje, od_esfera_sd, od_cilindro_sd,
                        od_eje_sd, od_reflejo_rojo,
                        oi_esfera, oi_cilindro, oi_eje, oi_esfera_sd, oi_cilindro_sd,
                        oi_eje_sd, oi_reflejo_rojo,
                        riesgo, requiere_derivacion, observaciones,
                        duracion_segundos, timestamp_captura,
                        ruta_imagen_od, ruta_imagen_oi, hash_imagen_od, hash_imagen_oi,
                        estado_sync, estado_imagenes, intentos_sync, ultimo_error,
                        creado_en, actualizado_en
                    ) VALUES (
                        ?,?, ?,?,?,?, ?,?,?,?, ?,?,
                        ?,?,?,?,?,?,?, ?,?,?,?,?,?,?,
                        ?,?,?, ?,?, ?,?,?,?, ?,?,?,?, ?,?
                    )
                    """,
                    (
                        t.uuid_local, t.registro_id_servidor,
                        t.colegio_nombre, t.colegio_distrito, t.tecnologo, t.fecha_sesion,
                        t.dni, t.nombre_paciente, t.fecha_nacimiento, t.grado_seccion,
                        t.email_padre, t.telefono_padre,
                        t.od.esfera, t.od.cilindro, t.od.eje, t.od.esfera_sd,
                        t.od.cilindro_sd, t.od.eje_sd, _bool_a_int(t.od.reflejo_rojo),
                        t.oi.esfera, t.oi.cilindro, t.oi.eje, t.oi.esfera_sd,
                        t.oi.cilindro_sd, t.oi.eje_sd, _bool_a_int(t.oi.reflejo_rojo),
                        t.riesgo, _bool_a_int(t.requiere_derivacion), t.observaciones,
                        t.duracion_segundos, t.timestamp_captura,
                        t.ruta_imagen_od, t.ruta_imagen_oi,
                        t.hash_imagen_od, t.hash_imagen_oi,
                        t.estado_sync.value, t.estado_imagenes.value,
                        t.intentos_sync, t.ultimo_error,
                        t.creado_en, t.actualizado_en,
                    ),
                )
            self._auditar(t.uuid_local, "CREADO", f"estado={t.estado_sync.value}")
        return t.uuid_local

    def adjuntar_imagen(self, uuid_local: str, ojo: str, ruta_origen: str) -> None:
        """
        Copia una imagen a la carpeta gestionada y actualiza el registro con su
        ruta y hash. La subida es opcional; esto solo prepara el dato local.
        """
        ruta, h = self.imagenes.guardar_imagen(uuid_local, ojo, ruta_origen)
        col_ruta = "ruta_imagen_od" if ojo.lower() == "od" else "ruta_imagen_oi"
        col_hash = "hash_imagen_od" if ojo.lower() == "od" else "hash_imagen_oi"
        with self._lock:
            with self._conn:
                self._conn.execute(
                    f"UPDATE tamizajes SET {col_ruta}=?, {col_hash}=?, "
                    f"estado_imagenes=?, actualizado_en=? WHERE uuid_local=?",
                    (ruta, h, EstadoImagenes.PENDIENTE.value, ahora_utc_iso(), uuid_local),
                )
            self._auditar(uuid_local, "IMAGEN_ADJUNTADA", f"{ojo}={ruta}")

    def marcar_estado_sync(self, uuid_local: str, estado: EstadoSync,
                            registro_id_servidor: Optional[str] = None,
                            error: Optional[str] = None,
                            incrementar_intentos: bool = False) -> None:
        """Actualiza el estado de sincronización y audita la transición."""
        sets = ["estado_sync=?", "actualizado_en=?"]
        params: list = [estado.value, ahora_utc_iso()]

        if registro_id_servidor is not None:
            sets.append("registro_id_servidor=?")
            params.append(registro_id_servidor)
        if error is not None:
            sets.append("ultimo_error=?")
            params.append(error)
        if incrementar_intentos:
            sets.append("intentos_sync = intentos_sync + 1")

        params.append(uuid_local)
        with self._lock:
            with self._conn:
                self._conn.execute(
                    f"UPDATE tamizajes SET {', '.join(sets)} WHERE uuid_local=?",
                    params,
                )
            detalle = estado.value
            if registro_id_servidor:
                detalle += f" registro_id_servidor={registro_id_servidor}"
            if error:
                detalle += f" error={error}"
            self._auditar(uuid_local, "ESTADO_SYNC", detalle)

    def marcar_estado_imagenes(self, uuid_local: str, estado: EstadoImagenes) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "UPDATE tamizajes SET estado_imagenes=?, actualizado_en=? "
                    "WHERE uuid_local=?",
                    (estado.value, ahora_utc_iso(), uuid_local),
                )
            self._auditar(uuid_local, "ESTADO_IMAGENES", estado.value)

    # ── Lectura ──────────────────────────────────────────────────────────────
    def obtener(self, uuid_local: str) -> Optional[Tamizaje]:
        with self._lock:
            fila = self._conn.execute(
                "SELECT * FROM tamizajes WHERE uuid_local=?", (uuid_local,)
            ).fetchone()
        return self._fila_a_tamizaje(fila) if fila else None

    def listar_pendientes(self, max_intentos: int = 5) -> list[Tamizaje]:
        """
        Tamizajes que el sincronizador debe intentar enviar: los PENDIENTE y los
        ERROR_REINTENTABLE que no hayan superado el límite de intentos.
        Ordenados por antigüedad (los más viejos primero).
        """
        with self._lock:
            filas = self._conn.execute(
                """
                SELECT * FROM tamizajes
                WHERE estado_sync IN (?, ?) AND intentos_sync < ?
                ORDER BY creado_en ASC
                """,
                (EstadoSync.PENDIENTE.value, EstadoSync.ERROR_REINTENTABLE.value,
                 max_intentos),
            ).fetchall()
        return [self._fila_a_tamizaje(f) for f in filas]

    def contar_por_estado(self) -> dict[str, int]:
        with self._lock:
            filas = self._conn.execute(
                "SELECT estado_sync, COUNT(*) AS n FROM tamizajes GROUP BY estado_sync"
            ).fetchall()
        return {f["estado_sync"]: f["n"] for f in filas}

    def historial_auditoria(self, uuid_local: str) -> list[dict]:
        with self._lock:
            filas = self._conn.execute(
                "SELECT evento, detalle, creado_en FROM auditoria "
                "WHERE uuid_local=? ORDER BY id ASC",
                (uuid_local,),
            ).fetchall()
        return [dict(f) for f in filas]

    # ── Recuperación tras reinicio ───────────────────────────────────────────
    def recuperar_envios_interrumpidos(self) -> int:
        """
        RESTRICCIÓN/PRINCIPIO de robustez:
            Al arrancar, cualquier tamizaje que quedó en ENVIANDO (el dispositivo
            se reinició a mitad de un envío) se devuelve a PENDIENTE. Así ningún
            envío a medias se da por concluido y se reintentará limpiamente.
        Devuelve cuántos registros se recuperaron.
        """
        with self._lock:
            with self._conn:
                cur = self._conn.execute(
                    "UPDATE tamizajes SET estado_sync=?, actualizado_en=? "
                    "WHERE estado_sync=?",
                    (EstadoSync.PENDIENTE.value, ahora_utc_iso(),
                     EstadoSync.ENVIANDO.value),
                )
                n = cur.rowcount
            if n:
                self._auditar(None, "RECUPERACION",
                              f"{n} envío(s) interrumpido(s) devuelto(s) a PENDIENTE")
        return n

    # ── Internos ─────────────────────────────────────────────────────────────
    def _auditar(self, uuid_local: Optional[str], evento: str, detalle: str = "") -> None:
        # Ya se asume que el llamador sostiene self._lock (RLock: seguro
        # de tomar de nuevo desde el mismo hilo) — todos los llamadores
        # públicos de este método así lo hacen.
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO auditoria (uuid_local, evento, detalle, creado_en) "
                    "VALUES (?,?,?,?)",
                    (uuid_local, evento, detalle, ahora_utc_iso()),
                )

    @staticmethod
    def _fila_a_tamizaje(f: sqlite3.Row) -> Tamizaje:
        return Tamizaje(
            uuid_local=f["uuid_local"],
            registro_id_servidor=f["registro_id_servidor"],
            colegio_nombre=f["colegio_nombre"] or "",
            colegio_distrito=f["colegio_distrito"] or "",
            tecnologo=f["tecnologo"] or "",
            fecha_sesion=f["fecha_sesion"] or "",
            dni=f["dni"] or "",
            nombre_paciente=f["nombre_paciente"] or "",
            fecha_nacimiento=f["fecha_nacimiento"] or "",
            grado_seccion=f["grado_seccion"] or "",
            email_padre=f["email_padre"],
            telefono_padre=f["telefono_padre"],
            od=ResultadoOjo(
                esfera=f["od_esfera"], cilindro=f["od_cilindro"], eje=f["od_eje"],
                esfera_sd=f["od_esfera_sd"], cilindro_sd=f["od_cilindro_sd"],
                eje_sd=f["od_eje_sd"], reflejo_rojo=_int_a_bool(f["od_reflejo_rojo"]),
            ),
            oi=ResultadoOjo(
                esfera=f["oi_esfera"], cilindro=f["oi_cilindro"], eje=f["oi_eje"],
                esfera_sd=f["oi_esfera_sd"], cilindro_sd=f["oi_cilindro_sd"],
                eje_sd=f["oi_eje_sd"], reflejo_rojo=_int_a_bool(f["oi_reflejo_rojo"]),
            ),
            riesgo=f["riesgo"],
            requiere_derivacion=_int_a_bool(f["requiere_derivacion"]),
            observaciones=f["observaciones"] or "",
            duracion_segundos=f["duracion_segundos"],
            timestamp_captura=f["timestamp_captura"],
            ruta_imagen_od=f["ruta_imagen_od"],
            ruta_imagen_oi=f["ruta_imagen_oi"],
            hash_imagen_od=f["hash_imagen_od"],
            hash_imagen_oi=f["hash_imagen_oi"],
            estado_sync=EstadoSync(f["estado_sync"]),
            estado_imagenes=EstadoImagenes(f["estado_imagenes"]),
            intentos_sync=f["intentos_sync"],
            ultimo_error=f["ultimo_error"],
            creado_en=f["creado_en"],
            actualizado_en=f["actualizado_en"],
        )

    def cerrar(self) -> None:
        with self._lock:
            self._conn.close()
