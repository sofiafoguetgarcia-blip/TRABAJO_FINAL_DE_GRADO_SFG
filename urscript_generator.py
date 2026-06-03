# -*- coding: utf-8 -*-
"""
urscript_generator.py
=====================
Genera los tres scripts URScript que se envian a los robots.

Hay tres scripts por pieza:
1. UR5e recoger   -> el UR5e va a buscar la baldosa y la lleva a la zona compartida
2. UR3e dibujar   -> el UR3e dibuja encima de la baldosa
3. UR5e devolver  -> el UR5e recoge la baldosa de la zona compartida y la devuelve a su sitio

Notas importantes sobre el diseno:
- Las coordenadas X/Y vienen del JSON y se usan sin ningun ajuste.
- La orientacion de la muneca para coger/dejar piezas es siempre la misma
  (UR5E_PICK_ORIENTATION), independientemente del angulo que diga el JSON.
- El angulo de vision se incluye en un textmsg para que quede en el log
  del robot pero no se usa para nada mas.

Ventosa:
  SIMULAR_VENTOSA = True  -> solo manda un textmsg + sleep, no toca salidas digitales.
                             Util para pruebas sin la ventosa fisica conectada.
  SIMULAR_VENTOSA = False -> instruccion URScript real segun VENTOSA_TIPO_SALIDA:
      "DO_CONTROLADOR"    -> set_digital_out(pin, True/False)
      "TOOL_DO"           -> set_tool_digital_out(pin, True/False)
"""

from typing import List, Tuple
import logging

from config import (
    PC_IP,
    PORT_UR5_LISTO_UR3, PORT_UR3_LISTO_UR5,
    SYNC_MSG_LISTO,
    V_APROX, V_BAJA_UR5, V_TRASLADO,
    A_LENTO, A_RAPIDO,
    Z_APROX_UR5, Z_PIEZA_OFFSET,
    F_UMBRAL_UR5,
    SIMULAR_VENTOSA,
    VENTOSA_TIPO_SALIDA, VENTOSA_DO_PIN, VENTOSA_DELAY_ON, VENTOSA_DELAY_OFF,
    V_BAJA_UR3, V_DIBUJO, V_SUBIDA,
    A_DIBUJO,
    V_HOME,
    A_HOME,
    Z_PAPEL, Z_SUBIDA,
    F_UMBRAL_UR3,
    UR5E_DROP_APPROACH_POSE, UR5E_HOME_POSE, UR5E_PICK_ORIENTATION,
    UR3E_HOME_POSE,
)

from transform import obtener_drop_zones, formatear_pose

log = logging.getLogger(__name__)

Punto = Tuple[float, float]
Trayectoria = List[Punto]


def _pose_to_urscript(pose) -> str:
    """Convierte una lista de 6 valores en la sintaxis de pose de URScript: p[x,y,z,rx,ry,rz]."""
    p = [float(v) for v in pose]
    if len(p) != 6:
        raise ValueError("Una pose debe tener 6 valores [x,y,z,rx,ry,rz]")
    return "p[" + ", ".join(f"{v:.5f}" for v in p) + "]"


def _modo_ventosa_texto() -> str:
    """Devuelve una descripcion breve del modo de ventosa para los logs URScript."""
    if SIMULAR_VENTOSA:
        return "SIMULACION"
    return f"REAL ({VENTOSA_TIPO_SALIDA}, pin={VENTOSA_DO_PIN})"


def _parametros_pick_ur5(x_pieza: float, y_pieza: float) -> Tuple[float, float, float, float, float]:
    """Normaliza coordenadas de pieza y orientacion de recogida del UR5e."""
    xp = float(x_pieza)
    yp = float(y_pieza)
    rx_pick = float(UR5E_PICK_ORIENTATION[0])
    ry_pick = float(UR5E_PICK_ORIENTATION[1])
    rz_pick = float(UR5E_PICK_ORIENTATION[2])
    return xp, yp, rx_pick, ry_pick, rz_pick


def _pose_pick_ur5(z_expr: str = None) -> str:
    """Pose URScript del UR5e sobre la pieza usando x_pick, y_pick y orientacion fija."""
    z = z_expr if z_expr is not None else f"{Z_APROX_UR5:.5f}"
    return f"p[x_pick, y_pick, {z}, rx_pick, ry_pick, rz_pick]"


def _pose_dibujo_ur3(x: float, y: float, z_expr: str = "z_dibujo") -> str:
    """Pose URScript del UR3e para un punto del dibujo respecto al centro x0, y0."""
    return f"p[x0+{x:.5f}, y0+{y:.5f}, {z_expr}, rx, ry, rz]"

def _socket_aviso_pc(port: int, nombre: str, canal: str) -> List[str]:
    """
    Genera el bloque URScript para que el robot avise al PC de que ha terminado.
    Abre un socket, manda el mensaje LISTO y cierra la conexion.
    Si no puede conectar, para el programa con un popup de error.
    """
    return [
        f"  # Avisamos al PC de que esta fase ha terminado: {nombre}",
        f'  socket_ok = socket_open("{PC_IP}", {port}, "{canal}")',
        "  if (not socket_ok):",
        f'    popup("{nombre}: no pudo avisar al PC", error=True)',
        "    halt",
        "  else:",
        f'    socket_send_string("{SYNC_MSG_LISTO}", "{canal}")',
        "    sleep(0.2)",
        f'    socket_close("{canal}")',
        f'    textmsg("{nombre}: LISTO enviado al PC")',
        "  end",
    ]


def _bloque_ventosa(on: bool) -> List[str]:
    """
    Genera el bloque URScript para activar o desactivar la ventosa.

    Si SIMULAR_VENTOSA es True, solo se imprime un mensaje en el log del robot
    y se espera un momento. No se toca ninguna salida digital. Esto permite
    probar toda la secuencia de movimientos sin tener la ventosa conectada.

    Si SIMULAR_VENTOSA es False, se genera la instruccion real segun el tipo
    de salida configurado:
    - DO_CONTROLADOR: salida digital del armario del controlador
    - TOOL_DO: salida digital del conector de herramienta en la muneca
    """
    accion = "ON" if on else "OFF"
    estado_ur = "True" if on else "False"
    delay = VENTOSA_DELAY_ON if on else VENTOSA_DELAY_OFF
    pin = int(VENTOSA_DO_PIN)

    if SIMULAR_VENTOSA:
        if on:
            return [
                '  textmsg("SIMULACION ventosa: activando vacio (ON) - pieza cogida")',
                f"  sleep({VENTOSA_DELAY_ON:.2f})",
            ]
        else:
            return [
                '  textmsg("SIMULACION ventosa: liberando vacio (OFF) - pieza soltada")',
                f"  sleep({VENTOSA_DELAY_OFF:.2f})",
            ]

    # Ventosa fisica: elegimos la instruccion segun el tipo de salida
    tipo = VENTOSA_TIPO_SALIDA.strip().upper()

    if tipo == "DO_CONTROLADOR":
        instruccion = f"set_digital_out({pin}, {estado_ur})"
    elif tipo == "TOOL_DO":
        instruccion = f"set_tool_digital_out({pin}, {estado_ur})"
    else:
        raise ValueError(
            f"VENTOSA_TIPO_SALIDA desconocido: '{VENTOSA_TIPO_SALIDA}'. "
            "Usa 'DO_CONTROLADOR' o 'TOOL_DO'."
        )

    return [
        f'  textmsg("Ventosa {accion}: {instruccion}")',
        f"  {instruccion}",
        f"  sleep({delay:.2f})",
    ]


def _ir_home_ur5() -> List[str]:
    """Genera las lineas URScript para que el UR5e vaya a su posicion de reposo."""
    return [
        '  textmsg("UR5e: yendo a HOME")',
        f"  movej(q_home, a={A_HOME}, v={V_HOME})",
        "  sleep(0.3)",
    ]


def _detectar_superficie_ur5(nombre: str) -> List[str]:
    return [
        f'  textmsg("{nombre}: detectando superficie por fuerza")',
        "  zero_ftsensor()",
        "  sleep(0.5)",
        "  i_f = 0",

        # Mas iteraciones para que pueda bajar desde mas altura
        f"  while (force() < {F_UMBRAL_UR5:.3f} and i_f < 30000):",
        f"    speedl([0, 0, -{V_BAJA_UR5:.5f}, 0, 0, 0], 0.05, 0.008)",
        "    i_f = i_f + 1",
        "  end",

        # Parada mas suave/corta para evitar que siga apretando
        "  stopl(0.2)",
        "  sleep(0.1)",

        "  if (i_f >= 30000):",
        f'    popup("{nombre}: no se detecto contacto. Revisa posicion/Z/fuerza.", error=True)',
        "    halt",
        "  end",

        # Guardamos la altura de contacto
        "  z_contacto = get_actual_tcp_pose()[2]",

        # En tu caso NO queremos presionar mas ni subir antes de activar ventosa
        "  z_trabajo = z_contacto",

        f'  textmsg("{nombre}: z_contacto=", z_contacto)',
    ]


def _detectar_superficie_ur3() -> List[str]:
    """
    Genera el bloque URScript de deteccion de superficie para el UR3e.

    Funciona igual que en el UR5e pero con los parametros del UR3e.
    Una vez detectado el papel, calcula z_dibujo (la altura a la que
    tiene que ir el lapiz para tocar el papel justo) y sube a z_subida
    para estar listo para empezar el primer trazo.

    Esta deteccion solo se hace una vez al principio: todos los trazos
    del dibujo usan la misma z_dibujo.
    """
    return [
        '  textmsg("UR3e: detectando superficie una sola vez")',
        "  zero_ftsensor()",
        "  sleep(0.5)",
        "  i_f = 0",
        f"  while (force() < {F_UMBRAL_UR3:.3f} and i_f < 8000):",
        f"    speedl([0, 0, -{V_BAJA_UR3:.5f}, 0, 0, 0], 0.15, 0.02)",
        "    i_f = i_f + 1",
        "  end",
        "  stopl(3.0)",
        "  sleep(0.2)",
        "  if (i_f >= 8000):",
        '    popup("UR3e: no se detecto superficie. Revisa posicion/Z/fuerza.", error=True)',
        "    halt",
        "  end",
        "  z_contacto = get_actual_tcp_pose()[2]",
        f"  z_dibujo = z_contacto + {Z_PAPEL:.5f}",
        '  textmsg("UR3e: z_contacto=", z_contacto)',
        '  textmsg("UR3e: z_dibujo=", z_dibujo)',
        # Sube para estar listo antes del primer trazo
        f"  movel(p[x0, y0, z_dibujo+{Z_SUBIDA:.5f}, rx, ry, rz], a=0.03, v=0.010)",
    ]


def generar_script_ur5e_recoger(
    x_pieza: float,
    y_pieza: float,
    angulo_deg: float = 0.0
) -> str:
    """
    Genera el script URScript para que el UR5e recoja la baldosa y la lleve
    a la zona compartida donde el UR3e podra dibujar sobre ella.

    Secuencia de movimientos:
    1. Ir al HOME
    2. Ir al punto alto encima de la pieza (Z_APROX_UR5)
    3. Bajar por fuerza hasta tocar la pieza
    4. Activar ventosa
    5. Subir al punto alto
    6. Ir al HOME
    7. Ir al punto alto de la zona compartida
    8. Bajar por fuerza hasta depositar la pieza
    9. Desactivar ventosa
    10. Subir al punto alto de la zona compartida
    11. Ir al HOME
    12. Avisar al PC de que la pieza ya esta en la zona compartida
    """
    _, dz5 = obtener_drop_zones()
    dzx, dzy, dzz, drx_drop, dry_drop, drz_drop = [float(v) for v in dz5]
    xp, yp, rx_pick, ry_pick, rz_pick = _parametros_pick_ur5(x_pieza, y_pieza)

    modo_ventosa = _modo_ventosa_texto()

    L = [
        "def ur5e_recoger_baldosa():",
        '  textmsg("=== UR5e PARTE 1: recoger baldosa ===")',
        f'  textmsg("Ventosa: {modo_ventosa}")',
        "",
        f"  q_home = {_pose_to_urscript(UR5E_HOME_POSE)}",
        "",
        "  # Coordenadas de la pieza tal como vienen del JSON (ya en metros)",
        f"  x_pick = {xp:.5f}",
        f"  y_pick = {yp:.5f}",
        "",
        "  # Orientacion de la muneca para coger piezas (medida en tablet sobre la pieza real)",
        f"  rx_pick = {rx_pick:.5f}",
        f"  ry_pick = {ry_pick:.5f}",
        f"  rz_pick = {rz_pick:.5f}",
        "",
        "  # Orientacion propia de la zona compartida",
        f"  rx_drop = {drx_drop:.5f}",
        f"  ry_drop = {dry_drop:.5f}",
        f"  rz_drop = {drz_drop:.5f}",
        "",
        f'  textmsg("UR5e TARGET JSON x={xp:.5f}, y={yp:.5f}")',
        f'  textmsg("UR5e ORIENT PICK rx={rx_pick:.5f}, ry={ry_pick:.5f}, rz={rz_pick:.5f}")',
        f'  textmsg("Angulo vision ignorado={angulo_deg:.2f}")',
        "",
        "  # Paso 1: ir al HOME y luego al punto alto encima de la pieza",
    ]

    L.extend(_ir_home_ur5())

    L += [
        f"  movej({_pose_pick_ur5()}, a={A_RAPIDO}, v={V_APROX})",
        "  sleep(0.3)",
    ]

    # Paso 2: bajar hasta tocar la pieza y activar ventosa
    L.extend(_detectar_superficie_ur5("UR5e pieza original"))
    L.extend(_bloque_ventosa(True))

    L += [
        "",
        "  # Paso 3: subir por el mismo camino que hemos bajado",
        f"  movel({_pose_pick_ur5()}, a={A_LENTO}, v={V_APROX})",
        "  sleep(0.2)",
    ]

    L.extend(_ir_home_ur5())

    L += [
        "",
        "  # Paso 4: ir a la zona compartida y dejar la pieza",
        f"  movej({_pose_to_urscript(UR5E_DROP_APPROACH_POSE)}, a={A_RAPIDO}, v={V_TRASLADO})",
        "  sleep(0.3)",
    ]

    L.extend(_detectar_superficie_ur5("UR5e deposito DROP_ZONE"))
    L.extend(_bloque_ventosa(False))

    L += [
        "",
        "  # Paso 5: retirarse de la zona compartida y volver al HOME",
        f"  movel({_pose_to_urscript(UR5E_DROP_APPROACH_POSE)}, a={A_LENTO}, v={V_APROX})",
        "  sleep(0.2)",
    ]

    L.extend(_ir_home_ur5())

    L += [
        "",
        '  textmsg("UR5e: baldosa en DROP_ZONE. Avisando al PC")',
    ]

    L.extend(_socket_aviso_pc(PORT_UR5_LISTO_UR3, "UR5e", "sync_ur5_ur3"))

    L += [
        '  textmsg("UR5e PARTE 1 finalizada")',
        "end",
        "ur5e_recoger_baldosa()",
    ]

    return "\n".join(L)


def generar_script_ur3e_dibujar(trayectorias: List[Trayectoria]) -> str:
    """
    Genera el script URScript para que el UR3e dibuje sobre la baldosa.

    Las trayectorias vienen del modulo trajectory.py ya escaladas y centradas
    en (0,0). Aqui se suman a la posicion de la zona compartida (x0, y0)así, 
    el dibujo queda sobre la baldosa.

    Por cada trazo:
    1. El robot va al punto inicial del trazo a altura z_subida (sin tocar la baldosa)
    2. Baja a z_dibujo (tocando el papel)
    3. Recorre todos los puntos del trazo dibujando
    4. Sube a z_subida antes de pasar al siguiente trazo
    """
    # Filtramos trayectorias con menos de 2 puntos porque no se puede dibujar nada con ellas
    trayectorias = [t for t in trayectorias if len(t) >= 2]
    if not trayectorias:
        raise ValueError("No hay trayectorias validas para el UR3e.")

    dz3, _ = obtener_drop_zones()
    x0, y0, z0, rx, ry, rz = [float(v) for v in dz3]
    log.info(f"UR3e usara DROP_ZONE: {formatear_pose(dz3)}")

    L = [
        "def ur3e_dibujar_en_baldosa():",
        '  textmsg("=== UR3e: dibujo en baldosa ===")',
        f"  q_home = {_pose_to_urscript(UR3E_HOME_POSE)}",
        "  # Centro de la zona compartida, sobre el que se superpone el dibujo",
        f"  x0 = {x0:.5f}",
        f"  y0 = {y0:.5f}",
        f"  z0 = {z0:.5f}",
        f"  rx = {rx:.5f}",
        f"  ry = {ry:.5f}",
        f"  rz = {rz:.5f}",
        "",
        "  # Ir al HOME y luego al punto alto sobre la baldosa",
        "  movej(q_home, a={:.5f}, v={:.5f})".format(A_HOME, V_HOME),
        "  sleep(0.3)",
        f"  movej(p[x0, y0, z0+0.08000, rx, ry, rz], a={A_HOME}, v={V_HOME})",
        "  sleep(0.3)",
    ]

    # Detectar la superficie del papel una sola vez para todos los trazos
    L.extend(_detectar_superficie_ur3())

    total = len(trayectorias)
    L.append(f"  # === DIBUJO: {total} trazos en total ===")

    for idx, tray in enumerate(trayectorias):
        x_ini, y_ini = tray[0]
        x_fin, y_fin = tray[-1]

        L += [
            "",
            f"  # Trazo {idx + 1} de {total}",
            f'  textmsg("UR3e: trazo {idx + 1} de {total}")',
            # Ir al inicio del trazo a altura segura
            f"  movej({_pose_dibujo_ur3(x_ini, y_ini, f'z_dibujo+{Z_SUBIDA:.5f}')}, a={A_HOME}, v={V_SUBIDA})",
            # Bajar hasta el papel
            f"  movel({_pose_dibujo_ur3(x_ini, y_ini)}, a={A_DIBUJO}, v={V_DIBUJO})",
        ]

        # Recorrer el resto de puntos del trazo
        for x, y in tray[1:]:
            L.append(
                f"  movel({_pose_dibujo_ur3(x, y)}, a={A_DIBUJO}, v={V_DIBUJO}, r=0.001)"
            )

        # Levantar el lapiz al terminar el trazo
        L.append(
            f"  movel({_pose_dibujo_ur3(x_fin, y_fin, f'z_dibujo+{Z_SUBIDA:.5f}')}, a={A_HOME}, v={V_SUBIDA})"
        )

    L += [
        '  textmsg("UR3e: dibujo terminado. Volviendo a HOME")',
        f"  movej(q_home, a={A_HOME}, v={V_HOME})",
    ]

    L.extend(_socket_aviso_pc(PORT_UR3_LISTO_UR5, "UR3e", "sync_ur3_ur5"))

    L += [
        '  textmsg("UR3e finalizado")',
        "end",
        "ur3e_dibujar_en_baldosa()",
    ]

    return "\n".join(L)


def generar_script_ur5e_devolver(
    x_pieza: float,
    y_pieza: float
) -> str:
    """
    Genera el script URScript para que el UR5e recoja la baldosa de la zona
    compartida y la devuelva exactamente a donde estaba antes.

    Secuencia de movimientos (es la inversa del script de recogida):
    1. Ir al HOME
    2. Ir al punto alto de la zona compartida
    3. Bajar por fuerza hasta la baldosa
    4. Activar ventosa
    5. Subir al punto alto de la zona compartida
    6. Ir al HOME
    7. Ir al punto alto encima de la posicion original de la pieza
    8. Bajar por fuerza hasta depositar la pieza
    9. Desactivar ventosa
    10. Subir al punto alto
    11. Ir al HOME
    12. Avisar al PC de que la pieza ya esta en su sitio
    """
    _, dz5 = obtener_drop_zones()
    dzx, dzy, dzz, drx_drop, dry_drop, drz_drop = [float(v) for v in dz5]
    xp, yp, rx_pick, ry_pick, rz_pick = _parametros_pick_ur5(x_pieza, y_pieza)

    modo_ventosa = _modo_ventosa_texto()

    L = [
        "def ur5e_devolver_baldosa():",
        '  textmsg("=== UR5e PARTE 2: devolver baldosa ===")',
        f'  textmsg("Ventosa: {modo_ventosa}")',
        f"  q_home = {_pose_to_urscript(UR5E_HOME_POSE)}",
        f"  x_pick = {xp:.5f}",
        f"  y_pick = {yp:.5f}",
        f"  rx_pick = {rx_pick:.5f}",
        f"  ry_pick = {ry_pick:.5f}",
        f"  rz_pick = {rz_pick:.5f}",
        f"  rx_drop = {drx_drop:.5f}",
        f"  ry_drop = {dry_drop:.5f}",
        f"  rz_drop = {drz_drop:.5f}",
        "",
        "  # Paso 1: ir al HOME y luego a recoger la baldosa de la zona compartida",
    ]

    L.extend(_ir_home_ur5())

    L += [
        f"  movej({_pose_to_urscript(UR5E_DROP_APPROACH_POSE)}, a={A_RAPIDO}, v={V_APROX})",
        "  sleep(0.3)",
    ]

    L.extend(_detectar_superficie_ur5("UR5e recogida DROP_ZONE"))
    L.extend(_bloque_ventosa(True))

    L += [
        "",
        "  # Paso 2: subir y volver al HOME",
        f"  movel({_pose_to_urscript(UR5E_DROP_APPROACH_POSE)}, a={A_LENTO}, v={V_APROX})",
        "  sleep(0.2)",
    ]

    L.extend(_ir_home_ur5())

    L += [
        "",
        "  # Paso 3: ir a la posicion original de la pieza y depositarla",
        f'  textmsg("UR5e DEVOLVER TARGET JSON x={xp:.5f}, y={yp:.5f}")',
        f"  movej({_pose_pick_ur5()}, a={A_RAPIDO}, v={V_TRASLADO})",
        "  sleep(0.3)",
    ]

    L.extend(_detectar_superficie_ur5("UR5e deposito original"))
    L.extend(_bloque_ventosa(False))

    L += [
        "",
        "  # Paso 4: retirarse y volver al HOME",
        f"  movel({_pose_pick_ur5()}, a={A_LENTO}, v={V_APROX})",
        "  sleep(0.2)",
    ]

    L.extend(_ir_home_ur5())

    L += [
        "",
        '  textmsg("UR5e: baldosa devuelta. Avisando al PC")',
    ]

    L.extend(_socket_aviso_pc(PORT_UR5_LISTO_UR3, "UR5e DEVOLVER", "sync_ur5_devuelto"))

    L += [
        '  textmsg("UR5e PARTE 2 finalizada")',
        "end",
        "ur5e_devolver_baldosa()",
    ]

    return "\n".join(L)


def guardar_script(script: str, path: str) -> None:
    """Guarda el script en un archivo de texto para poder revisarlo antes de enviarlo."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(script)
    log.info(f"URScript guardado: {path}")
