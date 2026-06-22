# -*- coding: utf-8 -*-
"""
transform.py
============
Funciones para convertir coordenadas entre los dos robots.

El UR5e y el UR3e estan en mesas distintas y se miran de frente.
Esto significa que el mismo punto fisico del espacio tiene coordenadas
distintas segun cual de los dos robots lo mida. Por ejemplo, lo que
para el UR5e esta "a la derecha" para el UR3e esta "a la izquierda".

Para hacer la conversion se usa la zona compartida (DROP_ZONE) como
punto de referencia comun, ya que ambos robots conocen su posicion
respecto a ella.
"""

from __future__ import annotations
from typing import Iterable, List, Tuple

from config import DROP_ZONE_UR5E, DROP_ZONE_UR3E


# robots enfrentados, el eje X se mantiene igual
# pero el eje Y hay que invertirlo.
AXIS_SIGN_X = 1.0
AXIS_SIGN_Y = -1.0

# La Z no se transforma: cada robot detecta la superficie por fuerza
COPY_Z_OFFSET = False


def _validar_pose(pose: Iterable[float], nombre: str) -> List[float]:
    """Comprueba que la pose tiene 6 valores [x, y, z, rx, ry, rz]."""
    p = [float(v) for v in pose]
    if len(p) != 6:
        raise ValueError(f"{nombre} debe tener 6 valores: [x, y, z, rx, ry, rz]")
    return p


def formatear_pose(pose: Iterable[float]) -> str:
    """Devuelve la pose como cadena legible, util para los logs."""
    return "[" + ", ".join(f"{float(v):.5f}" for v in pose) + "]"


def obtener_drop_zones() -> Tuple[List[float], List[float]]:
    """
    Devuelve las poses de la zona compartida tal como la ve cada robot.
    Orden de retorno: (drop_zone_ur3e, drop_zone_ur5e)
    """
    return list(DROP_ZONE_UR3E), list(DROP_ZONE_UR5E)


def convertir_pose(pose: Iterable[float], desde: str, hacia: str) -> List[float]:
    """
    Convierte una pose de las coordenadas de un robot a las del otro.

    El metodo calcula el desplazamiento de la pose respecto a la zona
    compartida en el robot de origen, y aplica ese mismo desplazamiento
    (con los signos de eje correctos) en el robot de destino.

    Como se ha dicho, es una aproximacion valida para la demostracion.
    """
    desde = desde.lower().strip()
    hacia = hacia.lower().strip()

    if desde not in ("ur3e", "ur5e"):
        raise ValueError("desde debe ser 'ur3e' o 'ur5e'")
    if hacia not in ("ur3e", "ur5e"):
        raise ValueError("hacia debe ser 'ur3e' o 'ur5e'")

    p = _validar_pose(pose, f"pose_{desde}")

    # Si origen y destino son el mismo robot, no hay nada que convertir
    if desde == hacia:
        return p

    # Elegimos el punto de referencia segun la direccion de la conversion
    if desde == "ur5e" and hacia == "ur3e":
        ref_from = DROP_ZONE_UR5E
        ref_to = DROP_ZONE_UR3E
    else:
        ref_from = DROP_ZONE_UR3E
        ref_to = DROP_ZONE_UR5E

    # Calculamos cuanto se aleja la pose del punto de referencia en origen
    dx = p[0] - ref_from[0]
    dy = p[1] - ref_from[1]
    dz = p[2] - ref_from[2]

    # Aplicamos ese desplazamiento en destino, invirtiendo Y porque los
    # robots estan enfrentados
    x = ref_to[0] + AXIS_SIGN_X * dx
    y = ref_to[1] + AXIS_SIGN_Y * dy

    # La Z viene de la zona de destino porque cada robot mide la suya
    if COPY_Z_OFFSET:
        z = ref_to[2] + dz
    else:
        z = ref_to[2]

    # La orientacion de destino tambien viene de la zona de referencia de destino
    rx = ref_to[3]
    ry = ref_to[4]
    rz = ref_to[5]

    return [x, y, z, rx, ry, rz]


def pose_pieza_en_ur3e(pose_pieza_ur5e: Iterable[float]) -> List[float]:
    """Para convertir una pose del UR5e al sistema de coordenadas del UR3e."""
    return convertir_pose(pose_pieza_ur5e, desde="ur5e", hacia="ur3e")


def pose_pieza_en_ur5e(pose_pieza_ur3e: Iterable[float]) -> List[float]:
    """Para convertir una pose del UR3e al sistema de coordenadas del UR5e."""
    return convertir_pose(pose_pieza_ur3e, desde="ur3e", hacia="ur5e")


