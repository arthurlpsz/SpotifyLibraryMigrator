import re

from src.utils import (
    similar,
    split_artists,
    match_year,
    match_date,
)

from src.spotify_client import (
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

    if result_is_remaster and not wanted_remaster:
        return -200

    if wanted_remaster and not result_is_remaster:
        return -200

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
    # A coluna TIPO da planilha identifica que esta linha é uma
    # música/single, mas isso NÃO significa que a faixa correta
    # precisa vir de um release do tipo "single".
    #
    # Quando a mesma gravação existe dentro de um álbum completo,
    # a versão do álbum é preferível. Isso evita pegar capas de
    # singles/EPs promocionais quando a música também faz parte
    # do álbum do artista.
    album_type = (
        result.get("album", {})
        .get("album_type", "")
    )

    if album_type == "album":
        score += 15

    elif album_type == "single":
        # Continua sendo um candidato válido. Só não recebe o
        # bônus artificial que antes fazia singles/EPs vencerem.
        score += 0

    elif album_type == "compilation":
        score -= 50

    return score

def _same_track_identity(row, result):
    """
    Verifica se o resultado parece ser realmente a mesma música
    antes de aplicar a preferência pela versão presente em álbum.
    """

    wanted_name = str(
        row["NOME"]
    ).lower().strip()

    result_name = str(
        result.get("name", "")
    ).lower().strip()

    # Exigimos uma correspondência forte do título.
    if similar(
        wanted_name,
        result_name
    ) < 0.92:
        return False

    sheet_artists = split_artists(
        row["ARTISTAS/GRUPO"]
    )

    result_artists = [
        a.get("name", "")
        for a in result.get(
            "artists",
            []
        )
    ]

    if not sheet_artists or not result_artists:
        return False

    main_sheet = sheet_artists[0]
    main_result = result_artists[0]

    if similar(
        main_sheet,
        main_result
    ) > 0.9:
        return True

    return any(
        similar(sa, ra) > 0.8
        for sa in sheet_artists
        for ra in result_artists
    )


def choose_best(row, results):

    valid_results = []

    for r in results:

        score = score_result(
            row,
            r
        )

        # -1000 significa que o candidato foi rejeitado por nome,
        # artista, remix/remaster incompatível etc.
        if score <= -1000:
            continue

        valid_results.append(
            (r, score)
        )

    if not valid_results:
        return None, float("-inf")

    # ---------------------------------------------------------
    # PREFERÊNCIA POR FAIXA DO ÁLBUM
    # ---------------------------------------------------------
    # Se a mesma música, do mesmo artista, também aparece em um
    # álbum completo, priorizamos essa ocorrência.
    #
    # Isso evita selecionar releases isolados que usam capas de
    # single/EP quando a faixa faz parte do álbum oficial.
    album_versions = [
        (result, score)
        for result, score in valid_results
        if (
            result.get("album", {}).get(
                "album_type",
                ""
            ) == "album"
            and _same_track_identity(
                row,
                result
            )
        )
    ]

    if album_versions:

        best, best_score = max(
            album_versions,
            key=lambda item: item[1]
        )

        print(
            "Preferindo versão presente no álbum:",
            best.get("album", {}).get(
                "name",
                ""
            )
        )

        return best, best_score

    # Se a música não existir em nenhum álbum compatível,
    # usa normalmente o melhor single/release encontrado.
    best, best_score = max(
        valid_results,
        key=lambda item: item[1]
    )

    return best, best_score
