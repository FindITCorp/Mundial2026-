"""
scripts/seed_tactics.py — Crea tabla team_tactics y pobla con datos 2026.
Idempotente. Fuente: formaciones conocidas de los técnicos confirmados.

pressing_intensity: 0=mínimo … 1=máximo (PPDA proxy)
  >0.75 = pressing alto (Liverpool style)
  0.50–0.75 = pressing medio
  <0.50 = bloque bajo / defensivo

defensive_line: "high" | "mid" | "low"
build_up_style: "short" | "mixed" | "direct"
style_tags: texto libre para notas del modelo
"""
import sqlite3, logging
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "mundial2026.db"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("seed_tactics")

# fmt: (formation, pressing_intensity, defensive_line, build_up_style, style_tags)
TACTICS: dict[str, tuple] = {
    # ── UEFA ──────────────────────────────────────────────────────────────
    "Spain":          ("4-3-3",   0.85, "high",  "short",  "tiki-taka evolved, Rodri pivot, Yamal/Nico width"),
    "France":         ("4-2-3-1", 0.60, "mid",   "mixed",  "counter + transitions, Mbappé on left, Tchouaméni-Rabiot double pivot"),
    "England":        ("4-2-3-1", 0.55, "mid",   "mixed",  "compact shape, Bellingham #10, Rice defensive anchor"),
    "Germany":        ("4-2-3-1", 0.72, "high",  "mixed",  "aggressive press, Kimmich hybrid, Musiala/Wirtz free roles"),
    "Portugal":       ("4-3-3",   0.58, "mid",   "short",  "Ronaldo false-9, Bernardo-Bruno creative, Joao Neves press trigger"),
    "Netherlands":    ("4-3-3",   0.68, "high",  "short",  "Koeman positional play, Gakpo left, van Dijk sweeper"),
    "Belgium":        ("4-3-3",   0.62, "mid",   "mixed",  "De Bruyne creator, Lukaku target, transition focus"),
    "Croatia":        ("4-3-3",   0.55, "mid",   "short",  "Modrić-Kovačić possession midfield, low block on defense"),
    "Switzerland":    ("3-4-2-1", 0.60, "mid",   "mixed",  "Shaqiri free, solid defensive block"),
    "Denmark":        ("4-3-3",   0.65, "mid",   "mixed",  "high energy, Eriksen free role behind striker"),
    "Turkey":         ("4-2-3-1", 0.58, "mid",   "direct", "Calhanoglu pivot, quick transitions, Arda Güler creative"),
    "Austria":        ("4-2-3-1", 0.70, "high",  "short",  "Rangnick pressing philosophy"),
    "Scotland":       ("3-4-2-1", 0.62, "mid",   "direct", "Robertson overlaps, aggressive wide play"),
    "Serbia":         ("3-4-2-1", 0.52, "mid",   "direct", "Milinkovic-Savić depth, Vlahovic target"),
    "Romania":        ("4-2-3-1", 0.48, "low",   "direct", "defensive, Stanciu playmaker"),
    "Poland":         ("4-2-3-1", 0.50, "low",   "direct", "Lewandowski-centric, defensive shape"),
    "Hungary":        ("3-5-2",   0.48, "low",   "direct", "Magyar block, counter attack"),
    "Czech Republic": ("4-2-3-1", 0.55, "mid",   "mixed",  "Soucek-Barak midfield"),
    "Slovenia":       ("4-4-2",   0.52, "mid",   "mixed",  "Sesko target man"),
    "Slovakia":       ("4-3-3",   0.50, "mid",   "mixed",  "Duda/Lobotka creative"),
    "Bosnia and Herzegovina": ("4-3-3", 0.50, "mid", "mixed", "physical style"),
    "Norway":         ("4-3-3",   0.60, "mid",   "mixed",  "Haaland target, Odegaard creator"),
    "Albania":        ("4-4-2",   0.48, "low",   "direct", "compact block"),

    # ── CONMEBOL ──────────────────────────────────────────────────────────
    "Argentina":      ("4-4-2",   0.62, "mid",   "mixed",  "Scaloni flexible 4-3-3 / 4-4-2, Messi free, Mac Allister pivot"),
    "Brazil":         ("4-2-3-1", 0.65, "mid",   "short",  "Ancelotti: Vinicius-Rodrygo width, Casemiro-Fabinho double pivot, posesión"),
    "Colombia":       ("4-2-3-1", 0.60, "mid",   "mixed",  "James #10 free role, Luis Díaz left, Ríos-Lerma pivot"),
    "Uruguay":        ("4-4-2",   0.55, "mid",   "mixed",  "Valverde box-to-box, Núñez-Suárez front two, pressing medio"),
    "Ecuador":        ("4-4-2",   0.58, "mid",   "mixed",  "Valencia target, Caicedo energy"),
    "Paraguay":       ("4-4-2",   0.50, "low",   "direct", "Sanabria target, physical, defensive block"),
    "Venezuela":      ("4-2-3-1", 0.55, "mid",   "mixed",  "Soteldo creative, organized defensively"),
    "Bolivia":        ("4-4-2",   0.42, "low",   "direct", "altitude advantage home, direct play"),
    "Peru":           ("4-2-3-1", 0.52, "mid",   "mixed",  "Cueva/Peña playmakers"),
    "Chile":          ("3-4-3",   0.68, "high",  "short",  "pressing residual Bielsa legacy"),

    # ── CONCACAF ──────────────────────────────────────────────────────────
    "USA":            ("4-3-3",   0.70, "high",  "mixed",  "Berhalter gegenpressing, Pulisic-Weah-Reyna front three"),
    "Mexico":         ("4-2-3-1", 0.55, "mid",   "mixed",  "Memo Ochoa last line, Lozano right, Chucky Lozano creative"),
    "Canada":         ("4-3-3",   0.65, "high",  "mixed",  "Davies left flank, Jonathan David striker"),
    "Panama":         ("5-4-1",   0.40, "low",   "direct", "compact 5-4-1 bloque bajo, Carrasquilla playmaker, transiciones"),
    "Costa Rica":     ("5-4-1",   0.38, "low",   "direct", "Navas last line, defensive first"),
    "Honduras":       ("4-4-2",   0.45, "low",   "direct", "physical, defensive"),
    "Jamaica":        ("4-4-2",   0.48, "low",   "direct", "athletic, direct"),

    # ── AFC ───────────────────────────────────────────────────────────────
    "Japan":          ("4-2-3-1", 0.78, "high",  "short",  "Moriyasu high press, Mitoma-Kubo width, intense gegenpress"),
    "South Korea":    ("4-2-3-1", 0.65, "mid",   "mixed",  "Son left, Hwang striker, organized midfield"),
    "Saudi Arabia":   ("4-3-3",   0.55, "mid",   "mixed",  "Hervé Renard structure, Al-Dawsari creative"),
    "Iran":           ("4-2-3-1", 0.48, "low",   "direct", "defensive compact, Azmoun target"),
    "Australia":      ("4-2-3-1", 0.55, "mid",   "mixed",  "Duke striker, Irvine-Mooy midfield"),
    "Jordan":         ("4-4-2",   0.48, "low",   "direct", "physical defensive"),
    "Iraq":           ("4-4-2",   0.50, "mid",   "mixed",  "organized"),
    "Uzbekistan":     ("4-3-3",   0.55, "mid",   "mixed",  "technical play"),
    "New Zealand":    ("4-4-2",   0.45, "low",   "direct", "Wood target man"),
    "Qatar":          ("3-5-2",   0.60, "mid",   "short",  "Sánchez style, Akram Hassan"),

    # ── CAF ───────────────────────────────────────────────────────────────
    "Morocco":        ("4-3-3",   0.65, "mid",   "mixed",  "Regragui defensive first → counter, Ziyech-En-Nesyri"),
    "Senegal":        ("4-3-3",   0.62, "mid",   "mixed",  "Mané-Dia front, organized midfield"),
    "Nigeria":        ("4-2-3-1", 0.58, "mid",   "mixed",  "Osimhen target, Iwobi-Chukwueze creative"),
    "Cameroon":       ("4-2-3-1", 0.55, "mid",   "mixed",  "Choupo-Moting, Anguissa midfield"),
    "Ivory Coast":    ("4-2-3-1", 0.58, "mid",   "mixed",  "Zaha-Pepe width, Sangare pivot"),
    "Ghana":          ("4-2-3-1", 0.55, "mid",   "mixed",  "Kudus creator, Semenyo striker"),
    "Egypt":          ("4-2-3-1", 0.52, "mid",   "mixed",  "Salah free role"),
    "DR Congo":       ("4-4-2",   0.52, "mid",   "mixed",  "Mbokani/Bongonda"),
    "Algeria":        ("4-2-3-1", 0.55, "mid",   "mixed",  "Mahrez free"),
    "Tunisia":        ("4-3-3",   0.50, "mid",   "mixed",  "organized"),
    "South Africa":   ("4-4-2",   0.50, "mid",   "direct", "Tau creative"),
    "Cape Verde":     ("4-3-3",   0.52, "mid",   "mixed",  "compact organization"),
}


def run(db_path: Path = DB_PATH) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_tactics (
            team_id            INTEGER PRIMARY KEY REFERENCES teams(id),
            formation          TEXT    NOT NULL DEFAULT '4-4-2',
            pressing_intensity REAL    NOT NULL DEFAULT 0.50,
            defensive_line     TEXT    NOT NULL DEFAULT 'mid',
            build_up_style     TEXT    NOT NULL DEFAULT 'mixed',
            style_tags         TEXT,
            updated_at         TEXT
        )
    """)

    from datetime import datetime
    now = datetime.utcnow().isoformat()

    inserted = updated = skipped = 0
    for team_name, (formation, press, def_line, build, tags) in TACTICS.items():
        row = conn.execute("SELECT id FROM teams WHERE name=?", (team_name,)).fetchone()
        if not row:
            log.warning("Equipo no encontrado: %s", team_name)
            skipped += 1
            continue
        tid = row["id"]
        conn.execute("""
            INSERT INTO team_tactics
                (team_id, formation, pressing_intensity, defensive_line, build_up_style, style_tags, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(team_id) DO UPDATE SET
                formation=excluded.formation,
                pressing_intensity=excluded.pressing_intensity,
                defensive_line=excluded.defensive_line,
                build_up_style=excluded.build_up_style,
                style_tags=excluded.style_tags,
                updated_at=excluded.updated_at
        """, (tid, formation, press, def_line, build, tags, now))
        inserted += 1

    conn.commit()
    conn.close()
    log.info("team_tactics: %d equipos insertados/actualizados, %d no encontrados", inserted, skipped)


if __name__ == "__main__":
    run()
    # Verificar
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT t.name, tt.formation, tt.pressing_intensity, tt.defensive_line, tt.build_up_style
        FROM team_tactics tt JOIN teams t ON t.id=tt.team_id
        ORDER BY tt.pressing_intensity DESC LIMIT 20
    """).fetchall()
    print(f"\n{'='*72}")
    print(f"  {'Equipo':<20} {'Forma':^8} {'Press':^7} {'Línea':^7} {'Estilo':^8}")
    print(f"  {'-'*68}")
    for r in rows:
        print(f"  {r['name']:<20} {r['formation']:^8} {r['pressing_intensity']:^7.2f} {r['defensive_line']:^7} {r['build_up_style']:^8}")
    conn.close()
