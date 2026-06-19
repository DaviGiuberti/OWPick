# Documentação Técnica — OWPick (Overwatch Best Picks)

---

## Atualização — OWPick (versão 1.1.1)

**Novos módulos / arquivos:**

- `utils.py` — utilitário comum e **FONTE ÚNICA de dados de heróis e mapas** (constantes `HEROES_ROLES` e `MAPS_DATA` embutidas). Centraliza `resource_path()`, leitura/cache das planilhas, normalização de nomes (`normalize_hero_name`), coordenadas de captura (`config.json`) e a **matemática de resolução** (720p/1080p/2K e outras, por escala/interpolação). Não lê mais `heroes_roles.json` nem `maps.txt`.
- `map.py` — identificação automática do mapa. Recorta a região do nome do mapa em `print/full.png`, roda OCR (Tesseract embutido em `ocr/`) e faz fuzzy match (`rapidfuzz`) contra `utils.get_map_names()`. Grava o resultado em `current_map.txt`.
- `config.json` — coordenadas de captura por resolução (`map_region` + `base_resolution`). Usado como âncoras para escala/interpolação de qualquer resolução (inclui 1080p).
- `stats_inputs.csv` — winrate/pickrate por mapa, base do MetaStrength. Gerado por `coletar_stats.py`. Lido em runtime com cache.
- `coletar_stats.py` — **scraper externo** (Playwright) que coleta winrate/pickrate por mapa em owtics.gg e gera `stats_inputs.csv`, usando `utils` como fonte de heróis e mapas. Roda offline (ferramenta de dados).

> `heroes_roles.json` e `maps.txt` permanecem no repositório como referência, mas **não são mais lidos pelo programa** — a fonte de verdade é `utils.py`.

**Modelo de scoring:**

```
S(h) = β_meta · m_scaled(h, k) + β_ctr · T_ctr(h) + T_syn(h)

m_scaled(h,k) = α · clamp( (wr_adj(h,k) - wr̄(k)) / σ(k), -Mmax, +Mmax )   (MetaStrength)
T_ctr(h)      = Σ_e  w_e · C(h, e)            (counter com threat weighting)
w_e           = max(0.1, 1 + λ · Σ_a C(e,a) + μ · m(e,k)) (peso de ameaça; inclui MetaStrength do inimigo no mapa)
T_syn(h)      = Σ_a  Y(h, a) · β_syn          (sinergia; diagonal h==a ignorada)
```

Parâmetros iniciais: `κ_base=100`, `ε=0.001`, `Mmax=3.0`, `α=1.0`, `λ=0.25`, `μ=0.3`, `β_meta=1.0`, `β_ctr=1.0`, `β_syn=0.65`. Heróis já presentes no time aliado são **excluídos** do ranking (regra rígida — substitui o antigo hack `-11` da diagonal de sinergia).

**Mudanças de comportamento:**

- O *threat weighting* é comportamento padrão e sempre ativo. O antigo multiplicador `(total/4)+1`, o arquivo `prioritize.txt`, a opção de menu 4 e `toggle_prioritize_file()` foram removidos. `enemy_mult.py` foi mantido apenas como utilitário de diagnóstico. A partir da v1.1.1, o `w_e` incorpora também o MetaStrength do inimigo no mapa atual: `w_e = max(0.1, 1 + λ·Σ_a C(e,a) + μ·m(e,k))`.
- O pipeline agora roda `map.executar()` entre `comparar` e `choose_ow_hero` (em `main.py`).
- As planilhas e o `stats_inputs.csv` são lidos **uma única vez** (cache `lru_cache` em `utils`) e convertidos em dicionários normalizados, eliminando releituras de disco entre execuções do pipeline.
- Nomes de herói são normalizados no scoring, tornando-o tolerante a `D.Va`/`DVa` e `Soldier: 76`/`Soldier 76`.
- **Suporte a 1080p (e qualquer resolução):** a lógica de resolução foi centralizada em `utils` (`nearest_resolution_key`, `resolution_scale`, `get_scaled_map_region`). 720p e 2K são âncoras; resoluções intermediárias (1080p) têm a região do mapa **interpolada** entre as âncoras, e os templates são redimensionados pela escala — sem tabelas independentes por resolução.
- `overwatch.spec`: `selenium` removido; `pytesseract`/`ocr/` mantidos (usados por `map.py`); `config.json` e `stats_inputs.csv` e módulos (`utils`, `map`) no bundle. `heroes_roles.json`/`maps.txt` **não** são mais empacotados (dados embutidos em `utils.py`).
- Typos de template corrigidos: `Illarri.png → Illari.png`, `Rroadhog.png → Roadhog.png`. `Shion` adicionado.

**Arquivos novos gerados em runtime:** `current_map.txt` (mapa identificado na última captura).

---

## Visão Geral

### Objetivo do Projeto

OWPick é uma ferramenta desktop para jogadores de **Overwatch 2** que automatiza a recomendação de heróis durante a fase de escolha de personagem. O sistema captura a tela do jogo, identifica os heróis presentes na tela de seleção (aliados e inimigos) por comparação de imagem e, com base em planilhas de counters e sinergias, gera um ranking dos melhores heróis que o usuário pode jogar naquela partida.

### Funcionalidades Principais

- Captura automática da tela de seleção de heróis via hotkey global (`TAB+1`)
- Identificação de heróis por comparação de imagem (template matching com janela deslizante)
- Suporte a múltiplas resoluções de tela (720p e 2K, com escalonamento automático)
- Cálculo de pontuação baseado em:
  - **Counter score**: quão bem o herói do jogador countera os inimigos
  - **Sinergia score**: quão bem o herói do jogador sinergiza com os aliados (peso 0.65)
- Modo opcional de **priorização de counters**: pondera inimigos mais difíceis de enfrentar com multiplicador dinâmico
- Gerenciamento de heróis favoritos por função (DPS, Suporte, Tank, Fila Aberta)
- Sistema de **auto-atualização** via GitHub Releases
- Empacotamento como executável único (`.exe`) via PyInstaller

---

## Arquitetura

### Estrutura de Pastas

```
Overwatch-Best-Picks/
├── main.py                  # Ponto de entrada — menu e hotkeys
├── screenshot.py            # Captura de tela e recorte de retratos
├── comparar.py              # Template matching para identificar heróis
├── map.py                   #  OCR + fuzzy match do nome do mapa
├── choose_ow_hero.py        # Cálculo e exibição do ranking de heróis
├── enemy_mult.py            #  Utilitário de threat weight (fora do pipeline)
├── favoriteHero.py          # CRUD de heróis favoritos
├── roles.py                 # Seleção e persistência de função (role)
├── updater.py               # Sistema de auto-update
├── utils.py                 #  Utilitários comuns (resource_path, planilhas, nomes)
├── coletar_stats.py         #  Scraper externo → stats_inputs.csv + maps.txt
│
├── heroscreenshot.py        # [Utilitário legado, não usado no pipeline]
├── resolucao.py             # [Utilitário de seleção de coordenadas de tela]
│
├── heroes ally.xlsx         # Planilha de sinergia entre heróis
├── heroes enemy.xlsx        # Planilha de counters entre heróis
├── heroes_roles.json        # [ref] Não lido em runtime (dados embutidos em utils.py)
├── maps.txt                 # [ref] Não lido em runtime (dados embutidos em utils.py)
├── config.json              #  Coordenadas de captura por resolução (âncoras)
├── stats_inputs.csv         #  Winrate/pickrate por mapa (MetaStrength)
├── version.txt              # Versão atual do executável
├── version.json             # Versão remota para verificação de update
├── overwatch.spec           # Spec do PyInstaller para gerar o .exe
│
├── heroes/                  # Templates de imagem dos heróis
│   ├── 720p/
│   │   ├── dps/             # Retratos de DPS em 720p
│   │   ├── sup/             # Retratos de Suporte em 720p
│   │   └── tank/            # Retratos de Tank em 720p
│   └── 2k/
│       ├── dps/             # Retratos de DPS em 2K
│       ├── sup/             # Retratos de Suporte em 2K
│       └── tank/            # Retratos de Tank em 2K
│
├── ocr/                     # Tesseract OCR embutido (binários e tessdata)
├── dist/OWPick/             # Executável gerado pelo PyInstaller
│   ├── OWPick.exe
│   └── _internal/           # DLLs, módulos Python e assets empacotados
│
└── .venv/                   # Ambiente virtual Python
```

**Arquivos gerados em tempo de execução** (não versionados):
```
Roles.txt         # Role selecionada ("DPS", "SUP", "TANK", "ALL")
ALL.txt           # Lista de todos os heróis favoritos
DPS.txt           # Favoritos DPS
SUP.txt           # Favoritos Suporte
TANK.txt          # Favoritos Tank
prioritize.txt    # Flag de priorização ("0" ou "1") — legado; não afeta o scoring
lineup.txt        # Heróis identificados na última captura (9 linhas)
current_map.txt   # Mapa identificado na última captura
print/            # Recortes de tela temporários
```

### Componentes Principais

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| **Orquestrador** | `main.py` | Menu, hotkeys, threading, inicialização |
| **Captura** | `screenshot.py` | Screen capture via MSS, recorte de retratos |
| **Identificação** | `comparar.py` | Template matching com OpenCV/NumPy/Pillow |
| **Mapa** | `map.py` | OCR + fuzzy match do nome do mapa → `current_map.txt` |
| **Ranking** | `choose_ow_hero.py` | Scoring (MetaStrength + threat weighting + sinergia) e output |
| **Threat weight** | `enemy_mult.py` | Utilitário de threat weight (não chamado no pipeline) |
| **Favoritos** | `favoriteHero.py` | Lista de heróis jogáveis do usuário |
| **Role** | `roles.py` | Função do jogador na partida |
| **Updater** | `updater.py` | Auto-update via GitHub |
| **Utilitários** | `utils.py` | `resource_path`, planilhas, normalização de nomes, config |
| **Dados (offline)** | `coletar_stats.py` | Scraper que gera `stats_inputs.csv` + `maps.txt` |

### Relação entre os Módulos

```
main.py
├── updater.check_for_updates()      → updater.py
├── roles.executar()                 → roles.py        → [grava Roles.txt]
├── favoriteHero.executar()          → favoriteHero.py → [grava ALL/DPS/SUP/TANK.txt]
└── [TAB+1 hotkey]
    ├── screenshot.executar()        → screenshot.py   → [grava print/]
    ├── comparar.executar()          → comparar.py     → [lê print/, heroes/, escreve lineup.txt]
    └── choose_ow_hero.run_hero_ranking()
        ├── [lê Roles.txt, {role}.txt, lineup.txt]
        ├── [lê heroes ally.xlsx, heroes enemy.xlsx]
        └── enemy_mult.executar(hero)  → enemy_mult.py  → [lê lineup.txt, planilhas]
```

---

## Fluxo de Funcionamento

### Como o Sistema Inicia

1. O usuário executa `OWPick.exe` (ou `python main.py`)
2. `updater.check_for_updates()` é chamado:
   - Baixa `version.json` do GitHub
   - Compara a versão remota com `version.txt` local
   - Se houver versão nova, pergunta ao usuário se quer atualizar
3. Se `Roles.txt` não existir → `roles.executar()` é chamado (escolha de role obrigatória)
4. Se `ALL.txt` não existir → `favoriteHero.executar()` é chamado (configuração de favoritos)
5. O hotkey global `TAB+1` é registrado via `keyboard.hook()`
6. O loop de input de menu é iniciado em uma thread daemon separada
7. O programa entra em loop principal (`while True: time.sleep(1)`)

### Como os Dados Fluem entre os Módulos

```
[Jogo Overwatch aberto na tela de seleção]
        ↓
[TAB+1 pressionado]
        ↓
screenshot.executar()
  - Captura full.png (tela inteira)
  - Calcula escala (full_w / 1280)
  - Para cada variação de perk (0perk, 1perk, 2perk, bug):
      - Recorta ally1..ally5 e enemy1..enemy5 nas coordenadas escaladas
      - Salva em print/{perk}/
  - Também recorta e salva print/map/map.png
        ↓
comparar.executar()
  - Detecta resolução a partir de print/full.png → seleciona heroes/720p/ ou heroes/2k/
  - Para cada pasta perk (0perk, 1perk, 2perk, bug):
      - Aplica sliding-window MAE entre o recorte e todos os templates da categoria correta
      - Registra nome do herói identificado e score (erro médio absoluto normalizado)
  - Seleciona a pasta com menor avg_score (melhor identificação)
  - Escreve os 9 nomes em lineup.txt (4 aliados + 5 inimigos)
        ↓
choose_ow_hero.run_hero_ranking()
  - Lê role de Roles.txt → abre {role}.txt com heróis jogáveis
  - Lê lineup.txt: lines[:4] = aliados, lines[4:9] = inimigos
  - Para cada herói jogável:
      - enemy_score = Σ(heroes enemy.xlsx[herói][inimigo] × multiplicador)
      - ally_score  = Σ(heroes ally.xlsx[herói][aliado] × 0.65)
      - total = enemy_score + ally_score
  - Exibe ranking ordenado por total decrescente
```

### Modo de Priorização de Counters

Quando `prioritize.txt` contém `"1"`, `choose_ow_hero` chama `enemy_mult.executar(hero)` para cada herói inimigo antes de calcular o ranking. O `enemy_mult` avalia quanto aquele inimigo countera o time aliado e retorna um multiplicador:

```python
if total >= 0:
    mult = (total / 4) + 1   # inimigo forte: multiplica acima de 1.0
else:
    mult = 1 - 0.125 * |total|  # inimigo fraco: multiplica abaixo de 1.0
```

Esse multiplicador é então aplicado ao `enemy_score` do herói jogável contra esse inimigo específico, ampliando a importância de counterar inimigos mais perigosos.

### Como o Executável é Gerado e Utilizado

O executável `OWPick.exe` é gerado pelo **PyInstaller** a partir do arquivo `overwatch.spec`:

1. O spec inclui no bundle:
   - Todos os módulos Python do projeto
   - As planilhas `heroes ally.xlsx` e `heroes enemy.xlsx`
   - A pasta `heroes/` (templates de imagem)
   - A pasta `ocr/` (Tesseract OCR completo com tessdata)
   - O arquivo `version.txt`
2. O PyInstaller empacota tudo em `dist/OWPick/`:
   - `OWPick.exe` — executável principal
   - `_internal/` — DLLs, módulos Python compilados, assets
3. Quando `OWPick.exe` é executado, o PyInstaller extrai o conteúdo em uma pasta temporária (`sys._MEIPASS`) e executa `main.py`. A função `resource_path()` presente em vários módulos resolve os caminhos corretos tanto no modo desenvolvimento quanto no executável.
4. Para distribuição, a pasta `dist/OWPick/` inteira é compactada em um `.zip` e publicada nas GitHub Releases.
5. O sistema de auto-update (`updater.py`) detecta a nova versão via `version.json` no GitHub e aplica a atualização com um `.bat` gerado dinamicamente (usando `robocopy`).

---

## Detalhamento dos Arquivos Python

---

### `main.py`

**Caminho**: `D:\DAVI\Projetos\Overwatch-Best-Picks\main.py`

**Responsabilidade**: Ponto de entrada e orquestrador central do programa. Gerencia o hotkey global, o menu de texto interativo e garante que as configurações iniciais existam.

**Classes**: Nenhuma

**Principais Funções**:

| Função | Descrição |
|---|---|
| `print_main_menu()` | Exibe o menu completo de comandos |
| `print_small_menu()` | Exibe menu resumido após execução de ação |
| `run_pipeline()` | Executa a sequência screenshot → comparar → ranking |
| `run_role()` | Chama `roles.executar()` para alterar a role |
| `run_favorite()` | Chama `favoriteHero.executar()` para gerenciar favoritos |
| `toggle_prioritize_file()` | Alterna o arquivo `prioritize.txt` entre `0` e `1` |
| `spawn_in_thread(func)` | Executa uma função em thread daemon |
| `_on_key_event(event)` | Handler global de teclado; detecta `TAB+1` |
| `enable_pipeline_hotkey_hook()` | Registra o hook de teclado |
| `disable_pipeline_hotkey_hook()` | Remove o hook de teclado |
| `call_and_pause_main(func)` | Pausa o estado `IN_MAIN` durante execução de subcomando |
| `input_loop()` | Loop principal de leitura de comandos do terminal |

**Interação com outros módulos**:
- Importa e chama: `choose_ow_hero`, `favoriteHero`, `roles`, `screenshot`, `updater`
- Importa `comparar` (referenciado internamente dentro de `run_pipeline`, mas o import está no topo)

**Fluxo de Execução**:
1. Verifica atualização via `updater`
2. Garante configurações iniciais (Roles.txt, ALL.txt)
3. Registra hotkey `TAB+1` e inicia thread de input
4. Mantém o processo vivo com `while True: time.sleep(1)`

---

### `screenshot.py`

**Caminho**: `D:\DAVI\Projetos\Overwatch-Best-Picks\screenshot.py`

**Responsabilidade**: Captura a tela do monitor principal e recorta os retratos dos heróis aliados e inimigos em múltiplas variações (perk slots), salvando-os em `print/{perk}/`. Adapta automaticamente as coordenadas à resolução da tela do usuário.

**Classes**: Nenhuma

**Principais Funções**:

| Função | Descrição |
|---|---|
| `executar()` | Função principal: captura, escala e salva todos os recortes |
| `read_role()` (local) | Lê `Roles.txt` para saber qual slot pular |
| `scale_and_clamp()` (local) | Converte coordenadas da resolução base (1280×720) para a resolução atual |

**Lógica de Captura**:
- Captura a tela inteira com `mss` e salva como `print/full.png`
- Calcula `scale_x = full_w / 1280` e `scale_y = full_h / 720`
- Define 4 variações de posição horizontal (`left`) chamadas perks: `0perk`(230), `1perk`(217), `bug`(212), `2perk`(197), representando diferentes estados visuais da UI do Overwatch
- Para cada perk, recorta 10 posições verticais (ally1..5, enemy1..5) aplicando um buffer vertical de 8px acima e abaixo para tolerância de alinhamento
- Pula um arquivo baseado na role (ex: DPS pula `ally2.png`, o slot DPS aliado seria o próprio jogador)
- Recorta também a área do mapa (`print/map/map.png`) com coordenadas específicas por resolução

**Interação**: Produz os arquivos lidos por `comparar.py`.

---

### `comparar.py`

**Caminho**: `D:\DAVI\Projetos\Overwatch-Best-Picks\comparar.py`

**Responsabilidade**: Compara os recortes capturados pelo `screenshot.py` com templates de imagem de heróis para identificar quem está na tela de seleção. Escreve o resultado em `lineup.txt`.

**Classes**: Nenhuma

**Principais Funções**:

| Função | Descrição |
|---|---|
| `executar()` | Ponto de entrada: coordena todo o processo de matching |
| `get_scale_from_full(watch_dir)` | Calcula escala a partir de `print/full.png` |
| `compute_dims(scale)` | Retorna `crop_size` e `window_height` escalados |
| `detect_screenshot_resolution(watch_dir)` | Detecta resolução dos arquivos em `print/` |
| `find_nearest_resolution_folder(resolution)` | Mapeia resolução para pasta `720p` ou `2k` |
| `load_image_gray(path, target_size)` | Carrega imagem em escala de cinza como array NumPy |
| `normalized_mae(a, b)` | Calcula erro médio absoluto normalizado entre dois arrays |
| `load_templates_from_category(dir, category, size)` | Carrega templates de uma categoria (dps/sup/tank) |
| `load_all_templates(dir, size)` | Carrega templates de todas as categorias |
| `find_best_match_sliding(img, templates, window_h, crop_w)` | Matching com janela deslizante vertical |
| `_best_against_templates(img, templates)` | Compara uma janela contra todos os templates |
| `process_folder(folder_path, templates, crop_size, window_h)` | Processa todos os arquivos em uma pasta perk |

**Algoritmo de Matching**:
1. Carrega o template de cada herói da pasta de resolução correspondente (`heroes/720p/` ou `heroes/2k/`)
2. Para cada recorte de herói, desliza uma janela de altura `window_height` verticalmente sobre a imagem (compensando possíveis desalinhamentos)
3. Em cada posição da janela, calcula `normalized_mae` contra todos os templates da categoria correta
4. O template com menor MAE é o herói identificado
5. Após processar todas as 4 variações de perk, seleciona aquela com o menor `avg_score` (identificação mais confiante)

**Constantes importantes**:
- `FILE_TO_CATEGORY`: mapeia nome de arquivo para categoria do herói
- `BASE_CROP_SIZE = (42, 57)` — tamanho base do recorte em 720p
- `BASE_WINDOW_HEIGHT = 42` — altura da janela deslizante em 720p

**Interação**: Lê de `print/`, lê templates de `heroes/`, escreve `lineup.txt`.

---

### `choose_ow_hero.py`

**Caminho**: `D:\DAVI\Projetos\Overwatch-Best-Picks\choose_ow_hero.py`

**Responsabilidade**: Módulo central de análise e recomendação. Lê o lineup identificado, carrega as planilhas de synergy/counter, calcula a pontuação de cada herói jogável e exibe o ranking ordenado.

**Classes**: Nenhuma

**Principais Funções**:

| Função | Descrição |
|---|---|
| `resource_path(path)` | Resolve caminhos para funcionar tanto no `.py` quanto no `.exe` |
| `read_role()` | Lê `Roles.txt` e valida a existência do arquivo `{role}.txt` |
| `read_playable_heroes(role)` | Lê a lista de heróis favoritos da role atual |
| `read_lineup(filepath)` | Lê `lineup.txt`; retorna `(allies[:4], enemies[4:9])` |
| `read_heroes_ally_data()` | Carrega `heroes ally.xlsx` como DataFrame pandas |
| `read_heroes_enemy_data()` | Carrega `heroes enemy.xlsx` como DataFrame pandas |
| `read_priority_mode()` | Retorna `True` se `prioritize.txt` == `"1"` |
| `build_enemy_multipliers(enemies, priority_mode)` | Para cada inimigo, chama `enemy_mult.executar()` e armazena o multiplicador |
| `calculate_hero_score(hero, ally_df, enemy_df, allies, enemies, multipliers)` | Calcula `enemy_score`, `ally_score` e `total` para um herói |
| `print_ranking(rankings)` | Exibe a tabela ordenada por `total` no console |
| `run_hero_ranking()` | Orquestra toda a sequência de leitura, cálculo e exibição |

**Fórmula de Pontuação ** — ver a seção "Atualização — OWPick ":
```
S(h) = β_meta · m_scaled(h, k) + β_ctr · T_ctr(h) + T_syn(h)
T_ctr(h) = Σ_e  w_e · C(h, e)        com  w_e = max(0.1, 1 + λ·Σ_a C(e, a))
T_syn(h) = Σ_a  Y(h, a) · 0.65       (diagonal h==a ignorada)
m_scaled(h, k) = MetaStrength do herói no mapa atual (z-score do winrate ajustado)
```

**Interação **: Lê `Roles.txt`, `{role}.txt`, `lineup.txt`, `current_map.txt`, `heroes ally.xlsx`, `heroes enemy.xlsx`, `stats_inputs.csv`, `heroes_roles.json`. O threat weighting é calculado internamente (não chama mais `enemy_mult.executar()` no scoring).

---

### `enemy_mult.py`

**Caminho**: `D:\DAVI\Projetos\Overwatch-Best-Picks\enemy_mult.py`

**Responsabilidade**: Avalia um herói inimigo específico contra o lineup atual para gerar um multiplicador. O multiplicador indica quão perigoso aquele inimigo é para o time aliado — inimigos que counter muito o time recebem multiplicador > 1.

**Importante**: Este módulo lê o `lineup.txt` com perspectiva invertida em relação a `choose_ow_hero.py`: `lines[:4]` são tratados como **inimigos do herói avaliado** (= seus aliados) e `lines[4:9]` como **aliados do herói avaliado** (= os inimigos reais + o próprio herói).

**Classes**: Nenhuma

**Principais Funções**:

| Função | Descrição |
|---|---|
| `resource_path(path)` | Resolve caminhos para funcionar no `.exe` |
| `read_lineup(filepath)` | Lê `lineup.txt` com perspectiva do herói inimigo |
| `read_heroes_ally_data()` | Carrega `heroes ally.xlsx` |
| `read_heroes_enemy_data()` | Carrega `heroes enemy.xlsx` |
| `calculate_hero_score(hero, ally_df, enemy_df, allies, enemies)` | Calcula score do herói inimigo |
| `executar(hero)` | Função exportada: retorna o multiplicador float para o herói passado |

**Fórmula (threat weighting)**:
```python
w_e = max(0.1, 1 + λ * Σ_a C(e, a))   # λ = 0.25; a ∈ aliados do jogador
```
O antigo multiplicador `(total/4)+1` foi substituído pelo threat weighting.

**Interação **: Não é mais chamado por `choose_ow_hero` (o threat weighting é interno). Mantido como utilitário de diagnóstico; aceita a matriz de counters pré-carregada para evitar releitura de disco.

---

### `favoriteHero.py`

**Caminho**: `D:\DAVI\Projetos\Overwatch-Best-Picks\favoriteHero.py`

**Responsabilidade**: Gerencia a lista de heróis favoritos do usuário. Persiste os dados em `ALL.txt` (todos os favoritos), e em arquivos separados por role: `DPS.txt`, `SUP.txt`, `TANK.txt`.

**Classes**: Nenhuma

**Constantes**:
- `HEROES`: dicionário com os heróis do Overwatch 2 organizados por função (DPS: 23, SUP: 14, TANK: 14)
- `FAVORITES_FILE = "ALL.txt"`

**Principais Funções**:

| Função | Descrição |
|---|---|
| `normalize_text(text)` | Remove acentos, converte para minúsculas (para busca fuzzy) |
| `get_all_heroes()` | Retorna lista flat de todos os heróis |
| `get_hero_role(hero_name)` | Retorna a role de um herói (DPS/SUP/TANK) |
| `find_best_match(user_input, normalized_heroes)` | Fuzzy matching com `difflib.get_close_matches` (cutoff 0.4) |
| `save_heroes_to_files(heroes_list)` | Salva heróis em ALL.txt + arquivos por role |
| `load_favorites()` | Carrega lista de ALL.txt |
| `add_favorite(hero_name)` | Adiciona herói e persiste |
| `remove_favorite(hero_name)` | Remove herói e persiste |
| `list_favorites()` | Lista heróis favoritos com sua role |
| `add_role_or_all()` | Adiciona em lote toda uma role ou todos os heróis |
| `add_role_or_all_menu()` | Exibe submenu de seleção de lote |
| `executar()` | Loop interativo de gerenciamento de favoritos |

**Interação**: Chamado por `main.py`. Produz arquivos `.txt` por role que são lidos por `choose_ow_hero.py` e `screenshot.py`.

---

### `roles.py`

**Caminho**: `D:\DAVI\Projetos\Overwatch-Best-Picks\roles.py`

**Responsabilidade**: Permite ao usuário selecionar sua função (role) na partida e persiste a escolha em `Roles.txt`. Usa leitura de teclado sem echo (`msvcrt.getch`) para captura imediata de uma tecla.

**Classes**: Nenhuma

**Principais Funções**:

| Função | Descrição |
|---|---|
| `executar()` | Exibe menu de role e salva a escolha em `Roles.txt` |

**Mapeamento de teclas**:
- `1` → `ALL` (Fila Aberta)
- `2` → `TANK`
- `3` → `SUP`
- `4` → `DPS`

**Interação**: Chamado por `main.py`. Grava `Roles.txt` lido por `screenshot.py` e `choose_ow_hero.py`.

---

### `updater.py`

**Caminho**: `D:\DAVI\Projetos\Overwatch-Best-Picks\updater.py`

**Responsabilidade**: Sistema de auto-atualização. Verifica a versão remota no GitHub, oferece download e aplica a atualização via script `.bat` gerado dinamicamente (sem precisar de instalador).

**Classes**: Nenhuma

**Constantes**:
- `VERSION_JSON_URL`: URL do `version.json` no GitHub
- `VERSION_FILE = "version.txt"`

**Principais Funções**:

| Função | Descrição |
|---|---|
| `resource_path(path)` | Resolve caminhos para o `.exe` |
| `get_exe_dir()` | Retorna a pasta do executável (para sobrescrever na atualização) |
| `get_local_version()` | Lê `version.txt` embutido no pacote |
| `_parse_version(v)` | Converte string `"1.2.3"` em tupla `(1, 2, 3)` |
| `_fetch_version_info()` | Baixa `version.json` remoto via `urllib` (timeout 6s) |
| `_download_file(url, dest_path)` | Baixa arquivo com barra de progresso |
| `_apply_update(download_url)` | Baixa o `.zip`, extrai, gera `.bat` e encerra o processo para aplicação |
| `check_for_updates()` | Ponto de entrada: compara versões e age se necessário |

**Fluxo de Update**:
1. Baixa `version.json` do GitHub
2. Compara tuplas de versão
3. Se remota > local: pergunta ao usuário
4. Se confirmado: baixa o `.zip`, extrai em `%TEMP%`, gera `owpick_update.bat`
5. O `.bat` usa `robocopy` para copiar os novos arquivos por cima dos antigos após o `.exe` fechar

**Interação**: Chamado por `main.py` na inicialização.

---

### `resolucao.py`

**Caminho**: `D:\DAVI\Projetos\Overwatch-Best-Picks\resolucao.py`

**Responsabilidade**: Utilitário de desenvolvimento para selecionar visualmente uma área da tela e imprimir as coordenadas. **Não é usado no pipeline principal.** Serve para o desenvolvedor descobrir coordenadas corretas de recorte.

**Classes**:

| Classe | Descrição |
|---|---|
| `AreaSelector` | Janela fullscreen semitransparente com seleção de área via mouse |

**Métodos de `AreaSelector`**:

| Método | Descrição |
|---|---|
| `__init__()` | Inicializa a janela Tkinter com countdown de 3 segundos |
| `on_press(event)` | Registra ponto inicial do retângulo |
| `on_drag(event)` | Atualiza o retângulo vermelho visualmente |
| `on_release(event)` | Calcula e imprime `left`, `top`, `width`, `height` |

**Interação**: Standalone. Não importado por nenhum outro módulo.

---

### `heroscreenshot.py`

**Caminho**: `D:\DAVI\Projetos\Overwatch-Best-Picks\heroscreenshot.py`

**Responsabilidade**: Script legado de captura de tela com região fixa e hotkey `TAB+1`. **Não é usado no pipeline atual.** Representa uma versão anterior do sistema de screenshot antes da refatoração que o substituiu por `screenshot.py`.

**Classes**: Nenhuma

**Principais Funções**:

| Função | Descrição |
|---|---|
| `tirar_print()` | Captura uma região fixa da tela e salva como `print{N}.jpg` |

**Diferenças em relação a `screenshot.py`**:
- Usa região fixa (`monitor = {"left": 461, "top": 252, ...}`) sem escalonamento por resolução
- Salva um único arquivo por vez (`print1.jpg`, `print2.jpg`, ...)
- Usa `keyboard.wait()` bloqueante (incompatível com threading)
- Não gera o `lineup.txt` nem lida com variações de perk

**Interação**: Não importado por nenhum módulo. Arquivo legado.

---

## Dependências

### Dependências Python Identificadas no `.spec`

| Biblioteca | Versão (no .venv) | Finalidade |
|---|---|---|
| `mss` | 10.2.0 | Captura de tela multiplataforma (mais rápido que PyAutoGUI) |
| `Pillow` (PIL) | 12.2.0 | Manipulação de imagens, conversão de formatos, crop |
| `opencv-python` (cv2) | 4.13.0.92 | Redimensionamento de imagens, resize para matching |
| `numpy` | 2.4.4 | Arrays numéricos para cálculo de MAE nos templates |
| `pandas` | (via openpyxl) | Leitura das planilhas `.xlsx` como DataFrames |
| `openpyxl` | 3.1.5 | Backend para pandas ler arquivos `.xlsx` |
| `keyboard` | 0.13.5 | Hotkeys globais e captura de teclas sem foco na janela |
| `rapidfuzz` | 3.14.5 | Fuzzy matching para busca de heróis (presente no spec, `difflib` é usado no código) |
| `unidecode` | 1.4.0 | Normalização de strings com acentos |
| `pytesseract` | 0.3.13 | Wrapper Python para Tesseract OCR (incluído no spec, mas não usado no código atual) |
| `PyInstaller` | 6.20.0 | Geração do executável `.exe` |
| `msvcrt` | stdlib | Leitura de tecla sem echo (Windows only) |
| `tkinter` | stdlib | Interface gráfica para o seletor de área (`resolucao.py`) |
| `difflib` | stdlib | `get_close_matches` para busca fuzzy de heróis |
| `unicodedata` | stdlib | Remoção de acentos para normalização |
| `urllib` | stdlib | Download de `version.json` e do pacote de update |
| `zipfile`, `shutil`, `subprocess` | stdlib | Extração e aplicação do pacote de atualização |

### Dependência Externa (Binária)

| Componente | Localização | Finalidade |
|---|---|---|
| **Tesseract OCR** | `ocr/` | Reconhecimento óptico de caracteres (embutido no executável, mas não chamado no código atual) |

---

## Melhorias Possíveis

### Bugs Identificados

1. **Typo em nomes de arquivo de template**:
   - `heroes/2k/sup/Illarri.png` (duplo 'r') — deveria ser `Illari.png`
   - `heroes/2k/tank/Rroadhog.png` (duplo 'R') — deveria ser `Roadhog.png`
   - Esses typos podem causar falhas silenciosas no matching se o stem do arquivo for comparado ao nome do herói

2. **Herói `Shion` sem entrada no dicionário `HEROES`**:
   - Existem imagens `heroes/2k/dps/Shion.jpg` e `heroes/2k/dps/Shion.png` (novos arquivos não-commitados)
   - O nome `"Shion"` não está na lista `HEROES["DPS"]` em `favoriteHero.py`
   - O herói pode ser identificado pelo `comparar.py` mas nunca aparecer no ranking

3. **Leitura do `lineup.txt` invertida em `enemy_mult.py` vs `choose_ow_hero.py`**:
   - `choose_ow_hero.py`: `allies = lines[:4]`, `enemies = lines[4:9]`
   - `enemy_mult.py`: `enemies = lines[:4]`, `allies = lines[4:9]`
   - Embora essa inversão seja intencional (avalia do ponto de vista do herói inimigo), não há comentário explicando isso claramente e os nomes de variáveis locais são opostos ao esperado, dificultando manutenção

4. **Selenium listado como hidden import sem uso**:
   - O `overwatch.spec` declara `selenium` e seus submódulos como `hiddenimports`, mas `selenium` não é importado em nenhum arquivo `.py`. Aumenta o tamanho do executável sem necessidade.

5. **`pytesseract` e a pasta `ocr/` incluídos sem uso**:
   - Nenhum arquivo `.py` atual chama `pytesseract`. O OCR foi planejado ou removido sem limpeza do spec. Isso adiciona dezenas de MB ao executável.

### Sugestões de Refatoração

1. **Eliminar duplicação de código**:
   - `resource_path()` é definida identicamente em `choose_ow_hero.py`, `enemy_mult.py`, `updater.py` e `comparar.py`. Deveria estar em um módulo utilitário comum (ex: `utils.py`)
   - `read_heroes_ally_data()` e `read_heroes_enemy_data()` também são duplicadas entre `choose_ow_hero.py` e `enemy_mult.py`

2. **Cache das planilhas**:
   - Quando `priority_mode` está ativo, `enemy_mult.executar()` é chamado uma vez por inimigo (até 5 vezes), e cada chamada relê as planilhas `.xlsx` do disco. As planilhas deveriam ser lidas uma única vez e passadas como argumento, o que já foi parcialmente endereçado em `choose_ow_hero.build_enemy_multipliers()`, mas `enemy_mult.py` as relê internamente

3. **Nomenclatura no `enemy_mult.py`**:
   - As variáveis `allies` e `enemies` têm semântica invertida (são do ponto de vista do inimigo, não do jogador). Adicionar comentários claros ou renomear para `heroes_of_enemy` / `opponents_of_enemy` melhoraria a legibilidade

4. **Remover `heroscreenshot.py`**:
   - Este arquivo é um artefato de desenvolvimento que não é mais utilizado. Pode causar confusão para novos contribuidores

5. **Externalizar configurações de captura**:
   - As coordenadas de recorte em `screenshot.py` estão hardcoded. Um arquivo de configuração (`config.json`) permitiria ajustes sem alterar o código

6. **Limpar o `.spec` de dependências mortas**:
   - Remover `selenium` e avaliar se `pytesseract`/`ocr/` ainda fazem parte dos planos. Se não, removê-los reduzirá o executável em 50-100 MB

7. **Adicionar `requirements.txt`**:
   - O projeto não possui `requirements.txt`. Qualquer novo desenvolvedor precisa inferir as dependências a partir do `.spec` ou do `.venv`. Um `requirements.txt` (ou `pyproject.toml`) tornaria o setup explícito

8. **Adicionar `Shion` (e futuros heróis novos) ao dicionário `HEROES`**:
   - O processo de adição de novos heróis requer alteração manual em pelo menos dois lugares: `favoriteHero.py` (dicionário `HEROES`) e a pasta `heroes/` (imagens de template). Considerar um processo documentado para onboarding de novos heróis.
