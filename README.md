# Spotify Library Migrator 🎵

Projeto em Python para **migrar, reconstruir e organizar uma biblioteca musical no Spotify a partir de uma planilha Excel**, utilizando a Spotify Web API.

A proposta vai além de simplesmente pesquisar uma música pelo nome. O programa tenta identificar a versão mais adequada considerando metadados como artista, data, tipo do lançamento, remix, remaster, explicit/clean, álbuns, compilações e discos específicos.

## Principais funcionalidades

- Leitura de uma biblioteca musical a partir de `Musicas_Curtidas.xlsx`.
- Busca de músicas, singles, álbuns, EPs e compilações.
- Comparação de resultados por nome, artista, data e tipo de lançamento.
- Tratamento de versões remix e remastered.
- Prioridade para correspondências exatas de título.
- Rejeição de versões alternativas não solicitadas, como `Mix`, `Single ver.`, `classic`, karaoke, instrumental, live, acoustic e outras.
- Preferência pela faixa presente em um álbum compatível quando a mesma música também existe como release isolado.
- Tratamento de versões explicit/clean.
- Suporte a compilações e `Various Artists`.
- Seleção de discos específicos de um álbum.
- Cache das buscas realizadas.
- Registro de progresso para continuar execuções interrompidas.
- Credenciais do Spotify armazenadas localmente de forma segura com `keyring`.
- Cache do token OAuth fora da pasta do projeto.
- Adição automática às Músicas Curtidas do Spotify.
- Opção de remover as músicas curtidas atuais antes da importação.

## Estrutura do projeto

```text
SpotifyLibraryMigrator/
│
├── main.py
├── Musicas_Curtidas.xlsx
├── README.md
├── .gitignore
│
├── src/
│   ├── utils.py
│   ├── spotify_client.py
│   ├── track_matcher.py
│   ├── album_matcher.py
│   └── storage.py
│
└── debug/
    ├── teste_single.py
    └── teste_album.py
```

Os arquivos `progress.json` e `spotify_cache.json` são criados durante o uso do programa e não precisam ser versionados no GitHub.

## Organização dos módulos

### `main.py`

É o coordenador principal do programa.

Responsável por:

- ler a planilha;
- percorrer os registros;
- identificar se a linha representa uma faixa ou coleção;
- chamar os módulos responsáveis pelas buscas;
- adicionar o resultado escolhido à biblioteca;
- controlar o progresso da execução.

### `src/utils.py`

Contém funções auxiliares utilizadas por outros módulos, incluindo:

- comparação de similaridade entre textos;
- separação de artistas;
- comparação de datas e anos;
- identificação de Single, Álbum, EP e Compilação;
- interpretação da coluna `DISCO`.

### `src/spotify_client.py`

Centraliza a comunicação com a Spotify Web API:

- autenticação OAuth;
- armazenamento das credenciais;
- cache do token OAuth;
- retry de chamadas temporariamente indisponíveis;
- adição de músicas;
- adição das faixas de álbuns;
- seleção de discos;
- remoção das músicas curtidas.

### `src/track_matcher.py`

Responsável por localizar e selecionar a melhor ocorrência de uma música no Spotify.

Analisa:

- título da faixa;
- artista;
- data;
- tipo do lançamento;
- remix;
- remaster;
- explicit;
- álbum associado;
- versões alternativas.

O algoritmo prioriza títulos exatamente iguais ao nome informado na planilha e pode rejeitar resultados incompatíveis completamente.

Exemplos de versões alternativas que podem ser rejeitadas quando não foram solicitadas:

```text
2023 Mix
Single ver.
classic
Radio Edit
Extended Mix
Club Mix
Karaoke
Instrumental
Acoustic
Live
Sped Up
Slowed
```

Um detalhe importante é o tratamento de álbuns remasterizados. Uma faixa normal não é descartada apenas porque está dentro de um álbum cujo nome possui `(Remastered)`.

Exemplo:

```text
Planilha:
Mayonaka no Door~stay with me

Spotify:
Mayonaka no Door~stay with me
Pocket Park (Remastered)

Resultado:
a faixa continua sendo considerada válida
```

### Faixa dentro de um álbum

Quando existem múltiplas ocorrências compatíveis da mesma música, o projeto procura priorizar a faixa presente em um álbum oficial.

Exemplo:

```text
Release isolado:
Example Song

Álbum:
Official Album
└── Example Song

Resultado preferido:
Official Album → Example Song
```

Isso não significa que todo resultado do tipo `album` será escolhido automaticamente.

A correspondência ainda precisa ser compatível com o nome e o artista. Caso não exista uma ocorrência adequada em álbum, o release isolado continua sendo válido.

### `src/album_matcher.py`

Responsável pela busca e escolha de álbuns, EPs e compilações.

Analisa:

- nome;
- artista;
- data;
- quantidade de faixas;
- tipo de lançamento;
- versões explicit/clean.

Compilações recebem tratamento especial porque o Spotify pode cadastrar o artista principal como:

```text
Various Artists
```

### `src/storage.py`

Responsável pelos arquivos locais utilizados pelo programa:

```text
spotify_cache.json
progress.json
```

O cache reduz chamadas repetidas à API e o arquivo de progresso permite continuar uma execução interrompida.

## Arquivos de debug

A pasta `debug/` contém programas auxiliares para testar os algoritmos sem executar a importação completa.

### `debug/teste_single.py`

Permite informar manualmente:

- nome da música;
- artista;
- data.

O programa exibe os resultados encontrados, seus scores e qual ocorrência seria escolhida pelo algoritmo.

Execute com:

```bash
python debug/teste_single.py
```

### `debug/teste_album.py`

Permite testar a busca de álbuns e EPs, incluindo:

- score dos resultados;
- quantidade de faixas;
- versões explicit;
- seleção de discos.

Execute com:

```bash
python debug/teste_album.py
```

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
| `ESTREIA` | Data usada na comparação com o Spotify |
| `QTD` | Quantidade esperada de faixas |
| `DISCO` | Disco ou discos que devem ser adicionados |

Todas as abas são lidas, com exceção da aba chamada `Dashboard`.

## Seleção de discos

A coluna `DISCO` permite selecionar partes específicas de lançamentos com múltiplos discos.

| Valor | Comportamento |
| --- | --- |
| vazio | todos os discos |
| `1` | somente o disco 1 |
| `2` | somente o disco 2 |
| `1,2` | discos 1 e 2 |
| `1,2,4` | discos 1, 2 e 4 |

É recomendado formatar essa coluna como **Texto** no Excel.

## Instalação

Recomendado:

- Python 3.10 ou superior;
- conta no Spotify;
- aplicação criada no Spotify for Developers.

Instale as dependências:

```bash
pip install pandas tqdm spotipy openpyxl keyring
```

## Configuração do Spotify

Antes da primeira execução, crie uma aplicação no Spotify for Developers.

No painel da aplicação, configure o Redirect URI:

```text
http://127.0.0.1:8888/callback
```

O endereço cadastrado no Spotify precisa ser igual ao utilizado pelo programa.

O projeto utiliza os seguintes escopos:

```text
user-library-read
user-library-modify
```

## Primeira execução

Execute:

```bash
python main.py
```

Caso as credenciais ainda não estejam salvas, o programa solicitará:

```text
Spotify Client ID:
Spotify Client Secret:
Spotify Redirect URI [http://127.0.0.1:8888/callback]:
```

Digite os valores **sem aspas**.

Exemplo correto:

```text
Spotify Client ID: abc123
```

Evite:

```text
Spotify Client ID: "abc123"
```

O `Client Secret` não é exibido enquanto está sendo digitado.

### Onde as credenciais são armazenadas?

O projeto utiliza a biblioteca `keyring`.

No Windows, as credenciais são armazenadas através do **Gerenciador de Credenciais do Windows**, em vez de serem gravadas diretamente no código-fonte.

Depois da primeira configuração, normalmente não é necessário digitá-las novamente.

Variáveis de ambiente continuam tendo prioridade caso estejam configuradas:

```text
SPOTIPY_CLIENT_ID
SPOTIPY_CLIENT_SECRET
SPOTIPY_REDIRECT_URI
```

### Token OAuth

O token de autorização do Spotify é armazenado fora da pasta do projeto, no perfil do usuário:

```text
~/.spotify-library-migrator/
```

No Windows, isso corresponde a algo semelhante a:

```text
C:\Users\SEU_USUARIO\.spotify-library-migrator\
```

O Spotipy utiliza o refresh token para renovar a autorização quando necessário.

Um novo login pode ser solicitado se, por exemplo:

- o acesso do aplicativo for revogado no Spotify;
- as credenciais da aplicação forem alteradas;
- o cache OAuth for apagado;
- o usuário trocar de computador ou perfil do sistema.

## Execução

Mantenha `Musicas_Curtidas.xlsx` na raiz do projeto e execute:

```bash
python main.py
```

Antes de iniciar a importação, o programa pergunta:

```text
Deseja apagar todas as músicas salvas antes de rodar o código? [s/n]:
```

Use:

```text
n
```

para preservar as músicas que já estão na biblioteca.

> **Atenção:** escolher `s` remove as músicas atualmente salvas na biblioteca antes da importação.

## Cache

As buscas realizadas são armazenadas em:

```text
spotify_cache.json
```

Isso evita repetir várias chamadas à Spotify Web API.

Quando as regras de busca forem alteradas significativamente, pode ser útil apagar esse arquivo para testar novamente os resultados com um cache limpo.

## Progresso

Os itens processados são armazenados em:

```text
progress.json
```

O identificador de progresso também considera os discos selecionados.

Dessa forma, o mesmo álbum pode aparecer mais de uma vez na planilha com seleções de discos diferentes.

## Segurança

Nunca publique no GitHub:

- Spotify Client Secret;
- tokens OAuth;
- arquivos contendo credenciais;
- caches de autenticação.

As credenciais não ficam armazenadas diretamente no repositório.

## `.gitignore`

Exemplo recomendado:

```gitignore
spotify_cache.json
progress.json
.env
.cache
.spotify-library-migrator/
__pycache__/
*.pyc
```

## Tecnologias utilizadas

- Python
- Pandas
- Spotipy
- Spotify Web API
- Keyring
- OpenPyXL
- Excel

## Próximas melhorias

Algumas possibilidades de evolução:

- relatório das músicas que não foram encontradas;
- auditoria de divergências entre datas da planilha e Spotify;
- revisão manual de correspondências duvidosas;
- testes automatizados;
- interface gráfica;
- suporte a outras plataformas de streaming.

## Aviso

Projeto independente e sem vínculo oficial com o Spotify.

Spotify e Spotify Web API pertencem aos seus respectivos proprietários.
