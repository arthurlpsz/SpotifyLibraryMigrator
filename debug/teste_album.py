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


def parse_discs(value):
    """
    Converte o valor digitado em uma lista de discos.
    Exemplos:
      ""      -> None (todos os discos)
      "1"     -> {1}
      "1,2"   -> {1, 2}
      "1,2,4" -> {1, 2, 4}
    """
    value = str(value).strip()

    if not value:
        return None

    discs = set()

    for part in value.split(","):
        part = part.strip()

        if not part:
            continue

        if not part.isdigit():
            raise ValueError(
                f"Valor inválido em DISCO: '{part}'. "
                "Use apenas números separados por vírgula, ex.: 1,2"
            )

        discs.add(int(part))

    return discs if discs else None


def get_album_tracks(album_id):
    """
    Busca todas as faixas do álbum, incluindo álbuns com mais de 50 faixas.
    """
    all_tracks = []
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

        all_tracks.extend(tracks)

        if len(tracks) < 50:
            break

        offset += 50

    return all_tracks


def count_explicit_tracks(album_id):
    """
    Conta quantas faixas explicit existem em um álbum.
    Usada somente no desempate entre edições do mesmo álbum.
    """
    tracks = get_album_tracks(album_id)

    explicit_count = sum(
        1
        for track in tracks
        if track.get("explicit", False)
    )

    return explicit_count, len(tracks)


def filter_tracks_by_disc(tracks, selected_discs):
    """
    Se selected_discs for None, retorna todas as faixas.
    Caso contrário, retorna apenas as faixas dos discos escolhidos.
    """
    if selected_discs is None:
        return tracks

    return [
        track
        for track in tracks
        if track.get("disc_number", 1) in selected_discs
    ]


def show_disc_summary(tracks):
    """
    Mostra quantas faixas existem em cada disco.
    """
    summary = {}

    for track in tracks:
        disc = track.get("disc_number", 1)
        summary[disc] = summary.get(disc, 0) + 1

    print("\nDiscos encontrados no álbum:")

    for disc in sorted(summary):
        print(
            f"  Disco {disc}: {summary[disc]} faixa(s)"
        )


def main():

    print("=" * 60)
    print("TESTE DE ÁLBUM")
    print("=" * 60)

    nome = input("Nome do álbum: ").strip()
    artista = input("Artista: ").strip()
    tipo = input("Tipo (Album/EP/etc): ").strip()
    estreia = input("Data (DD/MM/AAAA): ").strip()
    qtd = input("Quantidade de faixas: ").strip()

    disco_input = input(
        "Disco(s) desejado(s) "
        "(ex.: 1 | 1,2 | vazio = todos): "
    ).strip()

    try:
        selected_discs = parse_discs(
            disco_input
        )
    except ValueError as e:
        print(f"\nErro: {e}")
        return

    row = pd.Series({
        "NOME": nome,
        "ARTISTAS/GRUPO": artista,
        "TIPO": tipo,
        "ESTREIA": estreia,
        "QTD": int(qtd) if qtd else None,
        "DISCO": disco_input if disco_input else None
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

    # Ordena apenas para facilitar a leitura
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

    # Só consulta explicit para desempate
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

    # Escolhe o álbum
    if len(empatados) == 1:
        melhor = empatados[0]
    else:
        melhor = max(
            empatados,
            key=lambda album: explicit_info[
                album["id"]
            ][0]
        )

    # Exibe todos os candidatos
    for i, (album, score) in enumerate(
        scored,
        start=1
    ):

        print("=" * 60)
        print(f"Resultado #{i}")
        print()

        print("Nome........:", album.get("name", ""))

        print(
            "Artista.....:",
            ", ".join(
                a["name"]
                for a in album.get("artists", [])
            )
        )

        print("Data........:", album.get("release_date", ""))
        print("Precisão....:", album.get("release_date_precision", ""))
        print("Tipo........:", album.get("album_type", ""))
        print("Faixas......:", album.get("total_tracks", ""))
        print("Score.......:", score)
        print("ID..........:", album.get("id", ""))

        if album["id"] in explicit_info:
            explicit_count, total = explicit_info[
                album["id"]
            ]

            print(
                "Explicit....:",
                f"{explicit_count}/{total}"
            )

            if explicit_count == 0:
                print("Versão......: provável CLEAN")
            else:
                print("Versão......: possui faixas EXPLICIT")

        if melhor and album["id"] == melhor["id"]:
            print()
            print("⭐ ESCOLHIDO PELO ALGORITMO")

    print("=" * 60)

    if not melhor:
        print("\nNenhum álbum foi escolhido.")
        return

    print("\nRESULTADO FINAL")
    print("-" * 60)

    print("Planilha....:", nome, "-", artista)

    print(
        "Spotify.....:",
        melhor["name"],
        "-",
        ", ".join(
            a["name"]
            for a in melhor["artists"]
        )
    )

    print("ID..........:", melhor["id"])

    # Busca as faixas do álbum escolhido
    all_tracks = get_album_tracks(
        melhor["id"]
    )

    show_disc_summary(
        all_tracks
    )

    selected_tracks = filter_tracks_by_disc(
        all_tracks,
        selected_discs
    )

    print("\n" + "-" * 60)

    if selected_discs is None:
        print("DISCO.......: todos os discos")
    else:
        print(
            "DISCO.......:",
            ", ".join(
                str(d)
                for d in sorted(selected_discs)
            )
        )

    print(
        "Faixas que seriam adicionadas:",
        len(selected_tracks)
    )

    print("-" * 60)

    if not selected_tracks:
        print(
            "\n⚠ Nenhuma faixa corresponde ao(s) disco(s) informado(s)."
        )
        return

    for track in sorted(
        selected_tracks,
        key=lambda t: (
            t.get("disc_number", 1),
            t.get("track_number", 0)
        )
    ):

        disc_number = track.get(
            "disc_number",
            1
        )

        track_number = track.get(
            "track_number",
            0
        )

        explicit = (
            "EXPLICIT"
            if track.get("explicit", False)
            else "clean"
        )

        print(
            f"Disco {disc_number} | "
            f"Faixa {track_number:02d} | "
            f"{track.get('name', '')} | "
            f"{explicit}"
        )


if __name__ == "__main__":
    main()