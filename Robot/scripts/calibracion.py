"""
Calibración: transformación de similitud con reflexión en Y
(imagen: x→der, y↓  →  robot: x→der, y↑).
"""

import math

import numpy as np


# Referencias: mm en sistema del robot
REF1_ROBOT = (263.93, -239.43)
REF2_ROBOT = (-363.60, -822.42)


def calcular_calibracion(
    ref1_px: tuple[float, float],
    ref1_robot: tuple[float, float],
    ref2_px: tuple[float, float],
    ref2_robot: tuple[float, float],
) -> dict:
    """
    Calcula la transformación de similitud con reflexión en Y.

    Modelo:
        xr = a·u + b·v + c
        yr = b·u − a·v + f

    Donde  s = √(a²+b²)  es la escala uniforme (mm/px) y θ = atan2(b,a)
    es la rotación del eje de la cámara respecto al robot (tras reflejar Y).
    """
    u1, v1 = ref1_px
    u2, v2 = ref2_px
    x1, y1 = ref1_robot
    x2, y2 = ref2_robot

    du = u2 - u1
    dv = v2 - v1
    dx = x2 - x1
    dy = y2 - y1

    denom = du * du + dv * dv
    b = (dy * du + dx * dv) / denom
    a = (dx - b * dv) / du if du != 0 else 0.0

    c = x1 - a * u1 - b * v1
    f = y1 - b * u1 + a * v1

    s = math.hypot(a, b)
    theta = math.degrees(math.atan2(b, a))

    # Matriz afin 2×3 para cv2.transform
    M = np.array([[a, b, c],
                  [b, -a, f]], dtype=np.float64)

    return {
        "M": M,
        "s": s,
        "theta_grados": round(theta, 2),
        "a": a,
        "b": b,
        "c": c,
        "f": f,
    }


def pixel_a_robot(
    px: float,
    py: float,
    cal: dict,
) -> tuple[float, float]:
    """Convierte coordenadas píxeles a coordenadas robot (mm)."""
    M = cal["M"]
    rx = M[0, 0] * px + M[0, 1] * py + M[0, 2]
    ry = M[1, 0] * px + M[1, 1] * py + M[1, 2]
    return rx, ry
