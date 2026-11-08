import os
import time
from getpass import getpass
from pathlib import Path

import keyring
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException


SERVICE_NAME = "spotify-library-migrator"

TOKEN_DIR = Path.home() / ".spotify-library-migrator"
TOKEN_CACHE = TOKEN_DIR / "spotify_oauth_cache"

TOKEN_DIR.mkdir(
    parents=True,
    exist_ok=True
)


def _clean_value(value):
    """
    Remove espaços e aspas colocadas por engano.

    Exemplo:
        "abc123" -> abc123
        'abc123' -> abc123
    """

    if value is None:
        return None

    value = str(value).strip()

    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {'"', "'"}
    ):
        value = value[1:-1].strip()

    return value


def _get_saved_credential(
    env_name,
    prompt,
    secret=False,
    default=None
):
    """
    Ordem:
    1. variável de ambiente;
    2. Gerenciador de Credenciais do Windows;
    3. pergunta uma vez e salva.

    Valores antigos com aspas são corrigidos automaticamente.
    """

    env_value = _clean_value(
        os.getenv(env_name)
    )

    if env_value:
        keyring.set_password(
            SERVICE_NAME,
            env_name,
            env_value
        )
        return env_value

    saved_value = _clean_value(
        keyring.get_password(
            SERVICE_NAME,
            env_name
        )
    )

    if saved_value:

        # Regrava o valor já limpo caso a versão anterior
        # estivesse salva com aspas.
        keyring.set_password(
            SERVICE_NAME,
            env_name,
            saved_value
        )

        return saved_value

    label = (
        f"{prompt} [{default}]: "
        if default is not None
        else f"{prompt}: "
    )

    if secret:
        value = getpass(label)
    else:
        value = input(label)

    value = _clean_value(value)

    if not value and default is not None:
        value = default

    if not value:
        raise ValueError(
            f"{env_name} não pode ficar vazio."
        )

    keyring.set_password(
        SERVICE_NAME,
        env_name,
        value
    )

    print(
        f"{env_name} salvo com segurança neste computador."
    )

    return value


client_id = _get_saved_credential(
    "SPOTIPY_CLIENT_ID",
    "Spotify Client ID"
)

client_secret = _get_saved_credential(
    "SPOTIPY_CLIENT_SECRET",
    "Spotify Client Secret",
    secret=True
)

redirect_uri = _get_saved_credential(
    "SPOTIPY_REDIRECT_URI",
    "Spotify Redirect URI",
    default="http://127.0.0.1:8888/callback"
)


sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=(
            "user-library-read "
            "user-library-modify"
        ),
        cache_path=str(
            TOKEN_CACHE
        ),
        open_browser=True
    )
)


def spotify_call(func, *args, **kwargs):
    """
    Executa chamadas à API do Spotify com retry simples
    para erros temporários e rate limit.
    """

    while True:

        try:
            return func(
                *args,
                **kwargs
            )

        except SpotifyException as e:

            status = getattr(
                e,
                "http_status",
                None
            )

            if status == 429:

                retry_after = 5

                headers = getattr(
                    e,
                    "headers",
                    None
                )

                if headers:
                    retry_after = int(
                        headers.get(
                            "Retry-After",
                            retry_after
                        )
                    )

                print(
                    f"Rate limit. "
                    f"Aguardando {retry_after}s..."
                )

                time.sleep(
                    retry_after
                )

                continue

            if status in (
                500,
                502,
                503,
                504
            ):

                print(
                    "Erro temporário do Spotify. "
                    "Tentando novamente em 5s..."
                )

                time.sleep(5)

                continue

            raise


def like_track(track_id):

    spotify_call(
        sp.current_user_saved_tracks_add,
        [track_id]
    )

    time.sleep(0.2)


def add_album(
    album_id,
    selected_discs=None
):

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

        tracks = results.get(
            "items",
            []
        )

        if not tracks:
            break

        for track in tracks:

            disc_number = track.get(
                "disc_number",
                1
            )

            if (
                selected_discs is not None
                and disc_number not in selected_discs
            ):
                continue

            track_id = track.get(
                "id"
            )

            if (
                not track_id
                or track_id in seen_tracks
            ):
                continue

            seen_tracks.add(
                track_id
            )

            ids.append(
                (
                    disc_number,
                    track.get(
                        "track_number",
                        0
                    ),
                    track_id,
                    track.get(
                        "name",
                        ""
                    )
                )
            )

        if len(tracks) < 50:
            break

        offset += 50

    ids.sort(
        key=lambda item: (
            item[0],
            item[1]
        )
    )

    if selected_discs is None:

        print(
            "Discos selecionados: todos"
        )

    else:

        print(
            "Discos selecionados:",
            ", ".join(
                str(disc)
                for disc
                in sorted(
                    selected_discs
                )
            )
        )

    print(
        "Faixas que serão adicionadas:",
        len(ids)
    )

    for i in range(
        0,
        len(ids),
        50
    ):

        batch = [
            item[2]
            for item
            in ids[i:i + 50]
        ]

        spotify_call(
            sp.current_user_saved_tracks_add,
            batch
        )

        time.sleep(0.2)


def delete_all_saved_tracks():

    print(
        "Apagando todas as músicas "
        "salvas do Spotify..."
    )

    while True:

        results = spotify_call(
            sp.current_user_saved_tracks,
            limit=50
        )

        items = results.get(
            "items",
            []
        )

        if not items:
            break

        ids = [
            item["track"]["id"]
            for item
            in items
            if (
                item.get("track")
                and item["track"].get("id")
            )
        ]

        if not ids:
            break

    for inicio in range(0, len(ids), 50):
        lote = ids[inicio:inicio + 50]

        spotify_call(
            sp.current_user_saved_tracks_delete,
            lote
        )

        print(
            f"{len(ids)} música(s) removida(s)."
        )

        time.sleep(0.2)

    print(
        "Biblioteca de músicas curtidas apagada."
    )
