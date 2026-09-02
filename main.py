import pandas as pd
from tqdm import tqdm
import json
import os
import time
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
from difflib import SequenceMatcher
import re
import atexit

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

client_id = os.getenv("SPOTIPY_CLIENT_ID")
client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI", "https://127.0.0.1:8888/callback")

sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="user-library-read user-library-modify"
    )
)

def spotify_call(func, *args, max_retries=5, **kwargs):
    retries = 0

    while True:
        try:
            return func(*args, **kwargs)

        except SpotifyException as e:

            # Rate limit
            if e.http_status == 429 and retries < max_retries:

                retry_after = int(
                    e.headers.get("Retry-After", 5)
                )

                print(
                    f"Rate limit atingido. Esperando {retry_after}s..."
                )

                time.sleep(retry_after + 1)

                retries += 1
                continue

            raise

        except Exception as e:

            if retries < max_retries:
                retries += 1

                print(
                    f"Erro temporário: {e}"
                )

                time.sleep(2)

                continue

            raise


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return set(json.load(f)["processed"])
    return set()

def save_progress(processed_ids):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"processed": list(processed_ids)}, f)

def similar(a, b):
    return SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()


def split_artists(artist_str):
    return [a.strip() for a in re.split(r',|feat\.|ft\.|with|&', str(artist_str), flags=re.IGNORECASE)]

def match_year(sheet_date, spotify_date):
    try:
        sheet_text = str(sheet_date).strip()
        spotify_text = str(spotify_date).strip()
        sheet_match = re.search(r"\b(?:19|20)\d{2}\b", sheet_text)
        spotify_match = re.search(r"\b(?:19|20)\d{2}\b", spotify_text)
        if not sheet_match or not spotify_match:
            return False
        return sheet_match.group() == spotify_match.group()
    except:
        return False


def match_date(sheet_date, spotify_date):
    try:
        # Assume sheet_date is DD/MM/YYYY or DD-MM-YYYY
        parts = re.split(r'[/-]', str(sheet_date))
        if len(parts) == 3:
            day, month, year = parts
            formatted = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            return formatted == spotify_date
        else:
            # Fallback to year
            return str(sheet_date)[:4] in spotify_date
    except:
        return False

def search_spotify(track, artist, allow_compilation=False):

    def execute_search(title):

        query = (
            f"track:{title} "
            f"artist:{artist}"
        ).lower().strip()

        cache_key = (
            f"{query}|allow_compilation="
            f"{allow_compilation}"
        )

        if cache_key in search_cache:
            return search_cache[cache_key]

        results = spotify_call(
            sp.search,
            q=query,
            type="track",
            limit=25
        )

        items = results["tracks"]["items"]

        if allow_compilation:

            filtered = items

        else:

            filtered = [
                t
                for t in items
                if t["album"].get(
                    "album_type",
                    ""
                ) != "compilation"
            ]

        search_cache[cache_key] = filtered

        return filtered

    # 1. Primeiro tenta exatamente o título da planilha.
    filtered = execute_search(track)

    if filtered:
        return filtered

    # 2. Se não encontrou, tenta remover complementos
    # de trilha sonora, por exemplo:
    #
    # Double Life - From "Despicable Me 4"
    # Double Life (From "Despicable Me 4")
    # Double Life - From the Movie
    #
    # A busca simplificada só acontece quando a original falhou.

    simplified = re.sub(
        r"\s*[-–—]?\s*\(?\s*from\b.*$",
        "",
        str(track),
        flags=re.IGNORECASE
    ).strip()

    if (
        simplified
        and simplified.lower() != str(track).lower().strip()
    ):

        print(
            f"Busca simplificada: "
            f"'{track}' -> '{simplified}'"
        )

        return execute_search(simplified)

    return filtered


def score_result(row, result):

    score = 0

    track_name = (
        result.get("name", "")
        .lower()
    )

    album_name = (
        result.get("album", {})
        .get("name", "")
        .lower()
    )

    artist_names = " ".join([
        a["name"]
        for a in result.get(
            "artists",
            []
        )
    ]).lower()

    combined = (
        track_name
        + " "
        + album_name
        + " "
        + artist_names
    )

    wanted_name = str(
        row["NOME"]
    ).lower()

    # só bloqueia remix se a planilha não pediu remix
    if (
        "remix" in combined
        and
        "remix" not in wanted_name
    ):
        return -1000

    blocked_terms = [
        "video",
        "videoclipe",
        "music video",
        "official video",
        "official music video",

        "live",
        "ao vivo",

        "karaoke",
        "instrumental",

        "performance",
        "session",

        "commentary",

        "remaster",
        "remastered",

        "acoustic"
    ]

    if any(
        term in combined
        for term in blocked_terms
    ):
        return -1000

    # similaridade do nome
    similarity = similar(
        row["NOME"],
        result["name"]
    )

    if track_name == wanted_name:
        score += 60

    score += similarity * 40

    # artistas
    result_artists = [
        a["name"]
        for a in result["artists"]
    ]

    sheet_artists = split_artists(
        row["ARTISTAS/GRUPO"]
    )

    main_sheet = (
        sheet_artists[0]
        if sheet_artists
        else ""
    )

    main_result = (
        result_artists[0]
        if result_artists
        else ""
    )

    if similar(
        main_sheet,
        main_result
    ) > 0.9:

        score += 50

    elif any(
        similar(sa, ra) > 0.8
        for sa in sheet_artists
        for ra in result_artists
    ):

        score += 20

    else:
        score -= 100

    # Explicit funciona apenas como preferência secundária
    if result.get(
        "explicit",
        False
    ):

        score += 10

    # datas: nome/data são sinais principais para identificar a gravação correta
    if match_date(
        row["ESTREIA"],
        result["album"]["release_date"]
    ):

        score += 50

    elif match_year(
        row["ESTREIA"],
        result["album"]["release_date"]
    ):

        score += 30

    else:

        score -= 50

    # tipo de álbum
    album_type = result["album"].get(
        "album_type",
        ""
    )

    if album_type == "album":
        score += 20

    elif album_type == "single":
        score -= 10

    elif album_type == "compilation":
        score -= 50

    return score

def score_album_result(row, album):
    score = 0

    if similar(row["NOME"], album["name"]) > 0.8:
        score += 40

    album_artists = [a["name"] for a in album["artists"]]
    sheet_artists = split_artists(row["ARTISTAS/GRUPO"])

    # Check if main artist matches closely
    main_sheet_artist = sheet_artists[0] if sheet_artists else ""
    main_album_artist = album_artists[0] if album_artists else ""
    if similar(main_sheet_artist, main_album_artist) > 0.9:
        score += 30
    elif any(similar(sa, ra) > 0.8 for sa in sheet_artists for ra in album_artists):
        score += 20  # Lower score for secondary matches
    else:
        score -= 50  # Heavy penalty if no artist match

    if match_date(row["ESTREIA"], album["release_date"]):
        score += 15
    elif match_year(row["ESTREIA"], album["release_date"]):
        score += 10

    # Handle compilations based on user intent
    album_type = album.get("album_type", "")
    user_wants_compilation = is_collection(row.get("TIPO", ""))

    if album_type == "compilation":
        if user_wants_compilation:
            score += 10  # Bonus if user wants compilation
        else:
            score -= 20  # Penalty if not
    elif album_type == "album":
        score += 10  # Prefer full albums over singles/EPs
    elif album_type == "single":
        score -= 20  # Avoid singles when album is expected
    elif album_type == "ep":
        score -= 15  # Avoid EPs when album is expected
    else:
        score += 0

    if user_wants_compilation and album_type != "compilation":
        score -= 10  # Prefer compilations only when explicitly requested

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


def choose_best(row, results):

    best = None
    best_score = float("-inf")

    for r in results:
        score = score_result(row, r)
        if score > best_score:
            best_score = score
            best = r

    return best, best_score


def process_row(row):

    tipo = str(
        row.get(
            "TIPO",
            ""
        )
    ).lower()

    if is_collection(tipo):

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
            allow_compilation=False
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

            return (
                "track",
                best["id"]
            )

    return None

def like_track(track_id):

    spotify_call(
        sp.current_user_saved_tracks_add,
        [track_id]
    )

    time.sleep(0.2)
    
def is_collection(tipo):
    if not tipo:
        return False

    tipo = str(tipo).lower()

    return any(x in tipo for x in [
    "album", "álbum", "ep", "compilacao", "coletanea"
])

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

    # usar só o artista principal
    main_artist = split_artists(artista)[0]

    query = (
        f"album:{nome} "
        f"artist:{main_artist}"
    )

    try:

        results = spotify_call(
            sp.search,
            q=query,
            type="album",
            limit=10
        )

        albums = results["albums"]["items"]

        # remover duplicados (Spotify costuma retornar
        # deluxe, remaster, versões repetidas etc.)
        seen = set()
        filtered = []

        for album in albums:

            album_id = album["id"]

            if album_id in seen:
                continue

            seen.add(album_id)

            album_name = album["name"].lower()

            # remover algumas versões ruins
            if any(x in album_name for x in [
                "karaoke",
                "instrumental",
                "commentary"
            ]):
                continue

            filtered.append(album)

        album_search_cache[cache_key] = filtered

        return filtered

    except Exception as e:

        print(
            f"Erro buscando álbum: {nome} - {artista}"
        )

        print(e)

        return []

def add_album(album_id):

    ids = []
    seen_tracks = set()

    offset = 0

    while True:

        results = spotify_call(
            sp.album_tracks,
            album_id,
            limit=50,
            offset=offset
        )

        tracks = sorted(
            results.get("items", []),
            key=lambda t: t.get(
                "track_number",
                0
            )
        )

        for t in tracks:

            track_id = t.get("id")

            if not track_id:
                continue

            if track_id in seen_tracks:
                continue

            seen_tracks.add(track_id)
            ids.append(track_id)

        if len(tracks) < 50:
            break

        offset += 50

    BATCH_SIZE = 5

    for i in range(
        0,
        len(ids),
        BATCH_SIZE
    ):

        spotify_call(
            sp.current_user_saved_tracks_add,
            ids[i:i+BATCH_SIZE]
        )

    print(
        f"Álbum adicionado ({len(ids)} músicas)"
    )

    time.sleep(2)

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

def delete_all_saved_tracks():

    print("Apagando todas as músicas salvas do Spotify...")

    all_ids = []
    offset = 0

    while True:

        results = spotify_call(
            sp.current_user_saved_tracks,
            limit=50,
            offset=offset
        )

        items = results.get("items", [])

        if not items:
            break

        for item in items:

            track = item.get("track")

            if track and track.get("id"):
                all_ids.append(
                    track["id"]
                )

        offset += len(items)

    if not all_ids:

        print(
            "Nenhuma música salva encontrada."
        )

        return

    total = len(all_ids)

    # usar 20 em vez de 50
    BATCH_SIZE = 20

    for i in range(
        0,
        total,
        BATCH_SIZE
    ):

        batch = all_ids[
            i:i+BATCH_SIZE
        ]

        spotify_call(
            sp.current_user_saved_tracks_delete,
            batch
        )

        print(
            f"Removidas {min(i+BATCH_SIZE,total)}/{total}"
        )

    print(
        f"{total} músicas removidas com sucesso."
    )

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

            unique_id = f"{row['NOME']}|{row['ARTISTAS/GRUPO']}"

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

                        add_album(
                            spotify_id
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
