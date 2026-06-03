# Sistema de Detección de Piezas Cerámicas para Robot

Este proyecto detecta automáticamente piezas de pavimento cerámico desde una imagen fotográfica, calcula su centro geométrico, dimensiones (ancho y alto) y ángulo de giro, y transforma todas las coordenadas al sistema de medidas del robot (milímetros). La cámara no está perfectamente perpendicular a la mesa de trabajo, por lo que el pipeline comienza con una **rectificación de perspectiva** que transforma la imagen a una vista cenital fiel antes de cualquier detección.

## ¿Qué hace?

- **Rectifica** la imagen original a vista cenital detectando automáticamente las 4 esquinas de la mesa.
- **Detecta** cada pieza cerámica visible mediante un pipeline de dos fases complementarias (contraste local + saturación).
- **Refina** los contornos eliminando sombras periféricas para ajustar el borde exacto del cerámico.
- **Deduplica** detecciones solapadas conservando la pieza visible superior.
- **Calcula** centro, ancho, alto y ángulo de rotación normalizado al rango **(-45°, 45°]**.
- **Calibra** la imagen usando dos cruces de referencia para pasar de píxeles a milímetros reales del robot.
- **Genera** archivos JSON estructurados listos para ser consumidos por un cobot, e imágenes anotadas opcionales para validación visual.

## Requisitos

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (gestor de paquetes recomendado)

## Dependencias

- `numpy >= 2.4.4`
- `opencv-python >= 4.13.0.92`

## Instalación

```bash
cd /workspaces/Container1/Robot
uv sync
```

> Si no usas `uv`, puedes instalar las dependencias manualmente con `pip install numpy opencv-python`.

## Uso

Ejecuta el orquestador principal:

```bash
python main.py
```

El programa procesará la imagen de entrada (`assets/imagenes/DSC07665.jpg`), mostrará el progreso por consola y guardará todos los resultados en la carpeta `resultados/`.

### Salida esperada

```
Imagen: assets/imagenes/DSC07665.jpg
Esquinas mesa detectadas: 4
Imagen rectificada: 4136x3102 px
Imagen recortada: 3309x2792 px

Piezas detectadas: 9

 N°        Centro (px)        Ancho     Alto     Ángulo
-------------------------------------------------------
  1  ( 1975,   890)        444px      458px      3.78°
  ...

Parámetros de calibración (similitud con reflexión Y):
  escala s = 0.292250 mm/px
  rotación θ = -84.97°
  traslación c = 401.23, f = 197.00

Piezas en coordenadas robot:
 N°   Robot X (mm)   Robot Y (mm)    Ancho      Alto     Ángulo
-----------------------------------------------------------------
  1       192.70        -400.76     129.8mm    133.9mm     1.25°
  ...

JSON detección guardado: resultados/deteccion.json
JSON robot guardado: resultados/datos_robot.json
```

---

## Estructura del proyecto

```
Robot/
├── main.py                           # Orquestador puro: rectifica, detecta, calibra, genera JSON
├── scripts/
│   ├── homografia.py                 # Detección automática de esquinas de mesa + rectificación perspectiva
│   ├── deteccion_piezas.py           # Lógica de detección de piezas (OpenCV)
│   ├── deteccion_referencias.py      # Lógica de detección de cruces de calibración (sobre imagen rectificada)
│   ├── calibracion.py                # Transformación de similitud píxeles → robot
│   └── visualizacion.py              # Dibujo de anotaciones (opcional, solo validación)
├── dev/                              # Código legacy (no usado en el pipeline actual)
├── assets/imagenes/DSC07665.jpg      # Imagen de entrada
├── resultados/                       # Archivos generados
│   ├── mesa_esquinas_detectadas.jpg  # Original con las 4 esquinas de la mesa marcadas (validación homografía)
│   ├── imagen_rectificada.jpg        # Imagen corregida a vista cenital, solo la mesa (validación)
│   ├── imagen1_resultado.jpg         # Imagen anotada en píxeles (validación)
│   ├── imagen1_resultado_robot.jpg   # Imagen anotada en coordenadas robot (validación)
│   ├── deteccion.json                # JSON de detección en píxeles (sobre imagen rectificada)
│   └── datos_robot.json              # JSON con coordenadas robot (mm) y ángulos
├── pyproject.toml                    # Dependencias
└── README.md                         # Este archivo
```

> **Separación lógica / visualización**: `homografia.py`, `deteccion_piezas.py`, `deteccion_referencias.py` y `calibracion.py` contienen únicamente la lógica de procesamiento. `visualizacion.py` es completamente opcional; `main.py` lo importa solo en la sección 4 (marcada explícitamente como opcional) para generar las imágenes de validación. El sistema produce los JSON correctamente aunque se elimine `visualizacion.py`.

---

## Cómo funciona el pipeline

El sistema está diseñado como un pipeline secuencial de 7 fases, orquestadas por `main.py`. Cada fase delega en un script especializado, manteniendo una separación clara entre lógica de procesamiento y visualización. A continuación se describe el flujo completo, paso a paso, exactamente como ocurre durante la ejecución.

---

### Paso 0 — Rectificación de perspectiva (`scripts/homografia.py`)

La cámara no está perfectamente perpendicular a la mesa de trabajo. Si se detectaran piezas directamente sobre la imagen original, las dimensiones estarían distorsionadas por la perspectiva (objetos más lejanos parecerían más pequeños y sus ángulos de rotación no serían fiables). Por ello, el primer paso obligatorio es **rectificar la imagen a una vista cenital**.

La mesa de trabajo mide **1200 mm de ancho × 900 mm de alto**. El objetivo de esta fase es obtener una imagen en la que la mesa ocupe todo el encuadre, con una escala uniforme en los ejes X e Y, de modo que objetos cuadrados reales se vean como cuadrados en píxeles.

#### Detección automática de las 4 esquinas

El algoritmo no requiere coordenadas manuales. Detecta automáticamente las esquinas de la mesa en la imagen original analizando los perfiles de brillo en ventanas locales:

1. **Esquinas derechas (superior e inferior)**: Están libres de obstáculos, por lo que el cambio brusco entre la mesa clara y el fondo oscuro es muy marcado. Se buscan en ROIs muy cercanas al borde derecho de la imagen.
2. **Esquinas izquierdas**: Están junto a otra mesa adyacente, por lo que la transición mesa→fondo es más sutil. La esquina inferior izquierda se detecta también por score de perfiles de brillo, aunque con ventanas más pequeñas. La esquina superior izquierda se estima geométricamente a partir de las otras tres (`sup_izq ≈ sup_der + inf_izq - inf_der`) y luego se refina localmente buscando el punto de máximo contraste en una ventana de búsqueda.

El criterio de detección de una esquina es maximizar la siguiente métrica de contraste local:

```
score = |mediana(derecha) - mediana(izquierda)| + |mediana(arriba) - mediana(abajo)|
```

Se explora una ROI candidata con paso grueso (3-5 píxeles) y luego se refina en una ventana local de 15-20 píxeles con paso 1. Las ventanas laterales deben ser lo suficientemente grandes para capturar la transición mesa-fondo, pero lo suficientemente pequeñas para no verse afectadas por objetos sobre la mesa.

#### Cálculo de la homografía

Una vez detectadas las 4 esquinas en la imagen original (ordenadas como `[sup-izq, sup-der, inf-der, inf-izq]`), se calcula la homografía que las mapea a un rectángulo de salida:

- El ancho en píxeles de salida (`W_out`) se calcula a partir de la resolución natural de la mesa en la imagen original: `max(anchos_superior, inferior)`.
- El alto (`H_out`) mantiene la proporción real de la mesa: `W_out * 900 / 1200`.
- Se aplica un ajuste conservador si la proporción natural detectada difiere mucho de 4:3 (más del 20 %), mezclando el valor teórico con el natural para robustez ante distorsiones leves.

Se utiliza `cv2.getPerspectiveTransform` para obtener la matriz de homografía 3×3, y `cv2.warpPerspective` para generar la imagen rectificada final. El resultado es una imagen donde **solo se ve la mesa**, con escala uniforme en ambos ejes.

**Salidas de esta fase**: `img_rect` (imagen rectificada), `M` (matriz de homografía) y `esquinas` (coordenadas en la imagen original).

**Validación independiente**: Puedes ejecutar `python scripts/homografia.py` de forma aislada. Esto dibujará las esquinas detectadas sobre la imagen original, guardará `resultados/mesa_esquinas_detectadas.jpg` e `imagen_rectificada.jpg`, y mostrará las coordenadas por consola.

---

### Paso 0b — Recorte de bordes (`main.py`, líneas 74-81)

La rectificación de perspectiva, especialmente cerca de los bordes de la mesa, puede introducir artefactos, zonas desenfocadas o pérdida de información por el muestreo de `warpPerspective`. Para evitar que estos artefactos confundan la detección de piezas, `main.py` recorta los márgenes de la imagen rectificada:

- **20 % a la izquierda**: Es el margen más amplio porque en ese lado suele haber más distorsión y además hay otra mesa adyacente que puede entrar en el encuadre.
- **5 % a la derecha, 5 % arriba y 5 % abajo**: Márgenes conservadores para eliminar solo los bordes degradados.

La detección de piezas se ejecuta sobre esta imagen recortada (`img_crop`), pero es importante entender que **las coordenadas finales se ajustan de vuelta al espacio de la imagen rectificada completa**. `main.py` suma los offsets `x0` e `y0` a todos los centros y contornos antes de guardar los JSON o calibrar. Esto garantiza que las coordenadas de las piezas y las referencias de calibración estén en el mismo sistema de coordenadas.

---

### Paso 1 — Detección de piezas (`scripts/deteccion_piezas.py`)

Este es el núcleo del sistema. El algoritmo debe detectar piezas de muy diferentes colores y texturas (grises, marrones, beige oscuro, beige muy claro) sobre un fondo de mesa clara. Una única técnica de umbralizado no es suficiente, porque una pieza beige muy clara tiene poco contraste local con el fondo, mientras que una pieza oscura tiene mucho. Por ello, se implementa un **pipeline de dos fases complementarias** que se ejecutan en paralelo sobre la misma imagen recortada, y cuyos resultados se fusionan posteriormente.

#### Fase 1 — Piezas con contraste local (grises, marrones, oscuras)

Esta fase captura piezas cuyo brillo difiere significativamente del fondo local de la mesa.

1. Se convierte la imagen a escala de grises.
2. Se aplica `cv2.adaptiveThreshold` con los siguientes parámetros:
   - `blockSize = 71`: Tamaño de la ventana local. Está calibrado para piezas de tamaño medio (~300-500 píxeles de lado). Ventanas más pequeñas capturarían ruido; ventanas más grandes perderían piezas pequeñas.
   - `C = 6`: Constante de sustracción. Un valor menor haría el umbral más sensible a bajo contraste (más falsos positivos); un valor mayor perdería piezas tenues.
   - `method = ADAPTIVE_THRESH_GAUSSIAN_C`: Pondera los píxeles cercanos al centro de la ventana, suavizando el efecto de texturas locales.
   - `type = THRESH_BINARY_INV`: Los objetos oscuros (menor brillo que el fondo local) se convierten a blanco (255).
3. Se aplica morfología matemática para limpiar:
   - `MORPH_OPEN` con kernel 5×5 (1 iteración): Elimina ruido puntual y pequeños artefactos.
   - `MORPH_CLOSE` con kernel 9×9 (2 iteraciones): Cierra pequeños huecos dentro de las piezas sin unir piezas adyacentes.
4. `cv2.findContours(RETR_EXTERNAL)` extrae los contornos externos de cada región blanca.
5. Se filtran por área del **convex hull**: solo se conservan contornos cuya envolvente convexa supere `AREA_MIN_HULL = 50 000 px²`. El convex hull es más robusto que el área del contorno real ante pequeñas roturas en el borde.

**Limitación**: Esta fase captura perfectamente piezas oscuras y de color medio, pero **puede perder piezas muy claras** (como una cerámica beige sobre fondo blanco) si su contraste local es demasiado bajo.

#### Fase 2 — Piezas con saturación/beige (watershed)

Para capturar la pieza beige y otros tonos claros que la Fase 1 pierde, se explota el hecho de que incluso las cerámicas aparentemente "blancas" o "beige" tienen algo de saturación de color, o textura que se traduce en variaciones de saturación en el espacio HSV.

1. Se convierte la imagen a HSV (Hue, Saturation, Value).
2. Se umbraliza el canal de saturación (`S > SATURATION_THRESHOLD = 8`). Esto convierte en blanco cualquier píxel con algo de color, por tenue que sea. La mesa blanca pura tiene saturación cercana a cero y queda en negro.
3. Morfología:
   - `MORPH_CLOSE` 9×9 (2 iteraciones): Une regiones fragmentadas de la misma pieza.
   - `MORPH_OPEN` 5×5 (1 iteración): Elimina ruido de fondo.
4. **Algoritmo Watershed**: Las piezas están físicamente separadas sobre la mesa, pero en la imagen pueden estar muy juntas o solapadas parcialmente, creando puentes blancos en la máscara de saturación. El watershed separa estas regiones:
   - `cv2.distanceTransform`: Calcula, para cada píxel blanco, su distancia al píxel negro más cercano. El centro de una pieza tendrá valores altos; los puentes con piezas adyacentes tendrán valores bajos.
   - Se generan semillas (`sure_fg`) umbralizando el distance transform al 25 % de su máximo. Cada región conectada de semillas se etiqueta con `cv2.connectedComponents`.
   - Se define el fondo seguro (`sure_bg`) dilatando la máscara original.
   - `cv2.watershed` expande las etiquetas desde las semillas hasta los bordes, forzando la separación en las zonas de mínimo distance transform (los puentes).
5. Para cada región etiquetada (excepto fondo y fronteras), se extraen contornos y se filtran por área > `AREA_MIN_HULL = 50 000 px²`.

**Nota**: El parámetro `frac=0.25` del watershed está ajustado empíricamente para esta imagen. Para piezas muy juntas puede ser necesario un valor mayor; para piezas muy separadas, uno menor.

#### Paso 3 — Refinado de contorno

Tanto la Fase 1 como la Fase 2 devuelven contornos que incluyen un **fleco de sombra** alrededor de cada pieza: la propia pieza proyecta una sombra suave sobre la mesa, y los algoritmos de umbral tienden a capturar parte de esa sombra como parte del objeto. Esto distorsiona las dimensiones calculadas (sobreestima ancho y alto) y desplaza ligeramente el centroide.

La función `_refinar_contorno_tile` elimina esta sombra periférica para cada contorno detectado:

1. **Identificación del núcleo interior**: Se dibuja el contorno en una máscara binaria local y se ejecuta `cv2.distanceTransform`. Los píxeles más alejados del borde (máxima distancia) están libres de sombra. Se selecciona el núcleo como aquellos píxeles cuya distancia sea mayor al `REFINE_CORE_FRAC = 40 %` del máximo.
2. **Color de referencia**: Se calcula la mediana del nivel de gris en ese núcleo. Esta mediana representa el color real de la superficie del tile, sin influencia de la sombra.
3. **Máscara ajustada**: Se genera una nueva máscara que solo incluye píxeles cuyo nivel de gris esté dentro de la tolerancia `[referencia ± REFINE_GRAY_TOL = 12]` del color de referencia. Esto descarta la sombra (más oscura) pero conserva la pieza completa.
4. **Morfología de limpieza**: Se aplica `CLOSE` + `OPEN` para cerrar pequeños huecos sin inflar artificialmente el área.
5. **Selección del contorno correcto**: El refinado puede generar múltiples contornos (por ejemplo, capturando también parte de una pieza adyacente si sus tonos son similares). Se selecciona únicamente el contorno cuyo centroide esté más cercano al centroide del contorno original, con un límite de `max_dist * 1.5`.
6. **Decisión final**: Si el contorno refinado tiene menor área que el original (la sombra se ha eliminado), se devuelve el refinado. Si no, se devuelve el original para evitar empeorar la detección.

Si el contorno original está muy fragmentado (área real < 50 % del convex hull), se usa el convex hull como base para el refinado, garantizando una forma cerrada.

#### Paso 4 — Deduplicación inteligente

Las dos fases de detección (contraste local + saturación) pueden detectar la misma pieza física dos veces, especialmente las piezas marrones que tienen tanto contraste de brillo como de saturación. La deduplicación elimina estas repeticiones sin perder piezas reales superpuestas.

El algoritmo funciona así:

1. Se ordenan todas las detecciones candidatas por **área ascendente**.
2. Para cada candidato, se compara con todos los candidatos ya aceptados.
3. Se consideran duplicados (y se descarta el actual) si se cumplen **las tres condiciones simultáneamente**:
   - **Distancia de centros** < `DEDUP_DIST_MAX = 60 px`.
   - **Diferencia de ángulo** < `DEDUP_ANGLE_MAX = 8°`.
   - **Diferencia de ancho** < `DEDUP_DIM_DIFF_MAX = 30 px` **Y** diferencia de alto < `30 px`.
4. Si son duplicados, se conserva la de **menor área**. Esto es importante en caso de superposición física: la pieza superior visible suele tener menor área proyectada que la inferior parcialmente oculta.

**Caso especial**: Si dos piezas están físicamente superpuestas en el mismo centro pero tienen **ángulos diferentes** (por ejemplo, una pieza encima de otra girada), NO se consideran duplicados y se mantienen ambas.

#### Paso 5 — Propiedades geométricas y filtrado

Para cada contorno único refinado, se calculan sus propiedades geométricas:

1. **`cv2.minAreaRect`**: Devuelve el rectángulo de área mínima que encierra el contorno, expresado como `(centro, (w, h), ángulo)`. Este ángulo es la orientación del lado más largo respecto al eje X horizontal.
2. **Normalización del ángulo**: OpenCV devuelve el ángulo en el rango `[-90, 0)`. El sistema lo normaliza a **(-45°, 45°]**:
   - Si `ángulo < -45°`, se suma 90° y se intercambian `w` y `h`.
   - Esto garantiza que `ancho = min(w, h)` (lado corto) y `alto = max(w, h)` (lado largo), y que el ángulo represente la rotación mínima desde la posición alineada.
3. **Filtros geométricos finales**:
   - **Rectangularidad**: `área_contorno / área_bounding_box >= RECT_RATIO_MIN = 0.65`. Descarta formas muy irregulares que no son piezas de pavimento.
   - **Área**: Debe estar entre `AREA_MIN_CONTOUR = 80 000` y `AREA_MAX = 2 500 000` px².
   - **Proporción**: `alto / ancho <= ALTO_ANCHO_RATIO_MAX = 2.0`. Descarta formas extremadamente alargadas (por ejemplo, reflejos, bordes de mesa mal detectados).

#### Paso 6 — Ordenamiento y numeración

Las piezas se numeran en orden de lectura natural: de **izquierda a derecha** y de **arriba a abajo**.

Para evitar que piezas ligeramente desalineadas verticalmente se mezclen en el ordenamiento, se usa una tolerancia de fila:

```python
tolerancia_fila = alto_imagen * FILA_TOLERANCIA_FACTOR  # 12 % de la altura total
```

La clave de ordenamiento es `(round(centro_y / tolerancia_fila), centro_x)`, lo que agrupa en filas aproximadas y luego ordena horizontalmente dentro de cada fila.

**Salida de esta fase**: Lista ordenada de diccionarios, cada uno con `numero`, `centro_x`, `centro_y`, `ancho`, `alto`, `angulo_grados`, y campos internos `_rect` (tupla de `minAreaRect`) y `_contour` (array NumPy del contorno refinado).

---

### Paso 2 — Detección de referencias (`scripts/deteccion_referencias.py`)

Para poder convertir píxeles a milímetros reales del robot, es necesario conocer la transformación geométrica entre ambos sistemas de coordenadas. Esta transformación se calcula a partir de **dos puntos de referencia** cuyas coordenadas son conocidas tanto en píxeles (detectadas automáticamente) como en milímetros del robot (valores fijos calibrados de antemano).

Las referencias son dos cruces oscuras en forma de "X" pintadas directamente sobre la mesa. Están siempre en la misma posición relativa a los bordes de la mesa, lo que permite definir sus zonas de búsqueda (ROIs) como **porcentajes del ancho y alto de la imagen rectificada**, en lugar de píxeles absolutos. Esto hace que el sistema sea robusto ante cambios de distancia de la cámara o resolución.

| Referencia | Posición relativa sobre la mesa | Coordenadas robot fijas (mm) |
|---|---|---|
| Ref 1 | ~20 % desde arriba, ~71 % desde la derecha (≈29 % desde la izquierda) | (263.93, -239.43) |
| Ref 2 | ~89 % desde arriba, ~22 % desde la derecha (≈78 % desde la izquierda) | (-363.60, -822.42) |

En coordenadas normalizadas (0–1) desde la esquina superior izquierda:
- Ref 1: aprox. `(0.29, 0.20)` → ROI de búsqueda: x ∈ [0.23, 0.35], y ∈ [0.14, 0.26]
- Ref 2: aprox. `(0.78, 0.89)` → ROI de búsqueda: x ∈ [0.72, 0.84], y ∈ [0.83, 0.95]

**Mecanismo de conversión**: En tiempo de ejecución, estos porcentajes se multiplican por el ancho (`W`) y alto (`H`) reales de la imagen rectificada: `x0 = int(W * x_min)`, `y0 = int(H * y_min)`, etc. Esto garantiza que los ROIs escalen correctamente.

#### Algoritmo de detección dentro de cada ROI

1. Se extrae la región de interés en escala de grises.
2. Se aplica umbral adaptativo con **Otsu** (`cv2.threshold(..., THRESH_BINARY_INV + THRESH_OTSU)`). Otsu es robusto ante cambios de iluminación porque calcula el umbral óptimo analizando el histograma local del ROI.
3. Se limpia con morfología OPEN 3×3 para eliminar ruido puntual.
4. `cv2.findContours` extrae los contornos externos.
5. Se selecciona el contorno cuyo centroide esté más cercano al centro del ROI (usando distancia Manhattan). Esto descarta ruido o manchas fuera de la cruz.
6. Si no se encuentra ningún contorno, o si Otsu devuelve un umbral de 0 (sin separación bimodal en el histograma), se emite un `warnings.warn` y se usa el **centro del ROI como fallback**.

**Salida de esta fase**: Diccionario `{"ref1": (x1, y1), "ref2": (x2, y2)}` con las coordenadas de los centros de las cruces en píxeles de la **imagen rectificada completa** (no recortada).

**Nota importante**: La detección de referencias se ejecuta sobre `img_rect` (la imagen rectificada sin recortar), mientras que la detección de piezas se ejecuta sobre `img_crop` (recortada). Sin embargo, como `main.py` ajusta las coordenadas de las piezas sumando los offsets del recorte, ambos sistemas de coordenadas son compatibles.

---

### Paso 3 — Calibración y transformación (`scripts/calibracion.py`)

Con las dos referencias detectadas (en píxeles) y sus coordenadas conocidas en el robot (en milímetros), se calcula una **transformación de similitud con reflexión en Y**.

#### Por qué reflexión en Y

- En el sistema de coordenadas de **OpenCV**, el origen está en la esquina superior izquierda, **X crece hacia la derecha** e **Y crece hacia abajo**.
- En el sistema de coordenadas del **robot**, **X también crece hacia la derecha**, pero **Y crece hacia arriba** (es un sistema de coordenadas cartesiano estándar visto desde arriba).

Por tanto, antes de aplicar la rotación y escala, es necesario **reflejar el eje Y**: `Y = -y`.

#### Modelo matemático

Tras reflejar Y, se aplica una similitud 2D (rotación `θ` + escala uniforme `s` + traslación `tx, ty`):

```
XR = s·cos(θ)·X − s·sin(θ)·Y + tx
YR = s·sin(θ)·X + s·cos(θ)·Y + ty
```

Sustituyendo `X = x` e `Y = -y`:

```
robot_x = a·px + b·py + c
robot_y = b·px − a·py + f
```

Donde:
- `a = s·cos(θ)`
- `b = s·sin(θ)`
- `s = √(a² + b²)` → escala en **mm/píxel**
- `θ = atan2(b, a)` → rotación de la cámara respecto al robot (en grados, tras compensar la reflexión en Y)
- `c, f` → componentes de traslación

La matriz afín 2×3 (compatible con `cv2.transform`) es:

```
| a   b   c |
| b  -a   f |
```

#### Cálculo de parámetros a partir de dos puntos

Con dos pares de puntos conocidos `(ref1_px ↔ ref1_robot)` y `(ref2_px ↔ ref2_robot)`, se resuelve el sistema lineal de 4 ecuaciones con 4 incógnitas (`a`, `b`, `c`, `f`).

Definiendo las diferencias:
- Imagen: `Δu = u₂ − u₁`, `Δv = v₂ − v₁`
- Robot: `Δx = x₂ − x₁`, `Δy = y₂ − y₁`

Las soluciones cerradas son:

```
b = (Δy·Δu + Δx·Δv) / (Δu² + Δv²)
a = (Δx − b·Δv) / Δu          (si Δu ≠ 0)
c = x₁ − a·u₁ − b·v₁
f = y₁ − b·u₁ + a·v₁
```

#### Conversión de puntos, dimensiones y ángulos

**Puntos**: Dado cualquier punto `(px, py)` en la imagen rectificada:
```
robot_x = a·px + b·py + c
robot_y = b·px − a·py + f
```

**Dimensiones**: Como la escala `s` es uniforme (misma para X e Y):
```
ancho_mm = ancho_px · s
alto_mm  = alto_px  · s
```

**Ángulo**: El ángulo de una pieza **no puede copiarse directamente** de píxeles a robot, porque depende del sistema de coordenadas. El procedimiento correcto es:
1. Obtener las 4 esquinas del `minAreaRect` en píxeles (`cv2.boxPoints`).
2. Convertir esas 4 esquinas al espacio del robot aplicando la matriz afín.
3. Ejecutar `cv2.minAreaRect` sobre las 4 esquinas transformadas.
4. Normalizar el resultado al rango **(-45°, 45°]**.

Así, el ángulo final está referido al eje X del robot y tiene en cuenta tanto la rotación física de la pieza como la orientación de la cámara respecto al robot.

**Salida de esta fase**: Diccionario de calibración con `M` (matriz afín 2×3), `s`, `theta_grados`, `a`, `b`, `c`, `f`.

---

### Paso 3 (continuación) — Serialización JSON (`main.py`)

Una vez calculadas todas las propiedades de las piezas y los parámetros de calibración, `main.py` guarda dos archivos JSON:

#### `resultados/deteccion.json`

Coordenadas en píxeles **sobre la imagen rectificada** (no sobre la original). Esto es útil para depuración y validación visual.

```json
{
  "imagen": "DSC07665.jpg",
  "total_piezas": 9,
  "piezas": [
    {
      "numero": 1,
      "centro_x": 1975,
      "centro_y": 890,
      "ancho": 444,
      "alto": 458,
      "angulo_grados": 3.78
    }
  ]
}
```

| Campo | Descripción |
|---|---|
| `numero` | Orden de lectura (1–N), izquierda→derecha, arriba→abajo |
| `centro_x`, `centro_y` | Coordenadas del centro en píxeles de la imagen rectificada |
| `ancho` | Lado corto de la pieza en píxeles |
| `alto` | Lado largo de la pieza en píxeles |
| `angulo_grados` | Ángulo de giro del lado corto respecto al eje X horizontal, ∈ (-45, 45] |

Este JSON es generado por la función `guardar_json()` dentro de `scripts/deteccion_piezas.py`, que se encarga de eliminar los campos internos privados (prefijados con `_`) antes de serializar.

#### `resultados/datos_robot.json`

Coordenadas transformadas al sistema del robot (mm), junto con los parámetros completos de calibración.

```json
{
  "imagen": "DSC07665.jpg",
  "total_piezas": 9,
  "piezas": [
    {
      "numero": 1,
      "robot_x": 192.70,
      "robot_y": -400.76,
      "ancho_mm": 129.76,
      "alto_mm": 133.85,
      "angulo_grados": 1.25
    }
  ],
  "calibracion": {
    "ref1_px": {"x": 1446.46, "y": 598.84},
    "ref1_robot": {"x": 263.93, "y": -239.43},
    "ref2_px": {"x": 3245.47, "y": 2912.61},
    "ref2_robot": {"x": -363.60, "y": -822.42},
    "escala_mm_px": 0.292250,
    "rotacion_grados": -84.97,
    "matriz_afin": {
      "m11": 0.025607,
      "m12": -0.291126,
      "m13": 401.23,
      "m21": -0.291126,
      "m22": -0.025607,
      "m23": 197.00
    }
  }
}
```

| Campo | Descripción |
|---|---|
| `robot_x`, `robot_y` | Centro de la pieza en coordenadas del robot (mm) |
| `ancho_mm`, `alto_mm` | Dimensiones reales de la pieza en mm |
| `angulo_grados` | Ángulo de giro del lado corto respecto al eje X del robot, ∈ (-45, 45] |
| `calibracion` | Parámetros de transformación de similitud píxeles→robot, incluyendo las referencias usadas, escala, rotación y matriz afín completa |

---

### Paso 4 — Visualización (opcional, `scripts/visualizacion.py`)

Este paso es **completamente opcional** y su único propósito es generar imágenes anotadas para validación visual por parte de un operador humano. Si se comenta o elimina todo este bloque en `main.py`, el sistema sigue generando los dos archivos JSON correctamente.

El módulo `visualizacion.py` proporciona dos funciones principales:

#### `dibujar_anotaciones(img, piezas, modo)`

Dibuja sobre una copia de la imagen rectificada, para cada pieza detectada, los siguientes elementos:

| Elemento | Color | Descripción |
|---|---|---|
| Contorno rotado | Verde | `cv2.boxPoints` del `minAreaRect` de la pieza |
| Centro | Rojo | Círculo relleno con las coordenadas `(cx, cy)` en texto blanco con sombra negra |
| Número | Amarillo | Identificador de la pieza en la esquina superior del bounding box |
| Línea ALTO | Naranja | Eje largo de la pieza, con su valor en px o mm |
| Línea ANCHO | Cian | Eje corto de la pieza, con su valor en px o mm |
| Ángulo | Lila | Valor numérico del ángulo en grados, junto al centro |

Los textos se renderizan con una **sombra negra** desplazada 1-2 píxeles para garantizar legibilidad sobre cualquier fondo (claro u oscuro). El tamaño de la fuente y el grosor de las líneas se escalan automáticamente según la resolución de la imagen.

Según el parámetro `modo`:
- `modo="camara"`: Muestra coordenadas en píxeles y dimensiones en px.
- `modo="robot"`: Muestra coordenadas en mm del robot y dimensiones en mm.

#### `dibujar_referencias(img, refs, label_coords)`

Dibuja las dos cruces de referencia detectadas:
- Un rectángulo que delimita el ROI de búsqueda (magenta para Ref1, cian para Ref2).
- Una cruz centrada en el punto detectado.
- Un círculo alrededor del punto.
- El label con las coordenadas (en px o en mm del robot, según `label_coords`).

**Imágenes generadas**:
- `resultados/imagen1_resultado.jpg`: Anotaciones en píxeles, sobre imagen rectificada.
- `resultados/imagen1_resultado_robot.jpg`: Anotaciones en milímetros del robot, sobre imagen rectificada.

---

## Configuración y ajuste de parámetros

Todas las constantes que controlan la sensibilidad de la detección están definidas al inicio de `scripts/deteccion_piezas.py`. Si cambias la iluminación, el tipo de pieza o la distancia de la cámara, probablemente necesites ajustar estos valores:

| Constante | Valor | Descripción |
|---|---|---|
| `ADAPTIVE_BLOCK_SIZE` | 71 | Tamaño del bloque del `adaptiveThreshold`. Debe ser impar y mayor que el tamaño de las piezas. |
| `ADAPTIVE_C` | 6 | Constante de sustracción del umbral adaptativo. Menor = más sensible a bajo contraste. |
| `SATURATION_THRESHOLD` | 8 | Umbral mínimo de saturación (HSV) para la fase de watershed. |
| `AREA_MIN_HULL` | 50 000 | Área mínima del convex hull para considerar un candidato válido tras las fases 1 y 2. |
| `AREA_MIN_CONTOUR` | 80 000 | Área mínima del contorno real tras el refinado de sombra. |
| `AREA_MAX` | 2 500 000 | Área máxima permitida (descarta la mesa entera si se detectara por error). |
| `RECT_RATIO_MIN` | 0.65 | Rectangularidad mínima (`área_contorno / área_bounding_box`). |
| `ALTO_ANCHO_RATIO_MAX` | 2.0 | Ratio máximo alto/ancho. Descarta formas extremadamente alargadas. |
| `REFINE_CORE_FRAC` | 0.40 | Fracción del distance transform máximo usada para definir el núcleo interior libre de sombra. |
| `REFINE_GRAY_TOL` | 12.0 | Tolerancia de nivel de gris en el refinado de contorno (±). |
| `DEDUP_DIST_MAX` | 60.0 | Distancia máxima entre centros para considerar dos detecciones como la misma pieza (px). |
| `DEDUP_ANGLE_MAX` | 8.0 | Diferencia máxima de ángulo para considerar duplicados (grados). |
| `DEDUP_DIM_DIFF_MAX` | 30 | Diferencia máxima de ancho y alto para considerar duplicados (px). |
| `FILA_TOLERANCIA_FACTOR` | 0.12 | Tolerancia de fila para el ordenamiento de lectura (12 % de la altura de la imagen). |

---

## Limitaciones conocidas

- **Umbral de saturación (`S > 8`)**: Captura piezas con muy poca saturación (como la beige), pero también puede incluir ruido del fondo si hay manchas o reflejos coloreados. En escenarios con iluminación cambiante puede necesitar ajuste.
- **Pieza beige**: Se detecta exclusivamente en la fase de saturación (Fase 2). Si el fondo tuviera una mancha de tonalidad similar con saturación > 8, podría generar un falso positivo.
- **Watershed (`frac=0.25`)**: El porcentaje del distance transform usado como semilla está ajustado empíricamente para esta imagen. Para piezas muy juntas puede ser necesario aumentarlo; para piezas muy separadas, disminuirlo.
- **AdaptiveThreshold (`blockSize=71`, `C=6`)**: Está calibrado para piezas de tamaño medio (~300-500 px de lado) sobre fondo claro. Piezas significativamente más pequeñas o más grandes pueden requerir ajustes de `blockSize`.
- **Rectificación de perspectiva**: Depende de que los bordes de la mesa sean detectables automáticamente por cambio de brillo. Si la iluminación cambia drásticamente o el fondo se confunde con el color de la mesa, la homografía podría fallar.
- **Detección de referencias (Otsu)**: Si el ROI contiene ruido que genera un histograma bimodal artificial, Otsu podría seleccionar un umbral subóptimo. En ese caso se emite un `warning` y se usa el centro del ROI como fallback.

---

## Notas técnicas

- No se requieren librerías de aprendizaje profundo; todo el procesamiento se realiza con OpenCV de forma determinista y totalmente reproducible.
- El entorno usa **uv** como gestor de paquetes. No se necesita scipy ni otras librerías adicionales.
- El código está estructurado para que la lógica pura (pasos 0-3) sea independiente de la visualización (paso 4). Esto facilita la integración en un sistema embebido o servidor donde no se necesita generar imágenes.
