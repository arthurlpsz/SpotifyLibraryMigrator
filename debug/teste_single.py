import sys
from pathlib import Path
import pandas as pd

# Permite importar o main.py que está uma pasta acima
sys.path.append(
    str(Path(__file__).resolve().parent.parent)
)

from main import (
    search_spotify,
    choose_best,
    score_result
)


def main():

    print("=" * 60)
    print("TESTE DE SINGLE / MÚSICA")
    print("=" * 60)

    nome = input("Nome da música: ").strip()
    artista = input("Artista: ").strip()
    estreia = input("Data (DD-MM-AAAA): ").strip()

    row = pd.Series({
        "NOME": nome,
        "ARTISTAS/GRUPO": artista,
        "TIPO": "Single",
        "ESTREIA": estreia
    })

    print("\n" + "=" * 60)
    print("BUSCANDO NO SPOTIFY")
    print("=" * 60)

    resultados = search_spotify(
        nome,
        artista,
        allow_compilation=False
    )

    if not resultados:
        print("\nNenhuma música encontrada.")
        return

    print(
        f"\n{len(resultados)} resultado(s) "
        "passaram pelos filtros.\n"
    )

    best, best_score = choose_best(
        row,
        resultados
    )

    # Ordena apenas para exibição:
    # maior score primeiro.
    resultados_ordenados = sorted(
        resultados,
        key=lambda r: score_result(row, r),
        reverse=True
    )

    for i, result in enumerate(
        resultados_ordenados,
        start=1
    ):

        score = score_result(
            row,
            result
        )

        print("=" * 60)
        print(f"Resultado #{i}")
        print()

        print(
            "Nome........:",
            result.get("name", "")
        )

        print(
            "Artista.....:",
            ", ".join(
                a["name"]
                for a in result.get("artists", [])
            )
        )

        print(
            "Álbum.......:",
            result.get(
                "album",
                {}
            ).get(
                "name",
                ""
            )
        )

        print(
            "Data........:",
            result.get(
                "album",
                {}
            ).get(
                "release_date",
                ""
            )
        )

        print(
            "Tipo álbum..:",
            result.get(
                "album",
                {}
            ).get(
                "album_type",
                ""
            )
        )

        print(
            "Explícita...:",
            "Sim"
            if result.get("explicit", False)
            else "Não"
        )

        print(
            "Score.......:",
            score
        )

        print(
            "ID..........:",
            result.get("id", "")
        )

        if (
            best
            and result.get("id") == best.get("id")
        ):
            print()
            print(
                "⭐ ESCOLHIDA PELO ALGORITMO"
            )

    print("=" * 60)

    if best:

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
            best["name"],
            "-",
            ", ".join(
                a["name"]
                for a in best["artists"]
            )
        )

        print(
            "Score.......:",
            best_score
        )

    else:

        print(
            "\nNenhum resultado foi escolhido."
        )


if __name__ == "__main__":
    main()