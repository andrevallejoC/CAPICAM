"""
ui/estilos.py — Paleta de colores y hoja de estilos (QSS) de Lux Eyes.

DECISIÓN de rendimiento (pantalla táctil de 5", Raspberry Pi 4): todo el
estilo vive en QSS (hojas de estilo de Qt, equivalente a CSS) — no hay
QGraphicsEffect, ni QPropertyAnimation, ni gradientes complejos, ni
imágenes grandes redibujándose. QSS lo resuelve el motor de renderizado
de Qt una sola vez por widget; es prácticamente gratis en comparación con
efectos gráficos reales. La única imagen (el capibara) se guarda ya
reducida en assets/ — nunca se decodifica ni reescala la original de
607x737 en tiempo de ejecución.

Paleta: tonos cálidos (crema, ámbar) combinados con un teal profundo —
ligado al nombre "LUXeyes" (ámbar = luz) sin perder un aire clínico/
confiable (teal, muy usado en salud visual). Grises cálidos en vez de
negro puro, para que se sienta menos "formulario frío".
"""

from __future__ import annotations

# ── Paleta (también usada directamente en código, no solo en QSS) ──────
PRIMARIO = "#2A6F77"          # teal profundo — botones principales, títulos
PRIMARIO_OSCURO = "#1F5459"   # estado presionado del primario
PRIMARIO_CLARO = "#5FA8AE"    # bordes/acentos secundarios
ACENTO = "#E8A33D"            # ámbar cálido — ligado a "LUX"
FONDO = "#FBF8F3"             # crema suave, no blanco puro
SUPERFICIE = "#FFFFFF"        # tarjetas/campos sobre el fondo crema
TEXTO = "#33322E"             # gris cálido oscuro, no negro puro
TEXTO_SUAVE = "#6B6960"       # texto secundario
BORDE = "#DDD5C7"             # bordes suaves, tono cálido
EXITO = "#4F9A5B"
ERROR = "#C0522D"
ADVERTENCIA = "#C77C1F"


def hoja_de_estilos() -> str:
    """QSS aplicado UNA vez, a nivel de VentanaPrincipal — se hereda hacia
    todos los widgets hijos sin coste adicional por pantalla."""
    return f"""
        QMainWindow, QWidget {{
            background-color: {FONDO};
            color: {TEXTO};
            font-size: 12pt;
        }}

        QLabel {{
            background: transparent;
        }}

        QLabel[rolTitulo="true"] {{
            color: {PRIMARIO};
            font-size: 16pt;
            font-weight: 700;
        }}

        QLabel[rolSubtitulo="true"] {{
            color: {TEXTO_SUAVE};
            font-size: 10pt;
        }}

        QLineEdit {{
            background-color: {SUPERFICIE};
            border: 2px solid {BORDE};
            border-radius: 8px;
            padding: 6px 10px;
            selection-background-color: {ACENTO};
        }}
        QLineEdit:focus {{
            border: 2px solid {PRIMARIO_CLARO};
        }}

        QPushButton {{
            background-color: {PRIMARIO};
            color: white;
            border: none;
            border-radius: 10px;
            padding: 10px 20px;
            font-weight: 600;
            min-height: 28px;
        }}
        QPushButton:pressed {{
            background-color: {PRIMARIO_OSCURO};
        }}
        QPushButton:disabled {{
            background-color: {BORDE};
            color: {TEXTO_SUAVE};
        }}

        /* Botones secundarios ("Atrás", "Cancelar") — con
        setProperty("secundario", True) + polish(), se ven de contorno
        en vez de sólidos, para no competir visualmente con la acción
        principal de cada pantalla. */
        QPushButton[secundario="true"] {{
            background-color: transparent;
            color: {PRIMARIO};
            border: 2px solid {PRIMARIO_CLARO};
        }}
        QPushButton[secundario="true"]:pressed {{
            background-color: {FONDO};
        }}

        QStatusBar {{
            background-color: {SUPERFICIE};
            border-top: 1px solid {BORDE};
            color: {TEXTO_SUAVE};
        }}
    """
