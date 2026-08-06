"""
storage/ — Fuente de verdad local de Lux Eyes. Única puerta de acceso al
almacenamiento (patrón Repository). No modificado en la Fase 2.
"""

from .repositorio import RepositorioTamizajes

__all__ = ["RepositorioTamizajes"]
