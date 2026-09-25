import pandas as pd
from tqdm import tqdm
import json
import os
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

PROGRESS_FILE = "progress.json"
artist_id_cache = {}
search_cache = {}
album_search_cache = {}

CACHE_FILE = "spotify_cache.json"

if os.path.exists(CACHE_FILE):

    with open(CACHE_FILE, "r") as f:

        cache = json.load(f)

        artist_id_cache = cache.get(
            "artist", {}
        )

        search_cache = cache.get(
            "search", {}
        )

        album_search_cache = cache.get(
            "album", {}
        )


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return set(json.load(f)["processed"])
    return set()

def save_progress(processed_ids):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"processed": list(processed_ids)}, f)











def score_album_result(row, album):
    score = 0

    tipo_planilha = row.get("TIPO", "")
    user_wants_compilation = is_compilation(tipo_planilha)

    album_type = album.get("album_type", "")

    # Nome do álbum
    name_similarity = similar(
        row["NOME"],
        album["name"]
    )

    if name_similarity > 0.8:
        score += 40

    # Artistas
    album_artists = [
        a["name"]
        for a in album["artists"]
    ]

    sheet_artists = split_artists(
        row["ARTISTAS/GRUPO"]
    )

    main_sheet_artist = (
        sheet_artists[0]
        if sheet_artists
        else ""
    )

    main_album_artist = (
        album_artists[0]
        if album_artists
        else ""
    )

    if similar(
        main_sheet_artist,
        main_album_artist
    ) > 0.9:

        score += 30

    elif any(
        similar(sa, ra) > 0.8
        for sa in sheet_artists
        for ra in album_artists
    ):

        score += 20

    else:
        # Em compilações é comum o Spotify usar "Various Artists".
        if not (
            user_wants_compilation
            and album_type == "compilation"
        ):
            score -= 50

    # Data
    if match_date(
        row["ESTREIA"],
        album["release_date"]
    ):

        score += 15

    elif match_year(
        row["ESTREIA"],
        album["release_date"]
    ):

        score += 10

    # Tipo
    if album_type == "compilation":

        if user_wants_compilation:
            score += 30
        else:
            score -= 20

    elif album_type == "album":

        if user_wants_compilation:
            score -= 10
        else:
            score += 10

    elif album_type == "single":
        score -= 20

    elif album_type == "ep":
        score -= 15

    # Quantidade de faixas
    expected_tracks = get_expected_track_count(row)

    if expected_tracks is not None:

        spotify_tracks = album.get(
            "total_tracks",
            0
        )

        difference = abs(
            expected_tracks - spotify_tracks
        )

        if difference == 0:
            score += 30

        elif difference <= 2:
            score += 15

        elif difference <= 5:
            score += 5

        else:
            score -= 5

    return score


def count_explicit_tracks(album_id):
    """Conta faixas explicit; usada apenas no desempate de álbuns."""
    explicit_count = 0
    total = 0
    offset = 0

    while True:
        results = spotify_call(
            sp.album_tracks,
            album_id,
            limit=50,
            offset=offset
        )
        tracks = results.get("items", [])

        if not tracks:
            break

        total += len(tracks)
        explicit_count += sum(
            1 for track in tracks
            if track.get("explicit", False)
        )

        if len(tracks) < 50:
            break

        offset += 50

    return explicit_count, total


def choose_best_album(row, results):

    if not results:
        return None

    scored = []

    for album in results:
        score = score_album_result(row, album)
        scored.append((album, score))

    best_score = max(score for _, score in scored)

    tied = [
        album
        for album, score in scored
        if score == best_score
    ]

    # Sem empate: não faz chamadas extras à API.
    if len(tied) == 1:
        return tied[0]

    print(
        f"Empate entre {len(tied)} álbuns. "
        "Verificando versões explicit..."
    )

    explicit_info = {}

    for album in tied:
        explicit_count, total = count_explicit_tracks(
            album["id"]
        )

        explicit_info[album["id"]] = (
            explicit_count,
            total
        )

        print(
            f"{album['name']} [{album['id']}] "
            f"-> {explicit_count}/{total} explicit"
        )

    # Prefere mais faixas explicit.
    # Persistindo empate, mantém o primeiro resultado.
    return max(
        tied,
        key=lambda album: explicit_info[album["id"]][0]
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
            tipo
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


def search_album(nome, artista, tipo=""):

    cache_key = (
        f"{nome.lower().strip()}|"
        f"{artista.lower().strip()}|"
        f"{tipo.lower().strip()}"
    )

    if cache_key in album_search_cache:
        return album_search_cache[cache_key]

    main_artist = split_artists(artista)[0]
    user_wants_compilation = is_compilation(tipo)

    queries = [
        f"album:{nome} artist:{main_artist}"
    ]

    # Compilações frequentemente aparecem como "Various Artists".
    # Nesses casos também buscamos apenas pelo título.
    if user_wants_compilation:
        queries.append(
            f"album:{nome}"
        )

    try:

        albums = []
        seen = set()

        for query in queries:

            results = spotify_call(
                sp.search,
                q=query,
                type="album",
                limit=20
            )

            for album in results["albums"]["items"]:

                album_id = album["id"]

                if album_id in seen:
                    continue

                seen.add(album_id)

                album_name = album["name"].lower()

                if any(
                    x in album_name
                    for x in [
                        "karaoke",
                        "instrumental",
                        "commentary"
                    ]
                ):
                    continue

                albums.append(album)

        album_search_cache[cache_key] = albums

        return albums

    except Exception as e:

        print(
            f"Erro buscando álbum: {nome} - {artista}"
        )

        print(e)

        return []







def get_expected_track_count(row):

    try:

        qtd = row.get("QTD")

        if qtd is None:
            return None

        if str(qtd).strip() == "":
            return None

        return int(qtd)

    except:

        return None

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


def save_cache():

    with open(
        CACHE_FILE,
        "w"
    ) as f:

        json.dump(
            {
                "artist": artist_id_cache,
                "search": search_cache,
                "album": album_search_cache
            },
            f
        )

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
