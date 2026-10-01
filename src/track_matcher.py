import re

from src.utils import similar, split_artists, match_year, match_date
from src.spotify_client import sp, spotify_call


VARIANT_PATTERNS = [
    r"\bmix\b",
    r"\bsingle\s*(?:ver(?:sion)?\.?)($|\s)",
    r"\bclassic\b",
    r"\bradio\s+edit\b",
    r"\bextended(?:\s+mix|\s+version)?\b",
    r"\bclub\s+(?:mix|version)\b",
    r"\bkaraoke\b",
    r"\binstrumental\b",
    r"\bacoustic\b",
    r"\blive\b",
    r"\bao\s+vivo\b",
    r"\bperformance\b",
    r"\bsession\b",
    r"\bcommentary\b",
    r"\bsped\s+up\b",
    r"\bslowed(?:\s+down)?\b",
    r"\bnightcore\b",
]

CONTEXT_PATTERNS = [
    r"\bvideo\b",
    r"\bvideoclipe\b",
    r"\bmusic\s+video\b",
    r"\bofficial\s+(?:music\s+)?video\b",
    r"\blive\b",
    r"\bao\s+vivo\b",
    r"\bkaraoke\b",
    r"\binstrumental\b",
    r"\bperformance\b",
    r"\bsession\b",
    r"\bcommentary\b",
    r"\bacoustic\b",
]


def search_spotify(track, artist, allow_compilation=False, search_cache=None):
    if search_cache is None:
        search_cache = {}

    def execute_search(title):
        query = f"track:{title} artist:{artist}".lower().strip()
        cache_key = f"{query}|allow_compilation={allow_compilation}"

        if cache_key in search_cache:
            return search_cache[cache_key]

        results = spotify_call(sp.search, q=query, type="track", limit=25)
        items = results["tracks"]["items"]

        if not allow_compilation:
            items = [
                item
                for item in items
                if item.get("album", {}).get("album_type", "") != "compilation"
            ]

        search_cache[cache_key] = items
        return items

    results = execute_search(track)

    if results:
        return results

    # Fallback para títulos do tipo:
    # Double Life - From "Despicable Me 4"
    simplified = re.sub(
        r"\s*[-–—]?\s*\(?\s*from\b.*$",
        "",
        str(track),
        flags=re.IGNORECASE,
    ).strip()

    if simplified and simplified.lower() != str(track).lower().strip():
        print(f"Busca simplificada: '{track}' -> '{simplified}'")
        return execute_search(simplified)

    return results


def _contains(text, pattern):
    return bool(re.search(pattern, str(text), flags=re.IGNORECASE))


def _normalize_track_title(name):
    """
    Remove apenas complementos de participação usados como metadado
    no fim do título.

    Exemplos:
        Under Pressure
        Under Pressure (feat. David Bowie)

    passam a ser comparados como o mesmo título principal.

    Remix, Mix, Live, Remastered etc. NÃO são removidos aqui.
    """

    name = str(name).lower().strip()

    feat_patterns = [
        r"\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring)\s+[^)\]]+[\)\]]\s*$",
        r"\s*[-–—]\s*(?:feat\.?|ft\.?|featuring)\s+.+$",
        r"\s+(?:feat\.?|ft\.?|featuring)\s+.+$",
    ]

    for pattern in feat_patterns:
        name = re.sub(
            pattern,
            "",
            name,
            flags=re.IGNORECASE,
        ).strip()

    return name


def _has_unrequested_pattern(wanted_name, text, patterns):
    return any(
        _contains(text, pattern) and not _contains(wanted_name, pattern)
        for pattern in patterns
    )


def _has_unrequested_variant(wanted_name, result_name):
    if _has_unrequested_pattern(wanted_name, result_name, VARIANT_PATTERNS):
        return True

    # Bloqueia títulos com ano acrescentado, por exemplo "- 2024",
    # quando esse ano não fazia parte do título pedido.
    result_years = set(re.findall(r"\b(?:19|20)\d{2}\b", str(result_name)))
    wanted_years = set(re.findall(r"\b(?:19|20)\d{2}\b", str(wanted_name)))

    return bool(result_years - wanted_years)


def score_result(row, result):
    wanted_name = str(row["NOME"]).lower().strip()
    track_name = str(result.get("name", "")).lower().strip()

    album = result.get("album", {})
    album_name = str(album.get("name", "")).lower().strip()

    result_artists = [
        artist.get("name", "")
        for artist in result.get("artists", [])
    ]
    artist_names = " ".join(result_artists).lower()
    combined = f"{track_name} {album_name} {artist_names}"

    # Remix continua sendo tratado de forma simétrica.
    wanted_remix = "remix" in wanted_name
    result_is_remix = "remix" in combined

    if result_is_remix != wanted_remix:
        return -1000

    # Remaster é diferente: "Remastered" apenas no nome do álbum
    # não elimina uma faixa normal.
    wanted_remaster = "remaster" in wanted_name
    track_is_remaster = "remaster" in track_name
    album_is_remaster = "remaster" in album_name

    if track_is_remaster and not wanted_remaster:
        return -1000

    if wanted_remaster and not (track_is_remaster or album_is_remaster):
        return -1000

    # Mix, Single ver., classic, karaoke etc. no título da faixa.
    if _has_unrequested_variant(wanted_name, track_name):
        return -1000

    # Preserva a proteção antiga contra versões ao vivo,
    # acústicas, instrumentais etc. também no contexto do álbum.
    if _has_unrequested_pattern(wanted_name, combined, CONTEXT_PATTERNS):
        return -1000

    normalized_wanted = _normalize_track_title(wanted_name)
    normalized_track = _normalize_track_title(track_name)

    name_similarity = similar(
        normalized_wanted,
        normalized_track,
    )

    if name_similarity < 0.45:
        return -1000

    score = name_similarity * 40

    if normalized_track == normalized_wanted:
        score += 60

    if wanted_remaster and (track_is_remaster or album_is_remaster):
        score += 35

    if wanted_remix and result_is_remix:
        score += 25

    sheet_artists = split_artists(row["ARTISTAS/GRUPO"])
    main_sheet = sheet_artists[0] if sheet_artists else ""
    main_result = result_artists[0] if result_artists else ""

    if similar(main_sheet, main_result) > 0.9:
        score += 50
    elif any(
        similar(sheet_artist, result_artist) > 0.8
        for sheet_artist in sheet_artists
        for result_artist in result_artists
    ):
        score += 20
    else:
        return -1000

    # Explicit é preferência secundária.
    if result.get("explicit", False):
        score += 10

    spotify_date = album.get("release_date", "")

    if match_date(row["ESTREIA"], spotify_date):
        score += 50
    elif match_year(row["ESTREIA"], spotify_date):
        score += 30
    else:
        score -= 50

    # TIPO=Single na planilha significa "uma faixa",
    # não "obrigatoriamente um release album_type=single".
    album_type = album.get("album_type", "")

    if album_type == "album":
        score += 15
    elif album_type == "compilation":
        score -= 50

    return score


def _same_track_identity(row, result):
    wanted_name = _normalize_track_title(
        row["NOME"]
    )
    result_name = _normalize_track_title(
        result.get("name", "")
    )

    if similar(wanted_name, result_name) < 0.92:
        return False

    sheet_artists = split_artists(row["ARTISTAS/GRUPO"])
    result_artists = [
        artist.get("name", "")
        for artist in result.get("artists", [])
    ]

    if not sheet_artists or not result_artists:
        return False

    if similar(sheet_artists[0], result_artists[0]) > 0.9:
        return True

    return any(
        similar(sheet_artist, result_artist) > 0.8
        for sheet_artist in sheet_artists
        for result_artist in result_artists
    )


def choose_best(row, results):
    valid_results = []

    for result in results:
        score = score_result(row, result)

        if score > -1000:
            valid_results.append((result, score))

    if not valid_results:
        return None, float("-inf")

    wanted_name = _normalize_track_title(
        row["NOME"]
    )

    # "(feat. Artista)" no fim do nome é tratado como metadado.
    # Outras versões (Mix, Live, Remix etc.) continuam diferentes.
    exact_results = [
        (result, score)
        for result, score in valid_results
        if _normalize_track_title(
            result.get("name", "")
        ) == wanted_name
    ]

    candidate_pool = exact_results or valid_results

    if exact_results:
        print("Correspondência exata de título encontrada.")

    # Entre candidatos equivalentes, mantém a preferência pela
    # ocorrência da música dentro de um álbum oficial.
    album_versions = [
        (result, score)
        for result, score in candidate_pool
        if result.get("album", {}).get("album_type", "") == "album"
        and _same_track_identity(row, result)
    ]

    if album_versions:
        best, best_score = max(album_versions, key=lambda item: item[1])

        print(
            "Preferindo ocorrência presente no álbum:",
            best.get("album", {}).get("name", ""),
        )

        return best, best_score

    return max(candidate_pool, key=lambda item: item[1])
