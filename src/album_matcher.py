from src.utils import (
    similar,
    split_artists,
    match_year,
    match_date,
    is_compilation,
)

from src.spotify_client import (
    sp,
    spotify_call,
)


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

def search_album(nome, artista, tipo="", album_search_cache=None):

    if album_search_cache is None:
        album_search_cache = {}

    nome_texto = str(nome).strip()
    artista_texto = str(artista).strip()
    tipo_texto = str(tipo).strip()

    cache_key = (
        f"{nome_texto.lower()}|"
        f"{artista_texto.lower()}|"
        f"{tipo_texto.lower()}"
    )

    if cache_key in album_search_cache:
        return album_search_cache[cache_key]

    artists = split_artists(artista_texto)
    main_artist = artists[0] if artists else ""
    user_wants_compilation = is_compilation(tipo_texto)

    queries = [
        f"album:{nome_texto} artist:{main_artist}"
    ]

    # Compilações frequentemente aparecem como "Various Artists".
    # Nesses casos também buscamos apenas pelo título.
    if user_wants_compilation:
        queries.append(
            f"album:{nome_texto}"
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

                album_name = str(
                    album.get("name", "")
                ).lower()

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
            f"Erro buscando álbum: {nome_texto} - {artista_texto}"
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

