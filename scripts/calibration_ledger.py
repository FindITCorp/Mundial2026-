"""
calibration_ledger.py — ¿Mis overrides SUMAN o restan vs el modelo base? (idea autónoma #2)

La pregunta incómoda: cuando piso al modelo con criterio experto, ¿acierto más o meto
ruido? Para cada partido JUGADO compara tres cosas sobre el resultado de 90':
  • SELLADO   = la predicción guardada en match_predictions (experto donde intervine).
  • MODELO    = predict_match re-corrido (la línea base sin mi mano).
  • REAL      = resultado de 90' (score en wc_matches).
Reporta acierto y Brier de cada uno, y —lo clave— el head-to-head SOLO en los partidos
donde SELLADO≠MODELO (ahí se ve si mi override ayuda).

⚠️ Caveat honesto: en knockout mis sellos usan semántica de AVANCE (p.ej. 'Draw' =
avanza en penales), así que sobre el resultado de 90' un sello 'Draw' que fue 2-1 cuenta
como fallo aunque acertara el avance. Por eso se reporta grupos y knockout por separado.

Uso:  python scripts/calibration_ledger.py
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
DB = BASE_DIR / "data" / "mundial2026.db"
from models.match_predictor import predict_match


def _outcome(sh, sa):
    return "H" if sh > sa else ("A" if sa > sh else "D")


def _argmax(ph, pd, pa):
    return "H" if ph >= pd and ph >= pa else ("D" if pd >= pa else "A")


def _brier(ph, pd, pa, actual):
    y = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}[actual]
    return sum((p - t) ** 2 for p, t in zip((ph, pd, pa), y))


def _norm(v):
    s = sum(v)
    return tuple(x / s for x in v) if s > 2 else tuple(v)   # 0-100 → 0-1


def run(conn):
    rows = conn.execute(
        "SELECT p.match_id,p.home_team_name,p.away_team_name,p.home_win_prob,p.draw_prob,"
        "p.away_win_prob,p.model_version,m.score_home,m.score_away,m.home_team_id,m.away_team_id "
        "FROM match_predictions p JOIN wc_matches m ON m.id=p.match_id "
        "WHERE m.played=1 AND m.score_home IS NOT NULL").fetchall()
    cats = {"GRUPOS": [], "KNOCKOUT": []}
    for (mid, hn, an, ph, pd, pa, mv, sh, sa, hid, aid) in rows:
        actual = _outcome(sh, sa)
        sph, spd, spa = _norm((ph or 0, pd or 0, pa or 0))
        sealed_ok = _argmax(sph, spd, spa) == actual
        sealed_br = _brier(sph, spd, spa, actual)
        try:
            m = predict_match(hid, aid, neutral=True, db_path=str(DB))
            mph, mpd, mpa = _norm((m["prob_home_win"], m["prob_draw"], m["prob_away_win"]))
            model_ok = _argmax(mph, mpd, mpa) == actual
            model_br = _brier(mph, mpd, mpa, actual)
            differ = _argmax(sph, spd, spa) != _argmax(mph, mpd, mpa)
        except Exception:
            model_ok = model_br = None; differ = False
        cat = "KNOCKOUT" if mid >= 400021518 else "GRUPOS"
        cats[cat].append((mid, hn, an, sealed_ok, sealed_br, model_ok, model_br, differ, mv))

    for cat, L in cats.items():
        if not L:
            continue
        n = len(L)
        s_acc = sum(x[3] for x in L) / n
        s_br = sum(x[4] for x in L) / n
        mvals = [x for x in L if x[5] is not None]
        m_acc = sum(x[5] for x in mvals) / len(mvals) if mvals else None
        m_br = sum(x[6] for x in mvals) / len(mvals) if mvals else None
        print(f"=== {cat} (n={n}) ===")
        print(f"  SELLADO  acierto {s_acc*100:.0f}%  Brier {s_br:.3f}")
        if m_acc is not None:
            print(f"  MODELO   acierto {m_acc*100:.0f}%  Brier {m_br:.3f}")
        # head-to-head donde difieren
        diff = [x for x in L if x[7] and x[5] is not None]
        if diff:
            s_win = sum(x[3] and not x[5] for x in diff)
            m_win = sum(x[5] and not x[3] for x in diff)
            print(f"  OVERRIDES (sellado≠modelo, n={len(diff)}): mi override ganó {s_win}, "
                  f"el modelo ganó {m_win}, empate {len(diff)-s_win-m_win}")
            for x in diff:
                print(f"     {(x[1] or '?')[:10]} v {(x[2] or '?')[:10]:10}: yo {'OK' if x[3] else 'X'} / modelo "
                      f"{'OK' if x[5] else 'X'}  [{(x[8] or '')[:22]}]")
        print()


if __name__ == "__main__":
    conn = sqlite3.connect(str(DB))
    run(conn)
    print("Nota: n pequeño; el ledger es para acumular ronda a ronda, no para concluir hoy.")
    conn.close()
