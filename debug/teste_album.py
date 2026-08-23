import sys
from pathlib import Path
import pandas as pd

# Permite importar o main.py que está uma pasta acima da pasta debug
sys.path.append(
    str(Path(__file__).resolve().parent.parent)
)

from main import (
    search_album,
    score_album_result,
    spotify_call,
    sp
)


def count_explicit_tracks(album_id):
    """
    Conta quantas faixas explicit existem em um álbum.
    Esta função fica somente no teste por enquanto,
    sem necessidade de alterar o main.py.
    """

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
            1
            for track in tracks
            if track.get("explicit", False)
        )

        if len(tracks) < 50:
            break

        offset += 50

    return explicit_count, total


def main():

    print("=" * 60)
    print("TESTE DE ÁLBUM")
    print("=" * 60)

    nome = input("Nome do álbum: ").strip()
    artista = input("Artista: ").strip()
    tipo = input("Tipo (Album/EP/etc): ").strip()
    estreia = input("Data (DD/MM/AAAA): ").strip()
    qtd = input("Quantidade de faixas: ").strip()

    row = pd.Series({
        "NOME": nome,
        "ARTISTAS/GRUPO": artista,
        "TIPO": tipo,
        "ESTREIA": estreia,
        "QTD": int(qtd) if qtd else None
    })

    print("\n" + "=" * 60)
    print("BUSCANDO NO SPOTIFY")
    print("=" * 60)

    resultados = search_album(
        nome,
        artista,
        tipo
    )

    if not resultados:
        print("\nNenhum álbum encontrado.")
        return

    print(
        f"\n{len(resultados)} resultado(s) encontrado(s).\n"
    )

    scored = []

    for album in resultados:

        score = score_album_result(
            row,
            album
        )

        scored.append(
            (album, score)
        )

    # Ordena apenas para exibição.
    scored.sort(
        key=lambda item: item[1],
        reverse=True
    )

    best_score = scored[0][1]

    empatados = [
        album
        for album, score in scored
        if score == best_score
    ]

    explicit_info = {}

    # Só faz chamadas extras quando há empate no melhor score.
    if len(empatados) > 1:

        print(
            f"Empate entre {len(empatados)} álbuns "
            f"com score {best_score}."
        )

        print(
            "Verificando quantidade de faixas explicit...\n"
        )

        for album in empatados:

            explicit_count, total = count_explicit_tracks(
                album["id"]
            )

            explicit_info[album["id"]] = (
                explicit_count,
                total
            )

    # Decide o vencedor.
    if len(empatados) == 1:

        melhor = empatados[0]

    else:

        # Prefere a edição com mais faixas explicit.
        # Em novo empate, mantém o primeiro resultado.
        melhor = max(
            empatados,
            key=lambda album: explicit_info[
                album["id"]
            ][0]
        )

    for i, (album, score) in enumerate(
        scored,
        start=1
    ):

        print("=" * 60)
        print(f"Resultado #{i}")
        print()

        print(
            "Nome........:",
            album.get("name", "")
        )

        print(
            "Artista.....:",
            ", ".join(
                a["name"]
                for a in album.get(
                    "artists",
                    []
                )
            )
        )

        print(
            "Data........:",
            album.get(
                "release_date",
                ""
            )
        )

        print(
            "Precisão....:",
            album.get(
                "release_date_precision",
                ""
            )
        )

        print(
            "Tipo........:",
            album.get(
                "album_type",
                ""
            )
        )

        print(
            "Faixas......:",
            album.get(
                "total_tracks",
                ""
            )
        )

        print(
            "Score.......:",
            score
        )

        print(
            "ID..........:",
            album.get(
                "id",
                ""
            )
        )

        if album["id"] in explicit_info:

            explicit_count, total = explicit_info[
                album["id"]
            ]

            print(
                "Explicit....:",
                f"{explicit_count}/{total}"
            )

            if explicit_count == 0:

                print(
                    "Versão......: provável CLEAN"
                )

            else:

                print(
                    "Versão......: possui faixas EXPLICIT"
                )

        if (
            melhor
            and album["id"] == melhor["id"]
        ):

            print()
            print(
                "⭐ ESCOLHIDO PELO ALGORITMO"
            )

    print("=" * 60)

    if melhor:

        print("\nRESULTADO FINAL")
        print("-" * 60)

        print(
            "Planilha....:",
            nome,
            "-",
            artista
        )

        print(
            "Spotify.....:",
            melhor["name"],
            "-",
            ", ".join(
                a["name"]
                for a in melhor["artists"]
            )
        )

        print(
            "ID..........:",
            melhor["id"]
        )

        if melhor["id"] in explicit_info:

            explicit_count, total = explicit_info[
                melhor["id"]
            ]

            print(
                "Explicit....:",
                f"{explicit_count}/{total}"
            )


if __name__ == "__main__":
    main()
