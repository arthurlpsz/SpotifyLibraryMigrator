import pandas as pd
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from main import (
    search_album,
    choose_best_album,
    score_album_result
)

def main():

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

    print("\n==============================")
    print("BUSCANDO NO SPOTIFY")
    print("==============================")

    resultados = search_album(
        nome,
        artista,
        tipo
    )

    print(resultados)

    if not resultados:
        print("Nenhum álbum encontrado.")
        return

    print(f"\n{len(resultados)} resultado(s) encontrado(s).\n")

    melhor = choose_best_album(
        row,
        resultados
    )

    for i, album in enumerate(resultados, start=1):

        score = score_album_result(
            row,
            album
        )

        print("=" * 60)

        print(f"Resultado #{i}")

        print("Nome........:", album["name"])

        print(
            "Artista.....:",
            ", ".join(
                a["name"]
                for a in album["artists"]
            )
        )

        print(
            "Data........:",
            album["release_date"]
        )

        print(
            "Tipo........:",
            album["album_type"]
        )

        print(
            "Faixas......:",
            album["total_tracks"]
        )

        print(
            "Score.......:",
            score
        )

        if melhor and album["id"] == melhor["id"]:
            print("⭐ ESCOLHIDO PELO ALGORITMO")

    print("=" * 60)

if __name__ == "__main__":
    main()