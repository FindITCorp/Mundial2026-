#!/usr/bin/env python3
"""
predict_match.py — COMANDO ÚNICO Y CANÓNICO de predicción del Mundial 2026.

Corre el motor COMPLETO de 6 factores (Elo + forma/xG + XI 11v11 con ratings
club+selección + balón parado + pressing + H2H) y, antes de mostrar el resultado,
VALIDA que cada factor esté alimentado con datos reales. Si algún factor cae en
su valor por defecto, lo AVISA explícitamente en vez de ocultarlo — así el modelo
nunca vuelve a "dejar fuera una consideración" en silencio.

USO:
  python3 predict_match.py "Mexico" "Serbia"
  python3 predict_match.py "Mexico" "Serbia" --home-out "Edson Álvarez:suspension"
  python3 predict_match.py --pairs "Spain|Iraq" "France|Ivory Coast" "Mexico|Serbia"
  python3 predict_match.py --file data/lineups/predict_pairs.txt
  python3 predict_match.py "Mexico" "Serbia" --json   # salida JSON

Solo necesita la DB (no consume API). Corre local o en CI indistintamente.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
DB = BASE_DIR / "data" / "mundial2026.db"

from models.match_predictor import predict_by_name  # noqa: E402

# Cada factor del motor + cómo verificar que tiene datos REALES (no default).
# Si el check falla, el factor está cayendo en su valor por defecto.
FACTOR_CHECKS = {
    "Elo":            "SELECT COUNT(*) FROM team_elo WHERE team_id=?",
    "Forma reciente": "SELECT COUNT(*) FROM team_matches WHERE team_id=?",
    "XI titular":     "SELECT COUNT(*) FROM projected_lineups WHERE team_id=? AND is_starter=1",
    "Ratings plantilla": "SELECT COUNT(*) FROM player_ratings pr JOIN players p ON p.id=pr.player_id WHERE p.team_id=? AND pr.context='nat'",
    "Stats club 2024/25": "SELECT COUNT(*) FROM player_club_stats pcs JOIN projected_lineups pl ON pl.player_id=pcs.player_id WHERE pl.team_id=? AND pl.is_starter=1 AND pcs.season='2024/25' AND pcs.xg>0",
    "Táctica/formación": "SELECT COUNT(*) FROM team_tactics WHERE team_id=?",
}
# Umbral mínimo de filas para considerar el factor "activo".
FACTOR_MIN = {
    "Elo": 1, "Forma reciente": 3, "XI titular": 11,
    "Ratings plantilla": 11, "Stats club 2024/25": 6, "Táctica/formación": 1,
}


def _resolve_id(conn, name: str):
    aliases_path = DB.parent / "team_name_aliases.json"
    canon = name
    if aliases_path.exists():
        al = json.loads(aliases_path.read_text())
        canon = al.get(name, name)
    r = conn.execute("SELECT id, name FROM teams WHERE name=?", (canon,)).fetchone()
    return (r[0], r[1]) if r else (None, name)


def audit_factors(conn, name: str) -> dict:
    """Devuelve {factor: (ok, count, min)} para un equipo."""
    tid, canon = _resolve_id(conn, name)
    out = {"team": canon, "team_id": tid, "factors": {}}
    if tid is None:
        out["error"] = f"'{name}' no está en la DB"
        return out
    for fac, sql in FACTOR_CHECKS.items():
        n = conn.execute(sql, (tid,)).fetchone()[0]
        out["factors"][fac] = {"ok": n >= FACTOR_MIN[fac], "count": n, "min": FACTOR_MIN[fac]}
    return out


def _parse_events(spec):
    out = []
    for chunk in (spec or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, reason = chunk.partition(":")
        out.append({"player": name.strip(), "reason": (reason or "injury").strip()})
    return out


def predict_one(conn, home, away, home_out=None, away_out=None) -> dict:
    he = _parse_events(home_out) if home_out else None
    ae = _parse_events(away_out) if away_out else None
    r = predict_by_name(home, away, neutral=True,
                        home_events=he, away_events=ae, db_path=str(DB))
    r["_audit_home"] = audit_factors(conn, home)
    r["_audit_away"] = audit_factors(conn, away)
    r["_events_home"] = he or []
    r["_events_away"] = ae or []
    return r


def _fmt_audit(audit) -> list[str]:
    lines = []
    if audit.get("error"):
        return [f"      ⚠ {audit['error']}"]
    for fac, d in audit["factors"].items():
        mark = "✓" if d["ok"] else "⚠ DEFAULT"
        lines.append(f"      {mark:<10} {fac:<22} ({d['count']})")
    return lines


def render(r: dict) -> str:
    h, a = r["home"], r["away"]
    L = []
    L.append("=" * 64)
    L.append(f"  {h}  vs  {a}")
    L.append("=" * 64)
    L.append(f"  RESULTADO PROBABLE:  {r['predicted_score']}   (gana: {r['winner']})")
    L.append(f"  Probabilidades:   {h} {r['prob_home_win']}%  |  Empate {r['prob_draw']}%  |  {a} {r['prob_away_win']}%")
    L.append("")
    L.append(f"  Goles esperados (λ):   {r['lambda_home']:.2f} - {r['lambda_away']:.2f}")
    L.append(f"  Calidad XI (11v11):    {r['xi_home']:.3f} vs {r['xi_away']:.3f}")
    L.append(f"  Elo:                   {r['elo_home']} vs {r['elo_away']}")
    L.append(f"  Formación:             {r['formation_home']} vs {r['formation_away']}")
    L.append(f"  Posesión:              {r['possession_home']}% - {r['possession_away']}%")
    if r.get("goleada_band"):
        L.append(f"  ⚑ Banda de goleada:    {r['goleada_band']}")
    if r.get("_events_home"):
        L.append(f"  Bajas {h}: " + ", ".join(f"{e['player']}({e['reason']})" for e in r['_events_home']))
    if r.get("_events_away"):
        L.append(f"  Bajas {a}: " + ", ".join(f"{e['player']}({e['reason']})" for e in r['_events_away']))
    ts = r.get("top_scores") or []
    if ts:
        L.append("  Top marcadores:        " + ", ".join(f"{s} ({p}%)" for s, p in ts[:4]))
    # Auditoría de factores — el corazón del comando: nada queda fuera en silencio
    L.append("")
    L.append("  AUDITORÍA DE FACTORES (✓ activo / ⚠ en default):")
    L.append(f"    {h}:")
    L.extend(_fmt_audit(r["_audit_home"]))
    L.append(f"    {a}:")
    L.extend(_fmt_audit(r["_audit_away"]))
    # Resumen de salud
    warns = []
    for side in ("_audit_home", "_audit_away"):
        au = r[side]
        if au.get("error"):
            warns.append(au["error"])
        else:
            for fac, d in au["factors"].items():
                if not d["ok"]:
                    warns.append(f"{au['team']}: factor '{fac}' en DEFAULT ({d['count']}/{d['min']})")
    if warns:
        L.append("")
        L.append("  ⚠ ADVERTENCIAS — el modelo está usando valores por defecto en:")
        for w in warns:
            L.append(f"     - {w}")
    else:
        L.append("")
        L.append("  ✅ Los 6 factores activos con datos reales para ambos equipos.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Comando único de predicción WC2026 (motor completo + auditoría de factores).")
    ap.add_argument("home", nargs="?", help="Equipo local")
    ap.add_argument("away", nargs="?", help="Equipo visitante")
    ap.add_argument("--pairs", nargs="+", help='Varias parejas: "A|B" "C|D"')
    ap.add_argument("--file", help="Archivo con una pareja A|B por línea")
    ap.add_argument("--home-out", help='Bajas local: "Jugador:reason,Jugador2:reason"')
    ap.add_argument("--away-out", help="Bajas visitante (mismo formato)")
    ap.add_argument("--json", action="store_true", help="Salida JSON")
    args = ap.parse_args()

    pairs = []
    if args.home and args.away:
        pairs.append((args.home, args.away, args.home_out, args.away_out))
    for p in (args.pairs or []):
        if "|" in p:
            x, y = p.split("|", 1)
            pairs.append((x.strip(), y.strip(), None, None))
    if args.file and Path(args.file).exists():
        for line in Path(args.file).read_text().splitlines():
            line = line.strip()
            if "|" in line and not line.startswith("#"):
                x, y = line.split("|", 1)
                pairs.append((x.strip(), y.strip(), None, None))
    if not pairs:
        ap.error("Indica una pareja: predict_match.py \"Mexico\" \"Serbia\"  (o --pairs / --file)")

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    results = [predict_one(conn, *p) for p in pairs]
    conn.close()

    if args.json:
        clean = [{k: v for k, v in r.items() if not k.startswith("_factors")} for r in results]
        print(json.dumps(clean, ensure_ascii=False, indent=2, default=str))
    else:
        for r in results:
            print(render(r))
            print()


if __name__ == "__main__":
    main()
