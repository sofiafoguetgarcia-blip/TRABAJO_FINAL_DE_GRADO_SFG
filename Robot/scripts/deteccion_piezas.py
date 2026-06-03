"""
Detección de piezas cerámicas rectangulares (solo lógica).

Algoritmo:
   1. adaptiveThreshold(71×71, C=6)  → captura piezas con contraste local.
   2. HSV S > 8 + watershed          → captura piezas con saturación/beige.
  3. Deduplicación inteligente: centro+ángulo+dimensiones similares → menor área.
  4. Normalización de ángulo y dimensiones con cv2.minAreaRect.
  5. Ordenamiento en lectura (arriba→abajo, izquierda→derecha).
  6. Exportación JSON.
"""

import json
import math
from pathlib import Path

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Constantes de detección
# ---------------------------------------------------------------------------

# ── adaptiveThreshold (Fase 1) ──
ADAPTIVE_BLOCK_SIZE = 71
ADAPTIVE_C = 6

# ── Saturación / watershed (Fase 2) ──
SATURATION_THRESHOLD = 8

# ── Área mínima para considerar un contorno como candidato ──
AREA_MIN_HULL = 50_000       # filtro de convex hull tras cada fase
AREA_MIN_CONTOUR = 80_000    # filtro de área real tras refinado

# ── Filtros geométricos finales ──
AREA_MAX = 2_500_000
RECT_RATIO_MIN = 0.65
ALTO_ANCHO_RATIO_MAX = 2.0   # descarta formas muy alargadas

# ── Deduplicación ──
DEDUP_DIST_MAX = 60.0        # px entre centros
DEDUP_ANGLE_MAX = 8.0        # grados
DEDUP_DIM_DIFF_MAX = 30      # px (ancho y alto)

# ── Ordenamiento ──
FILA_TOLERANCIA_FACTOR = 0.12

# ── Refinado de contorno ──
REFINE_CORE_FRAC = 0.40      # fracción del distance transform máximo
REFINE_GRAY_TOL = 12.0       # tolerancia en niveles de gris (±)


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def normalizar_rect(w_rect: float, h_rect: float, angle: float) -> tuple[float, float, float]:
    """
    Normaliza las dimensiones de minAreaRect para que:
      - ancho  = dimensión mínima (lado corto)
      - alto   = dimensión máxima (lado largo)
      - angulo ∈ (-45, 45] — ángulo de giro mínimo desde posición alineada

    Convención: angulo es el ángulo del lado CORTO (ancho) con el eje horizontal.
    El lado largo (alto) está a angulo + 90° del horizontal.
    """
    if angle < -45.0:
        angle += 90.0
        w_rect, h_rect = h_rect, w_rect
    ancho = min(w_rect, h_rect)
    alto = max(w_rect, h_rect)
    return ancho, alto, angle


# ---------------------------------------------------------------------------
# Refinado de contorno de tile
# ---------------------------------------------------------------------------

def _refinar_contorno_tile(cnt: np.ndarray,
                           gray: np.ndarray,
                           img_size: tuple[int, int]) -> np.ndarray:
    """
    Elimina el fleco de sombra del contorno de una pieza cerámica.

    Estrategia:
      1. Transformada de distancia dentro de la región → identifica el núcleo
         interior (lejos de cualquier borde), libre de sombra.
      2. Mediana del núcleo → color real de la superficie del tile.
      3. Máscara ajustada: solo píxeles con gray ∈ [mediana ± tolerancia].
      4. Morfología leve para cerrar pequeños huecos en la máscara ajustada.

    Si el contorno está muy roto (área mucho menor que su convex hull),
    se usa el convex hull como base para el refinado.

    Devuelve el contorno refinado (o el original si el refinado empeora).
    """
    h, w = img_size

    # Si el contorno está muy fragmentado, usar convex hull como base
    area_orig = cv2.contourArea(cnt)
    hull = cv2.convexHull(cnt)
    area_hull = cv2.contourArea(hull)
    if area_hull > 0 and area_orig < area_hull * 0.5:
        cnt = hull

    region_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.drawContours(region_mask, [cnt], -1, 255, cv2.FILLED)

    dist_local = cv2.distanceTransform(region_mask, cv2.DIST_L2, 5)
    max_dist = dist_local.max()
    if max_dist < 50:
        return cnt

    core_mask = (dist_local >= REFINE_CORE_FRAC * max_dist)
    core_vals = gray[core_mask]
    if len(core_vals) < 10:
        return cnt

    ref_color = float(np.median(core_vals))
    tight_mask = np.uint8(
        (region_mask > 0)
        & (gray.astype(np.float32) >= ref_color - REFINE_GRAY_TOL)
        & (gray.astype(np.float32) <= ref_color + REFINE_GRAY_TOL)
    ) * 255

    k = np.ones((9, 9), np.uint8)
    tight_mask = cv2.morphologyEx(tight_mask, cv2.MORPH_CLOSE, k, iterations=2)
    tight_mask = cv2.morphologyEx(tight_mask, cv2.MORPH_OPEN, k, iterations=1)

    cnts_r, _ = cv2.findContours(tight_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts_r:
        return cnt

    # Filtrar por centroide: solo considerar contornos cuyo centroide esté
    # dentro del contorno original, para evitar seleccionar regiones ajenas
    M_orig = cv2.moments(cnt)
    cx_orig = M_orig["m10"] / M_orig["m00"] if M_orig["m00"] != 0 else 0
    cy_orig = M_orig["m01"] / M_orig["m00"] if M_orig["m00"] != 0 else 0

    cnts_cercanos = []
    for c in cnts_r:
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]
        if math.hypot(cx - cx_orig, cy - cy_orig) < max_dist * 1.5:
            cnts_cercanos.append(c)

    if not cnts_cercanos:
        return cnt

    cnt_r = max(cnts_cercanos, key=cv2.contourArea)
    if cv2.contourArea(cnt_r) < cv2.contourArea(cnt):
        return cnt_r
    return cnt


# ---------------------------------------------------------------------------
# Deduplicación
# ---------------------------------------------------------------------------

def _deduplicar_candidatos(candidatos: list[dict]) -> list[dict]:
    """
    Elimina detecciones duplicadas de la misma pieza física.

    Criterio de duplicado:
      - Distancia entre centros < 60 px
      - Diferencia de ángulo < 8°
      - Diferencia de ancho < 30 px  Y  diferencia de alto < 30 px

    Si se cumplen las tres condiciones, se considera la misma pieza y se
    conserva la de MENOR área (prioridad al tile visible superior en
    caso de superposición).

    Si dos piezas están superpuestas pero con ángulos diferentes,
    NO se eliminan (mantienen ambas).
    """
    candidatos.sort(key=lambda x: x["area"])
    unicos: list[dict] = []

    for c in candidatos:
        es_dup = False
        for u in unicos:
            dist = math.hypot(c["centro_x"] - u["centro_x"], c["centro_y"] - u["centro_y"])
            if dist < DEDUP_DIST_MAX:
                diff_ang = abs(c["angulo_grados"] - u["angulo_grados"])
                diff_w = abs(c["ancho"] - u["ancho"])
                diff_h = abs(c["alto"] - u["alto"])
                if diff_ang < DEDUP_ANGLE_MAX and diff_w < DEDUP_DIM_DIFF_MAX and diff_h < DEDUP_DIM_DIFF_MAX:
                    es_dup = True
                    break
        if not es_dup:
            unicos.append(c)

    return unicos


# ---------------------------------------------------------------------------
# Detección
# ---------------------------------------------------------------------------

def detectar_piezas(img: np.ndarray) -> list[dict]:
    """
    Detecta piezas cerámicas rectangulares en la imagen.

    Args:
        img: imagen BGR en memoria (numpy array).

    Retorna lista ordenada (izquierda→derecha, arriba→abajo) con:
        numero, centro_x, centro_y, ancho, alto, angulo_grados
    """
    if img is None or len(img.shape) < 2:
        raise ValueError("Imagen no válida")

    h_img, w_img = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    contornos_totales: list[np.ndarray] = []

    # ── PASO 1: adaptiveThreshold para piezas con contraste local ───────────
    mask_adapt = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
        ADAPTIVE_BLOCK_SIZE, ADAPTIVE_C
    )
    mask_adapt = cv2.morphologyEx(mask_adapt, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8), iterations=1)
    mask_adapt = cv2.morphologyEx(mask_adapt, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)

    cnts_adapt, _ = cv2.findContours(mask_adapt, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts_adapt:
        if cv2.contourArea(cv2.convexHull(c)) > AREA_MIN_HULL:
            contornos_totales.append(c)

    # ── PASO 2: Saturación + watershed para piezas de color/beige ──────────
    mask_sat = (hsv[:, :, 1] > SATURATION_THRESHOLD).astype(np.uint8) * 255
    mask_sat = cv2.morphologyEx(mask_sat, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)
    mask_sat = cv2.morphologyEx(mask_sat, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8), iterations=1)

    dist = cv2.distanceTransform(mask_sat, cv2.DIST_L2, 5)
    if dist.max() > 0:
        _, sure_fg = cv2.threshold(dist, 0.25 * dist.max(), 255, 0)
    else:
        sure_fg = np.zeros_like(dist, dtype=np.uint8)
    sure_fg = np.uint8(sure_fg)

    num_lbl, lbl_map = cv2.connectedComponents(sure_fg)
    sure_bg = cv2.dilate(mask_sat, np.ones((11, 11), np.uint8), iterations=3)
    unknown = cv2.subtract(sure_bg, sure_fg)
    markers = lbl_map + 1
    markers[unknown == 255] = 0

    img_ws = img.copy()
    markers_ws = cv2.watershed(img_ws, markers)

    for lbl in range(2, int(markers_ws.max()) + 1):
        region_mask = np.uint8(markers_ws == lbl) * 255
        cnts, _ = cv2.findContours(region_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        cnt = max(cnts, key=cv2.contourArea)
        if cv2.contourArea(cnt) > AREA_MIN_HULL:
            contornos_totales.append(cnt)

    # ── PASO 3: Filtrar, refinar y extraer propiedades ─────────────────────
    candidatos = []

    for cnt in contornos_totales:
        area_c = cv2.contourArea(cnt)
        if area_c < AREA_MIN_CONTOUR:
            continue

        cnt = _refinar_contorno_tile(cnt, gray, (h_img, w_img))
        area_c = cv2.contourArea(cnt)
        if area_c < AREA_MIN_CONTOUR:
            continue

        rect = cv2.minAreaRect(cnt)
        (cx, cy), (w_rect, h_rect), angle = rect
        area_bbox = max(w_rect * h_rect, 1.0)
        rect_ratio = area_c / area_bbox

        if rect_ratio < RECT_RATIO_MIN:
            continue
        if area_c > AREA_MAX:
            continue

        ancho, alto, angulo = normalizar_rect(w_rect, h_rect, angle)

        if ancho > 0 and alto / ancho > ALTO_ANCHO_RATIO_MAX:
            continue

        candidatos.append({
            "centro_x": round(cx),
            "centro_y": round(cy),
            "ancho": round(ancho),
            "alto": round(alto),
            "angulo_grados": round(angulo, 2),
            "area": area_c,
            "_rect": rect,
            "_contour": cnt,
        })

    # ── PASO 4: Deduplicación inteligente ──────────────────────────────────
    candidatos = _deduplicar_candidatos(candidatos)

    # ── PASO 5: Ordenar en lectura (arriba→abajo, izquierda→derecha) ───────
    tolerancia_fila = h_img * FILA_TOLERANCIA_FACTOR
    candidatos.sort(key=lambda p: (
        round(p["centro_y"] / tolerancia_fila),
        p["centro_x"]
    ))

    for i, pieza in enumerate(candidatos, start=1):
        pieza["numero"] = i

    return candidatos


# ---------------------------------------------------------------------------
# Serialización JSON
# ---------------------------------------------------------------------------

def guardar_json(piezas: list[dict], ruta_imagen: Path, ruta_salida: Path) -> None:
    """Guarda el JSON con los datos de cada pieza (sin campos privados _xxx)."""
    campos = ["numero", "centro_x", "centro_y", "ancho", "alto", "angulo_grados"]
    datos = {
        "imagen": ruta_imagen.name,
        "total_piezas": len(piezas),
        "piezas": [{k: p[k] for k in campos} for p in piezas],
    }
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
