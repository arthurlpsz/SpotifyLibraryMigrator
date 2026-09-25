import pandas as pd
import re
from difflib import SequenceMatcher


def similar(a, b):
    return SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()

def split_artists(artist_str):
    return [a.strip() for a in re.split(r',|feat\.|ft\.|with|&', str(artist_str), flags=re.IGNORECASE)]

def match_year(sheet_date, spotify_date):
    try:
        sheet_text = str(sheet_date).strip()
        spotify_text = str(spotify_date).strip()
        sheet_match = re.search(r"\b(?:19|20)\d{2}\b", sheet_text)
        spotify_match = re.search(r"\b(?:19|20)\d{2}\b", spotify_text)
        if not sheet_match or not spotify_match:
            return False
        return sheet_match.group() == spotify_match.group()
    except:
        return False

def match_date(sheet_date, spotify_date):
    try:
        # Assume sheet_date is DD/MM/YYYY or DD-MM-YYYY
        parts = re.split(r'[/-]', str(sheet_date))
        if len(parts) == 3:
            day, month, year = parts
            formatted = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            return formatted == spotify_date
        else:
            # Fallback to year
            return str(sheet_date)[:4] in spotify_date
    except:
        return False

def is_single(tipo):
    if not tipo:
        return False

    tipo = str(tipo).strip().lower()

    return "single" in tipo

def is_compilation(tipo):
    if not tipo:
        return False

    tipo = str(tipo).strip().lower()

    return any(
        x in tipo
        for x in [
            "compilacao",
            "compilação",
            "coletanea",
            "coletânea",
            "compilation"
        ]
    )

def is_collection(tipo):
    if not tipo:
        return False

    tipo = str(tipo).strip().lower()

    return (
        "album" in tipo
        or "álbum" in tipo
        or "ep" in tipo
        or is_compilation(tipo)
    )

def parse_discs(value):
    """
    Interpreta a coluna DISCO da planilha.

    Exemplos aceitos:
      vazio / NaN -> None (todos os discos)
      1           -> {1}
      2           -> {2}
      1,2         -> {1, 2}
      1.2         -> {1, 2}  # caso o Excel converta 1,2 para decimal
      1,2,4       -> {1, 2, 4}
      1.2.4       -> {1, 2, 4}
    """
    if value is None or pd.isna(value):
        return None

    value = str(value).strip()

    if not value:
        return None

    # Se o Excel leu um único disco como número decimal inteiro:
    # 1.0 -> 1
    # 2.0 -> 2
    if re.fullmatch(r"\d+\.0+", value):
        value = value.split(".")[0]

    # Aceita vírgula OU ponto como separador.
    # Isso resolve casos em que o Excel transforma "1,2" em 1.2.
    parts = re.split(r"[,.]", value)

    discs = set()

    for part in parts:
        part = part.strip()

        if not part:
            continue

        if not part.isdigit():
            raise ValueError(
                f"Valor inválido na coluna DISCO: '{value}'. "
                "Use números separados por vírgula, por exemplo: 1 ou 1,2."
            )

        disc = int(part)

        if disc < 1:
            raise ValueError(
                f"Valor inválido na coluna DISCO: '{value}'. "
                "Os discos devem começar em 1."
            )

        discs.add(disc)

    return discs if discs else None

