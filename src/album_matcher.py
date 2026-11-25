from src.utils import similar,split_artists,match_year,match_date,is_compilation
from src.spotify_client import sp, spotify_call


def score_album_result(row, album):
    score = 0

    tipo_planilha = row.get("TIPO", "")
    user_wants_compilation = is_compilation(tipo_planilha)

    album_type = album.get("album_type", "")

    # Nome do álbum
    name_similarity = similar(
        str(row["NOME"]),
        str(album["name"])
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

        score += 25

    elif match_year(
        row["ESTREIA"],
        album["release_date"]
    ):

        score += 15

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

        try:
            difference = abs(
                expected_tracks - int(spotify_tracks)
            )
        except (TypeError, ValueError):
            difference = None

        if difference == 0:
            score += 30

        elif difference is not None and difference <= 2:
            score += 15

        elif difference is not None and difference <= 5:
            score += 5

        elif difference is not None:
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

def choose_best_album(row, results, debug=False):

    if not results:
        if debug:
            print("Nenhum álbum retornado pelo Spotify.")

        return None

    scored = []

    if debug:
        print("\nCandidatos de álbuns encontrados:")

    for album in results:
        score = score_album_result(row, album)
        scored.append((album, score))

        if debug:
            artists = ", ".join(
                artist.get("name", "")
                for artist in album.get("artists", [])
            )

            status = (
                "APROVADO"
                if score >= 40
                else "REJEITADO: pontuação abaixo de 40"
            )

            print(
                f"- {album.get('name')} "
                f"| {artists} "
                f"| Score: {score} "
                f"| {status}"
            )

    best_score = max(score for _, score in scored)

    if best_score < 40:
        if debug:
            print(
                f"Nenhum álbum atingiu a pontuação mínima. "
                f"Melhor pontuação: {best_score}."
            )

        return None

    tied = [
        album
        for album, score in scored
        if score == best_score
    ]

    if len(tied) == 1:
        if debug:
            print(
                f"Melhor álbum selecionado: {tied[0]['name']} "
                f"(score: {best_score})"
            )

        return tied[0]

    if debug:
        print(
            f"Empate entre {len(tied)} álbuns. "
            "Verificando versões explicit..."
        )

    explicit_info = {}

    for album in tied:
        explicit_count, total = count_explicit_tracks(album["id"])

        explicit_info[album["id"]] = (
            explicit_count,
            total
        )

        if debug:
            print(
                f"{album['name']} "
                f"-> {explicit_count}/{total} explicit"
            )

    return max(
        tied,
        key=lambda album: explicit_info[album["id"]][0]
    )

def _collect_albums(query):
    results = spotify_call(
        sp.search,
        q=query,
        type="album",
        limit=20
    )
    albums = []
    for album in results.get("albums", {}).get("items", []):
        album_id = album.get("id")
        if not album_id:
            continue
        album_name = str(album.get("name", "")).lower()
        if any(
            term in album_name
            for term in ("karaoke", "instrumental", "commentary")
        ):
            continue
        albums.append(album)
    return albums


def search_album(nome, artista, tipo="", album_search_cache=None):
    if album_search_cache is None:
        album_search_cache = {}

    nome_texto = str(nome).strip()
    artista_texto = str(artista).strip()
    tipo_texto = str(tipo).strip()
    artists = split_artists(artista_texto)
    main_artist = artists[0] if artists else ""

    cache_key = (
        f"{nome_texto.lower()}|{artista_texto.lower()}|{tipo_texto.lower()}"
    )
    if cache_key in album_search_cache:
        return album_search_cache[cache_key]

    # Primeira tentativa: título e artista principal.
    albums = _collect_albums(
        f"album:{nome_texto} artist:{main_artist}"
    )
    album_search_cache[cache_key] = albums
    return albums


def search_album_fallback(nome, album_search_cache=None):
    """Segunda tentativa: pesquisa apenas pelo título, com cache separado."""
    if album_search_cache is None:
        album_search_cache = {}

    nome_texto = str(nome).strip()
    cache_key = f"fallback|album:{nome_texto.lower()}"
    if cache_key in album_search_cache:
        return album_search_cache[cache_key]

    albums = _collect_albums(f"album:{nome_texto}")
    album_search_cache[cache_key] = albums
    return albums

def get_expected_track_count(row):

    try:

        qtd = row.get("QTD")

        if qtd is None:
            return None

        if str(qtd).strip() == "":
            return None

        return int(float(qtd))

    except (TypeError, ValueError):

        return None

