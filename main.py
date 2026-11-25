import atexit
from spotipy.exceptions import SpotifyException
from requests.exceptions import RequestException

from src.execution_history import row_record, load_snapshot, compare_rows, save_execution

import pandas as pd
from tqdm import tqdm

from src.utils import (is_collection, is_compilation, parse_discs)
from src.spotify_client import (like_track, add_album, delete_all_saved_tracks)
from src.track_matcher import (search_spotify, search_spotify_fallback, choose_best)
from src.album_matcher import (search_album, search_album_fallback, choose_best_album)

from src.storage import (search_cache, album_search_cache, load_progress, save_progress, save_cache)


EXCEL_FILE = "Musicas_Curtidas.xlsx"
# False: execução normal.
# True: mostra detalhes das buscas e dos candidatos.
DEBUG_SEARCH = False


def process_row(row, debug=False):
    """
    Decide se a linha representa uma faixa ou uma coleção
    e procura a melhor correspondência no Spotify.
    """

    tipo = str(row.get("TIPO", "")).lower()

    # =========================
    # ÁLBUNS, EPS E COMPILAÇÕES
    # =========================

    if is_collection(tipo):

        results = search_album(
            row["NOME"],
            row["ARTISTAS/GRUPO"],
            tipo,
            album_search_cache=album_search_cache
        )

        if debug:
            print(f"\n[DIAGNÓSTICO] Álbum: {row['NOME']}")
            print(f"Busca original: {len(results)} resultado(s)")

        best = choose_best_album(row, results, debug=debug)

        if not best:
            if debug:
                print("Executando busca alternativa pelo título...")

            fallback_results = search_album_fallback(
                row["NOME"],
                album_search_cache=album_search_cache
            )

            if debug:
                print(
                    f"Busca alternativa: "
                    f"{len(fallback_results)} resultado(s)"
                )

            merged = {
                album.get("id"): album
                for album in results
                if album.get("id")
            }

            merged.update({
                album.get("id"): album
                for album in fallback_results
                if album.get("id")
            })

            best = choose_best_album(
                row,
                list(merged.values()),
                debug=debug
            )

        if best:
            return ("album", best["id"])

        return None

    # =========================
    # MÚSICAS
    # =========================

    results = search_spotify(
        row["NOME"],
        row["ARTISTAS/GRUPO"],
        allow_compilation=False,
        search_cache=search_cache,
        debug=debug
    )

    if debug:
        print(f"\n[DIAGNÓSTICO] Música: {row['NOME']}")
        print(f"Busca original: {len(results)} resultado(s)")

    best, best_score = choose_best(
        row,
        results,
        debug=debug
    )

    if not best:

        if debug:
            print("Executando busca alternativa pelo título...")

        fallback_results = search_spotify_fallback(
            row["NOME"],
            allow_compilation=False,
            search_cache=search_cache
        )

        if debug:
            print(
                f"Busca alternativa: "
                f"{len(fallback_results)} resultado(s)"
            )

        merged = {
            item.get("id"): item
            for item in results
            if item.get("id")
        }

        merged.update({
            item.get("id"): item
            for item in fallback_results
            if item.get("id")
        })

        best, best_score = choose_best(
            row,
            list(merged.values()),
            debug=debug
        )

    return ("track", best["id"]) if best else None

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

    stats = {
        "musicas": 0,
        "albuns": 0,
        "nao_encontrados": 0,
        "erros_api": 0,
        "outros_erros": 0,
        "mantidos": 0
    }

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

                result = process_row(row, debug=DEBUG_SEARCH)
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

                        if result[0] == "track":
                            stats["musicas"] += 1
                            print(f"[+] Música adicionada: {row['NOME']}")

                        elif result[0] == "album":
                            stats["albuns"] += 1
                            print(f"[+] Álbum adicionado: {row['NOME']}")

                    else:
                        stats["mantidos"] += 1

                    record["imported"] = True
                    processed.add(unique_id)

                else:
                    stats["nao_encontrados"] += 1
                    record["imported"] = False
                    processed.discard(unique_id)

                    print(f"[!] Não encontrado: {row['NOME']}")

                save_progress(processed)
            except (SpotifyException, RequestException) as exc:
                record["status"] = "erro_api"
                record["error"] = str(exc)
                stats["erros_api"] += 1

                print(f"[ERRO API] {row['NOME']}: {exc}")

            except Exception as exc:
                record["status"] = "erro"
                record["error"] = str(exc)
                stats["outros_erros"] += 1

                print(f"[ERRO] {row['NOME']}: {exc}")
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
        print("\n========== RESUMO DA EXECUÇÃO ==========")
        print(f"Músicas adicionadas: {stats['musicas']}")
        print(f"Álbuns adicionados: {stats['albuns']}")
        print(f"Itens já importados: {stats['mantidos']}")
        print(f"Não encontrados: {stats['nao_encontrados']}")
        print(f"Erros na API: {stats['erros_api']}")
        print(f"Outros erros: {stats['outros_erros']}")
        print("========================================")


if __name__ == "__main__":
    main()
