import re

from utils import (
    similar,
    split_artists,
    match_year,
    match_date,
    is_single,
)

from spotify_client import (
    sp,
    spotify_call,
)


def search_spotify(track, artist, allow_compilation=False, search_cache=None):

    if search_cache is None:
        search_cache = {}

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

