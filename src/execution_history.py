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
    HISTORY_DIR.mkdir(exist_ok=True)
    now = datetime.now().astimezone()
    snapshot = {"executed_at": now.isoformat(), "completed": completed, "rows": records}
    added, removed, changed, matched = compare_rows(
        previous["rows"] if previous else [], records
    )
    def label(record):
        f = record["fields"]
        return f'{f.get("ARTISTAS/GRUPO", "")} — {f.get("NOME", "")} [aba {record["sheet"]}, linha {record["line"]}]'
    lines = [
        f"Execução: {snapshot['executed_at']}",
        "Situação: " + ("concluída" if completed else "interrompida"),
        "Comparação: " + (previous["executed_at"] if previous else "primeira execução; referência inicial"),
        "Não encontrado significa ausência de correspondência pelo algoritmo; não comprova remoção pelo artista.",
    ]
    def section(title, entries):
        lines.extend(["", f"{title} ({len(entries)})"])
        lines.extend(entries or ["Nenhum."])
    section("Linhas adicionadas" if previous else "Linhas da referência inicial", [label(r) for r in added])
    section("Linhas removidas da planilha", [label(r) for r in removed])
    edits = []
    for old, new in changed:
        fields = sorted(old["fields"].keys() | new["fields"].keys())
        details = "; ".join(
            f'{key}: {old["fields"].get(key, "")!r} -> {new["fields"].get(key, "")!r}'
            for key in fields if old["fields"].get(key, "") != new["fields"].get(key, "")
        )
        edits.append(f"{label(new)}: {details}")
    section("Linhas alteradas", edits)
    section("Lançamentos não encontrados nesta execução", [
        label(r) for r in records if r["status"] == "nao_encontrado"
    ])
    transitions = []
    for old, new in matched:
        before = old.get("last_search")
        after = new.get("last_search")
        if new.get("checked") and before and after and before != after:
            transitions.append(f"{label(new)}: {before} -> {after}")
    section("Resultados de busca alterados em linhas iguais", transitions)
    section("Erros", [f'{label(r)}: {r["error"]}' for r in records if r.get("error")])
    section("Itens sem nova consulta nesta execução", [
        label(r) for r in records if not r.get("checked")
    ])
    stem = now.strftime("%Y%m%d_%H%M%S_%f")
    report = HISTORY_DIR / f"relatorio_{stem}.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (HISTORY_DIR / f"execucao_{stem}.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary = SNAPSHOT_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SNAPSHOT_FILE)
    print(f"Relatório salvo em: {report}", flush=True)
    print(
        f"Novas: {len(added)} | Removidas: {len(removed)} | Alteradas: {len(changed)} | "
        f"Não encontrados: {sum(r['status'] == 'nao_encontrado' for r in records)}",
        flush=True
    )
    return report
