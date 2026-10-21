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

    track_text = str(track).strip()
    artist_text = str(artist).strip()

    def execute_search(title):
        query = f"track:{title} artist:{artist_text}".lower().strip()
        cache_key = f"{query}|allow_compilation={allow_compilation}"
        if cache_key in search_cache:
            return search_cache[cache_key]

        results = spotify_call(sp.search, q=query, type="track", limit=25)
        items = results.get("tracks", {}).get("items", [])
        if not allow_compilation:
            items = [
                item for item in items
                if item.get("album", {}).get("album_type", "") != "compilation"
            ]
        search_cache[cache_key] = items
        return items

    results = execute_search(track_text)
    if results:
        return results

    simplified = re.sub(
        r"\s*[-–—]?\s*\(?\s*from\b.*$", "", track_text,
        flags=re.IGNORECASE,
    ).strip()
    if simplified and simplified.lower() != track_text.lower():
        print(f"Busca simplificada: '{track_text}' -> '{simplified}'")
        return execute_search(simplified)
    return results


def _contains(text, pattern):
    return bool(re.search(pattern, str(text), flags=re.IGNORECASE))


def _normalize_track_title(name):
    """Normaliza título para comparação, removendo apenas feat./ft. final."""
    name = str(name).lower().strip()
    patterns = [
        # Participações no fim do título: "Song (feat. Artist)", "Song ft Artist"
        r"\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s+[^)\]]+[)\]]\s*$",
        r"\s*[-–—]\s*(?:feat\.?|ft\.?|featuring|with)\s+.+$",
        r"\s+(?:feat\.?|ft\.?|featuring)\s+.+$",
    ]
    for pattern in patterns:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE).strip()
    return name


def _has_unrequested_pattern(wanted_name, text, patterns):
    return any(
        _contains(text, pattern) and not _contains(wanted_name, pattern)
        for pattern in patterns
    )


def _has_unrequested_variant(wanted_name, result_name):
    if _has_unrequested_pattern(wanted_name, result_name, VARIANT_PATTERNS):
        return True
    result_years = set(re.findall(r"\b(?:19|20)\d{2}\b", str(result_name)))
    wanted_years = set(re.findall(r"\b(?:19|20)\d{2}\b", str(wanted_name)))
    return bool(result_years - wanted_years)


def _artist_names(artists):
    return [str(a.get("name", "")).strip() for a in artists or [] if a.get("name")]


def _artist_match_score(wanted_artist, candidate_artist):
    if not wanted_artist or not candidate_artist:
        return 0
    return similar(str(wanted_artist), str(candidate_artist))


def _main_sheet_artist(row):
    artists = split_artists(str(row.get("ARTISTAS/GRUPO", "")))
    return str(artists[0]).strip() if artists else ""


def _album_artist_matches_main(row, result):
    main_artist = _main_sheet_artist(row)
    album_artists = _artist_names(result.get("album", {}).get("artists", []))
    return any(_artist_match_score(main_artist, artist) > 0.85 for artist in album_artists)


def _is_single_row(row):
    return str(row.get("TIPO", "")).strip().lower() == "single"


def score_result(row, result):
    wanted_name = str(row.get("NOME", "")).lower().strip()
    track_name = str(result.get("name", "")).lower().strip()
    album = result.get("album", {}) or {}
    album_name = str(album.get("name", "")).lower().strip()
    result_artists = _artist_names(result.get("artists", []))
    artist_names = " ".join(result_artists).lower()
    combined = f"{track_name} {album_name} {artist_names}"

    wanted_remix = "remix" in wanted_name
    result_is_remix = "remix" in combined
    if result_is_remix != wanted_remix:
        return -1000

    wanted_remaster = "remaster" in wanted_name
    track_is_remaster = "remaster" in track_name
    album_is_remaster = "remaster" in album_name
    if track_is_remaster and not wanted_remaster:
        return -1000
    if wanted_remaster and not (track_is_remaster or album_is_remaster):
        return -1000

    if _has_unrequested_variant(wanted_name, track_name):
        return -1000
    if _has_unrequested_pattern(wanted_name, combined, CONTEXT_PATTERNS):
        return -1000

    normalized_wanted = _normalize_track_title(wanted_name)
    normalized_track = _normalize_track_title(track_name)
    name_similarity = similar(normalized_wanted, normalized_track)
    if name_similarity < 0.45:
        return -1000

    sheet_artists = split_artists(str(row.get("ARTISTAS/GRUPO", "")))
    if not sheet_artists or not result_artists:
        return -1000

    # A candidate must match the requested main artist among the TRACK artists.
    # Matching only an unrelated album artist is not enough.
    main_sheet = str(sheet_artists[0]).strip()
    artist_scores = [_artist_match_score(main_sheet, artist) for artist in result_artists]
    main_artist_score = max(artist_scores, default=0)
    if main_artist_score <= 0.8:
        return -1000

    score = name_similarity * 40
    if normalized_track == normalized_wanted:
        score += 60
    if wanted_remaster and (track_is_remaster or album_is_remaster):
        score += 35
    if wanted_remix and result_is_remix:
        score += 25

    if main_artist_score > 0.9:
        score += 50
    else:
        score += 20

    # Other listed artists are positive evidence, but not required when the
    # Spotify track metadata omits a featured artist.
    for sheet_artist in sheet_artists[1:]:
        if any(_artist_match_score(sheet_artist, artist) > 0.8 for artist in result_artists):
            score += 15

    if result.get("explicit", False):
        score += 2

    # Data é evidência adicional, não requisito de identidade.
    # Isso permite selecionar edições comemorativas/remasterizadas quando
    # a edição original não está disponível no Spotify.
    spotify_date = album.get("release_date", "")
    if match_date(row.get("ESTREIA", ""), spotify_date):
        score += 10
    elif match_year(row.get("ESTREIA", ""), spotify_date):
        score += 5

    album_type = album.get("album_type", "")
    if album_type == "album":
        score += 5
    elif album_type == "compilation":
        score -= 50

    return score


def _same_track_identity(row, result):
    wanted_name = _normalize_track_title(row.get("NOME", ""))
    result_name = _normalize_track_title(result.get("name", ""))
    if similar(wanted_name, result_name) < 0.92:
        return False

    sheet_artists = split_artists(str(row.get("ARTISTAS/GRUPO", "")))
    result_artists = _artist_names(result.get("artists", []))
    if not sheet_artists or not result_artists:
        return False
    return max(
        (_artist_match_score(sheet_artists[0], artist) for artist in result_artists),
        default=0,
    ) > 0.8


def choose_best(row, results):
    valid_results = []
    for result in results:
        score = score_result(row, result)
        if score > -1000:
            valid_results.append((result, score))

    if not valid_results:
        return None, float("-inf")

    wanted_name = _normalize_track_title(row.get("NOME", ""))
    exact_results = [
        (result, score) for result, score in valid_results
        if _normalize_track_title(result.get("name", "")) == wanted_name
    ]
    candidate_pool = exact_results or valid_results
    if exact_results:
        print("Correspondência exata de título normalizado encontrada.")

    # A identidade é decidida nesta ordem:
    # 1. título normalizado (quando há correspondência exata);
    # 2. compatibilidade dos artistas, já validada e pontuada em score_result;
    # 3. data como bônus, nunca como filtro;
    # 4. pequenas preferências de lançamento, sem sobrepor título/artistas.
    #
    # Não forçamos album_type="single" quando TIPO=Single na planilha:
    # nesse contexto, Single significa uma faixa individual, não o tipo
    # de lançamento do Spotify.
    return max(candidate_pool, key=lambda item: item[1])
