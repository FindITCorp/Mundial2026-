"""
fetch_sofascore_pw.py — Fetcher automático de Sofascore vía Playwright.

Sofascore (jun-2026) metió Cloudflare "managed challenge": requests/curl/curl_cffi
reciben 403. Un Chromium real (Playwright) SÍ resuelve el challenge. Y el clearance
queda ACOTADO al partido cuya página está cargada, así que la forma robusta de bajar
los datos es: navegar a la página de cada partido e INTERCEPTAR las respuestas que el
propio SPA hace a /api/v1/event/{id}/* (esas pasan Cloudflare).

Captura TODO de una sola navegación: marcador (/event), alineaciones + ratings + minutos
(/lineups), estadísticas de equipo (/statistics: posesión, xG, intercepciones,
recuperaciones, entradas, despejes, duelos…), shotmap, incidencias, mejores jugadores.

Guarda el JSON CRUDO de cada endpoint en data/sofascore_raw/{event_id}/<endpoint>.json
ANTES de cualquier parseo — así nunca se pierde nada aunque el parseo falle.

Uso:
    python scripts/fetch_sofascore_pw.py URL1 URL2 ...
    python scripts/fetch_sofascore_pw.py --headed URL1 ...      # ver el navegador
Cada URL es la de la página del partido en Sofascore (copiada del navegador), p.ej.:
    https://www.sofascore.com/es/football/match/mexico-czechia/oUbsGVb

El event_id se extrae del propio /event interceptado, no hace falta pasarlo.
"""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "sofascore_raw"


def _slug_from_suffix(suffix: str) -> str:
    s = suffix.strip("/").replace("/", "_")
    return s or "event"


def _main_id(url: str) -> str | None:
    """El id del partido va en el hash de la URL de Sofascore: ...#id:12345,..."""
    m = re.search(r"[#&]id:(\d+)", url)
    return m.group(1) if m else None


def fetch_match(pg, url: str) -> dict:
    """Navega a la página de un partido e intercepta todos sus endpoints
    /api/v1/event/{id}/*. La página carga partidos relacionados (h2h) con OTROS
    ids, así que se capturan TODOS agrupados por id y se elige el partido
    principal: el del hash de la URL, o en su defecto el id con más endpoints.
    Devuelve {event_id, endpoints:{suffix:json}}."""
    from collections import defaultdict
    by_id: dict[str, dict] = defaultdict(dict)

    def on_resp(resp):
        if resp.status != 200:
            return
        m = re.search(r"/api/v1/event/(\d+)(/[^?]*)?", resp.url)
        if not m:
            return
        eid, suffix = m.group(1), (m.group(2) or "/event")
        try:
            by_id[eid][suffix] = resp.json()
        except Exception:
            pass

    def pick_main():
        if not by_id:
            return None
        hint = _main_id(pg.url) or _main_id(url)
        if hint and hint in by_id:
            return hint
        return max(by_id, key=lambda k: len(by_id[k]))

    pg.on("response", on_resp)
    pg.goto(url, wait_until="domcontentloaded", timeout=45000)

    # Esperar a que Cloudflare resuelva el challenge y el SPA dispare sus XHR.
    for _ in range(20):
        pg.wait_for_timeout(1000)
        if by_id:
            break
    pg.wait_for_timeout(3000)  # margen para /lineups, /best-players, etc.

    # Forzar la pestaña de estadísticas (lazy) con el id principal detectado.
    main = pick_main()
    if main and "/statistics" not in by_id.get(main, {}):
        base = url.split("#")[0]
        pg.goto(f"{base}#id:{main},tab:statistics",
                wait_until="domcontentloaded", timeout=45000)
        for _ in range(8):
            pg.wait_for_timeout(1000)
            if "/statistics" in by_id.get(main, {}):
                break
    pg.remove_listener("response", on_resp)

    main = pick_main()
    return {"event_id": main, "endpoints": dict(by_id.get(main, {}))}


def save_raw(event_id: str, endpoints: dict[str, dict]) -> Path:
    mdir = RAW_DIR / str(event_id)
    mdir.mkdir(parents=True, exist_ok=True)
    for suffix, data in endpoints.items():
        fname = _slug_from_suffix(suffix)
        (mdir / f"{fname}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return mdir


def summarize(endpoints: dict[str, dict]) -> str:
    ev = endpoints.get("/event", {}).get("event", {})
    line = ""
    if ev:
        line = (f"{ev['homeTeam']['name']} {ev.get('homeScore',{}).get('current','?')}-"
                f"{ev.get('awayScore',{}).get('current','?')} {ev['awayTeam']['name']} "
                f"[{ev['status']['type']}]")
    have = sorted(k for k in endpoints)
    return f"{line}  | endpoints: {', '.join(have)}"


def run(urls: list[str], headless: bool = True):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=headless)
        ctx = b.new_context(locale="es-ES")
        pg = ctx.new_page()
        for url in urls:
            print(f"\n→ {url}")
            try:
                res = fetch_match(pg, url)
            except Exception as e:
                print(f"   ERROR: {e}")
                continue
            eid = res["event_id"]
            if not eid or not res["endpoints"]:
                print("   sin datos (¿URL incorrecta o challenge no resuelto?)")
                continue
            mdir = save_raw(eid, res["endpoints"])
            print(f"   {summarize(res['endpoints'])}")
            print(f"   guardado crudo → {mdir}  ({len(res['endpoints'])} archivos)")
            results[eid] = res["endpoints"]
        b.close()
    return results


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    headed = "--headed" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    run(args, headless=not headed)
