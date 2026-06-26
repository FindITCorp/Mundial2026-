"""
discover_sofascore_urls.py — Auto-descubre las URLs de partido de Sofascore
(slug + customId) para una o varias FECHAS, sin que el usuario tenga que pegarlas.

Resuelve el muro que parecía "imposible" el 25-jun: el ACCESO DIRECTO a las APIs de
listado está bloqueado por Cloudflare, pero las llamadas que hace el propio SPA al
cargar la página de una fecha (`/api/v1/.../scheduled-events/...`) SÍ pasan. Con
Playwright se navega a https://www.sofascore.com/football/{fecha} y se INTERCEPTAN
esas respuestas, que traen id + customId + slugs de cada partido.

Salida: imprime y guarda en data/sofascore_urls.json un mapa {event_id: match_url}
listo para pasar a fetch_sofascore_pw.py.

Uso:
    python scripts/discover_sofascore_urls.py 2026-06-27 2026-06-28
    python scripts/discover_sofascore_urls.py 2026-06-27 --only 15186973 15186972
    python scripts/discover_sofascore_urls.py 2026-06-27 --headed
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
OUT = BASE_DIR / "data" / "sofascore_urls.json"


def discover(dates: list[str], only: set[int] | None = None, headless: bool = True) -> dict:
    captured: list = []

    def on_resp(resp):
        if "/api/v1/" not in resp.url or resp.status != 200:
            return
        try:
            captured.append(resp.json())
        except Exception:
            pass

    with sync_playwright() as p:
        b = p.chromium.launch(headless=headless)
        pg = b.new_context(locale="es-ES").new_page()
        pg.on("response", on_resp)
        pg.goto("https://www.sofascore.com/", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(5000)
        for d in dates:
            pg.goto(f"https://www.sofascore.com/football/{d}",
                    wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(7000)
        b.close()

    found: dict[int, str] = {}

    def scan(obj):
        if isinstance(obj, dict):
            eid = obj.get("id")
            if isinstance(eid, int) and obj.get("customId") and obj.get("homeTeam"):
                if only is None or eid in only:
                    hs = obj["homeTeam"].get("slug") or obj["homeTeam"].get("name", "")
                    as_ = obj["awayTeam"].get("slug") or obj["awayTeam"].get("name", "")
                    found[eid] = (f"https://www.sofascore.com/football/match/"
                                  f"{hs}-{as_}/{obj['customId']}#id:{eid}")
            for v in obj.values():
                scan(v)
        elif isinstance(obj, list):
            for v in obj:
                scan(v)

    for data in captured:
        scan(data)
    return found


def main():
    args = sys.argv[1:]
    headless = "--headed" not in args
    only = None
    if "--only" in args:
        i = args.index("--only")
        only = {int(x) for x in args[i + 1:] if x.isdigit()}
        args = args[:i]
    dates = [a for a in args if not a.startswith("--")]
    if not dates:
        print(__doc__)
        sys.exit(1)

    found = discover(dates, only=only, headless=headless)
    print(f"\n=== {len(found)} URLs descubiertas ===")
    for eid, url in sorted(found.items()):
        print(url)
    merged = {}
    if OUT.exists():
        merged = json.loads(OUT.read_text(encoding="utf-8"))
    merged.update({str(k): v for k, v in found.items()})
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardado en {OUT} ({len(merged)} URLs acumuladas).")


if __name__ == "__main__":
    main()
