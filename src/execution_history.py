import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HISTORY_DIR = Path("historico_execucoes")
SNAPSHOT_FILE = HISTORY_DIR / "ultima_execucao.json"


def row_record(row):
    fields = {
        str(key): "" if value is None or str(value) in ("nan", "NaT", "<NA>") else str(value).strip()
        for key, value in row.items() if not str(key).startswith("__")
    }
    encoded = json.dumps(fields, sort_keys=True, ensure_ascii=False)
    return {
        "id": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "fields": fields,
        "sheet": row.get("__aba", ""),
        "line": int(row.get("__linha", 0)),
        "status": "pendente",
    }


def load_snapshot():
    if not SNAPSHOT_FILE.exists():
        return None
    return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))


def compare_rows(previous, current):
    """Ignora reordenação; preserva ocorrências duplicadas da mesma linha."""
    available = defaultdict(list)
    for old in previous:
        available[old["id"]].append(old)
    added, matched = [], []
    for new in current:
        if available[new["id"]]:
            matched.append((available[new["id"]].pop(0), new))
        else:
            added.append(new)
    removed = [old for group in available.values() for old in group]
    # Só classifica como edição quando o nome/artista identifica um único par.
    def identity(record):
        fields = record["fields"]
        return (fields.get("NOME", "").casefold(), fields.get("ARTISTAS/GRUPO", "").casefold())
    old_groups, new_groups = defaultdict(list), defaultdict(list)
    for old in removed:
        old_groups[identity(old)].append(old)
    for new in added:
        new_groups[identity(new)].append(new)
    changed = []
    for key in old_groups.keys() & new_groups.keys():
        if len(old_groups[key]) == len(new_groups[key]) == 1:
            old, new = old_groups[key][0], new_groups[key][0]
            changed.append((old, new))
            removed.remove(old)
            added.remove(new)
    return added, removed, changed, matched


def save_execution(records, previous, completed):
    """
    Salva somente a referência da última execução.
    Não gera relatórios ou arquivos históricos acumulados.
    """

    HISTORY_DIR.mkdir(exist_ok=True)

    now = datetime.now().astimezone()

    snapshot = {
        "executed_at": now.isoformat(),
        "completed": completed,
        "rows": records
    }

    temporary = SNAPSHOT_FILE.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    temporary.replace(SNAPSHOT_FILE)