# Willy 🤖

Scripts en Python para trastear con un robot aspirador Xiaomi **sin rootearlo**, solo con lo que expone por la red de casa (protocolo miIO/MIoT). Lo más vistoso: **cambiarle la voz** por paquetes generados con IA y alternar entre personalidades con un comando.

[![Ver el vídeo: original, héroe y borde](https://img.youtube.com/vi/E3TezcurB4U/hqdefault.jpg)](https://youtube.com/shorts/E3TezcurB4U)

*▶️ Mismo robot, tres voces: la original, Willy héroe y Willy borde.*

Probado con un **Xiaomi Robot Vacuum S12** (`xiaomi.vacuum.b106eu`, firmware 4.3.3_0016), que por dentro es de la familia **Ijai**. Con otros modelos, las ideas valen pero los números de servicio y el formato de voz pueden cambiar.

## Qué hay

| Script | Qué hace |
| --- | --- |
| `voz.py` | Instala un set de voz en el robot: lo sirve desde tu ordenador y le pide que se lo descargue |
| `voces.py` | Crea sets de voz: genera las frases con ElevenLabs y monta el paquete en formato Ijai |
| `repertorio.py` | La misma mini limpieza con cada voz (salir, pausa, volver), para grabar una comparación |
| `escaparate.py` | El robot dice todas las frases de un set sin moverse de la base |
| `paseo.py` | El «hola mundo»: sale de la base, da una vuelta y vuelve. Graba la ruta |
| `grabar.py` | Graba la ruta de una limpieza lanzada desde la app o el botón |
| `mapa.py` | Dibuja una ruta grabada como plano en HTML *(experimental)* |
| `willy.py` | Web local con el mapa, puntos con nombre y «ve al punto X» *(experimental, aún no funciona bien)* |
| `token-extractor/` | El [Xiaomi Cloud Tokens Extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor) en Docker, para sacar el token |

Sets de voz incluidos en `voces/`, listos para instalar sin cuenta de ElevenLabs:

| Set | Estilo | Ejemplo al empezar a limpiar |
| --- | --- | --- |
| `heroe` | Héroe de dibujos de rescate | «¡Willy al rescate! Empieza la misión de limpieza.» |
| `borde` | Sarcástico y un poco bruto | «¿Otra vez quieres que te limpie la mierda de la casa? Venga, vale…» |
| `andaluz` | Andaluz de pueblo | «Killo, mi arma, ¿otra vez a limpiar? Ozú, qué cruz.» |

## Puesta en marcha

Necesitas Python 3, `ffmpeg` (solo para crear sets) y Docker (solo para sacar el token).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`python-miio` se instala desde su repositorio: la versión publicada en PyPI no soporta el modo genérico MIoT que necesita este robot y falla con el `click` actual.

### 1. El token

El robot solo obedece si le hablas con su token, una clave de 32 caracteres que se crea al emparejarlo con Mi Home:

```bash
token-extractor/run.sh
```

Entra con tu cuenta de Xiaomi (usuario y contraseña, o escaneando el QR que aparece en `http://127.0.0.1:31415`) y copia la IP, el token, el modelo y el ID de tu robot en un `.env` a partir de `.env.example`.

> Ejecútalo en tu terminal: es interactivo y así la contraseña y el token no pasan por ningún otro sitio. El `.env` está en `.gitignore`.

### 2. Comprobar que responde

```bash
./paseo.py --estado
# [18:55:03] batería 100 %, estado 4 (cargando)
```

Si el router le cambia la IP, los scripts lo buscan solos por su ID y actualizan el `.env`.

## Voces

```bash
./voz.py borde        # instala un set
./voz.py heroe
./voz.py andaluz
./voz.py estado       # qué voz tiene
./repertorio.py       # original → héroe → borde → andaluz, con una mini limpieza cada una
./escaparate.py borde # todas las frases del set, sin moverse (unos 13 min)
```

Para volver a la voz de fábrica no hace falta paquete: `repertorio.py` lo hace pidiendo `en_US` con la URL vacía.

### Crear un set nuevo

1. Crea `voces/<nombre>/frases.json` con las 91 frases (copia uno existente: las claves son los nombres de archivo que espera el robot).
2. Opcional: `voces/<nombre>/voz.json` para cambiar voz, modelo o añadir un prefijo (`eleven_v3` admite etiquetas como `[acento andaluz]`).
3. Con `ELEVENLABS_API_KEY` en el entorno:

```bash
./voces.py coste <nombre>   # cuántos caracteres gastará
./voces.py crear <nombre>   # genera lo que falte y monta voces/<nombre>/<nombre>.zip
./voz.py <nombre>
```

El audio se guarda en caché por texto y voz: reutilizar frases o reconstruir un set no vuelve a gastar caracteres.

## Cómo funciona

El robot usa **MIoT**: cada función es un servicio (`siid`) con propiedades (`piid`) y acciones (`aiid`). `miiocli genericmiot --ip … --token … status` y `… actions` listan todo lo que expone. Lo que usan estos scripts en el S12:

| Qué | siid / id | Notas |
| --- | --- | --- |
| Estado | 2 / piid 1 | 4 = cargando, 3 = volviendo, 5 = modo punto |
| Aspirar sin fregar | 2 / aiid 3 | |
| Pausa | 2 / aiid 2 | |
| Volver a la base | 3 / aiid 1 | |
| Batería | 3 / piid 1 | |
| Buscar robot («aquí estoy») | 4 / piid 1 = `true` | reproduce `43sound_I_am_here.mp3` |
| Potencia de succión | 7 / piid 5 | 0 silencioso … 3 turbo |
| Ruta actual | 10 / aiid 12 | `[índice, x, y, ángulo, 0, …, timestamp]`, en metros |
| Descargar voz | 14 / aiid 1 | `target-voice`, `voice-url`, `voice-mdfive` |
| Estado de la voz | 14 / aiid 2 | |

**Formato del paquete de voz (Ijai):** un `.zip` plano con 91 mp3 con nombre (`11sound_global_clean_start.mp3`, `43sound_I_am_here.mp3`…) y un `md5.ini` con la huella de cada uno. El formato numerado de otros Xiaomi (`130.mp3`…) lo descarga pero lo ignora. La lista de frases de ambos formatos está en `docs/`.

## Estructura

```
voces/<set>/        frases.json, voz.json y el .zip listo para instalar
docs/               listas de frases de los formatos Ijai y Xiaomi numerado
diario/index.html   el diario del proceso, entrada a entrada (fallos incluidos)
token-extractor/    extractor de token en Docker (MIT, Piotr Machowski)
data/               local, fuera de git: rutas grabadas, puntos del mapa…
```

## Making of

Cómo llegué hasta aquí, paso a paso y con los fallos incluidos:
**[Le he cambiado la voz a mi robot aspirador (y ahora tiene tres personalidades)](https://ablancodev.com/desarrollo/le-he-cambiado-la-voz-a-mi-robot-aspirador/)**

El diario completo de la sesión está en [`diario/index.html`](diario/index.html).

## Créditos

- [python-miio](https://github.com/rytilahti/python-miio)
- [Xiaomi Cloud Tokens Extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor), de Piotr Machowski (incluido en `token-extractor/`, licencia MIT)
- [GLaDOS UKR](https://github.com/sverdlyuk/glados_ukr), que documenta el formato de los paquetes de voz de Xiaomi e Ijai
- Voces generadas con [ElevenLabs](https://elevenlabs.io)

## Licencia

[MIT](LICENSE). El extractor de `token-extractor/` mantiene su propia licencia MIT, de Piotr Machowski.

## Aviso

Proyecto personal para trastear. Usa las mismas órdenes que la app oficial y no toca el firmware, pero úsalo bajo tu responsabilidad. No está afiliado a Xiaomi.
