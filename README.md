# Spotify Library Migrator 🎵

Projeto em Python para **migrar, reconstruir e organizar uma biblioteca musical no Spotify a partir de uma planilha Excel**, utilizando a Spotify Web API.

A proposta vai além de simplesmente pesquisar uma música pelo nome. O programa tenta identificar a versão mais adequada considerando metadados como artista, data, tipo do lançamento, remix, remaster, explicit/clean, álbuns, compilações e discos específicos.

## Principais funcionalidades

- Leitura de uma biblioteca musical a partir de `Musicas_Curtidas.xlsx`.
- Busca de músicas, singles, álbuns, EPs e compilações.
- Comparação de resultados por nome, artista, data e tipo de lançamento.
- Tratamento de versões remix e remastered.
- Preferência pela faixa presente no álbum oficial quando a mesma música também existe como um release isolado.
- Tratamento de versões explicit/clean.
- Suporte a compilações e `Various Artists`.
- Seleção de discos específicos de um álbum.
- Cache das buscas realizadas.
- Registro de progresso para continuar execuções interrompidas.
- Adição automática às Músicas Curtidas do Spotify.

## Estrutura do projeto

```text
spotify-library-migrator/
│
├── main.py
├── utils.py
├── spotify_client.py
├── track_matcher.py
├── album_matcher.py
├── storage.py
├── Musicas_Curtidas.xlsx
├── progress.json
└── spotify_cache.json
```

### `main.py`

É o coordenador do programa.

Responsável por:

- ler a planilha;
- percorrer os registros;
- decidir se a linha representa uma faixa ou coleção;
- chamar os módulos de busca;
- adicionar o resultado ao Spotify;
- controlar o progresso da execução.

### `utils.py`

Contém funções auxiliares utilizadas por outros módulos, incluindo:

- similaridade de textos;
- separação de artistas;
- comparação de datas e anos;
- identificação de Single, Álbum e Compilação;
- interpretação da coluna `DISCO`.

### `spotify_client.py`

Centraliza a comunicação direta com a Spotify Web API:

- autenticação OAuth;
- chamadas à API com retry;
- adição de músicas;
- adição de álbuns;
- seleção de discos;
- remoção das músicas salvas.

### `track_matcher.py`

Responsável por encontrar a melhor versão de uma música.

Analisa:

- nome da faixa;
- artista;
- data;
- tipo do lançamento;
- remix;
- remaster;
- explicit;
- álbum associado à faixa.

Quando a mesma música está disponível como um single isolado e também dentro de um álbum compatível, o algoritmo dá preferência à **faixa do álbum**.

### `album_matcher.py`

Responsável por álbuns, EPs e compilações.

Analisa:

- nome;
- artista;
- data;
- quantidade de faixas;
- tipo do lançamento;
- versões explicit/clean.

Também possui tratamento específico para compilações cadastradas pelo Spotify como `Various Artists`.

### `storage.py`

Responsável pelos arquivos locais de apoio:

```text
spotify_cache.json
progress.json
```

O cache evita buscas repetidas e o progresso permite continuar uma execução interrompida.

## Estrutura da planilha

O programa espera um arquivo chamado:

```text
Musicas_Curtidas.xlsx
```

Principais colunas:

| Coluna | Descrição |
| --- | --- |
| `NOME` | Nome da música, álbum, EP ou compilação |
| `ARTISTAS/GRUPO` | Artista ou grupo |
| `TIPO` | Single, Album, EP, Compilação etc. |
| `ESTREIA` | Data usada para comparar o lançamento |
| `QTD` | Quantidade esperada de faixas |
| `DISCO` | Disco ou discos que devem ser adicionados |

Todas as abas são lidas, com exceção de uma aba chamada `Dashboard`.

## Seleção de discos

A coluna `DISCO` permite controlar álbuns com vários discos.

| Valor | Comportamento |
| --- | --- |
| vazio | todos os discos |
| `1` | somente disco 1 |
| `2` | somente disco 2 |
| `1,2` | discos 1 e 2 |
| `1,2,4` | discos 1, 2 e 4 |

É recomendado formatar essa coluna como **Texto** no Excel.

## Correspondência de músicas

O Spotify pode possuir várias versões da mesma faixa:

```text
música original
single promocional
faixa do álbum
remix
remaster
clean
explicit
compilação
trilha sonora
```

Por isso o programa atribui pontuações aos resultados em vez de simplesmente utilizar o primeiro item retornado pela API.

Resultados incompatíveis podem ser rejeitados completamente.

### Faixa dentro do álbum

Quando uma música aparece tanto como release isolado quanto dentro de um álbum oficial compatível, o programa procura priorizar a ocorrência presente no álbum.

Exemplo:

```text
Single:
Example Song
└── capa do single

Álbum:
Official Album
└── Example Song

Resultado preferido:
Official Album → Example Song
```

Caso não exista uma versão compatível dentro de álbum, o single continua sendo utilizado normalmente.

## Remix e remaster

O programa diferencia versões especiais da faixa.

Se a planilha pede uma versão normal, resultados de remix/remaster incompatíveis podem ser descartados.

Se a própria planilha pede um remix ou remaster, essas versões passam a ser consideradas normalmente pelo algoritmo.

## Compilações

Compilações recebem tratamento separado porque o Spotify frequentemente define o artista principal como:

```text
Various Artists
```

Nesses casos, a busca também pode ser realizada pelo nome da compilação sem exigir que o artista principal corresponda literalmente ao valor da planilha.

## Cache

As buscas são armazenadas em:

```text
spotify_cache.json
```

Isso reduz chamadas repetidas à API.

Caso você altere significativamente as regras de busca e queira testar tudo novamente, pode ser útil apagar o cache antes da execução.

## Progresso

Os itens processados são armazenados em:

```text
progress.json
```

O identificador também considera os discos selecionados.

Assim, duas entradas do mesmo álbum usando discos diferentes podem ser processadas separadamente.

## Instalação

Recomendado:

- Python 3.10+
- conta no Spotify;
- aplicação criada no Spotify for Developers.

Instale as dependências:

```bash
pip install pandas tqdm spotipy openpyxl
```

## Configuração do Spotify

Configure:

```text
SPOTIPY_CLIENT_ID
SPOTIPY_CLIENT_SECRET
SPOTIPY_REDIRECT_URI
```

Exemplo no PowerShell:

```powershell
$env:SPOTIPY_CLIENT_ID="seu_client_id"
$env:SPOTIPY_CLIENT_SECRET="seu_client_secret"
$env:SPOTIPY_REDIRECT_URI="https://127.0.0.1:8888/callback"
```

O código utiliza os escopos:

```text
user-library-read
user-library-modify
```

Nunca publique seu `Client Secret` no GitHub.

## Executando

Mantenha a planilha na mesma pasta do projeto e execute:

```bash
python main.py
```

No início, o programa pergunta:

```text
Deseja apagar todas as músicas salvas antes de rodar o código? [s/n]:
```

Use `n` se deseja manter sua biblioteca atual.

> Atenção: escolher `s` remove as músicas atualmente salvas antes da importação.

## `.gitignore`

É recomendado ignorar:

```gitignore
spotify_cache.json
progress.json
.env
__pycache__/
*.pyc
```

## Tecnologias

- Python
- Pandas
- Spotipy
- Spotify Web API
- Excel

## Próximas melhorias

Algumas possibilidades de evolução:

- relatório das músicas que não foram encontradas;
- auditoria de divergências entre datas da planilha e da API;
- revisão manual de correspondências duvidosas;
- testes automatizados;
- interface gráfica;
- suporte a outras plataformas de streaming.

## Aviso

Projeto independente e sem vínculo oficial com o Spotify.

Spotify e Spotify Web API pertencem aos seus respectivos proprietários.
