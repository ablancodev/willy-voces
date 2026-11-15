#!/usr/bin/env python3
"""Dibuja la ruta grabada por paseo.py como un plano en SVG/HTML.

Uso:  ./mapa.py                    (último paseo de data/rutas/)
      ./mapa.py data/rutas/paseo-XXXX.jsonl

Genera data/rutas/<paseo>.html: la ruta en rojo y, debajo, el "suelo pisado"
(cada punto como un círculo del tamaño del robot).
"""
import json
import math
import sys
from pathlib import Path

ROBOT_DIAMETER = 0.35  # metros
SCALE = 120            # px por metro
MARGIN = 0.5           # metros alrededor


def load_segments(path):
    """Junta los puntos por su índice absoluto y devuelve tramos continuos [(x, y, ang), ...].

    Cada respuesta de get-cur-path es [índice del primer punto, x, y, ang, flag, ..., timestamp].
    El índice permite unir respuestas solapadas; donde faltan índices se corta el tramo.
    """
    by_index = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if "error" in row:
            continue
        v = json.loads(row["res"]["out"][0]["value"])
        if len(v) < 5:          # solo marca de tiempo
            continue
        first, pts = v[0], v[1:-1]
        for i in range(0, len(pts) - 3, 4):
            by_index[first + i // 4] = (pts[i], pts[i + 1], pts[i + 2])
    segments, current, prev = {}, [], None
    for idx in sorted(by_index):
        if prev is not None and idx != prev + 1:
            segments[(len(segments) + 1, 1)] = current
            current = []
        current.append(by_index[idx])
        prev = idx
    if current:
        segments[(len(segments) + 1, 1)] = current
    return segments


def render(path):
    segments = load_segments(path)
    all_pts = [p for pts in segments.values() for p in pts] or [(0, 0, 0)]
    xs = [p[0] for p in all_pts] + [0]
    ys = [p[1] for p in all_pts] + [0]
    x0, x1 = min(xs) - MARGIN, max(xs) + MARGIN
    y0, y1 = min(ys) - MARGIN, max(ys) + MARGIN
    w, h = (x1 - x0) * SCALE, (y1 - y0) * SCALE

    def px(x, y):  # y hacia arriba en el mundo, hacia abajo en SVG
        return (x - x0) * SCALE, (y1 - y) * SCALE

    r = ROBOT_DIAMETER / 2 * SCALE
    floor, routes = [], []
    colors = {1: "#e8590c", 2: "#1c64b8"}
    for (n, kind), pts in segments.items():
        coords = [px(x, y) for x, y, _ in pts]
        floor += [f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}"/>' for cx, cy in coords]
        line = " ".join(f"{cx:.1f},{cy:.1f}" for cx, cy in coords)
        routes.append(f'<polyline points="{line}" fill="none" stroke="{colors.get(kind, "#555")}" '
                      f'stroke-width="2" stroke-linejoin="round"/>')
        if coords:
            (cx, cy), ang = coords[-1], pts[-1][2]
            dx, dy = math.cos(ang) * 14, -math.sin(ang) * 14
            routes.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx + dx:.1f}" y2="{cy + dy:.1f}" '
                          f'stroke="{colors.get(kind, "#555")}" stroke-width="3"/>')

    # rejilla de 1 m
    grid = []
    for gx in range(math.ceil(x0), math.floor(x1) + 1):
        a, _ = px(gx, 0)
        grid.append(f'<line x1="{a:.1f}" y1="0" x2="{a:.1f}" y2="{h:.1f}"/>')
    for gy in range(math.ceil(y0), math.floor(y1) + 1):
        _, b = px(0, gy)
        grid.append(f'<line x1="0" y1="{b:.1f}" x2="{w:.1f}" y2="{b:.1f}"/>')

    bx, by = px(0, 0)
    n_pts = len(all_pts) if segments else 0
    span = f"{max(xs) - min(xs):.2f} × {max(ys) - min(ys):.2f} m"
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapa de ruta</title>
<style>
:root {{ --bg:#faf8f5; --fg:#1d1b18; --muted:#6b665e; --floor:#d9d2c5; --grid:#e8e3da; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#161513; --fg:#ece8e1; --muted:#9a948a; --floor:#3a352e; --grid:#262420; }} }}
body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--fg);
  font:15px/1.5 -apple-system, BlinkMacSystemFont, sans-serif; }}
h1 {{ font-size:1.3rem; margin:0 0 4px; }} p {{ color:var(--muted); margin:0 0 16px; }}
svg {{ max-width:100%; height:auto; border:1px solid var(--grid); border-radius:8px; }}
.grid line {{ stroke:var(--grid); }} .floor circle {{ fill:var(--floor); }}
.k {{ display:inline-block; width:12px; height:3px; vertical-align:middle; margin:0 4px 0 12px; }}
</style></head><body>
<h1>Mapa de ruta: {path.stem}</h1>
<p>{n_pts} puntos en {len(segments)} tramos · extensión {span} · cuadrícula de 1 m ·
<span class="k" style="background:#e8590c"></span>limpiando
<span class="k" style="background:#1c64b8"></span>saliendo/volviendo · ■ base (0,0)</p>
<svg viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}" xmlns="http://www.w3.org/2000/svg">
<g class="grid">{''.join(grid)}</g>
<g class="floor">{''.join(floor)}</g>
{''.join(routes)}
<rect x="{bx - 8:.1f}" y="{by - 8:.1f}" width="16" height="16" fill="var(--fg)"/>
</svg></body></html>"""
    out = path.with_suffix(".html")
    out.write_text(html)
    return out, n_pts, len(segments), span


if __name__ == "__main__":
    data = Path(__file__).parent / "data" / "rutas"
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else max(data.glob("paseo-*.jsonl"))
    out, n, segs, span = render(src)
    print(f"{out}  ({n} puntos, {segs} tramos, {span})")
