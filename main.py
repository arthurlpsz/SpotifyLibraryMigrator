import pandas as pd
from tqdm import tqdm
import atexit

from utils import (
    similar,
    split_artists,
    match_year,
    match_date,
    is_single,
    is_compilation,
    is_collection,
    parse_discs,
)

from spotify_client import (
    sp,
    spotify_call,
    like_track,
    add_album,
    delete_all_saved_tracks,
)

from track_matcher import (
    search_spotify,
    score_result,
    choose_best,
)

from album_matcher import (
    search_album,
    score_album_result,
    count_explicit_tracks,
    choose_best_album,
    get_expected_track_count,
)

from storage import (
    artist_id_cache,
    search_cache,
    album_search_cache,
    load_progress,
    save_progress,
    save_cache,
)
























def process_row(row):

    tipo = str(
        row.get(
            "TIPO",
            ""
        )
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

                return (
                    "album",
                    best["id"]
                )

        print(
            f"ALBUM NÃO ENCONTRADO: {row['NOME']}"
        )

    else:

        results = search_spotify(
            row["NOME"],
            row["ARTISTAS/GRUPO"],
            allow_compilation=False,
            search_cache=search_cache
        )

        best, best_score = choose_best(
            row,
            results
        )

        print(
            row["NOME"],
            "->",
            "ACHOU" if best else "NAO ACHOU",
            f"(score={best_score})"
        )

        if best:
            print(
                "Selecionado:",
                best.get("name", ""),
                "-",
                ", ".join(
                    a.get("name", "")
                    for a in best.get("artists", [])
                ),
                "|",
                best.get("album", {}).get("name", ""),
                "|",
                best.get("album", {}).get("release_date", ""),
                "|",
                best.get("album", {}).get("album_type", "")
            )

        if best:

            return (
                "track",
                best["id"]
            )

    return None

    






def get_artist_id(artist_name):
    cache_key = artist_name.lower().strip()
    if cache_key in artist_id_cache:
        return artist_id_cache[cache_key]

    query = f"artist:{artist_name}"
    results = spotify_call(sp.search, q=query, type="artist", limit=5)
    artists = results["artists"]["items"]

    artist_id = None
    for artist in artists:
        if similar(artist_name, artist["name"]) > 0.8:
            artist_id = artist["id"]
            break

    if not artist_id and artists:
        artist_id = artists[0]["id"]

    artist_id_cache[cache_key] = artist_id
    return artist_id










def load_all_sheets(file):
    xls = pd.ExcelFile(file)
    dfs = []
    for sheet in xls.sheet_names:
        if sheet.lower() == "dashboard":
            continue
        df = pd.read_excel(file, sheet_name=sheet)
        df = df.dropna(subset=["NOME", "ARTISTAS/GRUPO"])
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def ask_delete_all_tracks():
    while True:
        choice = input("Deseja apagar todas as músicas salvas antes de rodar o código? [s/n]: ").strip().lower()
        if choice in ("s", "sim"):
            return True
        if choice in ("n", "nao", "não", ""):
            return False
        print("Digite 's' para sim ou 'n' para não.")



def main():
    if ask_delete_all_tracks():
        delete_all_saved_tracks()

    df = load_all_sheets("Musicas_Curtidas.xlsx")
    processed = load_progress()

    atexit.register(
        lambda: save_progress(processed)
    )

    atexit.register(
        save_cache
    )

    pbar = tqdm(total=len(df), initial=len(processed))

    try:
        for _, row in df.iterrows():

            progress_discs = parse_discs(
                row.get("DISCO")
            )

            if progress_discs is None:
                disco_progress = ""
            else:
                disco_progress = ",".join(
                    str(d)
                    for d in sorted(progress_discs)
                )

            unique_id = (
                f"{row['NOME']}|"
                f"{row['ARTISTAS/GRUPO']}|"
                f"{disco_progress}"
            )

            if unique_id in processed:
                pbar.update(1)
                continue

            try:

                best = process_row(row)

                if best:

                    tipo, spotify_id = best

                    if tipo == "track":

                        like_track(
                            spotify_id
                        )

                    elif tipo == "album":

                        print(
                            f"ADICIONANDO ALBUM: {row['NOME']}"
                        )

                        selected_discs = parse_discs(
                            row.get("DISCO")
                        )

                        add_album(
                            spotify_id,
                            selected_discs
                        )

                processed.add(unique_id)

                if len(processed) % 100 == 0:
                    save_progress(processed)

            except Exception as e:
                print("Erro:", e)

            pbar.set_description(
                f"{row['NOME']}"
            )

            pbar.update(1)

    except KeyboardInterrupt:

        print(
            "\nInterrupção detectada."
        )

    finally:

        save_progress(processed)
        pbar.close()

if __name__ == "__main__":
    main()
