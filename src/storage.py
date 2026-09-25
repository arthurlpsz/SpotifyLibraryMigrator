import json
import os


PROGRESS_FILE = "progress.json"
CACHE_FILE = "spotify_cache.json"

artist_id_cache = {}
search_cache = {}
album_search_cache = {}


def load_cache():
    """
    Carrega o cache salvo anteriormente sem substituir os objetos
    de dicionário. Isso mantém as mesmas referências usadas pelos
    outros módulos durante toda a execução.
    """
    if not os.path.exists(CACHE_FILE):
        return

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    artist_id_cache.clear()
    artist_id_cache.update(
        cache.get("artist", {})
    )

    search_cache.clear()
    search_cache.update(
        cache.get("search", {})
    )

    album_search_cache.clear()
    album_search_cache.update(
        cache.get("album", {})
    )


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(
            PROGRESS_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return set(
                json.load(f)["processed"]
            )

    return set()


def save_progress(processed_ids):
    with open(
        PROGRESS_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            {
                "processed": list(
                    processed_ids
                )
            },
            f
        )


def save_cache():
    with open(
        CACHE_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            {
                "artist": artist_id_cache,
                "search": search_cache,
                "album": album_search_cache
            },
            f
        )


# Mantém o mesmo comportamento anterior:
# o cache é carregado assim que o módulo é importado.
load_cache()
