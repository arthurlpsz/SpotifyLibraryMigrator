import os
import time
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException


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

def like_track(track_id):

    spotify_call(
        sp.current_user_saved_tracks_add,
        [track_id]
    )

    time.sleep(0.2)

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

