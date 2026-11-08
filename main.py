import atexit

from src.execution_history import row_record, load_snapshot, compare_rows, save_execution

import pandas as pd
from tqdm import tqdm

from src.utils import (is_collection, is_compilation, parse_discs)
from src.spotify_client import (like_track, add_album, delete_all_saved_tracks)
from src.track_matcher import (search_spotify, choose_best)
from src.album_matcher import (search_album, choose_best_album)

from src.storage import (search_cache, album_search_cache, load_progress, save_progress, save_cache)


EXCEL_FILE = "Musicas_Curtidas.xlsx"


def process_row(row):
    """
    Decide se a linha representa uma faixa ou uma coleção
    (álbum, EP ou compilação) e procura a melhor correspondência.
    """

    tipo = str(
        row.get("TIPO", "")
    ).lower()

    if is_collection(tipo):

        if is_compilation(tipo):
            print(
                f"BUSCANDO COMPILAÇÃO: {row['NOME']}"
            )

        results = search_album(
            row["NOME"],
            row["ARTISTAS/GRUPO"],
            tipo,
            album_search_cache=album_search_cache
        )

        if results:

            best = choose_best_album(
                row,
                results
            )

            if best:
                return ("album",best["id"])

        print(f"ALBUM NÃO ENCONTRADO: {row['NOME']}")

        return None

    results = search_spotify(row["NOME"], row["ARTISTAS/GRUPO"], allow_compilation=False, search_cache=search_cache)

    best, best_score = choose_best(row, results)

    print(
        row["NOME"],
        "->",
        "ACHOU" if best else "NAO ACHOU",
        f"(score={best_score})"
    )

    if not best:
        return None

    print(
        "Selecionado:",
        best.get("name", ""),
        "-",
        ", ".join(
            artist.get("name", "")
            for artist in best.get("artists", [])
        ),
        "|",
        best.get("album", {}).get("name", ""),
        "|",
        best.get("album", {}).get("release_date", ""),
        "|",
        best.get("album", {}).get("album_type", "")
    )

    return (
        "track",
        best["id"]
    )


def load_all_sheets(file):
    """
    Lê todas as abas da planilha, ignorando a aba Dashboard.
    """

    xls = pd.ExcelFile(file)
    dfs = []

    for sheet in xls.sheet_names:

        if sheet.lower() == "dashboard":
            continue

        df = pd.read_excel(file, sheet_name=sheet)

        df = df.dropna(
            subset=["NOME", "ARTISTAS/GRUPO"]
        )

        df["__aba"] = sheet
        df["__linha"] = df.index + 2
        dfs.append(df)

    return pd.concat(
        dfs,
        ignore_index=True
    )


def ask_delete_all_tracks():
    """
    Pergunta se a biblioteca atual deve ser apagada antes da importação.
    """

    while True:

        choice = input(
            "Deseja apagar todas as músicas salvas antes de rodar o código? [s/n]: "
        ).strip().lower()

        if choice in (
            "s",
            "sim"
        ):
            return True

        if choice in (
            "n",
            "nao",
            "não",
            ""
        ):
            return False

        print(
            "Digite 's' para sim ou 'n' para não."
        )


def build_progress_id(row):
    """
    Cria um identificador único para o progresso.
    A seleção de discos também faz parte do identificador.
    """

    progress_discs = parse_discs(
        row.get("DISCO")
    )

    if progress_discs is None:
        disco_progress = ""

    else:
        disco_progress = ",".join(
            str(disc)
            for disc in sorted(
                progress_discs
            )
        )

    return (
        f"{row['NOME']}|"
        f"{row['ARTISTAS/GRUPO']}|"
        f"{disco_progress}"
    )


def add_result_to_library(row, result):
    """
    Adiciona à biblioteca o resultado escolhido pelo algoritmo.
    """

    if not result:
        return

    tipo, spotify_id = result

    if tipo == "track":
        like_track(spotify_id)
        return

    if tipo == "album":
        print(f"ADICIONANDO ALBUM: {row['NOME']}")

        selected_discs = parse_discs(
            row.get("DISCO")
        )

        add_album(
            spotify_id,
            selected_discs
        )


def main():
    df = load_all_sheets(EXCEL_FILE)
    previous = load_snapshot()
    records = [row_record(row) for _, row in df.iterrows()]
    added, removed, changed, matched = compare_rows(
        previous["rows"] if previous else [], records
    )
    if previous:
        print(
            f"Desde a última execução: {len(added)} linha(s) nova(s), "
            f"{len(changed)} alterada(s), {len(removed)} removida(s)."
        )
    else:
        print("Primeira comparação: esta execução criará a referência inicial.")

    deleted = ask_delete_all_tracks()
    if deleted:
        delete_all_saved_tracks()

    review_all = input(
        "Pesquisar novamente os itens já importados para conferir mudanças no Spotify? [s/n]: "
    ).strip().lower() in ("s", "sim")

    processed = set() if deleted else load_progress()
    # Resultados antigos de busca não devem esconder mudanças ou novos lançamentos.
    search_cache.clear()
    album_search_cache.clear()
    old_by_record = {id(new): old for old, new in matched}
    for old, new in matched:
        if old.get("last_search"):
            new["last_search"] = old["last_search"]
        new["imported"] = old.get("imported", False) and not deleted
    atexit.register(lambda: save_progress(processed))
    atexit.register(save_cache)
    pbar = tqdm(total=len(df))
    completed = False

    try:
        for (_, row), record in zip(df.iterrows(), records):
            old = old_by_record.get(id(record))
            if old and old.get("last_search"):
                record["last_search"] = old["last_search"]
            try:
                unique_id = build_progress_id(row)
                # Só pula linhas iguais com sucesso conhecido. Falhas são reavaliadas.
                if (
                    not review_all and old
                    and old.get("last_search", {}).get("status") == "encontrado"
                    and unique_id in processed and record.get("imported")
                ):
                    record["status"] = "mantido"
                    record["result"] = old["last_search"].get("result")
                    continue

                result = process_row(row)
                record["checked"] = True
                record["status"] = "encontrado" if result else "nao_encontrado"
                record["result"] = list(result) if result else None
                record["last_search"] = {
                    "status": record["status"], "result": record["result"]
                }

                if result:
                    already_added = (
                        old and unique_id in processed and record.get("imported")
                        and old.get("last_search", {}).get("result") == list(result)
                    )
                    if not already_added:
                        add_result_to_library(row, result)
                    record["imported"] = True
                    processed.add(unique_id)
                else:
                    record["imported"] = False
                    processed.discard(unique_id)

                save_progress(processed)
            except Exception as exc:
                record["status"] = "erro"
                record["error"] = str(exc)
                print("Erro:", exc)
            finally:
                pbar.set_description(str(row["NOME"]))
                pbar.update(1)
        completed = True
    except KeyboardInterrupt:
        print("\\nInterrupção detectada.")
    finally:
        save_progress(processed)
        save_cache()
        save_execution(records, previous, completed)
        pbar.close()


if __name__ == "__main__":
    main()
