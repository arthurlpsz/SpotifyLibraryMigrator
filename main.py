import atexit

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

    if ask_delete_all_tracks():
        delete_all_saved_tracks()

    df = load_all_sheets(
        EXCEL_FILE
    )

    processed = load_progress()

    atexit.register(
        lambda: save_progress(
            processed
        )
    )

    atexit.register(
        save_cache
    )

    pbar = tqdm(
        total=len(df),
        initial=len(processed)
    )

    try:

        for _, row in df.iterrows():

            unique_id = build_progress_id(row)

            if unique_id in processed:

                pbar.update(1)

                continue

            try:

                result = process_row(row)

                add_result_to_library(row, result)

                processed.add(unique_id)

                if len(processed) % 100 == 0:
                    save_progress(processed)

            except Exception as e:
                print("Erro:", e)

            pbar.set_description(f"{row['NOME']}")

            pbar.update(1)

    except KeyboardInterrupt:
        print("\nInterrupção detectada.")

    finally:
        save_progress(processed)
        pbar.close()

if __name__ == "__main__":
    main()
