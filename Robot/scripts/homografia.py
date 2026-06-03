"""
Detección automática de esquinas de mesa y rectificación de perspectiva.

Algoritmo:
  1. Detectar las 4 esquinas de la mesa mediante análisis de perfiles de color
     en ROIs relativas a los bordes de la imagen.
  2. Las esquinas derechas (libres) se detectan primero por cambio brusco
     mesa → fondo. Las izquierdas siguen la misma lógica en sus ROIs.
  3. Homografía 4:3 (1200:900) → vista cenital de solo la mesa.

Validación independiente: python scripts/homografia.py
"""

from pathlib import Path

import cv2
import numpy as np


BASE_DIR = Path(__file__).resolve().parent.parent
IMAGEN_ENTRADA = BASE_DIR / "assets" / "imagenes" / "DSC07665.jpg"
DIR_RESULTADOS = BASE_DIR / "resultados"


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _ordenar_esquinas(pts: np.ndarray) -> np.ndarray:
    """
    Ordena 4 puntos a: [sup-izq, sup-der, inf-der, inf-izq].
    """
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).flatten()

    sup_izq = pts[np.argmin(s)]
    inf_der = pts[np.argmax(s)]
    sup_der = pts[np.argmin(diff)]
    inf_izq = pts[np.argmax(diff)]

    return np.array([sup_izq, sup_der, inf_der, inf_izq], dtype=np.float32)


def _esquina_por_score(
    gray: np.ndarray,
    x_min: int,
    x_max: int,
    y_min: int,
    y_max: int,
    win_side: int = 100,
    win_perp: int = 20,
    paso: int = 3,
    refinado: int = 15,
) -> tuple[float, float]:
    """
    Busca una esquina dentro de un ROI como el punto que maximiza:
        score = |mediana(derecha) - mediana(izquierda)|
              + |mediana(arriba)   - mediana(abajo)|

    Las ventanas laterales (derecha/izquierda/arriba/abajo) deben tener
    tamaño suficiente (> 0). El punto debe mantenerse lejos de los bordes
    de la imagen para que todas las ventanas quepan.
    """
    h, w = gray.shape
    best_score = -1.0
    best = (float(x_min + x_max) / 2, float(y_min + y_max) / 2)

    for x in range(x_min, x_max, paso):
        for y in range(y_min, y_max, paso):
            if (x - win_side < 0 or x + win_side >= w or
                    y - win_side < 0 or y + win_side >= h):
                continue

            der = gray[y - win_perp:y + win_perp, x + win_perp:x + win_side]
            izq = gray[y - win_perp:y + win_perp, x - win_side:x - win_perp]
            arr = gray[y - win_side:y - win_perp, x - win_perp:x + win_perp]
            aba = gray[y + win_perp:y + win_side, x - win_perp:x + win_perp]

            if (der.size == 0 or izq.size == 0 or
                    arr.size == 0 or aba.size == 0):
                continue

            score = (
                abs(float(np.median(der)) - float(np.median(izq))) +
                abs(float(np.median(arr)) - float(np.median(aba)))
            )
            if score > best_score:
                best_score = score
                best = (float(x), float(y))

    # Refinado local paso 1 px
    cx, cy = int(round(best[0])), int(round(best[1]))
    best_score = -1.0
    best_ref = best
    for x in range(cx - refinado, cx + refinado + 1):
        for y in range(cy - refinado, cy + refinado + 1):
            if (x - win_side < 0 or x + win_side >= w or
                    y - win_side < 0 or y + win_side >= h):
                continue

            der = gray[y - win_perp:y + win_perp, x + win_perp:x + win_side]
            izq = gray[y - win_perp:y + win_perp, x - win_side:x - win_perp]
            arr = gray[y - win_side:y - win_perp, x - win_perp:x + win_perp]
            aba = gray[y + win_perp:y + win_side, x - win_perp:x + win_perp]

            if (der.size == 0 or izq.size == 0 or
                    arr.size == 0 or aba.size == 0):
                continue

            score = (
                abs(float(np.median(der)) - float(np.median(izq))) +
                abs(float(np.median(arr)) - float(np.median(aba)))
            )
            if score > best_score:
                best_score = score
                best_ref = (float(x), float(y))

    return best_ref


# ---------------------------------------------------------------------------
# Detección de esquinas de la mesa
# ---------------------------------------------------------------------------

def detectar_esquinas_mesa(img: np.ndarray) -> np.ndarray:
    """
    Detecta automáticamente las 4 esquinas de la mesa en la imagen original.

    Retorna array (4, 2) float32 ordenado [sup-izq, sup-der, inf-der, inf-izq].
    """
    h_img, w_img = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # ROIs definidas como porcentaje para escalar con distancia de cámara.
    # Las esquinas DERECHAS están libres → ROIs muy cercanas al borde derecho.
    # Las esquinas IZQUIERDAS están junto a otra mesa → ROIs más amplias.
    margin = 120

    # ── Esquinas derechas (libres, borde mesa → fondo) ──
    inf_der = _esquina_por_score(
        gray,
        x_min=max(margin, int(w_img * 0.88)),
        x_max=w_img - margin,
        y_min=max(margin, int(h_img * 0.82)),
        y_max=h_img - margin,
        win_side=100,
        win_perp=15,
        paso=5,
        refinado=20,
    )

    sup_der = _esquina_por_score(
        gray,
        x_min=max(margin, int(w_img * 0.85)),
        x_max=w_img - margin,
        y_min=margin,
        y_max=min(h_img - margin, int(h_img * 0.12)),
        win_side=100,
        win_perp=15,
        paso=5,
        refinado=20,
    )

    # ── Esquina izquierda inferior (score de perfiles) ──
    inf_izq = _esquina_por_score(
        gray,
        x_min=margin,
        x_max=min(int(w_img * 0.15), w_img - margin),
        y_min=max(margin, int(h_img * 0.85)),
        y_max=h_img - margin,
        win_side=80,
        win_perp=15,
        paso=3,
        refinado=20,
    )

    # ── Esquina izquierda superior ──
    # El score de perfiles falla aquí porque la transición mesa→fondo es muy sutil
    # y hay otra mesa adyacente. Usamos estimación geométrica + refinado local.
    sup_izq_est = (
        float(sup_der[0] + inf_izq[0] - inf_der[0]),
        float(sup_der[1] + inf_izq[1] - inf_der[1]),
    )
    sup_izq = _refinar_esquina_local(
        gray,
        int(round(sup_izq_est[0])),
        int(round(sup_izq_est[1])),
        ventana=60,
        win_side=80,
        win_perp=15,
    )

    esquinas = np.array([sup_izq, sup_der, inf_der, inf_izq], dtype=np.float32)
    return _ordenar_esquinas(esquinas)


def _refinar_esquina_local(
    gray: np.ndarray,
    cx: int,
    cy: int,
    ventana: int = 50,
    win_side: int = 80,
    win_perp: int = 15,
) -> tuple[float, float]:
    """
    Refina una esquina buscando el máximo score de perfiles en una ventana
    local alrededor de (cx, cy).
    """
    h, w = gray.shape
    best_score = -1.0
    best = (float(cx), float(cy))

    for x in range(cx - ventana, cx + ventana + 1):
        for y in range(cy - ventana, cy + ventana + 1):
            if (x - win_side < 0 or x + win_side >= w or
                    y - win_side < 0 or y + win_side >= h):
                continue

            der = gray[y - win_perp:y + win_perp, x + win_perp:x + win_side]
            izq = gray[y - win_perp:y + win_perp, x - win_side:x - win_perp]
            arr = gray[y - win_side:y - win_perp, x - win_perp:x + win_perp]
            aba = gray[y + win_perp:y + win_side, x - win_perp:x + win_perp]

            if (der.size == 0 or izq.size == 0 or
                    arr.size == 0 or aba.size == 0):
                continue

            score = (
                abs(float(np.median(der)) - float(np.median(izq))) +
                abs(float(np.median(arr)) - float(np.median(aba)))
            )
            if score > best_score:
                best_score = score
                best = (float(x), float(y))

    return best


# ---------------------------------------------------------------------------
# Rectificación de perspectiva
# ---------------------------------------------------------------------------

def rectificar_imagen(
    img: np.ndarray,
    mm_ancho: float = 1200.0,
    mm_alto: float = 900.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Rectifica la imagen original a vista cenital de solo la mesa.

    Args:
        img: imagen BGR original.
        mm_ancho, mm_alto: dimensiones reales de la mesa en mm (por defecto 1200×900).

    Returns:
        (img_rect, M, esquinas_orig)
        - img_rect: imagen BGR rectificada, solo la mesa.
        - M: matriz de homografía 3×3.
        - esquinas_orig: las 4 esquinas detectadas en la imagen original.
    """
    esquinas_orig = detectar_esquinas_mesa(img)

    sup_izq, sup_der, inf_der, inf_izq = esquinas_orig

    w1 = np.linalg.norm(sup_der - sup_izq)
    w2 = np.linalg.norm(inf_der - inf_izq)
    h1 = np.linalg.norm(inf_izq - sup_izq)
    h2 = np.linalg.norm(inf_der - sup_der)

    W_natural = max(w1, w2)
    H_natural = max(h1, h2)

    W_out = int(round(W_natural))
    H_out = int(round(W_out * mm_alto / mm_ancho))

    if H_natural > 0 and abs(H_out - H_natural) / H_natural > 0.20:
        H_out = int(round(0.7 * H_out + 0.3 * H_natural))

    dst = np.float32([
        [0, 0],
        [W_out - 1, 0],
        [W_out - 1, H_out - 1],
        [0, H_out - 1],
    ])

    M = cv2.getPerspectiveTransform(esquinas_orig, dst)
    img_rect = cv2.warpPerspective(img, M, (W_out, H_out))

    return img_rect, M, esquinas_orig


# ---------------------------------------------------------------------------
# Validación independiente
# ---------------------------------------------------------------------------

def main() -> None:
    DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)

    img = cv2.imread(str(IMAGEN_ENTRADA))
    if img is None:
        raise FileNotFoundError(f"No se pudo cargar la imagen: {IMAGEN_ENTRADA}")

    print(f"Imagen cargada: {img.shape[1]}x{img.shape[0]} px")

    img_rect, M, esquinas = rectificar_imagen(img)
    print(f"Esquinas mesa detectadas: {len(esquinas)}")
    for i, (x, y) in enumerate(esquinas, start=1):
        print(f"  Esquina {i}: ({x:.2f}, {y:.2f})")
    print(f"Imagen rectificada: {img_rect.shape[1]}x{img_rect.shape[0]} px")

    # Dibujar esquinas sobre imagen original
    img_debug = img.copy()
    pts = np.int32(esquinas.reshape(-1, 1, 2))
    cv2.drawContours(img_debug, [pts], 0, (0, 220, 0), 3)

    colores = [(0, 0, 255), (0, 140, 255), (255, 0, 0), (0, 255, 0)]
    nombres = ["sup-izq", "sup-der", "inf-der", "inf-izq"]
    for i, ((x, y), color, nombre) in enumerate(zip(esquinas, colores, nombres)):
        ix, iy = int(round(x)), int(round(y))
        cv2.circle(img_debug, (ix, iy), 12, color, -1)
        cv2.circle(img_debug, (ix, iy), 14, (255, 255, 255), 2)
        cv2.putText(img_debug, f"{i+1}:{nombre}", (ix + 18, iy - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 2, cv2.LINE_AA)

    ruta_debug = DIR_RESULTADOS / "mesa_esquinas_detectadas.jpg"
    cv2.imwrite(str(ruta_debug), img_debug)
    print(f"Guardado: {ruta_debug}")

    ruta_rect = DIR_RESULTADOS / "imagen_rectificada.jpg"
    cv2.imwrite(str(ruta_rect), img_rect)
    print(f"Guardado: {ruta_rect}")


if __name__ == "__main__":
    main()
