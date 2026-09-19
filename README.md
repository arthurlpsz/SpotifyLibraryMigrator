# Spotify Library Migrator 🎵

Ferramenta em Python para **migrar, reconstruir e organizar uma biblioteca musical no Spotify a partir de uma planilha Excel**, utilizando a Spotify Web API.

O projeto surgiu da necessidade de importar músicas de forma mais precisa do que uma busca simples por nome. Durante o desenvolvimento, foram adicionadas regras para diferenciar singles, álbuns, compilações, remixes, remasters, versões explicit/clean e álbuns divididos em múltiplos discos.

## Funcionalidades

- Leitura automática de uma planilha Excel com a biblioteca musical.
- Busca de músicas, singles, álbuns, EPs e compilações no Spotify.
- Comparação de resultados usando nome, artista, data de lançamento, tipo do lançamento, quantidade de faixas e versão explicit/clean.
- Tratamento específico para singles, remixes, versões remastered, compilações e trilhas sonoras com títulos no formato `From "..."`.
- Seleção de discos específicos em álbuns com múltiplos discos.
- Adição automática das músicas encontradas às **Músicas Curtidas**.
- Cache das buscas para reduzir chamadas repetidas à API.
- Registro de progresso para permitir continuar uma execução interrompida.
- Opção de apagar todas as músicas salvas antes de iniciar uma nova importação.

## Como funciona

O programa lê as linhas da planilha e decide se cada registro representa uma música individual ou uma coleção, como álbum, EP ou compilação.

Para músicas e singles, o programa consulta a Spotify Web API e atribui uma pontuação aos resultados encontrados. O objetivo é selecionar a versão mais compatível com os dados informados na planilha.

```text
Planilha Excel
      ↓
Leitura dos dados
      ↓
Busca na Spotify Web API
      ↓
Comparação dos resultados
      ↓
Nome + Artista + Data + Tipo + Versão
      ↓
Melhor correspondência
      ↓
Adicionar às Músicas Curtidas
```

Resultados incompatíveis podem ser descartados antes da seleção. Por exemplo, uma versão remix não deve vencer quando a planilha pede a versão original, e uma versão remastered só deve ser escolhida quando os dados indicarem esse tipo de lançamento.

## Álbuns e compilações

Álbuns, EPs e compilações possuem uma lógica própria. O programa compara:

- nome do lançamento;
- artista;
- data;
- tipo retornado pelo Spotify;
- quantidade esperada de faixas.

No caso de compilações, a busca também consegue considerar resultados associados a `Various Artists`, já que nem sempre o artista informado na planilha é o artista principal registrado pelo Spotify.

Quando há empate entre versões muito semelhantes de um álbum, o programa consulta as faixas das versões empatadas e pode utilizar a presença de conteúdo explicit como critério de desempate.

## Seleção de discos

Alguns álbuns são organizados pelo Spotify como `Disc 1`, `Disc 2`, `Disc 3` etc.

A coluna `DISCO` permite escolher quais deles serão adicionados.

| Valor em `DISCO` | Resultado |
| --- | --- |
| vazio | adiciona todos os discos |
| `1` | adiciona somente o disco 1 |
| `2` | adiciona somente o disco 2 |
| `1,2` | adiciona os discos 1 e 2 |
| `1,2,4` | adiciona os discos 1, 2 e 4 |

> Para evitar que o Excel altere valores como `1,2`, é recomendável formatar a coluna `DISCO` como **Texto**.

## Estrutura da planilha

O arquivo esperado pelo programa é:

```text
Musicas_Curtidas.xlsx
```

As principais colunas utilizadas são:

| Coluna | Descrição |
| --- | --- |
| `NOME` | Nome da música, álbum, EP ou compilação |
| `ARTISTAS/GRUPO` | Artista ou grupo responsável |
| `TIPO` | Tipo do registro, como Single, Album, EP ou Compilação |
| `ESTREIA` | Data de lançamento utilizada na comparação |
| `QTD` | Quantidade esperada de faixas para álbuns/coleções |
| `DISCO` | Disco(s) que devem ser adicionados; pode ficar vazio |

O programa lê todas as abas do Excel, exceto uma aba chamada `Dashboard`.

### Exemplo

| NOME | ARTISTAS/GRUPO | TIPO | ESTREIA | QTD | DISCO |
| --- | --- | --- | --- | ---: | --- |
| Double Life | Pharrell Williams | Single | 14/06/2024 |  |  |
| Abbey Road | The Beatles | Album | 26/09/1969 | 17 |  |
| Exemplo Deluxe | Artista | Album | 01/01/2020 | 30 | 1,2 |
| Exemplo Hits | Various Artists | Compilação | 15/05/2010 | 20 |  |

## Busca de músicas

A busca utiliza o nome da faixa e o artista.

Além da busca principal, existe um tratamento para títulos de trilhas sonoras. Por exemplo:

```text
Double Life - From "Despicable Me 4"
```

Caso uma busca com o título completo não retorne resultados, o programa pode tentar uma versão simplificada:

```text
Double Life
```

Os resultados encontrados passam pelo mesmo sistema de comparação antes de qualquer música ser adicionada.

## Sistema de pontuação

O algoritmo não escolhe simplesmente o primeiro resultado retornado pelo Spotify.

Cada candidato recebe uma pontuação baseada em diferentes critérios:

- similaridade do nome;
- correspondência do artista;
- data completa de lançamento;
- ano de lançamento;
- tipo do lançamento;
- presença de conteúdo explicit;
- identificação de remix;
- identificação de remaster.

Resultados claramente incompatíveis podem ser rejeitados completamente.

Isso ajuda a evitar casos como selecionar uma versão remix quando a planilha pede a versão original, ou escolher uma edição remastered quando a versão original foi solicitada.

## Cache

As buscas realizadas são armazenadas em:

```text
spotify_cache.json
```

O cache reduz chamadas repetidas à Spotify Web API, tornando execuções futuras mais rápidas e ajudando a evitar limites desnecessários de requisições.

## Controle de progresso

O projeto utiliza:

```text
progress.json
```

Esse arquivo registra itens já processados.

Caso a execução seja interrompida, o programa consegue continuar sem repetir todos os registros anteriores.

Para álbuns com discos selecionados, a escolha de discos também faz parte da identificação utilizada no progresso.

## Requisitos

- Python 3.10 ou superior recomendado.
- Conta no Spotify.
- Aplicação criada no Spotify for Developers.
- Arquivo `Musicas_Curtidas.xlsx`.

### Bibliotecas Python

Instale as dependências com:

```bash
pip install pandas tqdm spotipy openpyxl
```

## Configuração da Spotify Web API

Crie uma aplicação no painel do Spotify for Developers e configure uma Redirect URI.

Depois, defina as seguintes variáveis de ambiente:

```text
SPOTIPY_CLIENT_ID
SPOTIPY_CLIENT_SECRET
SPOTIPY_REDIRECT_URI
```

Se `SPOTIPY_REDIRECT_URI` não estiver configurada, o código utiliza:

```text
https://127.0.0.1:8888/callback
```

O projeto utiliza as permissões:

```text
user-library-read
user-library-modify
```

### Windows PowerShell

```powershell
$env:SPOTIPY_CLIENT_ID="seu_client_id"
$env:SPOTIPY_CLIENT_SECRET="seu_client_secret"
$env:SPOTIPY_REDIRECT_URI="https://127.0.0.1:8888/callback"
```

## Executando

Com a planilha na mesma pasta do programa:

```bash
python main.py
```

No início da execução, o programa pergunta se todas as músicas atualmente salvas devem ser removidas:

```text
Deseja apagar todas as músicas salvas antes de rodar o código? [s/n]:
```

Escolha `n` caso queira manter a biblioteca atual e apenas adicionar os novos registros.

> **Atenção:** escolher `s` remove as músicas atualmente salvas na biblioteca da conta autenticada antes da importação.

## Arquivos gerados

Durante o uso, o projeto pode criar:

```text
spotify_cache.json
progress.json
```

Uma sugestão de `.gitignore`:

```gitignore
spotify_cache.json
progress.json
.env
__pycache__/
*.pyc
```

Também é recomendado **nunca publicar seu Client Secret** no repositório.

## Possíveis melhorias

- separar o código em módulos menores;
- criar uma interface gráfica;
- gerar relatório das músicas que não foram encontradas;
- gerar relatório de divergências de datas entre a planilha e a Spotify Web API;
- permitir revisão manual antes de adicionar correspondências duvidosas;
- adicionar suporte a outras plataformas de streaming;
- criar testes automatizados para o algoritmo de correspondência.

## Tecnologias utilizadas

- Python
- Pandas
- Spotipy
- Spotify Web API
- Excel

## Objetivo do projeto

Além de automatizar a migração da biblioteca, este projeto explora problemas reais de **matching de dados e metadados**.

Uma mesma música pode existir no Spotify em diversas formas:

- single;
- versão de álbum;
- remix;
- remaster;
- clean;
- explicit;
- compilação;
- trilha sonora.

Por isso, a principal proposta do projeto é utilizar diferentes informações disponíveis para encontrar a correspondência mais adequada em vez de confiar apenas em uma busca textual simples.

## Aviso

Este é um projeto independente e não possui vínculo oficial com o Spotify.

Spotify e Spotify Web API são marcas e serviços de seus respectivos proprietários.

## Autor

Desenvolvido como projeto pessoal para estudo de Python, APIs, automação e tratamento de dados.
