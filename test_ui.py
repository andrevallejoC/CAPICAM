"""
test_ui.py — Pruebas de aceptación de la Fase 5 (ui/ PyQt5).

Corre con PyQt5 REAL en modo offscreen (QT_QPA_PLATFORM=offscreen) —
no son mocks del framework gráfico, es Qt de verdad ejecutándose sin
pantalla física. Motor, ReglasClinicas y el gestor de cámara SÍ son
dobles de prueba (mismo patrón que test_orchestrator.py): motor real
requiere hardware (cámara, LEDs), y no es el objetivo de esta fase
volver a probar engine/, ya validado en la Fase 4.

Cubre: cableado completo de VentanaPrincipal (navegación entre las 4
pantallas), el ciclo de vida de HiloOrquestador (cruce de hilos real,
verificado con QTest.qWait), reutilización de datos de sesión para
"siguiente niño, mismo colegio", cambio de colegio, cancelación, y
manejo de errores de captura con reinicio de la vista previa.
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from lux_eyes.common.tipos import ResultadoOjo
from lux_eyes.clinical import ReglasClinicasAAPOS
from lux_eyes.storage import RepositorioTamizajes
from lux_eyes.sync import ConfiguracionSync
from lux_eyes.ui import VentanaPrincipal
from lux_eyes.ui.pantallas import PantallaFormularioSesion  # noqa: F401 (confirma import)

VERDE = "\033[92m"; ROJO = "\033[91m"; RESET = "\033[0m"
_ok = 0; _fail = 0

_app = QApplication.instance() or QApplication([])


def check(nombre, condicion):
    global _ok, _fail
    if condicion:
        _ok += 1
        print(f"  {VERDE}PASA{RESET}  {nombre}")
    else:
        _fail += 1
        print(f"  {ROJO}FALLA{RESET} {nombre}")


def esperar(ms=200):
    QTest.qWait(ms)


def esperar_hasta(condicion, timeout_ms=3000, paso_ms=50, mensaje=None, lanzar=True):
    """
    Espera activamente hasta que condicion() sea verdadera.

    [CORRECCIÓN — bug real de esta misma prueba, detectado al validar en
    la Raspberry Pi con un usuario real] La versión anterior devolvía
    simplemente False si el timeout se cumplía, y varios de los helpers
    de este archivo llamaban a esperar_hasta() sin envolver el resultado
    en check() — es decir, si la pantalla nunca cambiaba, la prueba
    simplemente esperaba en silencio y SEGUÍA COMO SI NADA. Peor aún:
    QTest.mouseClick() puede hacer clic en un botón aunque ese widget NO
    sea la página visible del QStackedWidget (un clic simulado no
    necesita que el usuario "vea" el widget) — así que el resto del
    flujo seguía funcionando por dentro aunque la pantalla real nunca
    hubiera cambiado. El resultado: 18/18 y luego 22/22 "pasando" en
    esta prueba, mientras un usuario real veía el botón "Continuar" sin
    hacer nada.

    Por eso ahora, por defecto (lanzar=True), esperar_hasta() LANZA una
    excepción si el timeout se cumple — un fallo de configuración/setup
    dentro de un helper debe detener la prueba con un traceback claro,
    no continuar en silencio. Los usos dentro de check(...) en el cuerpo
    principal de main() pasan lanzar=False explícitamente, para seguir
    contando fallos sin abortar toda la corrida.
    """
    transcurrido = 0
    while not condicion() and transcurrido < timeout_ms:
        QTest.qWait(paso_ms)
        transcurrido += paso_ms
    resultado = condicion()
    if not resultado and lanzar:
        raise AssertionError(
            mensaje or f"esperar_hasta: la condición no se cumplió tras {timeout_ms}ms "
            f"(revisa si falta un setCurrentWidget() o una conexión de señal)"
        )
    return resultado


class MotorFalso:
    """No requiere hardware: devuelve resultados fijos o simula un fallo."""

    def __init__(self):
        self.guiones: dict[str, list] = {"od": [], "oi": []}

    def programar(self, ojo: str, *eventos):
        self.guiones[ojo] = list(eventos)

    def medir_ojo(self, ojo, reportar_progreso):
        reportar_progreso(f"iluminando meridiano 0° ({ojo})")
        guion = self.guiones.get(ojo, [])
        resultado = guion.pop(0) if guion else ResultadoOjo(esfera=1.0, cilindro=-0.5, eje=90.0)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


class GestorCamaraFalso:
    """Implementa el contrato GestorCamara sin ninguna cámara real."""

    def __init__(self):
        self.veces_iniciada = 0
        self.veces_detenida = 0
        self.activa = False

    def iniciar_vista_previa(self, callback_frame):
        self.veces_iniciada += 1
        self.activa = True
        # Simula un frame real para confirmar que actualizar_frame_preview funciona.
        imagen = QImage(4, 4, QImage.Format.Format_Grayscale8)
        imagen.fill(128)
        callback_frame(imagen)

    def detener_vista_previa(self):
        self.veces_detenida += 1
        self.activa = False


class ClienteSyncFalso:
    """Doble de prueba de ClienteAPI, sin red real — para probar HiloSync sin depender del servidor."""

    def __init__(self):
        self.llamadas_enviar_datos = 0
        self.debe_fallar_permanente = False

    def enviar_datos(self, payload):
        # Pequeña demora artificial (nada de red real) para que el estado
        # "sincronizando" del botón sea observable en la prueba — con un
        # cliente instantáneo, esa ventana dura microsegundos y la
        # verificación de "deshabilitado mientras sincroniza" se vuelve
        # una condición de carrera poco confiable.
        import time
        time.sleep(0.05)
        if self.debe_fallar_permanente:
            from lux_eyes.sync.excepciones import ErrorPermanente
            raise ErrorPermanente("422 simulado: payload rechazado por el servidor")
        self.llamadas_enviar_datos += 1
        return f"SRV-{self.llamadas_enviar_datos:04d}"

    def subir_imagenes(self, *args, **kwargs):
        pass

    def generar_pdf(self, *args, **kwargs):
        pass


def construir_ventana(motor=None, repo=None):
    tmp = Path(tempfile.mkdtemp(prefix="luxeyes_ui_"))
    repo = repo or RepositorioTamizajes(tmp / "a.db", tmp / "capturas")
    motor = motor or MotorFalso()
    clinical = ReglasClinicasAAPOS()
    camara = GestorCamaraFalso()
    cliente_sync = ClienteSyncFalso()
    config_sync = ConfiguracionSync(
        dispositivo_id="RPi-PRUEBA-01", version_firmware="1.0.0",
        url_base="http://prueba.invalido", token="token-de-prueba",
    )
    ventana = VentanaPrincipal(
        repo=repo, motor=motor, clinical=clinical, gestor_camara=camara,
        cliente_sync=cliente_sync, config_sync=config_sync,
    )
    ventana.show()  # necesario para que QWidget.isVisible() refleje la realidad en las pruebas
    esperar_hasta(lambda: ventana._pila.currentWidget() is ventana._pantalla_sesion,
                  mensaje="al arrancar, nunca se mostró PantallaFormularioSesion")
    return ventana, repo, motor, camara


def completar_sesion_y_paciente(ventana, colegio="I.E. San Miguel", dni="12345678", nombre="Ana Pérez"):
    ps = ventana._pantalla_sesion
    ps._campo_colegio.setText(colegio)
    ps._campo_distrito.setText("San Miguel")
    ps._campo_tecnologo.setText("TM. Rodríguez")
    ps._campo_fecha.setText("2026-07-01")
    QTest.mouseClick(ps._boton_continuar, Qt.LeftButton)  # clic REAL, no emit() directo
    esperar_hasta(lambda: ventana._pila.currentWidget() is ventana._pantalla_paciente,
                  mensaje="tras 'Continuar' en el formulario de sesión, nunca se "
                          "mostró PantallaFormularioPaciente")

    pp = ventana._pantalla_paciente
    pp._campo_dni.setText(dni)
    pp._campo_nombre.setText(nombre)
    pp._campo_fecha_nacimiento.setText("2020-01-01")
    pp._campo_grado.setText("3A")
    QTest.mouseClick(pp._boton_continuar, Qt.LeftButton)
    esperar_hasta(lambda: ventana._pila.currentWidget() is ventana._pantalla_captura,
                  mensaje="tras 'Continuar' en el formulario de paciente, nunca se "
                          "mostró PantallaCaptura")


def completar_solo_paciente(ventana, dni="12345678", nombre="Ana Pérez"):
    """Para el flujo 'siguiente niño': la sesión ya se reenvió automáticamente."""
    pp = ventana._pantalla_paciente
    pp._campo_dni.setText(dni)
    pp._campo_nombre.setText(nombre)
    pp._campo_fecha_nacimiento.setText("2020-01-01")
    pp._campo_grado.setText("3A")
    QTest.mouseClick(pp._boton_continuar, Qt.LeftButton)
    esperar_hasta(lambda: ventana._pila.currentWidget() is ventana._pantalla_captura,
                  mensaje="tras 'Continuar' (flujo siguiente niño), nunca se mostró PantallaCaptura")


def main():
    print("\n=== ui/ — VentanaPrincipal con PyQt5 real (offscreen) ===\n")

    # ── 0. Las 4 pantallas caben en la pantalla táctil real (800x480) ──
    # DECISIÓN (detectada en la práctica: la primera versión de
    # PantallaCaptura pedía 598px de alto, más de lo que existe físicamente
    # en la pantalla real del dispositivo). Esta prueba existe para que un
    # futuro cambio de tamaño en cualquier pantalla nunca vuelva a pasar
    # desapercibido — se mide sizeHint() real de Qt, no una suposición.
    print("0) Las 4 pantallas caben en la resolución real del dispositivo (800x480)")
    ANCHO_PANTALLA_REAL = 800
    ALTO_PANTALLA_REAL = 480
    from lux_eyes.ui.pantallas import (
        PantallaCaptura, PantallaFormularioPaciente, PantallaFormularioSesion, PantallaResultado,
    )
    for nombre, clase in [
        ("FormularioSesion", PantallaFormularioSesion),
        ("FormularioPaciente", PantallaFormularioPaciente),
        ("Captura", PantallaCaptura),
        ("Resultado", PantallaResultado),
    ]:
        w = clase()
        if hasattr(w, "preparar"):
            w.preparar("od")  # fuerza texto real (no vacío) antes de medir
        w.adjustSize()
        hint = w.sizeHint()
        check(f"{nombre}: sizeHint ({hint.width()}x{hint.height()}) cabe en "
              f"{ANCHO_PANTALLA_REAL}x{ALTO_PANTALLA_REAL}",
              hint.width() <= ANCHO_PANTALLA_REAL and hint.height() <= ALTO_PANTALLA_REAL)

    # El encabezado de marca (EncabezadoMarca) vive POR ENCIMA de las 4
    # pantallas en VentanaPrincipal — las mediciones de arriba, cada
    # pantalla por separado, NO capturan ese espacio adicional. Se mide
    # aparte, sumado al peor caso (Captura, la más ajustada de las 4),
    # para confirmar que la combinación real sigue cabiendo.
    from lux_eyes.ui.pantallas import EncabezadoMarca
    encabezado = EncabezadoMarca()
    encabezado.adjustSize()
    captura_para_medir = PantallaCaptura()
    captura_para_medir.preparar("od")
    captura_para_medir.adjustSize()
    alto_combinado = encabezado.sizeHint().height() + captura_para_medir.sizeHint().height()
    check(f"EncabezadoMarca ({encabezado.sizeHint().height()}px) + Captura "
          f"({captura_para_medir.sizeHint().height()}px) combinados "
          f"({alto_combinado}px) caben en {ALTO_PANTALLA_REAL}px, con margen "
          f"para la barra de estado de VentanaPrincipal",
          alto_combinado <= ALTO_PANTALLA_REAL - 30)  # 30px de margen para la barra de estado

    # ── 1. Arranque: se muestra el formulario de sesión ─────────────────
    print("\n1) Arranque de la ventana")
    ventana, repo, motor, camara = construir_ventana()
    esperar()
    check("al arrancar, se muestra PantallaFormularioSesion",
          ventana._pila.currentWidget() is ventana._pantalla_sesion)

    # ── 2. Flujo feliz completo: sesión -> paciente -> captura -> resultado -> guardar ──
    print("\n2) Flujo feliz completo")
    completar_sesion_y_paciente(ventana)
    check("tras confirmar sesión y paciente, se muestra PantallaCaptura (od)",
          ventana._pila.currentWidget() is ventana._pantalla_captura
          and ventana._pantalla_captura.ojo_actual == "od")
    check("la vista previa se inició automáticamente al entrar a captura",
          camara.veces_iniciada == 1 and camara.activa)

    QTest.mouseClick(ventana._pantalla_captura._boton_iniciar, Qt.LeftButton)
    # detener_vista_previa() es una llamada SÍNCRONA dentro de
    # _al_iniciar_captura (misma conexión directa, mismo hilo) — ya se
    # ejecutó en cuanto emit() retorna, antes de esperar la transición a
    # 'oi' (que a su vez reactivará la vista previa para el segundo ojo,
    # legítimamente — por eso esta verificación va ANTES de esperar esa
    # transición, no después).
    check("al iniciar captura, la vista previa se detuvo",
          camara.veces_detenida == 1 and not camara.activa)
    check("tras completar 'od', la pantalla pasa a 'oi' automáticamente",
          esperar_hasta(lambda: ventana._pantalla_captura.ojo_actual == "oi", lanzar=False))
    check("la vista previa se reinició para el segundo ojo",
          camara.veces_iniciada == 2)

    QTest.mouseClick(ventana._pantalla_captura._boton_iniciar, Qt.LeftButton)
    check("tras completar ambos ojos, se muestra PantallaResultado",
          esperar_hasta(lambda: ventana._pila.currentWidget() is ventana._pantalla_resultado, lanzar=False))
    check("PantallaResultado tiene ambos resultados guardados internamente",
          "od" in ventana._resultados and "oi" in ventana._resultados)

    QTest.mouseClick(ventana._pantalla_resultado._boton_guardar, Qt.LeftButton)
    check("tras guardar, storage/ tiene exactamente 1 registro",
          esperar_hasta(lambda: sum(repo.contar_por_estado().values()) == 1, lanzar=False))
    check("PantallaResultado muestra el modo post-guardado",
          esperar_hasta(lambda: ventana._pantalla_resultado._etiqueta_guardado.isVisible(), lanzar=False))

    # ── 3. "Siguiente niño, mismo colegio" — sin repetir el formulario de sesión ──
    print("\n3) Siguiente niño, mismo colegio")
    QTest.mouseClick(ventana._pantalla_resultado._boton_siguiente_nino, Qt.LeftButton)
    check("tras 'siguiente niño', se muestra directamente PantallaFormularioPaciente "
          "(NO se repite el formulario de sesión)",
          esperar_hasta(lambda: ventana._pila.currentWidget() is ventana._pantalla_paciente, lanzar=False))

    completar_solo_paciente(ventana, dni="87654321", nombre="Beto Quispe")
    esperar_hasta(lambda: ventana._pantalla_captura.ojo_actual == "od")
    QTest.mouseClick(ventana._pantalla_captura._boton_iniciar, Qt.LeftButton)
    esperar_hasta(lambda: ventana._pantalla_captura.ojo_actual == "oi")
    QTest.mouseClick(ventana._pantalla_captura._boton_iniciar, Qt.LeftButton)
    esperar_hasta(lambda: ventana._pila.currentWidget() is ventana._pantalla_resultado)
    QTest.mouseClick(ventana._pantalla_resultado._boton_guardar, Qt.LeftButton)
    check("segundo tamizaje del mismo colegio también se guardó (storage/ tiene 2)",
          esperar_hasta(lambda: sum(repo.contar_por_estado().values()) == 2, lanzar=False))

    # ── 4. Cambiar de colegio ─────────────────────────────────────────────
    print("\n4) Cambiar de colegio")
    QTest.mouseClick(ventana._pantalla_resultado._boton_cambiar_colegio, Qt.LeftButton)
    check("tras 'cambiar de colegio', se muestra PantallaFormularioSesion",
          esperar_hasta(lambda: ventana._pila.currentWidget() is ventana._pantalla_sesion, lanzar=False))

    # ── 5. Error de captura: reintento sin perder sesión/paciente ───────
    print("\n5) Error de captura y reintento")
    ventana2, repo2, motor2, camara2 = construir_ventana()
    esperar()
    motor2.programar("od", RuntimeError("pupila no detectada"))
    completar_sesion_y_paciente(ventana2)
    esperar_hasta(lambda: ventana2._pantalla_captura.ojo_actual == "od")
    QTest.mouseClick(ventana2._pantalla_captura._boton_iniciar, Qt.LeftButton)
    check("tras un fallo de captura, la pantalla de captura muestra el error",
          esperar_hasta(lambda: ventana2._pantalla_captura._etiqueta_error.isVisible(), lanzar=False))
    check("sigue en el mismo ojo ('od'), listo para reintentar",
          ventana2._pantalla_captura.ojo_actual == "od")
    check("la vista previa se reinició tras el error, para reposicionar",
          camara2.veces_iniciada == 2)  # 1 al entrar + 1 al fallar

    QTest.mouseClick(ventana2._pantalla_captura._boton_iniciar, Qt.LeftButton)  # reintento, ahora sin guion de error
    check("el reintento avanza normalmente a 'oi'",
          esperar_hasta(lambda: ventana2._pantalla_captura.ojo_actual == "oi", lanzar=False))

    # ── 6. Botón "Sincronizar ahora" ──────────────────────────────────────
    print("\n6) Botón de sincronización")
    check("al arrancar, la barra muestra el contador de pendientes (2, de las secciones 2-3)",
          "2" in ventana._etiqueta_pendientes.text())

    cliente_de_ventana = ventana._hilo_sync.worker._sincronizador._cliente
    QTest.mouseClick(ventana._boton_sincronizar, Qt.LeftButton)
    check("mientras sincroniza, el botón se deshabilita",
          esperar_hasta(lambda: not ventana._boton_sincronizar.isEnabled(), lanzar=False))
    check("tras terminar, el botón se reactiva y el contador baja a 0 "
          "(los 2 tamizajes pendientes se sincronizaron)",
          esperar_hasta(lambda: ventana._boton_sincronizar.isEnabled()
                        and "0" in ventana._etiqueta_pendientes.text(), lanzar=False))
    check("el cliente de sync falso realmente recibió las llamadas "
          "(no fue solo un cambio de UI sin efecto real)",
          cliente_de_ventana.llamadas_enviar_datos == 2)
    check("storage/ refleja SINCRONIZADO para los 2 tamizajes guardados",
          repo.contar_por_estado().get("SINCRONIZADO", 0) == 2)

    # ── 6b. CORRECCIÓN: '0 pendientes' no debe confundirse con éxito ────
    print("\n6b) Error permanente: '0 pendientes' no debe parecer éxito")
    print("    (bug real reportado por un usuario: un tamizaje con error")
    print("    permanente mostraba '0 pendientes', que se leía como todo bien)")
    ventana3, repo3, motor3, camara3 = construir_ventana()
    esperar()
    completar_sesion_y_paciente(ventana3, dni="99988877")
    QTest.mouseClick(ventana3._pantalla_captura._boton_iniciar, Qt.LeftButton)
    esperar_hasta(lambda: ventana3._pantalla_captura.ojo_actual == "oi")
    QTest.mouseClick(ventana3._pantalla_captura._boton_iniciar, Qt.LeftButton)
    esperar_hasta(lambda: ventana3._pila.currentWidget() is ventana3._pantalla_resultado)
    QTest.mouseClick(ventana3._pantalla_resultado._boton_guardar, Qt.LeftButton)
    esperar_hasta(lambda: sum(repo3.contar_por_estado().values()) == 1)

    ventana3._hilo_sync.worker._sincronizador._cliente.debe_fallar_permanente = True
    QTest.mouseClick(ventana3._boton_sincronizar, Qt.LeftButton)
    # Esperar PRIMERO a que se deshabilite (confirma que la sincronización
    # arrancó de verdad) y RECIÉN DESPUÉS a que se reactive (confirma que
    # terminó) — el mismo bug de "condición ya cumplida de entrada" que se
    # corrigió en la sección 6, reintroducido aquí al saltarme ese paso
    # intermedio. Sin él, a veces se revisaba la pantalla ANTES de que la
    # sincronización siquiera hubiera empezado a procesarse.
    esperar_hasta(lambda: not ventana3._boton_sincronizar.isEnabled(), lanzar=False)
    esperar_hasta(lambda: ventana3._boton_sincronizar.isEnabled(), lanzar=False)

    check("tras un error permanente, el contador dice '0 pendientes' PERO "
          "incluye la advertencia explícita (no se lee como éxito)",
          "0 tamizaje(s) pendiente(s)" in ventana3._etiqueta_pendientes.text()
          and "ATENCIÓN" in ventana3._etiqueta_pendientes.text()
          and "error permanente" in ventana3._etiqueta_pendientes.text())
    check("storage/ confirma ERROR_PERMANENTE (no SINCRONIZADO)",
          repo3.contar_por_estado().get("ERROR_PERMANENTE", 0) == 1)
    ventana3.close()
    repo3.cerrar()

    # ── 6c. Botones "Atrás" (navegación simple, sin perder el flujo) ────
    print("\n6c) Botones 'Atrás' (cancelar y volver a la pantalla anterior)")
    ventana4, repo4, motor4, camara4 = construir_ventana()
    esperar()

    # Atrás desde FormularioPaciente -> vuelve a FormularioSesion (sin
    # sesión cacheada todavía, en una ventana recién creada).
    ps4 = ventana4._pantalla_sesion
    ps4._campo_colegio.setText("I.E. San Miguel")
    ps4._campo_distrito.setText("San Miguel")
    ps4._campo_tecnologo.setText("TM. Rodríguez")
    ps4._campo_fecha.setText("2026-07-01")
    QTest.mouseClick(ps4._boton_continuar, Qt.LeftButton)  # clic REAL
    esperar_hasta(lambda: ventana4._pila.currentWidget() is ventana4._pantalla_paciente)
    QTest.mouseClick(ventana4._pantalla_paciente._boton_atras, Qt.LeftButton)
    check("Atrás desde FormularioPaciente vuelve a FormularioSesion",
          esperar_hasta(lambda: ventana4._pila.currentWidget() is ventana4._pantalla_sesion,
                        lanzar=False))
    check("el formulario de sesión queda PRE-LLENADO con lo ya escrito, "
          "no en blanco (mejor experiencia que retipear todo)",
          ventana4._pantalla_sesion._campo_colegio.text() == "I.E. San Miguel")

    # Atrás desde PantallaCaptura -> cancela y, como ya hay sesión
    # cacheada (se guardó en el primer paso de arriba), reanuda
    # directamente en FormularioPaciente (mismo colegio) sin repetir el
    # formulario de sesión.
    completar_sesion_y_paciente(ventana4, dni="55556666")
    check("la vista previa está activa al entrar a captura",
          camara4.activa)
    QTest.mouseClick(ventana4._pantalla_captura._boton_atras, Qt.LeftButton)
    check("Atrás desde captura libera la cámara",
          esperar_hasta(lambda: not camara4.activa, lanzar=False))
    check("Atrás desde captura vuelve a FormularioPaciente (sesión ya "
          "cacheada, no repite el formulario de sesión)",
          esperar_hasta(lambda: ventana4._pila.currentWidget() is ventana4._pantalla_paciente,
                        lanzar=False))
    ventana4.close()
    repo4.cerrar()

    # ── 7. Cierre limpio ──────────────────────────────────────────────────
    print("\n7) Cierre limpio de la ventana")
    ventana.close()
    ventana2.close()
    check("la vista previa quedó detenida tras cerrar", not camara.activa)
    repo.cerrar()
    repo2.cerrar()

    print(f"\n{'='*52}")
    total = _ok + _fail
    color = VERDE if _fail == 0 else ROJO
    print(f"{color}Resultado: {_ok}/{total} pruebas pasadas, {_fail} fallidas{RESET}")
    print(f"{'='*52}\n")
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
