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
        .strip()
    )

    album_name = (
        result.get("album", {})
        .get("name", "")
        .lower()
        .strip()
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
    ).lower().strip()

    # ---------------------------------------------------------
    # REMIX
    # ---------------------------------------------------------
    # Só aceita remix quando a própria planilha pede remix.
    wanted_remix = "remix" in wanted_name
    result_is_remix = "remix" in combined

    if result_is_remix and not wanted_remix:
        return -1000

    # Se a planilha pediu remix, evita escolher a versão normal.
    if wanted_remix and not result_is_remix:
        return -1000

    # ---------------------------------------------------------
    # REMASTER / REMASTERED
    # ---------------------------------------------------------
    # Antes, "remaster" e "remastered" estavam em blocked_terms,
    # então QUALQUER versão remasterizada recebia -1000, mesmo
    # quando a planilha pedia explicitamente essa versão.
    wanted_remaster = (
        "remaster" in wanted_name
        or "remastered" in wanted_name
    )

    result_is_remaster = (
        "remaster" in track_name
        or "remastered" in track_name
        or "remaster" in album_name
        or "remastered" in album_name
    )

    # Se a planilha não pediu remaster, evita versões remasterizadas.
    if result_is_remaster and not wanted_remaster:
        return -1000

    # Se a planilha pediu remaster, não deixa uma versão normal vencer.
    if wanted_remaster and not result_is_remaster:
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
        "acoustic"
    ]

    if any(
        term in combined
        for term in blocked_terms
    ):
        return -1000

    # ---------------------------------------------------------
    # NOME
    # ---------------------------------------------------------
    similarity = similar(
        wanted_name,
        track_name
    )

    # Resultado extremamente diferente não deve disputar só por
    # artista/data parecidos.
    if similarity < 0.45:
        return -1000

    if track_name == wanted_name:
        score += 60

    score += similarity * 40

    # Bônus específico quando a planilha realmente pediu remaster.
    if wanted_remaster and result_is_remaster:
        score += 35

    # Bônus específico quando a planilha realmente pediu remix.
    if wanted_remix and result_is_remix:
        score += 25

    # ---------------------------------------------------------
    # ARTISTAS
    # ---------------------------------------------------------
    result_artists = [
        a["name"]
        for a in result.get(
            "artists",
            []
        )
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
        return -1000

    # Explicit é apenas preferência secundária.
    if result.get(
        "explicit",
        False
    ):
        score += 10

    # ---------------------------------------------------------
    # DATA
    # ---------------------------------------------------------
    spotify_date = (
        result.get("album", {})
        .get("release_date", "")
    )

    if match_date(
        row["ESTREIA"],
        spotify_date
    ):

        score += 50

    elif match_year(
        row["ESTREIA"],
        spotify_date
    ):

        score += 30

    else:
        score -= 50

    # ---------------------------------------------------------
    # TIPO DO LANÇAMENTO
    # ---------------------------------------------------------
    album_type = (
        result.get("album", {})
        .get("album_type", "")
    )

    user_wants_single = is_single(
        row.get("TIPO", "")
    )

    if user_wants_single:

        if album_type == "single":
            score += 40

        elif album_type == "album":
            score -= 10

        elif album_type == "compilation":
            score -= 50

    else:

        if album_type == "album":
            score += 20

        elif album_type == "single":
            score -= 10

        elif album_type == "compilation":
            score -= 50

    return score


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


def choose_best(row, results):

    best = None
    best_score = float("-inf")

    for r in results:

        score = score_result(
            row,
            r
        )

        # -1000 significa que o resultado foi rejeitado.
        # Antes, se TODOS os resultados fossem -1000,
        # o primeiro deles ainda acabava sendo escolhido.
        if score <= -1000:
            continue

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

def like_track(track_id):

    spotify_call(
        sp.current_user_saved_tracks_add,
        [track_id]
    )

    time.sleep(0.2)
    
def is_single(tipo):
    if not tipo:
        return False

    tipo = str(tipo).strip().lower()

    return "single" in tipo


def is_compilation(tipo):
    if not tipo:
        return False

    tipo = str(tipo).strip().lower()

    return any(
        x in tipo
        for x in [
            "compilacao",
            "compilação",
            "coletanea",
            "coletânea",
            "compilation"
        ]
    )


def is_collection(tipo):
    if not tipo:
        return False

    tipo = str(tipo).strip().lower()

    return (
        "album" in tipo
        or "álbum" in tipo
        or "ep" in tipo
        or is_compilation(tipo)
    )


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


def parse_discs(value):
    """
    Interpreta a coluna DISCO da planilha.

    Exemplos aceitos:
      vazio / NaN -> None (todos os discos)
      1           -> {1}
      2           -> {2}
      1,2         -> {1, 2}
      1.2         -> {1, 2}  # caso o Excel converta 1,2 para decimal
      1,2,4       -> {1, 2, 4}
      1.2.4       -> {1, 2, 4}
    """
    if value is None or pd.isna(value):
        return None

    value = str(value).strip()

    if not value:
        return None

    # Se o Excel leu um único disco como número decimal inteiro:
    # 1.0 -> 1
    # 2.0 -> 2
    if re.fullmatch(r"\d+\.0+", value):
        value = value.split(".")[0]

    # Aceita vírgula OU ponto como separador.
    # Isso resolve casos em que o Excel transforma "1,2" em 1.2.
    parts = re.split(r"[,.]", value)

    discs = set()

    for part in parts:
        part = part.strip()

        if not part:
            continue

        if not part.isdigit():
            raise ValueError(
                f"Valor inválido na coluna DISCO: '{value}'. "
                "Use números separados por vírgula, por exemplo: 1 ou 1,2."
            )

        disc = int(part)

        if disc < 1:
            raise ValueError(
                f"Valor inválido na coluna DISCO: '{value}'. "
                "Os discos devem começar em 1."
            )

        discs.add(disc)

    return discs if discs else None



def add_album(album_id, selected_discs=None):

    ids = []
    seen_tracks = set()
    found_discs = set()

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

        # Ordena por disco e, dentro dele, pelo número da faixa.
        tracks = sorted(
            tracks,
            key=lambda t: (
                t.get("disc_number", 1),
                t.get("track_number", 0)
            )
        )

        for t in tracks:

            disc_number = t.get("disc_number", 1)
            found_discs.add(disc_number)

            # Se a coluna DISCO estiver preenchida,
            # ignora qualquer faixa que não pertença aos discos escolhidos.
            if (
                selected_discs is not None
                and disc_number not in selected_discs
            ):
                continue

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

    # Mostra no terminal o que o código realmente interpretou.
    print(
        "Discos encontrados no Spotify:",
        ", ".join(str(d) for d in sorted(found_discs))
        if found_discs else "nenhum"
    )

    if selected_discs is None:

        print(
            "DISCO na planilha: vazio -> adicionando todos os discos."
        )

    else:

        print(
            "DISCO na planilha:",
            ", ".join(str(d) for d in sorted(selected_discs))
        )

        missing_discs = selected_discs - found_discs

        if missing_discs:
            print(
                "AVISO: disco(s) solicitado(s) não encontrado(s): "
                + ", ".join(
                    str(d)
                    for d in sorted(missing_discs)
                )
            )

    if not ids:

        print(
            "Nenhuma faixa encontrada para o(s) disco(s) selecionado(s)."
        )
        return

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
