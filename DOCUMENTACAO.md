# Documentação Técnica — OWPick (Overwatch Best Picks)

---

## Visão Geral

### Objetivo do Projeto

OWPick é uma ferramenta desktop para jogadores de **Overwatch** que automatiza a recomendação de heróis durante a fase de escolha de personagem. O sistema captura a tela do jogo, identifica os heróis presentes na tela de seleção (aliados e inimigos) por comparação de imagem, identifica o mapa atual via OCR e, com base em planilhas de counters/sinergias e dados de meta por mapa, gera um ranking dos melhores heróis que o usuário pode jogar naquela partida.

### Funcionalidades Principais

- Captura automática da tela de seleção de heróis via hotkey global (`TAB+1`)
- Identificação de heróis por template matching com janela deslizante (MAE normalizado)
- **Suporte aos bans do modo Competitivo**: identifica os heróis banidos nos 5 slots de ban e os remove automaticamente do ranking (mesmo tratamento dos heróis já presentes no time). Os bans usam um banco de templates dedicado (`heroes/bans/`, ícones 3D oficiais — arte diferente dos retratos do lineup) e matching direto, sem janela deslizante
- Identificação automática do mapa via OCR (Tesseract embutido) + fuzzy match
- Suporte a múltiplas resoluções de tela: 720p e 2K com escalonamento automático; resoluções intermediárias (1080p) interpoladas
- **Escolha automática do banco de templates do lineup pelo TAMANHO do retrato** (não pela resolução da tela): retratos maiores usam o banco 2K (maior qualidade), menores usam 720p
- Cálculo de pontuação baseado em:
  - **MetaStrength** (`m_scaled`): desempenho estatístico do herói no mapa atual (z-score da winrate **bruta por role**, atenuado pela confiança da pickrate)
  - **Counter score** (`T_ctr`): quão bem o herói countera os inimigos, com ponderação por ameaça
  - **Sinergia score** (`T_syn`): quão bem o herói sinergiza com os aliados
- **Threat weighting**: pondera automaticamente inimigos mais perigosos (baseado em counters e meta no mapa)
- Exibição do ranking de ameaças inimigas antes do ranking de heróis
- Gerenciamento de heróis favoritos por função (DPS, Suporte, Tank, Fila Aberta)
- Sistema de **auto-atualização** via GitHub Releases
- Empacotamento como executável portátil (`.exe`) via PyInstaller

---

## Arquitetura

### Estrutura de Pastas

```
Overwatch-Best-Picks/
├── main.py                  # Ponto de entrada — menu e hotkeys
├── screenshot.py            # Captura de tela e recorte de retratos
├── comparar.py              # Template matching para identificar heróis
├── map.py                   # OCR + fuzzy match do nome do mapa
├── choose_ow_hero.py        # Cálculo e exibição do ranking de heróis
├── utils.py                 # Fonte única de dados: heróis, mapas, planilhas, utilitários
├── enemy_mult.py            # Utilitário de threat weight (fora do pipeline principal)
├── favoriteHero.py          # CRUD de heróis favoritos
├── roles.py                 # Seleção e persistência de função (role)
├── updater.py               # Sistema de auto-update
├── coletar_stats.py         # Scraper externo → stats_inputs.csv (ferramenta offline)
│
├── heroscreenshot.py        # [Legado, não usado no pipeline]
├── resolucao.py             # [Utilitário de desenvolvimento para coordenadas]
│
├── heroes ally.xlsx         # Planilha de sinergias entre heróis
├── heroes enemy.xlsx        # Planilha de counters entre heróis
├── heroes_roles.json        # [Referência — não lido em runtime; dados embutidos em utils.py]
├── maps.txt                 # [Referência — não lido em runtime; dados embutidos em utils.py]
├── config.json              # Coordenadas de captura do mapa por resolução (âncoras)
├── stats_inputs.csv         # Winrate/pickrate por mapa (fonte do MetaStrength)
├── version.txt              # Versão local do executável
├── version.json             # Versão remota para verificação de update
├── requirements.txt         # Dependências Python
├── overwatch.spec           # Spec do PyInstaller para gerar o .exe
│
├── heroes/                  # Templates de imagem dos heróis
│   ├── 720p/
│   │   ├── dps/             # Retratos de DPS em 720p
│   │   ├── sup/             # Retratos de Suporte em 720p
│   │   └── tank/            # Retratos de Tank em 720p
│   ├── 2k/
│   │   ├── dps/             # Retratos de DPS em 2K
│   │   ├── sup/             # Retratos de Suporte em 2K
│   │   └── tank/            # Retratos de Tank em 2K
│   └── bans/                # Ícones 3D oficiais (128px, pasta plana) — banco
│                            # dedicado dos bans; serve todas as resoluções
│
├── ocr/                     # Tesseract OCR embutido (binários + tessdata)
│   ├── tesseract.exe
│   └── tessdata/
│
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
lineup.txt        # Heróis identificados na última captura (9 linhas)
bans.txt          # Heróis banidos identificados na última captura (0-5 linhas)
current_map.txt   # Mapa identificado na última captura
print/            # Recortes de tela temporários (full.png + pastas por perk + bans/)
```

### Componentes Principais

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| **Orquestrador** | `main.py` | Menu, hotkeys, threading, inicialização |
| **Captura** | `screenshot.py` | Screen capture via MSS, recorte de retratos |
| **Identificação** | `comparar.py` | Template matching com OpenCV/NumPy/Pillow |
| **Mapa** | `map.py` | OCR + fuzzy match do nome do mapa → `current_map.txt` |
| **Ranking** | `choose_ow_hero.py` | Scoring (MetaStrength + threat weighting + sinergia) e output |
| **Utilitários** | `utils.py` | Fonte única: heróis, mapas, planilhas, normalização, config, resolução |
| **Threat weight** | `enemy_mult.py` | Utilitário de diagnóstico de threat weight (não chamado no pipeline) |
| **Favoritos** | `favoriteHero.py` | Lista de heróis jogáveis do usuário |
| **Role** | `roles.py` | Função do jogador na partida |
| **Updater** | `updater.py` | Auto-update via GitHub |
| **Dados (offline)** | `coletar_stats.py` | Scraper que gera `stats_inputs.csv` |

### Relação entre os Módulos

```
main.py
├── updater.check_for_updates()        → updater.py
├── roles.executar()                   → roles.py          → [grava Roles.txt]
├── favoriteHero.executar()            → favoriteHero.py   → [grava ALL/DPS/SUP/TANK.txt]
└── [TAB+1 hotkey]
    ├── screenshot.executar()          → screenshot.py     → [grava print/ (incl. print/bans/)]
    ├── comparar.executar()            → comparar.py       → [lê print/, heroes/, escreve lineup.txt e bans.txt]
    ├── map.executar()                 → map.py            → [lê print/full.png, escreve current_map.txt]
    └── choose_ow_hero.run_hero_ranking()
        ├── [lê Roles.txt, {role}.txt, lineup.txt, bans.txt, current_map.txt]
        ├── [lê heroes ally.xlsx, heroes enemy.xlsx via utils]
        └── [lê stats_inputs.csv via utils → MetaStrength]

utils.py  ←  importado por: comparar, map, choose_ow_hero, favoriteHero, screenshot, updater, coletar_stats
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
  - Captura tela inteira → print/full.png
  - Calcula escala: scale_x = full_w / 1280, scale_y = full_h / 720
  - Lê Roles.txt para saber qual slot de ally pular
  - Para cada variação de perk (0perk, 1perk, bug, 2perk):
      - Recorta ally1..ally5 e enemy1..enemy5 nas coordenadas escaladas
      - Salva em print/{perk}/ally1.png .. enemy5.png
  - Recorta os 5 slots de ban (uma única vez; independentes de perk;
    recorte EXATO do retrato, sem buffer vertical)
      - Salva em print/bans/ban1.png .. ban5.png
        ↓
comparar.executar()
  - Lê resolução de print/full.png e calcula a escala
  - Escolhe o banco de templates do LINEUP pelo tamanho do retrato normal na
    resolução atual (utils.template_bank_for_resolution) → heroes/720p/ ou heroes/2k/
  - Bans: matching DIRETO contra o banco dedicado heroes/bans/ (ícones 3D
    oficiais): descarta a moldura vermelha da UI, redimensiona recorte e
    templates para BAN_COMPARE_SIZE e calcula o MAE (sem janela deslizante).
    Se o melhor MAE ≤ BAN_MATCH_MAX_SCORE, registra o herói banido; senão o
    slot é tratado como vazio. Escreve os banidos em bans.txt (sempre refresca)
  - Carrega templates (dps, sup, tank) do banco do lineup em escala de cinza
  - Para cada pasta perk:
      - Desliza janela de altura window_height verticalmente sobre cada recorte
      - Calcula MAE normalizado contra todos os templates da categoria
      - Registra herói com menor MAE e o score
  - Seleciona a perk com menor avg_score (identificação mais confiante)
  - Escreve 9 nomes em lineup.txt (linhas 0-3: aliados, linhas 4-8: inimigos)
        ↓
map.executar()
  - Recorta região do nome do mapa em print/full.png
  - Pré-processa: grayscale → autocontraste → upscale 2×
  - Roda Tesseract OCR (psm 7)
  - Fuzzy match (fuzz.ratio) do texto OCR contra utils.get_map_names()
  - Grava nome do mapa em current_map.txt (ou "UNKNOWN" se score < 50)
        ↓
choose_ow_hero.run_hero_ranking()
  - Lê role de Roles.txt → abre {role}.txt com heróis jogáveis
  - Lê lineup.txt: lines[:4] = aliados, lines[4:9] = inimigos
  - Lê bans.txt: heróis banidos no competitivo (vazio se o modo não tiver bans)
  - Lê current_map.txt para o mapa atual
  - Carrega matrizes de sinergia e counters via utils (lru_cache)
  - Calcula MetaStrength: z-score da winrate bruta por role, atenuado pela confiança da pickrate
  - Calcula threat weights: w_e = softplus(1 + λ·Σ_a C(e,a) + μ·m(e,k))
  - Exibe ranking de ameaças inimigas (1º ao 5º por w_e)
  - Para cada herói jogável (excluindo aliados já presentes no time E banidos):
      - meta_score  = m_scaled(h, k)
      - ctr_score   = Σ_e w_e · C(h, e)
      - syn_score   = Σ_a Y(h, a) · β_syn  (diagonal ignorada)
      - total = β_meta · meta + β_ctr · ctr + syn
  - Exibe tabela ordenada por total decrescente: RANK | HERO | META | CTR | SYN | TOTAL
        ↓
[Terminal exibe o resultado e o menu retorna]
```

### Modelo de Scoring

```
S(h) = β_meta · m_scaled(h, k) + β_ctr · T_ctr(h) + T_syn(h)

m_scaled(h, k) = α · clamp( conf · (wr(h) - wr̄_role(k)) / σ_role(k), -Mmax, +Mmax )  [MetaStrength]
conf           = pr / (pr + k0_role),   k0_role = pickrate neutra da role            [confiança da pickrate]
T_ctr(h)       = Σ_e w_e · C(h, e)                                                    [counter com threat weighting]
raw_e          = 1 + λ · Σ_a C(e,a) + μ · m(e,k)
w_e            = softplus(raw_e) = ln(1 + e^{raw_e})                                  [peso de ameaça do inimigo e]
T_syn(h)       = Σ_a Y(h, a) · β_syn                                                  [sinergia; diagonal h==a ignorada]
```

O MetaStrength é o z-score da winrate **bruta por role** (DPS/TANK/SUP), atenuado
pela confiança da pickrate (`conf ∈ [0, 1]`), **sem shrinkage**. Cada herói é
comparado apenas com heróis da mesma função. O peso de ameaça usa `softplus`,
que é sempre `> 0` e monotônico em `raw_e`, preservando a ordenação das ameaças
baixas em vez de achatá-las num piso.

**Parâmetros**:

| Parâmetro | Valor | Descrição |
|---|---|---|
| `ε` | 0.001 | Piso numérico da pickrate (não é proxy de amostra) |
| `Mmax` | 3.0 | Clamp do z-score do MetaStrength |
| `α` | 2.25 | Escala final do MetaStrength (multiplica `conf·z` já clampado) |
| `k0_role` | pickrate neutra | Pseudo-contagem da confiança: `conf = pr/(pr+k0_role)` |
| `λ` | 0.25 | Intensidade do threat weighting (componente counter) |
| `μ` | 0.3 | Intensidade do threat weighting (componente mapa) |
| `β_meta` | 1.0 | Peso do MetaStrength no score total |
| `β_ctr` | 1.0 | Peso do counter term no score total |
| `β_syn` | 0.65 | Peso da sinergia no score total |
| `W_min` | 0.35 | (inerte) compat de assinatura; `softplus` garante `w_e > 0` |

Heróis já presentes no time aliado **e heróis banidos no competitivo** são
**excluídos do ranking** (regra rígida — mesmo tratamento de indisponibilidade).

### Como o Executável é Gerado e Utilizado

O executável `OWPick.exe` é gerado pelo **PyInstaller** a partir do arquivo `overwatch.spec`:

1. O spec inclui no bundle:
   - Todos os módulos Python do projeto
   - As planilhas `heroes ally.xlsx` e `heroes enemy.xlsx`
   - A pasta `heroes/` (templates de imagem em 720p e 2K)
   - A pasta `ocr/` (Tesseract OCR completo com tessdata)
   - Os arquivos `version.txt`, `config.json` e `stats_inputs.csv`
2. O PyInstaller empacota tudo em `dist/OWPick/`:
   - `OWPick.exe` — executável principal
   - `_internal/` — DLLs, módulos Python compilados, assets
3. Quando `OWPick.exe` é executado, o PyInstaller extrai os assets em `sys._MEIPASS`. A função `resource_path()` em `utils.py` resolve os caminhos corretos tanto no modo desenvolvimento quanto no executável.
4. Para distribuição, a pasta `dist/OWPick/` inteira é compactada em um `.zip` e publicada nas GitHub Releases.
5. O sistema de auto-update (`updater.py`) detecta a nova versão via `version.json` no GitHub e aplica a atualização com um `.bat` gerado dinamicamente (usando `robocopy`).

---

## Detalhamento dos Arquivos Python

---

### `main.py`

**Responsabilidade**: Ponto de entrada e orquestrador central. Gerencia o hotkey global, o menu de texto interativo e garante que as configurações iniciais existam.

**Variáveis globais**:
- `IN_MAIN`: flag de estado (`True` no menu principal, `False` durante subcomandos)
- `_tab_pressed`: controle do estado da tecla TAB para detecção do atalho

**Principais Funções**:

| Função | Descrição |
|---|---|
| `print_main_menu()` | Exibe o menu completo de comandos |
| `print_small_menu()` | Exibe menu resumido após execução de ação |
| `run_pipeline()` | Executa a sequência screenshot → comparar → map → ranking |
| `run_role()` | Chama `roles.executar()` para alterar a role |
| `run_favorite()` | Chama `favoriteHero.executar()` para gerenciar favoritos |
| `spawn_in_thread(func)` | Executa uma função em thread daemon |
| `_on_key_event(event)` | Handler global de teclado; detecta `TAB+1` |
| `enable_pipeline_hotkey_hook()` | Registra o hook de teclado via `keyboard.hook()` |
| `disable_pipeline_hotkey_hook()` | Remove o hook de teclado |
| `call_and_pause_main(func)` | Pausa o estado `IN_MAIN` durante execução de subcomando |
| `input_loop()` | Loop principal de leitura de comandos do terminal |

**Interação com outros módulos**: importa e chama `choose_ow_hero`, `comparar`, `favoriteHero`, `map`, `roles`, `screenshot`, `updater`.

---

### `screenshot.py`

**Responsabilidade**: Captura a tela do monitor principal e recorta os retratos dos heróis aliados e inimigos em múltiplas variações (perk slots), além dos 5 slots de ban do competitivo, salvando-os em `print/{perk}/` e `print/bans/`. Adapta automaticamente as coordenadas à resolução da tela.

**Constantes**:
- `BASE_W, BASE_H = 1280, 720` — resolução de referência para coordenadas
- `VERTICAL_BUFFER = 8` — margem vertical (px) para tolerância de alinhamento
- `captures_template`: lista de 10 posições (ally1..5, enemy1..5) com coordenadas base e dimensões
- `perks`: 4 variações horizontais de offset (`0perk`=230, `1perk`=217, `bug`=212, `2perk`=197)
- `bans_template`: lista de 5 slots de ban (ban1..5) com coordenadas base e dimensões. Os valores foram convertidos da referência 2K (÷2) para a base 1280×720, cada slot com seu próprio `left` (independente das variações de perk)

**Principais Funções**:

| Função | Descrição |
|---|---|
| `executar()` | Função principal: captura, escala e salva todos os recortes |
| `read_role()` (local) | Lê `Roles.txt` para saber qual slot de ally pular |
| `scale_and_clamp()` (local) | Converte coordenadas da base (1280×720) para a resolução atual, com clamping |

**Lógica de Captura**:
- Captura a tela inteira com `mss` e salva como `print/full.png`
- Calcula `scale_x = full_w / 1280` e `scale_y = full_h / 720`
- As 4 variações de perk representam diferentes estados visuais da UI do Overwatch (0, 1 ou 2 habilidades selecionadas, mais uma variante de bug visual)
- Para cada perk, recorta 10 posições (ally1..5, enemy1..5) com buffer vertical de 8px acima e abaixo
- Pula o arquivo correspondente à role do jogador (ex: DPS pula `ally2.png`)
- Recorta os 5 slots de ban (`bans_template`) **uma única vez** em `print/bans/`, reutilizando `scale_and_clamp`, porém **sem buffer vertical** — diferente do TAB+1, o slot de ban é fixo na UI e o matching é direto, então o recorte é o quadrado exato do retrato (ex.: 62×61 em 2K). Nem todo modo tem bans — slots vazios são descartados adiante, no matching de `comparar.py`

**Produz**: arquivos em `print/{perk}/` e `print/bans/`, lidos por `comparar.py`.

---

### `comparar.py`

**Responsabilidade**: Compara os recortes de `screenshot.py` com templates de heróis para identificar quem está na tela de seleção (lineup) e quem está banido (bans). Escreve o resultado em `lineup.txt` e `bans.txt`.

**Constantes**:
- `KNOWN_RESOLUTIONS`: `{"720p": (1280, 720), "2k": (2560, 1440)}`
- `BASE_CROP_SIZE = (42, 57)` — tamanho base do recorte (lineup) em 720p
- `BASE_WINDOW_HEIGHT = 42` — altura da janela deslizante (lineup) em 720p
- `FILE_TO_CATEGORY`: mapeia nome de arquivo para categoria (`dps`, `sup`, `tank`)
- `BANS_DIR_NAME = "bans"` / `BANS_OUTPUT_FILENAME = "bans.txt"` — subpasta de entrada (`print/bans/`) e arquivo de saída dos bans
- `BAN_TEMPLATES_DIR_NAME = "bans"` — subpasta de `heroes/` com o banco dedicado de ícones de ban
- `BAN_COMPARE_SIZE = (48, 48)` — tamanho comum de comparação (recorte e templates são redimensionados para ele)
- `BAN_FRAME_FRACTION = 0.05` — fração de cada borda do recorte descartada (moldura vermelha da UI de ban)
- `BAN_MATCH_MAX_SCORE = 0.12` — **limiar de confiança do ban** (MAE normalizado): recorte com melhor MAE acima disso é slot vazio. **Único ponto de ajuste.** Calibrado em captura real 2K: herói correto marca 0.04–0.08 e o melhor match de um slot sem ban fica ≥ 0.15; o matching imprime o score de cada slot no console para conferência

**Principais Funções**:

| Função | Descrição |
|---|---|
| `executar()` | Ponto de entrada: coordena todo o processo de matching |
| `get_full_resolution(watch_dir)` | Lê dimensões de `print/full.png` |
| `get_scale_from_full(watch_dir)` | Calcula fator de escala a partir de `full.png` |
| `compute_dims(scale)` | Retorna `crop_size` e `window_height` escalados |
| `detect_screenshot_resolution(watch_dir)` | Detecta resolução dos crops capturados |
| `find_nearest_resolution_folder(resolution, known)` | Mapeia para pasta `720p` ou `2k` |
| `load_image_gray(path, target_size)` | Carrega imagem em escala de cinza como array NumPy float32 |
| `normalized_mae(a, b)` | Calcula MAE normalizado (0–1) entre dois arrays |
| `load_templates_from_category(dir, category, size)` | Carrega templates de uma categoria |
| `load_all_templates(dir, size)` | Carrega templates de todas as categorias |
| `find_best_match_sliding(img, templates, window_h, crop_w)` | Matching com janela deslizante vertical |
| `_best_against_templates(window, templates)` | Compara uma janela contra todos os templates |
| `process_folder(folder_path, templates, crop_size, window_h)` | Processa todos os arquivos em uma pasta perk |
| `load_ban_templates(templates_dir, size)` | Carrega o banco dedicado `heroes/bans/` (pasta plana, LANCZOS) |
| `_prepare_ban_crop(path)` | Descarta a moldura da UI e redimensiona o recorte para `BAN_COMPARE_SIZE` |
| `match_bans(watch_dir)` | Identifica os heróis banidos nos 5 slots de ban (ver abaixo) |

**Algoritmo de Matching (lineup)**:
1. Lê a resolução de `print/full.png` e calcula a escala
2. Seleciona o banco (`heroes/720p/` ou `heroes/2k/`) pelo **tamanho do retrato normal** na resolução atual (`utils.template_bank_for_resolution`, ver seção de resolução)
3. Carrega templates de cada herói do banco escolhido
4. Para cada recorte, desliza uma janela de altura `window_height` verticalmente sobre a imagem (compensando possíveis desalinhamentos verticais)
5. Em cada posição, calcula `normalized_mae` contra todos os templates da categoria correta (dps, sup ou tank)
6. O template com menor MAE é o herói identificado
7. Após processar as 4 variações de perk, seleciona aquela com menor `avg_score`
8. Escreve 9 nomes em `lineup.txt` (linhas 0–3: aliados, linhas 4–8: inimigos)

**Algoritmo de Matching (bans)** — `match_bans()`:

Os ícones de ban usam uma **arte diferente** dos retratos do lineup: são os ícones
3D oficiais do herói (com moldura vermelha da UI), enquanto `heroes/720p|2k`
contêm os retratos ilustrados da tela de seleção. Por isso os bans têm um banco
dedicado, `heroes/bans/` (um `.png` de 128px por herói, pasta plana, mesma
convenção de nomes dos bancos existentes), que serve **todas** as resoluções.

O fluxo é deliberadamente **separado do TAB+1** — sem buffer vertical e sem
janela deslizante, pois o slot de ban é fixo na UI:

1. Carrega o banco `heroes/bans/` inteiro redimensionado para `BAN_COMPARE_SIZE` (um ban pode ser de qualquer role; downscale com LANCZOS)
2. Para cada `print/bans/ban{n}.png` (recorte exato do retrato): descarta `BAN_FRAME_FRACTION` de cada borda (moldura vermelha) e redimensiona para `BAN_COMPARE_SIZE`
3. Compara diretamente contra todos os templates (`_best_against_templates`, MAE normalizado) e pega o menor MAE
4. Se o melhor MAE ≤ `BAN_MATCH_MAX_SCORE`, o herói é considerado banido; caso contrário o slot é tratado como **vazio** e ignorado
5. Escreve os banidos (sem repetições) em `bans.txt`. O arquivo é **sempre reescrito** (mesmo vazio), evitando que bans de uma captura anterior "vazem" para a análise atual

Validação (captura real 2K com 5 bans): 5/5 corretos com MAE 0.048–0.077; o
segundo colocado de cada slot fica ≥ 0.17 e regiões sem ban ficam ≥ 0.13 —
separação ampla em relação ao limiar de 0.12.

---

### `map.py`

**Responsabilidade**: Identifica automaticamente o mapa atual da partida via OCR e fuzzy matching. Grava o resultado em `current_map.txt`.

**Constantes**:
- `FULL_IMAGE = "print/full.png"`
- `OUTPUT_FILE = "current_map.txt"`
- `MIN_CONFIDENCE = 50.0` — score mínimo do fuzzy match para aceitar a identificação
- `_TESSERACT_EXE`: caminho embutido para `ocr/tesseract.exe`
- `_TESSDATA_DIR`: caminho embutido para `ocr/tessdata`

**Principais Funções**:

| Função | Descrição |
|---|---|
| `_configure_tesseract()` | Aponta `pytesseract` para o executável embutido e `TESSDATA_PREFIX` |
| `load_maps()` | Retorna lista de nomes de mapas a partir de `utils.get_map_names()` |
| `extract_text_from_region(image_path, region)` | Recorta região, pré-processa e roda OCR |
| `get_all_substrings(text)` | Gera combinações de palavras do texto OCR para matching parcial |
| `identify_map(text, map_names)` | Fuzzy matching com `fuzz.ratio()` contra a lista de mapas |
| `executar()` | Ponto de entrada: extrai texto, identifica mapa, grava `current_map.txt` |

**Pré-processamento OCR**:
1. Recorta a região do mapa de `print/full.png` usando `utils.get_scaled_map_region()`
2. Converte para grayscale
3. Aplica autocontraste
4. Upscale 2× (melhora legibilidade para OCR)
5. Roda Tesseract com `--oem 3 --psm 7` (linha única)

**Saída**: `current_map.txt` com o nome do mapa identificado, ou `"UNKNOWN"` se o score for inferior a `MIN_CONFIDENCE`.

---

### `choose_ow_hero.py`

**Responsabilidade**: Módulo central de análise e recomendação. Lê o lineup identificado e o mapa atual, calcula MetaStrength, threat weights e scores para cada herói jogável, e exibe o ranking.

**Principais Funções**:

| Função | Descrição |
|---|---|
| `read_role()` | Lê `Roles.txt` e valida a existência do arquivo `{role}.txt` |
| `read_playable_heroes(role)` | Lê a lista de heróis favoritos da role atual |
| `read_lineup()` | Lê `lineup.txt`; retorna `(allies[:4], enemies[4:9])` |
| `read_bans()` | Lê `bans.txt`; retorna a lista de heróis banidos (vazia se ausente/sem bans) |
| `read_current_map()` | Lê `current_map.txt`; retorna `"UNKNOWN"` se ausente |
| `load_meta_strength(mapa_atual)` | Lê `stats_inputs.csv`, calcula MetaStrength por herói no mapa (z-score da winrate bruta por role, atenuado pela confiança da pickrate) |
| `compute_threat_weights(enemies, enemy_matrix, allies, meta_strength)` | Calcula `w_e` para cada inimigo |
| `print_threat_ranking(enemies, threat_weights)` | Exibe ranking de ameaças (1º ao 5º por peso) |
| `calculate_hero_score(hero, ally_matrix, enemy_matrix, allies, enemies, threat_weights, meta_strength)` | Calcula todos os componentes e o score total |
| `print_ranking(rankings)` | Exibe tabela `RANK | HERO | META | CTR | SYN | TOTAL` |
| `run_hero_ranking()` | Orquestra toda a sequência de leitura, cálculo e exibição |

**Fórmula de Pontuação** — ver seção [Modelo de Scoring](#modelo-de-scoring).

**MetaStrength (detalhado)**:
- Filtra `stats_inputs.csv` pelo mapa atual
- Calcula `wr̄_role` e `σ_role` da winrate **bruta** dentro de cada função (DPS/TANK/SUP)
- Para cada herói: `conf = pr / (pr + k0_role)` (k0_role = pickrate neutra da role) e `z = (wr − wr̄_role) / σ_role`
- Resultado: `α · clamp(conf · z, −Mmax, +Mmax)` (sem shrinkage; `α = 2.25`)

**Exclusão de candidatos**: antes de ranquear, os heróis normalizados presentes no
time aliado **e os banidos** (`bans.txt`) são removidos da lista de heróis jogáveis
— regra rígida idêntica para ambos os casos. A saída relata separadamente
"Excluídos (já no time aliado)" e "Excluídos (banidos)".

**Interação**: Lê `Roles.txt`, `{role}.txt`, `lineup.txt`, `bans.txt`, `current_map.txt`, `heroes ally.xlsx`, `heroes enemy.xlsx` e `stats_inputs.csv` (planilhas/CSV via `utils` com cache `lru_cache`).

---

### `utils.py`

**Responsabilidade**: Fonte única de dados e utilitários compartilhados por todos os módulos do projeto.

**Constantes embutidas (fonte de verdade)**:
- `HEROES_ROLES`: `{"DPS": [23 heróis], "TANK": [14 heróis], "SUP": [14 heróis]}`
- `MAPS_DATA`: lista de 27 mapas com `(nome, slug, modo)`
- `SLOTS`: `{"DPS": 2, "TANK": 1, "SUP": 2}` — slots por role por time

**Funções de dados**:

| Função | Descrição |
|---|---|
| `load_heroes_roles()` | Retorna `HEROES_ROLES` |
| `get_all_heroes()` | Lista flat de todos os heróis |
| `get_hero_role(hero_name)` | Retorna a role de um herói ou `None` |
| `get_role_neutral_pickrates()` | Calcula pickrate neutra por role |
| `get_map_names()` | Lista de nomes de todos os mapas |

**Normalização de nomes**:

| Função | Descrição |
|---|---|
| `normalize_hero_name(name)` | NFKD → remove acentos → minúsculas → não-alfanuméricos viram `-` |
| `build_matrix_dict(df)` | Converte DataFrame em `Dict[herói_norm, Dict[col_norm, valor]]` |

Exemplos: `"D.Va"` → `"dva"`, `"Soldier: 76"` → `"soldier-76"`, `"Lúcio"` → `"lucio"`.

**Leitura/cache de planilhas** (com `lru_cache`):

| Função | Descrição |
|---|---|
| `read_heroes_ally_data()` | Carrega `heroes ally.xlsx` |
| `read_heroes_enemy_data()` | Carrega `heroes enemy.xlsx` |
| `get_ally_matrix()` | Matriz de sinergias normalizada |
| `get_enemy_matrix()` | Matriz de counters normalizada |
| `read_stats_inputs()` | Carrega `stats_inputs.csv` |

**Suporte a múltiplas resoluções**:

| Função | Descrição |
|---|---|
| `resolution_scale(full_w)` | Fator linear em relação à resolução base (1280px) |
| `nearest_resolution_key(full_w, full_h)` | Âncora mais próxima por distância de resolução: `"720p"` ou `"2k"` (usada pela região do mapa) |
| `pick_template_bank(portrait_px)` | Banco cujo retrato representativo é o mais próximo em **tamanho** de `portrait_px`; empate → banco maior (2k) |
| `template_bank_for_resolution(full_w, base_portrait_px)` | Escala `base_portrait_px` pela resolução atual e delega a `pick_template_bank` |
| `get_scaled_map_region(full_w, full_h)` | Região do mapa interpolada/escalada para qualquer resolução |

**Escolha do banco de templates por tamanho de retrato** (centralizada aqui):

Em vez de escolher o banco pela resolução da tela, o sistema escolhe pelo **tamanho
do retrato** que será comparado na resolução atual. Constantes:

- `TEMPLATE_BANK_PORTRAIT_PX = {"720p": 41, "2k": 82}` — tamanho representativo (px) do retrato de cada banco
- `BASE_PORTRAIT_PX = 41` — tamanho-base (720p) do retrato normal do lineup (em 2K ≈ 82px)

`pick_template_bank` escolhe o banco de tamanho representativo mais próximo, com
empate resolvido para o banco maior (2K, maior qualidade). O limiar entre bancos é
o ponto médio dos tamanhos representativos (≈ 61,5px para 41/82) — **regra genérica,
sem `if` por resolução**:

| Resolução | Retrato do lineup | Banco (lineup) |
|---|---|---|
| 720p  | ~41px   | 720p |
| 1080p | ~61,5px | **2k** |
| 2K    | ~82px   | 2k |

Os templates do banco escolhido são então redimensionados pela escala da resolução
atual (`compute_dims` em `comparar.py`), sem necessidade de uma pasta dedicada por
resolução.

**Obs.:** os **bans não passam por esta escolha** — usam o banco dedicado
`heroes/bans/` (fonte de 128px, redimensionada para `BAN_COMPARE_SIZE` em
qualquer resolução; ver `comparar.match_bans`).

**Configuração**:
- `load_capture_config()`: lê `config.json` com âncoras de captura por resolução
- `resource_path(relative_path)`: resolve caminhos para `sys._MEIPASS` (executável) ou diretório atual (dev)

---

### `enemy_mult.py`

**Responsabilidade**: Utilitário de diagnóstico para calcular o threat weight de um herói inimigo específico contra o lineup atual. **Não é chamado no pipeline principal** — o cálculo de threat weights é feito internamente em `choose_ow_hero.py`.

**Fórmula**:
```
w_e = softplus(1 + λ · Σ_a C(e, a))   # λ = 0.25; a ∈ aliados do jogador
```

**Importante**: `enemy_mult.py` lê `lineup.txt` com perspectiva invertida em relação a `choose_ow_hero.py`: `lines[:4]` são os oponentes do herói inimigo avaliado (= aliados do jogador), e `lines[4:9]` são os aliados do herói inimigo avaliado (= inimigos reais). Essa inversão é intencional, pois avalia o mundo do ponto de vista do herói inimigo.

**Principais Funções**:

| Função | Descrição |
|---|---|
| `read_lineup()` | Lê `lineup.txt` com perspectiva invertida |
| `calculate_threat_weight(hero, enemy_matrix, opponents)` | Calcula `w_e` para o herói passado |
| `executar(hero, enemy_matrix)` | Função exportada: retorna o threat weight float |

---

### `favoriteHero.py`

**Responsabilidade**: Gerencia a lista de heróis favoritos do usuário. Persiste os dados em `ALL.txt` (todos) e em arquivos separados por role: `DPS.txt`, `SUP.txt`, `TANK.txt`.

**Principais Funções**:

| Função | Descrição |
|---|---|
| `normalize_text(text)` | NFKD normalize → remove acentos → minúsculas (para busca fuzzy) |
| `get_all_heroes()` | Lista flat de todos os heróis |
| `get_hero_role(hero_name)` | Retorna a role de um herói |
| `find_best_match(user_input, normalized_heroes)` | Fuzzy matching com `difflib.get_close_matches` (cutoff 0.4) |
| `save_heroes_to_files(heroes_list)` | Salva em `ALL.txt` + arquivos por role |
| `load_favorites()` | Carrega lista de `ALL.txt` |
| `add_favorite(hero_name)` | Adiciona herói e persiste |
| `remove_favorite(hero_name)` | Remove herói e persiste |
| `list_favorites()` | Lista heróis favoritos com sua role |
| `add_role_or_all()` | Adiciona em lote toda uma role ou todos os heróis |
| `add_role_or_all_menu()` | Exibe submenu de seleção de lote |
| `executar()` | Loop interativo: 1=add, 2=remove, 3=list, 4=add em lote, 5=exit |

**Interação**: Chamado por `main.py`. Produz arquivos `.txt` por role lidos por `choose_ow_hero.py` e `screenshot.py`.

---

### `roles.py`

**Responsabilidade**: Permite ao usuário selecionar sua função (role) na partida e persiste a escolha em `Roles.txt`. Usa leitura de teclado sem echo (`msvcrt.getch`) para captura imediata.

**Mapeamento de teclas**:
- `1` → `ALL` (Fila Aberta)
- `2` → `TANK`
- `3` → `SUP`
- `4` → `DPS`

**Interação**: Chamado por `main.py`. Grava `Roles.txt` lido por `screenshot.py` e `choose_ow_hero.py`.

---

### `updater.py`

**Responsabilidade**: Sistema de auto-atualização. Verifica a versão remota no GitHub, oferece download e aplica a atualização via script `.bat` gerado dinamicamente.

**Principais Funções**:

| Função | Descrição |
|---|---|
| `get_exe_dir()` | Retorna a pasta do executável |
| `get_local_version()` | Lê `version.txt` embutido no pacote |
| `_parse_version(v)` | Converte `"1.2.3"` em tupla `(1, 2, 3)` |
| `_fetch_version_info()` | Baixa `version.json` remoto via `urllib` (timeout 6s) |
| `_download_file(url, dest_path)` | Baixa arquivo com barra de progresso |
| `_apply_update(download_url)` | Baixa o `.zip`, extrai, gera `.bat` e encerra o processo |
| `check_for_updates()` | Ponto de entrada: compara versões e age se necessário |

**Fluxo de Update**:
1. Baixa `version.json` do GitHub
2. Compara tuplas de versão
3. Se remota > local: pergunta ao usuário
4. Se confirmado: baixa o `.zip`, extrai em `%TEMP%`, gera `owpick_update.bat`
5. O `.bat` usa `robocopy` para copiar os novos arquivos sobre os antigos após o `.exe` fechar e relança o programa

---

### `coletar_stats.py` (ferramenta offline)

**Responsabilidade**: Scraper externo (Playwright) que coleta winrate e pickrate por mapa em [owtics.gg](https://owtics.gg) e gera `stats_inputs.csv`. Roda separadamente do programa principal, como ferramenta de atualização de dados.

**Configuração**:
- `REGION = "AMER"`, `TIER = "GRANDMASTER_AND_CHAMPION"`
- `DELAY_MIN, DELAY_MAX = 2.0, 4.0` — intervalo aleatório entre requisições

**Estratégias de extração** (em ordem):
1. JavaScript direto via seletor DOM
2. XHR interceptado (API JSON da página)
3. Texto visível via regex (fallback)

**Saída**: `stats_inputs.csv` com colunas `[map, map_type, map_slug, hero, role, winrate, pickrate]`.

**Dependência extra**: requer `pip install playwright && playwright install chromium` (não inclusa em `requirements.txt`).

---

### `resolucao.py` (utilitário de desenvolvimento)

**Responsabilidade**: Permite ao desenvolvedor selecionar visualmente uma área da tela e imprimir as coordenadas `(left, top, width, height)`. **Não é usado no pipeline principal.**

**Classe `AreaSelector`**: janela fullscreen semitransparente (Tkinter) com seleção de área via mouse e countdown de 3 segundos antes de abrir.

---

### `heroscreenshot.py` (arquivo legado)

**Responsabilidade**: Versão anterior do sistema de screenshot, com região fixa e hotkey bloqueante. **Não é usado no pipeline atual** e não é importado por nenhum módulo.

---

## Dados do Jogo

### Heróis Suportados (51 total)

| Role | Heróis |
|---|---|
| **DPS** (23) | Anran, Ashe, Bastion, Cassidy, Echo, Emre, Freja, Genji, Hanzo, Junkrat, Mei, Pharah, Reaper, Shion, Sierra, Sojourn, Soldier: 76, Sombra, Symmetra, Torbjörn, Tracer, Vendetta, Venture, Widowmaker |
| **TANK** (14) | D.Va, Domina, Doomfist, Hazard, Junker Queen, Mauga, Orisa, Ramattra, Reinhardt, Roadhog, Sigma, Winston, Wrecking Ball, Zarya |
| **SUP** (14) | Ana, Baptiste, Brigitte, Illari, Jetpack Cat, Juno, Kiriko, Lifeweaver, Lúcio, Mercy, Mizuki, Moira, Wuyang, Zenyatta |

### Mapas Suportados (27 total)

| Modo | Mapas |
|---|---|
| **Control** (7) | Antarctic Peninsula, Busan, Ilios, Lijiang Tower, Nepal, Oasis, Samoa |
| **Escort** (8) | Circuit Royal, Dorado, Havana, Junkertown, Rialto, Route 66, Shambali Monastery, Watchpoint: Gibraltar |
| **Hybrid** (7) | Blizzard World, Eichenwalde, Hollywood, King's Row, Midtown, Neon Junction, Numbani, Paraíso |
| **Push** (4) | Colosseo, Esperança, New Queen Street, Runasapi |
| **Flashpoint** (2) | New Junk City, Suravasa |

### Templates de Imagem

Os templates do **lineup** estão organizados em `heroes/{resolucao}/{role}/` onde `resolucao` é `720p` ou `2k`. Cada arquivo é uma imagem `.png` do retrato ilustrado do herói extraída da tela de seleção do Overwatch 2.

Os templates dos **bans** ficam em `heroes/bans/` (pasta plana, sem divisão por role ou resolução): um `.png` de 128×128 por herói com o **ícone 3D oficial** — a mesma arte exibida nos slots de ban da UI, que é diferente do retrato ilustrado do lineup. Os nomes de arquivo seguem a mesma convenção dos bancos existentes (`DVa.png`, `Soldier 76.png`, `Lúcio.png`, ...).

---

## Dependências

### Dependências Python (`requirements.txt`)

| Biblioteca | Versão mínima | Finalidade |
|---|---|---|
| `mss` | 10.2.0 | Captura de tela de alta performance |
| `Pillow` | 12.2.0 | Manipulação de imagens, crop, autocontraste |
| `opencv-python` | 4.13.0 | Redimensionamento de imagens para template matching |
| `numpy` | 2.4.0 | Arrays numéricos para cálculo de MAE |
| `pandas` | 2.0.0 | Leitura de planilhas `.xlsx` e `stats_inputs.csv` |
| `openpyxl` | 3.1.5 | Backend para pandas ler arquivos `.xlsx` |
| `keyboard` | 0.13.5 | Hotkeys globais fora do foco da janela |
| `rapidfuzz` | 3.14.5 | Fuzzy matching para identificação de mapa (OCR) |
| `unidecode` | 1.4.0 | Normalização de strings com acentos |
| `pytesseract` | 0.3.13 | Wrapper Python para Tesseract OCR (identificação do mapa) |
| `PyInstaller` | 6.20.0 | Geração do executável `.exe` (build only) |
| `PyAutoGUI` | 0.9.54 | Seletor visual de coordenadas (`resolucao.py`, dev only) |

### Dependências de Stdlib

| Biblioteca | Finalidade |
|---|---|
| `msvcrt` | Leitura de tecla sem echo (`roles.py`, Windows only) |
| `tkinter` | Interface gráfica do seletor de área (`resolucao.py`) |
| `difflib` | `get_close_matches` para busca fuzzy de heróis por nome |
| `unicodedata` | Remoção de acentos para normalização |
| `urllib` | Download de `version.json` e do pacote de update |
| `zipfile`, `shutil`, `subprocess` | Extração e aplicação do pacote de atualização |
| `itertools`, `functools` | Combinações de substrings (OCR) e cache (`lru_cache`) |

### Dependência Externa (Binária)

| Componente | Localização | Finalidade |
|---|---|---|
| **Tesseract OCR** | `ocr/tesseract.exe` + `ocr/tessdata/` | Reconhecimento óptico de caracteres para identificação do mapa |

O Tesseract está embutido no repositório e no executável. Não é necessário instalá-lo separadamente.

---

## Pontos de Atenção

### Bugs Conhecidos

1. **`selenium` como hidden import no `.spec`**: `overwatch.spec` declara `selenium` e submódulos como `hiddenimports`, mas `selenium` não é importado em nenhum arquivo `.py`. Aumenta o tamanho do executável desnecessariamente. Pode ser removido.

2. **Perspectiva invertida em `enemy_mult.py`**: as variáveis `allies` e `enemies` têm semântica invertida — são do ponto de vista do herói inimigo avaliado, não do jogador. O código está correto, mas pode confundir quem lê pela primeira vez sem contexto.

### Adição de Novos Heróis

Para adicionar um novo herói ao sistema, é necessário atualizar pelo menos três lugares:
1. A constante `HEROES_ROLES` em `utils.py` (fonte de verdade para nome e role)
2. A pasta `heroes/` com os templates de imagem do lineup nas resoluções suportadas (`720p` e `2k`)
3. A pasta `heroes/bans/` com o ícone 3D oficial do herói (para o reconhecimento de bans)
