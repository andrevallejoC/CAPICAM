"""
storage/imagenes.py — Gestión de las imágenes IR en el sistema de archivos.

DECISIÓN de arquitectura:
    Las imágenes (binarios grandes) NO se guardan dentro de SQLite. Se guardan
    en disco y la base de datos almacena solo su ruta y su hash de integridad.
    Esto mantiene la base ligera y el acceso a binarios eficiente.

El vínculo entre un tamizaje y sus imágenes se hace por uuid_local, NO por el id
autoincremental de la base (que era el bug de la implementación previa: el nombre
del archivo no tenía relación fiable con el registro). Aquí el nombre del archivo
deriva del uuid_local, garantizando un vínculo estable.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Optional


class GestorImagenes:
    """Copia, nombra y verifica las imágenes asociadas a cada tamizaje."""

    def __init__(self, carpeta_base: str | Path):
        self.carpeta_base = Path(carpeta_base)
        self.carpeta_base.mkdir(parents=True, exist_ok=True)

    def _destino(self, uuid_local: str, ojo: str, extension: str) -> Path:
        """Ruta destino estable derivada del uuid_local. ojo ∈ {'od','oi'}."""
        return self.carpeta_base / f"{uuid_local}_{ojo}{extension}"

    @staticmethod
    def hash_archivo(ruta: str | Path) -> str:
        """SHA-256 del contenido de un archivo, para verificar integridad."""
        h = hashlib.sha256()
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(8192), b""):
                h.update(bloque)
        return h.hexdigest()

    def guardar_imagen(self, uuid_local: str, ojo: str, ruta_origen: str | Path
                       ) -> tuple[str, str]:
        """
        Copia la imagen capturada a la carpeta gestionada, con nombre derivado
        del uuid_local. Devuelve (ruta_destino, hash). Lanza si el origen no existe.
        """
        ojo = ojo.lower()
        if ojo not in ("od", "oi"):
            raise ValueError(f"ojo debe ser 'od' u 'oi', no {ojo!r}")

        origen = Path(ruta_origen)
        if not origen.is_file():
            raise FileNotFoundError(f"No existe la imagen de origen: {origen}")

        destino = self._destino(uuid_local, ojo, origen.suffix or ".jpg")
        shutil.copy2(origen, destino)
        return str(destino), self.hash_archivo(destino)

    def verificar_integridad(self, ruta: str | Path, hash_esperado: str) -> bool:
        """True si el archivo existe y su hash coincide con el esperado."""
        p = Path(ruta)
        if not p.is_file():
            return False
        return self.hash_archivo(p) == hash_esperado

    def eliminar_imagenes(self, uuid_local: str) -> None:
        """Borra todas las imágenes asociadas a un uuid_local (limpieza)."""
        for archivo in self.carpeta_base.glob(f"{uuid_local}_*"):
            try:
                archivo.unlink()
            except OSError:
                pass
