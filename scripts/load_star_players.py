"""
load_star_players.py — Carga la lista de jugadores diferenciadores (cracks de
nivel mundial) que elevan a su selección por encima de lo que indica el rating
promedio del XI: el "techo individual" que decide partidos cerrados.

Fuente: lista curada por el dueño (14-jun-2026), 100 jugadores con ranking.
El ranking → tier_weight (impacto). La posición (de la tabla players) → eje:
FWD/MID suben el λ propio (creación/gol); DEF/GK bajan el λ rival (solidez).

Tabla star_players:
  player_id  | id en players (NULL si su plantilla aún no está cargada)
  team_id    | selección
  player_name| nombre canónico de la lista
  rank       | 1..100 (1 = mayor impacto)
  tier_weight| peso por tier de rank
  pos_group  | 'OFF' (FWD/MID) | 'DEF' (DEF/GK) | NULL si sin posición

Idempotente: INSERT OR REPLACE por player_name+team_id. Acumula, no borra.
"""
import sqlite3
import unicodedata
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "mundial2026.db"

# (rank, nombre, nacionalidad_es)
STARS = [
    (1,"Kylian Mbappé","Francia"),(2,"Lamine Yamal","España"),(3,"Vinícius Júnior","Brasil"),
    (4,"Jude Bellingham","Inglaterra"),(5,"Harry Kane","Inglaterra"),(6,"Ousmane Dembélé","Francia"),
    (7,"Pedri","España"),(8,"Rodri","España"),(9,"Erling Haaland","Noruega"),(10,"Jamal Musiala","Alemania"),
    (11,"Federico Valverde","Uruguay"),(12,"Vitinha","Portugal"),(13,"Achraf Hakimi","Marruecos"),
    (14,"Cristiano Ronaldo","Portugal"),(15,"Lionel Messi","Argentina"),(16,"Lautaro Martínez","Argentina"),
    (17,"Julián Álvarez","Argentina"),(18,"Declan Rice","Inglaterra"),(19,"Bukayo Saka","Inglaterra"),
    (20,"Phil Foden","Inglaterra"),(21,"Cole Palmer","Inglaterra"),(22,"William Saliba","Francia"),
    (23,"Aurélien Tchouaméni","Francia"),(24,"Michael Olise","Francia"),(25,"Désiré Doué","Francia"),
    (26,"Eduardo Camavinga","Francia"),(27,"Florian Wirtz","Alemania"),(28,"Antonio Rüdiger","Alemania"),
    (29,"Joshua Kimmich","Alemania"),(30,"Manuel Neuer","Alemania"),(31,"Raphinha","Brasil"),
    (32,"Bruno Guimarães","Brasil"),(33,"Neymar","Brasil"),(34,"Alisson Becker","Brasil"),
    (35,"Marquinhos","Brasil"),(36,"Bernardo Silva","Portugal"),(37,"Bruno Fernandes","Portugal"),
    (38,"João Neves","Portugal"),(39,"Rúben Dias","Portugal"),(40,"Rafael Leão","Portugal"),
    (41,"Nicolás Otamendi","Argentina"),(42,"Alexis Mac Allister","Argentina"),(43,"Enzo Fernández","Argentina"),
    (44,"Cristian Romero","Argentina"),(45,"Emiliano Martínez","Argentina"),(46,"Martin Ødegaard","Noruega"),
    (47,"Alexander Sørloth","Noruega"),(48,"Mohamed Salah","Egipto"),(49,"Omar Marmoush","Egipto"),
    (50,"Kevin De Bruyne","Bélgica"),(51,"Jérémy Doku","Bélgica"),(52,"Loïs Openda","Bélgica"),
    (53,"Thibaut Courtois","Bélgica"),(54,"Romelu Lukaku","Bélgica"),(55,"Nico Williams","España"),
    (56,"Dani Olmo","España"),(57,"Fabián Ruiz","España"),(58,"Álvaro Morata","España"),
    (59,"Robin Le Normand","España"),(60,"Khvicha Kvaratskhelia","Georgia"),(61,"Giorgi Mamardashvili","Georgia"),
    (62,"Victor Osimhen","Nigeria"),(63,"Ademola Lookman","Nigeria"),(64,"Victor Boniface","Nigeria"),
    (65,"Sadio Mané","Senegal"),(66,"Kalidou Koulibaly","Senegal"),(67,"Ismaïla Sarr","Senegal"),
    (68,"Youssouf Sabaly","Senegal"),(69,"Hakim Ziyech","Marruecos"),(70,"Sofyan Amrabat","Marruecos"),
    (71,"Yassine Bounou","Marruecos"),(72,"Brahim Díaz","Marruecos"),(73,"Takefusa Kubo","Japón"),
    (74,"Kaoru Mitoma","Japón"),(75,"Wataru Endo","Japón"),(76,"Daichi Kamada","Japón"),
    (77,"Heung-Min Son","Corea del Sur"),(78,"Lee Kang-in","Corea del Sur"),(79,"Kim Min-jae","Corea del Sur"),
    (80,"Hwang Hee-chan","Corea del Sur"),(81,"Christian Pulisic","Estados Unidos"),(82,"Weston McKennie","Estados Unidos"),
    (83,"Tim Weah","Estados Unidos"),(84,"Yunus Musah","Estados Unidos"),(85,"Alphonso Davies","Canadá"),
    (86,"Jonathan David","Canadá"),(87,"Stephen Eustáquio","Canadá"),(88,"Tajon Buchanan","Canadá"),
    (89,"Luis Díaz","Colombia"),(90,"James Rodríguez","Colombia"),(91,"Jhon Durán","Colombia"),
    (92,"Richard Ríos","Colombia"),(93,"Ronald Araújo","Uruguay"),(94,"Darwin Núñez","Uruguay"),
    (95,"José María Giménez","Uruguay"),(96,"Manuel Ugarte","Uruguay"),(97,"Hakan Çalhanoğlu","Turquía"),
    (98,"Arda Güler","Turquía"),(99,"Kenan Yıldız","Turquía"),(100,"Granit Xhaka","Suiza"),
]

NAT2TEAM = {
    "Francia":"France","España":"Spain","Brasil":"Brazil","Inglaterra":"England","Noruega":"Norway",
    "Alemania":"Germany","Uruguay":"Uruguay","Portugal":"Portugal","Marruecos":"Morocco","Argentina":"Argentina",
    "Egipto":"Egypt","Bélgica":"Belgium","Georgia":"Georgia","Nigeria":"Nigeria","Senegal":"Senegal",
    "Japón":"Japan","Corea del Sur":"South Korea","Estados Unidos":"USA","Canadá":"Canada","Colombia":"Colombia",
    "Turquía":"Turkey","Suiza":"Switzerland",
}

# Overrides nombre→id en players para variantes que no matchean por normalización
ID_OVERRIDE = {
    ("Alisson Becker","Brazil"): 23,       # "Alisson"
    ("Heung-Min Son","South Korea"): 207,  # "Son Heung-min"
}
# Posición para los que no existen aún en players (plantilla sin cargar)
POS_OVERRIDE = {
    "Khvicha Kvaratskhelia":"FWD", "Giorgi Mamardashvili":"GK", "Victor Boniface":"FWD",
}


def _norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().split())


def tier_weight(rank: int) -> float:
    if rank <= 10:  return 1.00
    if rank <= 25:  return 0.75
    if rank <= 50:  return 0.55
    return 0.40


def pos_group(position: str | None) -> str | None:
    if not position: return None
    p = position.upper()
    if p in ("FWD", "MID", "F", "M"): return "OFF"
    if p in ("DEF", "GK", "D", "G"):  return "DEF"
    return None


def load(db_path=DB):
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS star_players (
            player_id   INTEGER,
            team_id     INTEGER NOT NULL,
            player_name TEXT NOT NULL,
            rank        INTEGER NOT NULL,
            tier_weight REAL NOT NULL,
            pos_group   TEXT,
            UNIQUE(player_name, team_id)
        )
    """)

    teams = {r[1]: r[0] for r in conn.execute("SELECT id, name FROM teams").fetchall()}
    # índice normalizado de players por equipo
    pl = {}
    for pid, name, tid, pos in conn.execute("SELECT id, name, team_id, position FROM players").fetchall():
        pl.setdefault(tid, {})[_norm(name)] = (pid, pos)

    rows = []
    matched = no_pos = no_player = 0
    for rank, name, nat in STARS:
        tname = NAT2TEAM.get(nat)
        tid = teams.get(tname)
        if not tid:
            print(f"  [SKIP] {name}: equipo {nat} no existe")
            continue
        pid = ID_OVERRIDE.get((name, tname))
        position = None
        if pid is None:
            rec = pl.get(tid, {}).get(_norm(name))
            if rec:
                pid, position = rec
        else:
            position = next((p for n, (i, p) in pl.get(tid, {}).items() if i == pid), None)
        if position is None:
            position = POS_OVERRIDE.get(name)
        pg = pos_group(position)
        if pid is not None:
            matched += 1
        else:
            no_player += 1
        if pg is None:
            no_pos += 1
        rows.append((pid, tid, name, rank, tier_weight(rank), pg))

    conn.executemany("""
        INSERT OR REPLACE INTO star_players
          (player_id, team_id, player_name, rank, tier_weight, pos_group)
        VALUES (?,?,?,?,?,?)
    """, rows)
    conn.commit()

    print(f"[load_star_players] {len(rows)} cargados | con player_id: {matched} | "
          f"sin player_id: {no_player} | sin pos_group: {no_pos}")
    # Resumen por equipo
    summ = conn.execute("""
        SELECT t.name, COUNT(*),
               SUM(CASE WHEN pos_group='OFF' THEN 1 ELSE 0 END),
               SUM(CASE WHEN pos_group='DEF' THEN 1 ELSE 0 END)
        FROM star_players s JOIN teams t ON t.id=s.team_id
        GROUP BY s.team_id ORDER BY COUNT(*) DESC
    """).fetchall()
    print("\nEstrellas por equipo (OFF/DEF):")
    for name, n, off, df in summ:
        print(f"  {name:<14} total={n:>2}  OFF={off}  DEF={df}")
    conn.close()


if __name__ == "__main__":
    load()
