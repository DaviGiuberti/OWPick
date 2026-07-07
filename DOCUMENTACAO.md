# Documentação Técnica — OWPick (Overwatch Best Picks)

---

## Visão Geral

### Objetivo do Projeto

OWPick é uma ferramenta desktop para jogadores de **Overwatch** que automatiza a recomendação de heróis durante a fase de escolha de personagem. O sistema captura a tela do jogo, identifica os heróis presentes na tela de seleção (aliados e inimigos) por comparação de imagem, identifica o mapa atual via OCR e, com base em planilhas de counters/sinergias e dados de meta por mapa, gera um ranking dos melhores heróis que o usuário pode jogar naquela partida.

### Funcionalidades Principais

- Captura automática da tela de seleção de heróis via hotkey global **configurável** (padrão `TAB+1`; opção 5 do menu captura uma nova combinação em tempo real e persiste em `settings.json`)
- **Captura da janela do jogo** (multi-monitor / modo janela): localiza a janela do Overwatch via Win32 (`ctypes`/user32) e captura o retângulo do cliente; sem a janela, cai para o monitor primário. **Compatível apenas com resolução 16:9** (sem ultrawide/21:9)
- Identificação de heróis por template matching com deslizamento vertical (`cv2.matchTemplate`, `TM_CCOEFF_NORMED` — correlação de média zero, robusta a brilho/HDR/highlight), com **limiar de confiança** por slot: slot cujo melhor score fica acima do limiar vira "não identificado" e é excluído das somas de counter/sinergia
- **Suporte aos bans do modo Competitivo**: identifica os heróis banidos nos 5 slots de ban e os remove automaticamente do ranking (mesmo tratamento dos heróis já presentes no time). Os bans usam um banco de templates dedicado (`assets/heroes/bans/`, ícones 3D oficiais — arte diferente dos retratos do lineup) e matching direto, sem janela deslizante
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
- **Settings único e validado** (`settings.json` em `%APPDATA%\OWPick`): hotkey, idioma, debug, preset de pesos, overrides avançados de calibração, perfis
- **Presets de pesos do modelo** ("Equilibrado" = atual, "Counter-first", "Meta-first", "Conforto+") + modo avançado (`custom_weights`); trocáveis pela **opção 8 do menu**, com a escolha **vinculada ao perfil ativo**
- **Atualização de stats de meta por download** (opção 4): baixa o `stats_inputs.csv` publicado (GitHub raw) direto no app — funciona no executável **sem Playwright nem código-fonte**
- **Explicabilidade do ranking** (opção 6 do menu, persistida): "por quê" dos top-3 — qual inimigo pesou (com peso de ameaça), qual sinergia puxou, quanto o mapa influenciou
- **Console rico** (`rich`): tabela com cores por role, top-3 destacado, barras de score, painel de ameaças e spinner durante o pipeline
- **Strings de UI por idioma** (PT-BR e EN, `assets/i18n/*.json`) no padrão "o que houve + o que fazer"
- **Modo manual/simulação**: `sim mapa=Ilios inimigos=Tracer,Winston aliados=Mei` roda apenas o scoring (fuzzy match de nomes; sem captura)
- **Múltiplos perfis** (opção 7 do menu): cada perfil = role + favoritos + preset de pesos + tier de stats; troca aplicada pelos mecanismos existentes
- Sistema de **auto-atualização** via GitHub Releases: **checagem não bloqueante** no boot (thread de fundo; comando `update` ou aplicação ao fechar) e **update seguro com rollback** (backup `OWPick.old` + restauração automática se a cópia falhar)
- Empacotamento via PyInstaller (one-folder) e distribuição por **instalador único** (`OWPick Installer.exe`, Inno Setup) com atalhos, desinstalador e identidade correta na barra de tarefas (Win10/Win11)

---

## Arquitetura

### Estrutura de Pastas

```
OWPick/
├── src/owpick/              # Pacote do aplicativo — 3 camadas (core/infra/ui)
│   ├── __main__.py          # Ponto de entrada (python -m owpick / entry do exe)
│   ├── pipeline.py          # Casos de uso: run_pipeline() → RankingResult
│   ├── paths.py             # Localização dos 3 tipos de dado (app/usuário/cache) + migração
│   ├── settings.py          # Settings único tipado/validado (settings.json em %APPDATA%)
│   ├── i18n.py              # Strings de UI por idioma (assets/i18n/*.json; pt-BR/en)
│   ├── log.py               # Logging estruturado (%APPDATA%\OWPick\logs + console)
│   ├── core/                # Domínio puro — ZERO I/O
│   │   ├── heroes.py        # Heróis/mapas embutidos + normalização + build_matrix_dict
│   │   ├── resolution.py    # Escala/interpolação, banco de templates, região do mapa
│   │   ├── models.py        # Dataclasses (Hero, Lineup, BanList, CaptureResult, ...)
│   │   ├── scoring.py       # MetaStrength + threat weighting + ranking + presets (ModelWeights)
│   │   └── ports.py         # Protocols (ScreenCapturer, MetaSource, MatrixSource)
│   ├── infra/               # I/O: captura, matching, OCR, dados, persistência, updater
│   │   ├── capture.py       # Screen capture (mss/janela do jogo) + recorte em memória
│   │   ├── matching.py      # Template matching (OpenCV TM_CCOEFF_NORMED) + limiar de confiança
│   │   ├── map_detect.py    # OCR + fuzzy match do mapa (token_set_ratio + aliases por idioma)
│   │   ├── ocr_backends.py  # Backends de OCR plugáveis (Tesseract padrão; Windows.Media.Ocr opcional)
│   │   ├── datasource.py    # Leitura/cache das matrizes CSV, stats e layout (override de stats do usuário)
│   │   ├── validation.py    # Validação de matrizes/stats/templates na carga (aviso claro)
│   │   ├── stats_update.py  # Atualização das stats de meta pelo app (baixa o CSV publicado)
│   │   ├── storage.py       # Persistência: Roles/ALL/lineup/bans/current_map
│   │   ├── resources.py     # resource_path + identidade no Windows (AUMID/ícone)
│   │   └── updater.py       # Sistema de auto-update
│   └── ui/                  # Console — a ÚNICA camada que imprime
│       ├── console.py       # Menu, hotkey de captura, threading
│       ├── roles.py         # Menu de função (input injetável)
│       ├── favorites.py     # Menu de favoritos (input injetável)
│       ├── hotkey.py        # Hotkey configurável: detector + captura em tempo real
│       ├── sim.py           # Modo manual/simulação (scoring sem captura)
│       ├── profiles.py      # Múltiplos perfis (role+favoritos+preset+tier)
│       ├── weights.py       # Menu de troca do preset de pesos (vinculado ao perfil)
│       └── ranking_view.py  # Formatação rich do ranking (consome RankingResult)
│
├── tools/                   # Ferramentas de desenvolvimento (não empacotadas)
│   ├── coletar_stats.py     # Scraper externo → data/stats_inputs.csv (aceita destino via argv)
│   ├── xlsx_to_csv.py       # Converte as matrizes .xlsx (edição) → .csv (runtime)
│   ├── enemy_mult.py        # Diagnóstico de threat weight (consumidor do core)
│   └── resolucao.py         # Seletor visual de coordenadas
│
├── assets/                  # Recursos imutáveis (empacotados no bundle)
│   ├── heroes/              # Templates de imagem dos heróis
│   │   ├── 720p/dps|sup|tank/   # Retratos do lineup em 720p
│   │   ├── 2k/dps|sup|tank/     # Retratos do lineup em 2K
│   │   └── bans/                # Ícones 3D oficiais (128px, pasta plana) — banco
│   │                            # dedicado dos bans; serve todas as resoluções
│   ├── ocr/                 # Tesseract OCR embutido (tesseract.exe + tessdata/)
│   ├── i18n/                # Strings de UI por idioma (pt-BR.json, en.json)
│   └── icone.ico            # Ícone do app (multi-tamanho: 16–256px)
│
├── data/                    # Dados do modelo
│   ├── synergies.csv        # Matriz de sinergias — LIDA em runtime (empacotada)
│   ├── counters.csv         # Matriz de counters — LIDA em runtime (empacotada)
│   ├── heroes ally.xlsx     # Sinergias: fonte de EDIÇÃO (NÃO empacotada; vira synergies.csv)
│   ├── heroes enemy.xlsx    # Counters: fonte de EDIÇÃO (NÃO empacotada; vira counters.csv)
│   ├── layouts/
│   │   └── ow_hero_select.json  # Layout de captura versionado: slots do lineup,
│   │                            # perks, slots de ban e âncoras da região do mapa
│   └── stats_inputs.csv     # Winrate/pickrate por mapa (fonte do MetaStrength;
│                            # override do usuário em %APPDATA%\OWPick tem prioridade)
│
├── packaging/               # Build e distribuição
│   ├── overwatch.spec       # Spec do PyInstaller (espelha assets/ e data/ no bundle)
│   ├── installer.iss        # Script do instalador (Inno Setup 6)
│   └── build.bat            # Build completo: PyInstaller → zip do updater → instalador
│
├── tests/                   # Testes pytest + fixtures golden (tests/fixtures/)
├── version.txt              # Versão local do executável (fonte única de versão)
├── version.json             # Versão remota para verificação de update
├── pyproject.toml           # Metadados, dependências (uv) e config Ruff/Pyright/Pytest
├── uv.lock                  # Lockfile de dependências (uv)
├── requirements.txt         # Referência de transição (fonte de verdade: pyproject)
│
├── dist/                    # Saídas do build (packaging/build.bat)
│   ├── OWPick/              # Build one-folder do PyInstaller
│   │   ├── OWPick.exe
│   │   └── _internal/       # DLLs, módulos Python, assets/ e data/ empacotados
│   ├── OWPick_v<versão>.zip # Pacote consumido pelo auto-updater
│   └── OWPick Installer.exe # Instalador distribuído a novos usuários
│
└── .venv/                   # Ambiente virtual Python
```

> Em execução `.py`, `infra.resources.resource_path` resolve recursos relativos
> à **raiz do repositório** (independente do CWD); no `.exe`, relativos a
> `_MEIPASS`. O `overwatch.spec` espelha `assets/` e `data/` dentro do bundle
> para que o mesmo caminho relativo funcione nos dois modos.
>
> **Regra de camadas**: `core` não importa `infra` nem `ui` (é puro, zero I/O);
> `ui` e `pipeline` compõem `infra` + `core`. Os dados (planilhas/CSV/config) e
> a captura chegam ao `core` **por parâmetro** — nunca lidos dentro dele.

**Arquivos gerados em tempo de execução** (não versionados). A localização é
resolvida por `owpick/paths.py`, que separa os **três tipos de dado** (nenhum
módulo usa mais caminho relativo/`Path.cwd()`):

*Config/dados do usuário* — `%APPDATA%\OWPick\` (preservados entre updates e
desinstalação; migrados automaticamente na primeira execução se existirem ao
lado do exe / no CWD de versões antigas):

```
settings.json     # Settings do usuário (hotkey, idioma, debug, preset de
                  # pesos, overrides avançados, perfis) — tipado e validado
Roles.txt         # Role selecionada ("DPS", "SUP", "TANK", "ALL")
ALL.txt           # Lista de todos os heróis favoritos
DPS.txt           # Favoritos DPS
SUP.txt           # Favoritos Suporte
TANK.txt          # Favoritos Tank
logs\owpick.log   # Log rotativo (2 x 1MB)
```

*Temporários/debug* — `%LOCALAPPDATA%\OWPick\cache\` (descartáveis; escritos só
no modo `--debug` ou pelos fluxos CLI standalone):

```
print\            # Recortes de tela (full.png + pastas por perk + bans/)
lineup.txt        # Heróis identificados na última captura (fluxo CLI)
bans.txt          # Heróis banidos identificados na última captura (fluxo CLI)
current_map.txt   # Mapa identificado na última captura (fluxo CLI)
```

*Aplicação (imutável)* — templates, planilhas, config e OCR, resolvidos por
`infra.resources.resource_path` (nunca gravados).

### Componentes Principais

| Camada | Módulo | Responsabilidade |
|---|---|---|
| ui | `ui/console.py` | Menu, hotkey de captura (configurável), threading, inicialização |
| ui | `ui/ranking_view.py` | Formatação rich do ranking, ameaças e explicações |
| ui | `ui/roles.py` / `ui/favorites.py` | Menus (fonte de input injetável para testes) |
| ui | `ui/hotkey.py` | Hotkey configurável: `HotkeyDetector` + captura em tempo real + menu |
| ui | `ui/sim.py` | Modo manual/simulação (`sim mapa=... inimigos=...`; só scoring) |
| ui | `ui/profiles.py` | Múltiplos perfis (salvar/trocar/remover; aplica via storage/settings) |
| app | `settings.py` | Settings único tipado/validado (`settings.json` em `%APPDATA%\OWPick`) |
| app | `i18n.py` | Strings de UI por idioma (`assets/i18n/pt-BR.json`, `en.json`) |
| app | `pipeline.py` | Casos de uso: `run_pipeline()` compõe infra + core → `RankingResult` |
| core | `core/scoring.py` | MetaStrength + threat weighting + sinergia → `Recommendation` (puro) |
| core | `core/heroes.py` | Heróis/mapas embutidos + normalização + `build_matrix_dict` |
| core | `core/resolution.py` | Escala/interpolação, banco de templates, região do mapa |
| core | `core/models.py` | Dataclasses de domínio; `Hero.from_name` normaliza na fronteira |
| infra | `infra/capture.py` | Screen capture via MSS + recorte em memória |
| infra | `infra/matching.py` | Template matching (OpenCV/NumPy/Pillow) |
| infra | `infra/map_detect.py` | OCR + fuzzy match do mapa (`token_set_ratio` + aliases por idioma) |
| infra | `infra/ocr_backends.py` | Backends de OCR plugáveis (Tesseract padrão; Windows.Media.Ocr opcional) |
| infra | `infra/datasource.py` | Leitura/cache das matrizes CSV, stats (com override do usuário) e layout |
| infra | `infra/validation.py` | Validação de matrizes/stats/templates na carga (aviso claro do que falta) |
| infra | `infra/stats_update.py` | Atualização das stats de meta pelo app (baixa o CSV publicado; sem deps externas) |
| infra | `infra/storage.py` | Persistência dos arquivos do usuário |
| infra | `infra/updater.py` | Auto-update via GitHub |
| tool | `tools/coletar_stats.py` | Scraper que gera `stats_inputs.csv` (destino via argv) |
| tool | `tools/xlsx_to_csv.py` | Converte as matrizes `.xlsx` (edição) em `.csv` (runtime) |
| tool | `tools/enemy_mult.py` | Diagnóstico de threat weight (consumidor do core) |
| tool | `tools/bump.py` | Sincroniza `version.txt` + `CHANGELOG` para um novo release |

### Relação entre os Módulos (pipeline TAB+1)

```
ui/console.main()
├── updater.check_for_updates()           → infra/updater.py
├── ui/roles.executar()                   → infra/storage.write_role()  [Roles.txt]
├── ui/favorites.executar()               → infra/storage.save_heroes_to_files()  [ALL/DPS/SUP/TANK.txt]
└── [TAB+1] → pipeline.run_pipeline()
    ├── capture.capture()                 → CaptureResult (recortes em memória; sem disco)
    ├── matching.match_bans() / match_lineup()   → BanList, Lineup (objetos Hero)
    ├── map_detect.detect(cap.full)       → MapDetection
    └── pipeline.rank(...)                → RankingResult
        ├── datasource.get_ally_matrix() / get_enemy_matrix() / read_stats_inputs()
        └── core/scoring: load_meta_strength + compute_threat_weights + rank_heroes
    → ui/ranking_view.render(result)      (única camada que imprime)
```

No modo `--debug`, `capture.save_debug_artifacts()` grava os PNGs de `print/`
e os fluxos CLI (`matching.executar()`, `map_detect.executar()`,
`pipeline.rank_from_files()`) mantêm os `.txt` em disco para uso standalone.

---

## Fluxo de Funcionamento

### Como o Sistema Inicia

1. O usuário executa `OWPick.exe` (pelo atalho criado pelo instalador) ou `python src\owpick\__main__.py` (dev)
2. `infra.resources.configure_windows_app_identity()` registra o AppUserModelID e o ícone da janela (identidade na taskbar do Windows)
3. `paths.ensure_dirs()` cria os diretórios de dados do usuário/cache e `paths.migrate_legacy_user_data()` migra `Roles.txt`/favoritos de versões antigas (que gravavam ao lado do exe); `settings.get()` carrega o `settings.json` validado e `setup_logging()` inicia o log — com `--debug` (ou `settings.debug`), a validação de dados (`validation.report_problems`) também roda
4. `updater.cleanup_old_backup()` apaga o backup `OWPick.old` de um update
   anterior bem-sucedido; em seguida `updater.start_background_check()` verifica
   atualizações **em thread de fundo** (boot não bloqueia):
   - Baixa `version.json` do GitHub e compara com `version.txt` local
   - Se houver versão nova, avisa no console; o usuário aplica pelo comando
     `update` ou ao fechar o programa
5. Se `Roles.txt` não existir (em `%APPDATA%\OWPick`) → `roles.executar()` é chamado (escolha de role obrigatória)
6. Se `ALL.txt` não existir → `favorites.executar()` é chamado (configuração de favoritos)
7. A hotkey global de captura é registrada (padrão `TAB+1`, configurável na opção 5; combinações com TAB usam `keyboard.hook()` + `HotkeyDetector`, as demais `keyboard.add_hotkey`)
8. O loop de input de menu é iniciado em uma thread daemon separada
9. O programa entra em loop principal (`while True: time.sleep(1)`)

### Como os Dados Fluem entre os Módulos (pipeline em memória)

O pipeline acionado pela hotkey roda **inteiramente em memória** — nenhum PNG ou
`.txt` intermediário é escrito (só no modo `--debug` ou nos fluxos CLI
standalone):

```
[Jogo Overwatch aberto na tela de seleção]
        ↓
[hotkey de captura pressionada]  → ui/console._trigger_pipeline (thread)
        ↓
pipeline.run_pipeline(report, save_debug)
  - storage.read_role() / read_playable_heroes(role)   [pré-requisitos; %APPDATA%]
        ↓
pipeline.analyze()
  - capture.capture() → CaptureResult
      - grab_screen(): retângulo do cliente da janela do Overwatch (ctypes)
        ou monitor primário (fallback)
      - crop_capture(): interpreta data/layouts/ow_hero_select.json —
        10 slots × 4 variações de perk (pula o slot da role) + 5 slots de ban,
        escalados por scale_and_clamp p/ a resolução atual (tudo em memória)
  - Em PARALELO (ThreadPoolExecutor, 2 workers):
      ├─ matching.match_bans(cap)   → BanList  (MAE direto vs assets/heroes/bans;
      │                                slot acima de BAN_MATCH_MAX_SCORE = vazio)
      │  matching.match_lineup(cap) → Lineup + MatchResult por slot
      │    - banco pelo TAMANHO do retrato (720p/2k); templates cacheados
      │    - cv2.matchTemplate TM_CCOEFF_NORMED (deslizamento vertical)
      │    - melhor variação de perk = menor score médio
      │    - slot acima de LINEUP_MATCH_MAX_SCORE → não identificado (excluído)
      └─ map_detect.detect(cap.full) → MapDetection
           - região do layout (get_scaled_map_region) → gray → autocontraste →
             2× → OCR (ocr_backends) → token_set_ratio vs nomes+aliases
           - score < MIN_CONFIDENCE → UNKNOWN (MetaStrength neutro)
        ↓
pipeline.rank(role, playable, allies, enemies, banned, mapa) → RankingResult
  - datasource.get_ally_matrix()/get_enemy_matrix()  [data/*.csv, cacheados]
  - datasource.read_stats_inputs()   [override do usuário > embutido]
  - pesos: settings.weights_preset + custom_weights (resolve_weights)
  - core/scoring: load_meta_strength → compute_threat_weights → rank_heroes
      - exclui aliados já no time E banidos (regra rígida)
      - Recommendation.reasons acumula as contribuições (explicabilidade)
        ↓
ui/ranking_view.render(result)   [ÚNICA camada que imprime: tabela rich com
  cores por role, barras, painel de ameaças e, se ativado, o "por quê" do top-3]
```

No modo `--debug`, `capture.save_debug_artifacts()` grava os PNGs em
`%LOCALAPPDATA%\OWPick\cache\print\`, e os fluxos CLI standalone
(`matching.executar()`, `map_detect.executar()`, `pipeline.rank_from_files()`)
mantêm os `.txt` (`lineup.txt`, `bans.txt`, `current_map.txt`) — mesma
implementação de matching do fluxo em memória.

### Modelo de Scoring

```
S(h) = β_meta · m_scaled(h, k) + β_ctr · T_ctr(h) + T_syn(h)

m_scaled(h, k) = α · clamp( conf · (wr(h) - wr̄_role(k)) / σ_role(k), -Mmax, +Mmax )  [MetaStrength]
conf           = pr / (pr + k0_role),   k0_role = pickrate neutra da role            [confiança da pickrate]
T_ctr(h)       = Σ_e w_e · C(h, e)                                                    [counter com threat weighting]
raw_e          = λ · Σ_a C(e,a) + μ · m(e,k)                                          [sinal bruto de ameaça; 0 = neutro]
w_e            = CAP ** tanh(raw_e / SCALE) = exp( ln(CAP) · tanh(raw_e / SCALE) )    [multiplicador de ameaça ∈ (1/CAP, CAP)]
T_syn(h)       = Σ_a Y(h, a) · β_syn                                                  [sinergia; diagonal h==a ignorada]
```

O MetaStrength é o z-score da winrate **bruta por role** (DPS/TANK/SUP), atenuado
pela confiança da pickrate (`conf ∈ [0, 1]`), **sem shrinkage**. Cada herói é
comparado apenas com heróis da mesma função.

#### Multiplicador de Enemy Threat — `w_e = CAP ** tanh(raw_e / SCALE)`

O peso de ameaça de cada inimigo transforma o **sinal bruto**
`raw_e = λ · Σ_a C(e,a) + μ · m(e,k)` (0 = inimigo que não countera ninguém e é
neutro no mapa) em um multiplicador aplicado ao counter term. A transformação é
`w(raw) = CAP ** tanh(raw / SCALE) = exp( ln(CAP) · tanh(raw / SCALE) )`, com as
propriedades:

- `w(0) = 1` **exatamente** (`tanh(0) = 0`); `raw < 0 ⇒ w < 1`; `raw > 0 ⇒ w > 1`.
- **Contínua, suave (C∞) e estritamente monotônica** em `raw` — preserva a
  ordenação das ameaças.
- **Limitada a `(1/CAP, CAP) = (0.40, 2.50)` por construção** (`tanh ∈ (−1, 1)`):
  o peso **nunca explode** nem fica não-positivo. Chegar abaixo de 0.5 ou acima de
  2.5 exige `raw` extremo (fora da faixa observada nos dados reais) — casos
  "extremamente extremos".
- **Log-simétrica:** `w(−raw) = 1 / w(raw)` — down/upweight de mesma magnitude são
  recíprocos, o comportamento natural de um multiplicador.

Os parâmetros `CAP = 2.5` e `SCALE = 2.5` foram calibrados sobre a distribuição
real de `raw` (Monte Carlo com a matriz de counters + MetaStrength por mapa:
`std ≈ 0.64`, p1 ≈ −1.44, p99 ≈ +1.50). Comportamento da curva:

| `raw` | −6 | −4 | −2 | −1 | −0.5 | 0 | 0.5 | 1 | 2 | 4 | 6 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `w` | 0.41 | 0.43 | 0.54 | 0.71 | 0.84 | **1.00** | 1.20 | 1.42 | 1.84 | 2.33 | 2.46 |

> Substitui o `softplus(1 + …)` das versões anteriores, que dava `w ≈ 1.313` em
> `raw = 0` (sem offset novo) e **não tinha teto** (podia explodir). O antigo piso
> `W_min` deixou de existir: os limites agora são estruturais.

**Parâmetros**:

| Parâmetro | Valor | Descrição |
|---|---|---|
| `ε` | 0.001 | Piso numérico da pickrate (não é proxy de amostra) |
| `Mmax` | 3.0 | Clamp do z-score do MetaStrength |
| `α` | 2.25 | Escala final do MetaStrength (multiplica `conf·z` já clampado) |
| `k0_role` | pickrate neutra | Pseudo-contagem da confiança: `conf = pr/(pr+k0_role)` |
| `λ` | 0.25 | Intensidade do threat weighting (componente counter) |
| `μ` | 0.3 | Intensidade do threat weighting (componente mapa) |
| `CAP` (`THREAT_CAP`) | 2.5 | Teto assintótico do multiplicador de ameaça (piso = `1/CAP` = 0.4) |
| `SCALE` (`THREAT_SCALE`) | 2.5 | Escala do `raw` ("temperatura") — controla a diferenciação das ameaças |
| `β_meta` | 2.0 | Peso do MetaStrength no score total (preset "equilibrado") |
| `β_ctr` | 1.0 | Peso do counter term no score total |
| `β_syn` | 0.65 | Peso da sinergia no score total |

Os valores acima são o preset **"equilibrado"** (default). `core/scoring.py`
expõe `ModelWeights` + `PRESETS`; o preset ativo vem de `settings.json`
(`weights_preset`), com overrides individuais via `custom_weights` (modo
avançado). Os quatro presets diferem apenas nos pesos abaixo (os demais
parâmetros — `α`, `μ`, `CAP`, `SCALE` — são comuns):

| Preset | `β_meta` | `λ` | `β_ctr` | `β_syn` | Prioriza |
|---|---|---|---|---|---|
| **Equilibrado** (padrão) | 2.0 | 0.25 | 1.0 | 0.65 | balanceia meta, counter e sinergia |
| **Counter-first** | 1.0 | 0.40 | 1.50 | 0.50 | counterar o time inimigo |
| **Meta-first** | 4.0 | 0.25 | 1.0 | 0.65 | desempenho estatístico no mapa atual |
| **Conforto+** | 2.0 | 0.25 | 1.0 | 1.25 | sinergia com o seu próprio time |

Heróis já presentes no time aliado **e heróis banidos no competitivo** são
**excluídos do ranking** (regra rígida — mesmo tratamento de indisponibilidade).

### Build e Distribuição

O build completo é feito pelo **`packaging/build.bat`**, que executa três etapas em sequência (a versão é lida de `version.txt`, fonte única):

1. **PyInstaller** (`packaging/overwatch.spec`) → `dist/OWPick/` (one-folder). O spec espelha no bundle:
   - Todos os módulos Python do pacote `owpick`
   - `assets/` — templates de heróis (`heroes/720p|2k|bans`), Tesseract OCR (`ocr/`), strings de UI (`i18n/`) e o ícone
   - `data/` — as matrizes **CSV** (`synergies.csv`, `counters.csv`), o layout de captura (`layouts/ow_hero_select.json`) e `stats_inputs.csv`
   - `version.txt`
   - Os `.xlsx` de edição e as ferramentas de `tools/` **não** são empacotados
2. **Zip do auto-updater** → `dist/OWPick_v<versão>.zip` (a pasta `dist/OWPick/` inteira; formato consumido pelo `updater.py`)
3. **Inno Setup** (`packaging/installer.iss`) → `dist/OWPick Installer.exe`

Quando `OWPick.exe` é executado, o PyInstaller resolve os assets em `sys._MEIPASS`. A função `infra.resources.resource_path()` resolve os caminhos corretos tanto no modo desenvolvimento (relativos à raiz do repositório, independente do CWD) quanto no executável.

**Distribuição (GitHub Releases)** — cada release publica dois artefatos:

| Artefato | Público | Papel |
|---|---|---|
| `OWPick Installer.exe` | Novos usuários | Instalação com atalhos e desinstalador; esconde a pasta `_internal` |
| `OWPick_v<versão>.zip` | Auto-updater | Baixado e aplicado automaticamente pelo `updater.py` (URL em `version.json`) |

**Requisito de build**: Inno Setup 6 instalado (o `build.bat` procura em `%LOCALAPPDATA%\Programs\Inno Setup 6` e `%ProgramFiles(x86)%\Inno Setup 6`). Não é dependência Python — não pertence ao `requirements.txt`.

**Release automatizado por tag** (`.github/workflows/release.yml`, tarefa 7.3):
um push de tag `v*` dispara, no runner Windows, o `build.bat` completo, gera os
`sha256`, cria a GitHub Release com o `.zip` + instalador e **commita o
`version.json`** atualizado na `main` (só então os usuários veem a atualização).
O script local `tools/bump.py X.Y.Z` sincroniza `version.txt` e o `CHANGELOG`
antes de criar a tag (o workflow valida que a tag bate com o `version.txt`).

### Instalador (`installer.iss`)

O instalador é per-user e **deliberadamente não requer administrador**:

- **Diretório de instalação**: `%LOCALAPPDATA%\Programs\OWPick` (`PrivilegesRequired=lowest`). Essencial para o auto-updater: o `robocopy` do update sobrescreve a instalação, o que exige permissão de escrita — instalar em `Program Files` quebraria o update.
- **Atalhos** (Menu Iniciar + Área de Trabalho opcional) gravados com `AppUserModelID: "DaviGiuberti.OWPick"` — o mesmo AUMID declarado em runtime (ver abaixo). É o vínculo oficial pelo qual a taskbar resolve o ícone do app.
- **Versão**: lida de `version.txt` em tempo de compilação (`#define` do preprocessador) — nenhuma duplicação de versão no script.
- **AppId fixo** (GUID): novas versões do instalador atualizam a mesma instalação em vez de criar outra.
- **Aviso de Termos de Serviço** (tarefa 8.1): antes de instalar, um diálogo de confirmação (`InitializeSetup`) informa que o OWPick é um observador passivo (sem overlay, sem leitura de memória, sem automação de input), mas que ferramentas externas são área cinzenta do ToS — o uso é por conta do usuário.
- **Desinstalador**: registrado em "Aplicativos instalados" do Windows; remove também arquivos residuais de versões antigas gravados ao lado do exe (`Roles.txt`, favoritos, `print/` etc.). Os dados atuais do usuário vivem em `%APPDATA%\OWPick` e **não** são removidos pelo update.
- Idiomas: PT-BR e EN; ícone do instalador: `icone.ico` do projeto.

### Ícone na barra de tarefas (Windows 10/11)

**Problema**: com `console=True`, no Windows 11 o host de console padrão é o **Windows Terminal** — a janela pertence ao Terminal, e a taskbar agrupa janelas por **AppUserModelID (AUMID)**; sem AUMID explícito, o OWPick herdava a identidade do Terminal e exibia o ícone genérico de terminal (no Windows 10 o host `conhost` herda o ícone do exe, por isso funcionava).

**Solução em três partes** (todas necessárias):

1. `infra.resources.configure_windows_app_identity()` — chamada no início de
   `ui.console.main()`: declara o AUMID `DaviGiuberti.OWPick`
   (`SetCurrentProcessExplicitAppUserModelID`) e aplica o ícone embutido do exe
   à janela do console (`WM_SETICON`).
2. Atalhos do instalador com o **mesmo AUMID** — a taskbar resolve o ícone de
   um AUMID a partir do atalho do Menu Iniciar correspondente.
3. `icone.ico` multi-tamanho (16/20/24/32/40/48/64/128/256 px) — a taskbar usa
   os tamanhos pequenos; o arquivo original só tinha 256×256.

### Auto-update

O sistema de auto-update (`infra/updater.py`) detecta a nova versão via
`version.json` no GitHub e aplica o `.zip` com um `.bat` gerado dinamicamente
(usando `robocopy`) sobre o diretório de instalação — compatível com a
instalação per-user do instalador.

**Checagem não bloqueante no boot** (tarefa 7.2): a verificação roda em uma
thread daemon (`updater.start_background_check`) — o boot é imediato, sem
`input()` nem I/O de rede travando a inicialização. Havendo versão nova, o
resultado é publicado em `updater.pending_update` e a UI avisa com uma linha no
console. O usuário aplica pelo comando `update` **ou** ao encerrar o programa
(`updater.apply_pending_update`). O fluxo bloqueante clássico
(`check_for_updates`, com `ask` injetável) permanece para uso via CLI/testes.

**Update seguro com rollback** (tarefa 7.1): o `.bat` gerado
(`updater._build_update_bat`) aplica a atualização nesta ordem:

1. Renomeia a instalação atual (`OWPick.exe` + `_internal/`) para `OWPick.old/`
   — `move` no mesmo volume é um rename atômico, então a versão antiga fica
   íntegra.
2. Copia a nova versão com `robocopy`.
3. Se o `robocopy` falhar (`ERRORLEVEL >= 8`), **restaura** o `OWPick.old` e
   **relança a versão antiga** — o usuário nunca fica sem app.
4. Em caso de sucesso, relança o `OWPick.exe`. O app novo, ao subir, apaga o
   `OWPick.old` (`updater.cleanup_old_backup`, chamado no início de
   `console.main`) — confirmando que a atualização deu certo.

---

## Detalhamento dos Módulos (`src/owpick`)

> Os antigos módulos flat (`main.py`, `screenshot.py`, `comparar.py`, `map.py`,
> `choose_ow_hero.py`, `utils.py`, `favoriteHero.py`) foram reorganizados nas
> três camadas abaixo durante a v1.2.0. Esta seção descreve o estado atual.

---

### Camada de aplicação (cross-cutting)

#### `__main__.py`

Ponto de entrada (`python -m owpick` e entry do PyInstaller): garante `src/` no
`sys.path` e chama `ui.console.main()`.

#### `pipeline.py` — casos de uso

| Função | Descrição |
|---|---|
| `RankingResult` | Dataclass com o resultado completo (role, lineup, bans, mapa, ameaças, recomendações, excluídos) — a `ui` só formata |
| `analyze(report, save_debug)` | Captura → matching → OCR, tudo **em memória**: `capture.capture()`; matching de bans+lineup roda **em paralelo** ao OCR do mapa (`ThreadPoolExecutor(max_workers=2)` — o Tesseract é subprocess-bound e o OpenCV libera o GIL); reporta slots não identificados |
| `rank(role, playable, allies, enemies, banned, mapa)` | Matrizes via `datasource`, pesos do preset ativo (`settings` + `resolve_weights`), `load_meta_strength` + `compute_threat_weights` + `rank_heroes` → `RankingResult` |
| `run_pipeline(report, save_debug)` | Caso de uso completo da hotkey de captura; `None` se role/favoritos ausentes (mensagens "o que houve + o que fazer") |
| `rank_from_files()` | Fluxo standalone por arquivos (equivalente ao antigo `choose_ow_hero`): lê `lineup.txt`/`bans.txt`/`current_map.txt` do cache e ranqueia |

O parâmetro `report` é um callback de progresso (a UI passa o console rich);
`save_debug=True` grava os PNGs intermediários (modo `--debug`).

#### `paths.py`

Separa os **três tipos de dado** (nenhum módulo usa caminho relativo/CWD):

| Função | Local | Conteúdo |
|---|---|---|
| `user_data_dir()` | `%APPDATA%\OWPick` | settings.json, Roles.txt, favoritos, stats override, logs |
| `cache_dir()` | `%LOCALAPPDATA%\OWPick\cache` | `print/` (debug), lineup/bans/current_map.txt (fluxo CLI) |
| `logs_dir()` | `%APPDATA%\OWPick\logs` | log rotativo |

`user_file`/`cache_file`/`ensure_dirs` são os helpers; `migrate_legacy_user_data()`
copia `Roles.txt`/favoritos do diretório do exe/CWD (versões antigas) para o novo
local **sem nunca sobrescrever** dados já migrados.

#### `settings.py`

Settings único, **tipado e validado** (`settings.json` em `%APPDATA%\OWPick`).
Campo inválido cai para o default com aviso claro e **nunca derruba o boot**;
chaves desconhecidas são ignoradas com aviso; campo `version` para upgrades de
esquema. API: `get()` (cacheado) / `save()` / `reload()` / `parse()`.

| Campo | Descrição |
|---|---|
| `hotkey` | Combinação de captura (default `["tab", "1"]`) |
| `language` | Idioma da UI: `pt-BR` (default) ou `en` |
| `debug` | Equivale à flag `--debug` |
| `explain_ranking` | Liga/desliga o "por quê" dos top-3 |
| `weights_preset` / `custom_weights` | Preset de pesos do modelo + overrides individuais |
| `scraper_region` / `scraper_tier` | Passados ao scraper na atualização de stats |
| `lineup_match_max_score`, `ban_match_max_score`, `map_min_confidence`, `updater_url` | Overrides avançados; `None` = default calibrado do módulo dono |
| `profiles` / `active_profile` | Múltiplos perfis (role + favoritos + preset + tier) |

#### `i18n.py`

`t(chave, **placeholders)` lê `assets/i18n/pt-BR.json` e `en.json`; o idioma vem
de `settings.language`. Degradação segura em cadeia (idioma → pt-BR → a própria
chave); placeholder inválido devolve o texto cru — uma string nunca derruba o app.

#### `log.py`

`setup_logging(debug)`: `RotatingFileHandler` (2×1MB) em `%APPDATA%\OWPick\logs`
no nível DEBUG + console em INFO. `--debug` (ou `settings.debug`) sobe o console
para DEBUG e preserva os PNGs intermediários.

---

### `core/` — domínio puro (ZERO I/O)

Os dados (DataFrames, matrizes, layout) chegam ao core **por parâmetro** — nunca
lidos dentro dele. `core` não importa `infra` nem `ui`.

#### `core/heroes.py`

Fonte de verdade dos dados embutidos e da normalização:

- `HEROES_ROLES` (24 DPS, 14 TANK, 14 SUP), `MAPS_DATA` (29 mapas), `SLOTS`, `VALID_ROLES`
- `MAP_ALIASES` + `get_map_search_index()`: aliases por idioma (ex.: `"Rota 66"`)
  mapeados de volta ao nome **canônico** (chave do `stats_inputs.csv`) — só entram
  aliases ancorados em token distintivo (evita falso positivo com OCR ruidoso)
- `normalize_hero_name(name)`: NFKD → remove acentos → minúsculas → não-alfanuméricos
  viram `-` (`"D.Va"`→`"dva"`, `"Soldier: 76"`→`"soldier-76"`, `"Lúcio"`→`"lucio"`)
- `build_matrix_dict(df)`: DataFrame → `dict[herói_norm][col_norm] = valor` (NaN descartado)
- `get_role_neutral_pickrates()`: pickrate neutra por role (usada pelo MetaStrength)

#### `core/resolution.py`

Matemática de resolução e recorte (pura):

| Função | Descrição |
|---|---|
| `resolution_scale(full_w)` | Fator linear em relação à base 1280×720 |
| `nearest_resolution_key(w, h)` | Âncora mais próxima (`"720p"`/`"2k"`); empate → maior |
| `pick_template_bank(portrait_px)` | Banco cujo retrato representativo é o mais próximo em **tamanho**; empate → 2k |
| `template_bank_for_resolution(full_w)` | Escala o retrato-base pela resolução e delega acima |
| `scale_and_clamp(...)` | Função **canônica** de conversão de caixa base → resolução atual (com clamp) |
| `get_scaled_map_region(w, h, config)` | Região do mapa para qualquer resolução: âncora exata, interpolação (1080p) ou extrapolação proporcional |

**Escolha do banco de templates por tamanho de retrato** — em vez da resolução
da tela, decide pelo tamanho do retrato que será comparado
(`TEMPLATE_BANK_PORTRAIT_PX = {"720p": 41, "2k": 82}`, `BASE_PORTRAIT_PX = 41`);
o limiar entre bancos é o ponto médio (≈61,5px), regra genérica sem `if` por
resolução:

| Resolução | Retrato do lineup | Banco (lineup) |
|---|---|---|
| 720p  | ~41px   | 720p |
| 1080p | ~61,5px | **2k** |
| 2K    | ~82px   | 2k |

Os **bans não passam por esta escolha** — usam o banco dedicado
`assets/heroes/bans/` (fonte 128px, redimensionada para `BAN_COMPARE_SIZE` em
qualquer resolução).

#### `core/models.py`

Dataclasses de domínio — a normalização acontece **uma vez, na fronteira**:

| Tipo | Papel |
|---|---|
| `Hero` | `from_name()` normaliza e resolve a role; erros aliado/inimigo viram erros de tipo |
| `MatchResult` | `(hero, score, confident)` — resultado de um slot |
| `Lineup` / `BanList` | Times identificados / heróis banidos |
| `MapDetection` | `(name, score)`; `UNKNOWN` quando não identificado |
| `CaptureResult` | Captura em memória: `full` + recortes por perk + recortes de ban |
| `Recommendation` | `(hero, meta, counter, synergy, total, reasons)` — `reasons` alimenta a explicabilidade |

#### `core/scoring.py`

MetaStrength + threat weighting + ranking (ver [Modelo de Scoring](#modelo-de-scoring)):

| Item | Descrição |
|---|---|
| Constantes | `EPS`, `MMAX`, `ALPHA`, `LAMBDA`, `MU_THREAT`, `THREAT_CAP`, `THREAT_SCALE`, `BETA_META/CTR/SYN`, `NEUTRAL_WEIGHT` (= 1.0) |
| `threat_multiplier(raw, cap, scale)` | Multiplicador de ameaça `CAP ** tanh(raw/SCALE)`; `w(0)=1`, `w ∈ (1/CAP, CAP)`, log-simétrico |
| `ModelWeights` + `PRESETS` + `resolve_weights` | Presets nomeados ("equilibrado" = default, "counter-first", "meta-first", "conforto+") + overrides do modo avançado |
| `load_meta_strength(stats_df, mapa, alpha)` | z-score da winrate bruta **por role**, atenuado pela confiança da pickrate |
| `compute_threat_weights(...)` | `w_e = threat_multiplier(λ·Σ C(e,a) + μ·m(e,k))` (sinal bruto sem offset; 0 = neutro) |
| `calculate_hero_score(...)` | Componentes meta/ctr/syn + **acumula contribuições por origem em `reasons`** |
| `rank_heroes(...)` | Exclui aliados + banidos e devolve `Recommendation`s ordenadas |

#### `core/ports.py`

`Protocol`s das fronteiras: `ScreenCapturer`, `MetaSource`, `MatrixSource`.

---

### `infra/` — I/O (captura, matching, OCR, dados, persistência, update)

#### `infra/capture.py`

| Função | Descrição |
|---|---|
| `find_overwatch_client_rect()` | Localiza a janela do Overwatch via `ctypes`/user32 (`FindWindowW` + `GetClientRect`/`ClientToScreen`); `None` se ausente/minimizada |
| `grab_screen()` | Captura o retângulo do cliente do jogo (multi-monitor/modo janela) ou **cai para o monitor primário**; avisa se o aspecto não for ~16:9 |
| `crop_capture(img, role)` | **Interpreta o layout versionado** (`data/layouts/ow_hero_select.json`): 10 slots × 4 variações de perk (com `vertical_buffer`; pula o slot da role do jogador) + 5 slots de ban (recorte exato, sem buffer) — tudo **em memória** |
| `capture()` | `grab_screen` + `crop_capture` → `CaptureResult` |
| `save_debug_artifacts(cap)` | Grava os PNGs em `cache/print/` (apenas `--debug` ou fluxo CLI) |

#### `infra/matching.py`

Template matching do lineup e dos bans, consumindo `CaptureResult`:

**Constantes**: `BASE_CROP_SIZE = (42, 57)` e `BASE_WINDOW_HEIGHT = 42` (720p,
escalados pela resolução); `LINEUP_MATCH_MAX_SCORE = 0.70` (limiar de confiança
do lineup, escala `1 − TM_CCOEFF_NORMED ∈ [0, 2]`); `BAN_COMPARE_SIZE = (48, 48)`,
`BAN_FRAME_FRACTION = 0.05`, `BAN_MATCH_MAX_SCORE = 0.12` (MAE normalizado).
Os dois limiares aceitam override via `settings.json`.

**Lineup** (`match_lineup(cap)`):
1. Banco escolhido pelo **tamanho do retrato** (`template_bank_for_resolution`)
2. Templates **cacheados** por `(banco, tamanho)` (`lru_cache` — resolução nova invalida sozinha)
3. `find_best_match_sliding`: `cv2.matchTemplate` com **`TM_CCOEFF_NORMED`**
   (correlação de média zero — imune a brilho/HDR/highlight); como o template tem
   a largura do recorte, o mapa de resultado é 1D = deslizamento vertical em C++
4. Melhor variação de perk = menor score médio
5. Slot com score acima do limiar → **não identificado** (`confident=False`),
   **excluído** do lineup (fora das somas de counter/sinergia) e reportado na saída

**Bans** (`match_bans(cap)`): matching **direto** (sem janela deslizante) contra o
banco dedicado `assets/heroes/bans/` (ícones 3D oficiais, 128px, pasta plana):
descarta a moldura vermelha da UI, redimensiona para `BAN_COMPARE_SIZE` e calcula
o MAE; melhor MAE acima do limiar = slot **vazio**. Validação em captura real 2K:
5/5 corretos (MAE 0.048–0.077; 2º colocado ≥ 0.17; sem ban ≥ 0.13).

`executar()` mantém o fluxo CLI standalone: lê `cache/print/`, escreve
`lineup.txt`/`bans.txt` — **mesma implementação de matching** do fluxo em memória.

#### `infra/map_detect.py`

`detect(full_img) → MapDetection`, em memória:

1. Região do nome do mapa via `get_scaled_map_region` + âncoras do layout
   (`datasource.load_capture_config`). A âncora **720p foi recalibrada na v1.2.0**
   (left 890→1055; agora consistente com a âncora 2K ÷ 2) — o OCR passou a ler o
   nome do mapa corretamente também em 720p
2. Pré-processamento: grayscale → autocontraste → upscale 2× (LANCZOS)
3. OCR via `ocr_backends.run_ocr` (Tesseract embutido por padrão, `--psm 7`)
4. `identify_map`: **uma** chamada a `rapidfuzz.process.extractOne` com
   `fuzz.token_set_ratio` (`processor=str.upper`) contra o índice canônico +
   aliases por idioma; devolve sempre o nome **canônico**
5. `MIN_CONFIDENCE = 30.0` (override no settings): abaixo disso → `UNKNOWN`
   (MetaStrength neutro, ranking continua)

`executar()` é o fluxo CLI (lê `cache/print/full.png`, grava `current_map.txt`).

#### `infra/ocr_backends.py`

Backends de OCR plugáveis, selecionados pela env `OWPICK_OCR_BACKEND`:
`tesseract` (default — `assets/ocr/tesseract.exe` + `tessdata/`, embutidos) e
`windows` (`Windows.Media.Ocr` via `winsdk`, **experimental**, grupo opcional
`ocr-win`; fallback automático para o Tesseract se indisponível).

#### `infra/datasource.py`

Leitura/cache dos dados do modelo (tudo `lru_cache`):

| Função | Fonte |
|---|---|
| `get_ally_matrix()` / `get_enemy_matrix()` | `data/synergies.csv` / `data/counters.csv` (o runtime lê **apenas** os CSVs; a edição é nos `.xlsx` + `tools/xlsx_to_csv.py`) |
| `read_stats_inputs()` | `stats_inputs.csv` — **override do usuário** em `%APPDATA%\OWPick` tem prioridade sobre o embutido (`stats_source_path`); `refresh_stats_cache()` invalida após atualização |
| `load_layout()` / `load_capture_config()` | `data/layouts/ow_hero_select.json` (geometria de captura + âncoras da região do mapa) |

#### `infra/validation.py`

Validação dos dados na carga com **aviso claro do que falta**: `validate_matrix`
(linhas E colunas ≡ `HEROES_ROLES` — pega órfãos/typos), `validate_stats` (29
mapas × roles), `validate_templates` (retratos 720p/2k + ícone de ban para todo
herói), `validate_all` + `report_problems`. Roda nos testes e no boot com `--debug`.

#### `infra/stats_update.py`

`update_stats(report)`: opção 4 do menu — **baixa** o `stats_inputs.csv` publicado
(GitHub raw, `STATS_CSV_URL`; override via `settings.stats_url`), valida as colunas
mínimas, grava de forma atômica no **override do usuário** e invalida o cache.
Usa só stdlib (`urllib`) + pandas → funciona no **executável congelado sem nenhuma
dependência externa** (sem Playwright/navegador/código-fonte). O usuário só baixa o
app e atualiza. Publicação (autor): regenerar `data/stats_inputs.csv` com o scraper
`tools/coletar_stats.py` e commitar na main. Falha de rede/CSV inválido → aviso
claro e as stats atuais são preservadas.

#### `infra/storage.py`

Persistência em texto: arquivos do **usuário** (`Roles.txt`, `ALL/DPS/SUP/TANK.txt`
em `%APPDATA%\OWPick`) e artefatos do **fluxo CLI** (`lineup.txt`, `bans.txt`,
`current_map.txt` no cache). `read_role`/`write_role` (validação `VALID_ROLES`),
`read_playable_heroes`, `load_favorites`/`save_heroes_to_files`,
`read/write_lineup|bans|current_map`.

#### `infra/resources.py`

`resource_path(rel)`: resolve recursos pela **raiz do repositório** em dev
(independente do CWD) e por `sys._MEIPASS` no exe. `APP_USER_MODEL_ID`
(`"DaviGiuberti.OWPick"`) + `configure_windows_app_identity()` (identidade na
taskbar — ver seção do ícone).

#### `infra/updater.py`

| Função | Descrição |
|---|---|
| `get_local_version()` | Lê `version.txt` embutido no pacote |
| `_parse_version(v)` | `"1.2.3"` → `(1, 2, 3)` (comparação numérica) |
| `_fetch_version_info()` | Baixa `version.json` (URL padrão ou override do settings; timeout 6s) |
| `_evaluate_update()` | Núcleo: `{version, download_url, notas}` se remota > local, senão `None` |
| `check_for_updates(ask)` | Fluxo bloqueante (CLI/testes; `ask` injetável) |
| `start_background_check(on_available)` | Checagem **não bloqueante** (thread daemon); publica `pending_update` |
| `apply_pending_update()` | Aplica o update pendente (comando `update`/ao fechar) |
| `_apply_update(url)` / `_build_update_bat(...)` | Baixa o `.zip`, extrai e gera o `.bat` de **update seguro** (testável) |
| `cleanup_old_backup()` | Apaga `OWPick.old` no boot (confirma o sucesso do update) |

O fluxo completo (rollback + não bloqueante) está descrito na seção
[Auto-update](#auto-update).

---

### `ui/` — console (a ÚNICA camada que imprime)

#### `ui/console.py`

`main()` (boot): identidade Windows → `paths.ensure_dirs` + migração →
`updater.cleanup_old_backup` → settings + logging → validação de dados (só
`--debug`) → `updater.start_background_check` → role/favoritos se ausentes →
registra a hotkey → `input_loop` em thread daemon.

Menu: `2` role · `3` favoritos · `4` atualizar stats · `5` hotkey · `6` explicação
do ranking · `7` perfis · `8` preset de pesos · `sim ...` simulação · `update`
aplicar update pendente · `exit`. `IN_MAIN` bloqueia a hotkey durante subcomandos; cooldown de 1s evita
disparo duplo. Combinações **com TAB** usam `keyboard.hook()` + `HotkeyDetector`
(o `RegisterHotKey` do Windows não aceita TAB); as demais, `keyboard.add_hotkey`.

#### `ui/ranking_view.py`

Apresentação `rich` do `RankingResult`: tabela com cores por role (DPS/TANK/SUP),
top-3 em negrito, barra proporcional ao score, painel do ranking de ameaças,
spinner durante o pipeline e explicações do top-3 (`settings.explain_ranking`).

#### `ui/roles.py` / `ui/favorites.py`

Menus com **fonte de input injetável** (default real: `msvcrt.getch()`/`input()`).
Roles: `1`=ALL, `2`=TANK, `3`=SUP, `4`=DPS → `storage.write_role`. Favoritos:
fuzzy match por `rapidfuzz` (`FUZZY_MIN_SCORE = 40`), adds em lote por role,
persistência via `storage.save_heroes_to_files`.

#### `ui/hotkey.py`

Hotkey configurável: `HotkeyDetector` (última tecla dispara, demais seguradas —
semântica do TAB+1), `capture_combo` (teclas exibidas em tempo real),
`validate_combo`, `executar` (confirmar/voltar ao padrão; persiste no settings).

#### `ui/sim.py`

Modo manual/simulação: `sim mapa=Ilios inimigos=Tracer,Winston aliados=Mei`
(chaves PT e EN; nomes com espaço suportados). Fuzzy de herói reutiliza
`favorites.find_best_match`; de mapa, `map_detect.identify_map` (aliases PT-BR
grátis; limiar próprio 60). Executa **apenas** `pipeline.rank` (zero captura) e
renderiza com a mesma `ranking_view`.

#### `ui/profiles.py`

Múltiplos perfis (perfil = role + favoritos + preset de pesos + tier de stats):
`save_profile` fotografa o estado atual; `apply_profile` aplica **pelos
mecanismos existentes** (`storage.write_role`, `save_heroes_to_files`, settings);
`delete_profile`; menu `executar` com input injetável. `set_weights_preset(name)`
troca o preset corrente e o **vincula ao perfil ativo** (se houver), preservando a
escolha ao alternar perfis.

#### `ui/weights.py`

Menu da opção 8: mostra o preset atual, lista os presets (rótulos em
`core.scoring.PRESET_LABELS`) e aplica a escolha via
`profiles.set_weights_preset` — a troca fica **vinculada ao perfil ativo**. Input
injetável para testes.

---

### `tools/` — ferramentas de desenvolvimento (NÃO empacotadas)

| Ferramenta | Descrição |
|---|---|
| `coletar_stats.py` | Scraper Playwright (owtics.gg) → `stats_inputs.csv`. `argv[1]` = destino (o app passa o override do usuário); `argv[2]`/`argv[3]` = região/tier. Estratégias: JS direto → XHR interceptado → regex no texto |
| `xlsx_to_csv.py` | Converte as matrizes de **edição** (`heroes ally.xlsx`/`heroes enemy.xlsx`) nos CSVs lidos em runtime (`synergies.csv`/`counters.csv`) — rodar antes de cada release com mudança de dados |
| `enemy_mult.py` | Diagnóstico de threat weight (consumidor do core). **Atenção**: lê o lineup com perspectiva **invertida** (do ponto de vista do herói inimigo avaliado) — intencional |
| `bump.py` | `python tools/bump.py X.Y.Z`: grava `version.txt` e insere o cabeçalho no `CHANGELOG` (o `version.json` é atualizado pelo workflow de release) |
| `resolucao.py` | Seletor visual de coordenadas (Tkinter) — uso em recalibração de layout |

---

## Dados do Jogo

### Heróis Suportados (52 total)

| Role | Heróis |
|---|---|
| **DPS** (24) | Anran, Ashe, Bastion, Cassidy, Echo, Emre, Freja, Genji, Hanzo, Junkrat, Mei, Pharah, Reaper, Shion, Sierra, Sojourn, Soldier: 76, Sombra, Symmetra, Torbjörn, Tracer, Vendetta, Venture, Widowmaker |
| **TANK** (14) | D.Va, Domina, Doomfist, Hazard, Junker Queen, Mauga, Orisa, Ramattra, Reinhardt, Roadhog, Sigma, Winston, Wrecking Ball, Zarya |
| **SUP** (14) | Ana, Baptiste, Brigitte, Illari, Jetpack Cat, Juno, Kiriko, Lifeweaver, Lúcio, Mercy, Mizuki, Moira, Wuyang, Zenyatta |

### Mapas Suportados (29 total)

| Modo | Mapas |
|---|---|
| **Control** (7) | Antarctic Peninsula, Busan, Ilios, Lijiang Tower, Nepal, Oasis, Samoa |
| **Escort** (8) | Circuit Royal, Dorado, Havana, Junkertown, Rialto, Route 66, Shambali Monastery, Watchpoint: Gibraltar |
| **Hybrid** (8) | Blizzard World, Eichenwalde, Hollywood, King's Row, Midtown, Neon Junction, Numbani, Paraíso |
| **Push** (4) | Colosseo, Esperança, New Queen Street, Runasapi |
| **Flashpoint** (2) | New Junk City, Suravasa |

### Templates de Imagem

Os templates do **lineup** estão organizados em `assets/heroes/{resolucao}/{role}/` onde `resolucao` é `720p` ou `2k`. Cada arquivo é uma imagem `.png` do retrato ilustrado do herói extraída da tela de seleção do Overwatch 2.

Os templates dos **bans** ficam em `assets/heroes/bans/` (pasta plana, sem divisão por role ou resolução): um `.png` de 128×128 por herói com o **ícone 3D oficial** — a mesma arte exibida nos slots de ban da UI, que é diferente do retrato ilustrado do lineup. Os nomes de arquivo seguem a mesma convenção dos bancos existentes (`DVa.png`, `Soldier 76.png`, `Lúcio.png`, ...).

---

## Dependências

A fonte de verdade das dependências é o **`pyproject.toml`** (lockfile `uv.lock`,
gerenciado pelo `uv`), com grupos separados: **runtime**, **dev** (Ruff, Pyright,
pytest, openpyxl para o conversor), **build** (PyInstaller), **scraper**
(Playwright) e **ocr-win** (winsdk, opcional). O `requirements.txt` é mantido
apenas como referência de transição.

### Dependências de runtime

| Biblioteca | Versão mínima | Finalidade |
|---|---|---|
| `mss` | 10.2.0 | Captura de tela de alta performance |
| `Pillow` | 12.2.0 | Manipulação de imagens, crop, autocontraste |
| `opencv-python` | 4.13.0 | `cv2.matchTemplate` (TM_CCOEFF_NORMED) e redimensionamento |
| `numpy` | 2.4.0 | Arrays numéricos do matching |
| `pandas` | 2.0.0 | Leitura dos CSVs (matrizes e `stats_inputs.csv`) |
| `keyboard` | 0.13.5 | Hotkey global fora do foco da janela (apenas detecção) |
| `rapidfuzz` | 3.14.5 | Fuzzy matching do mapa (OCR) e da busca de heróis por nome |
| `unidecode` | 1.4.0 | Normalização de strings com acentos |
| `pytesseract` | 0.3.13 | Wrapper Python para o Tesseract OCR embutido |
| `rich` | 13.0 | Console rico: tabela de ranking, painel de ameaças, spinner |

### Dependências de desenvolvimento/build (grupos do `pyproject.toml`)

| Biblioteca | Grupo | Finalidade |
|---|---|---|
| `ruff`, `pyright`, `pytest` | dev | Lint/format, type checking e testes |
| `openpyxl` | dev | `tools/xlsx_to_csv.py` (conversão das matrizes de edição) |
| `PyInstaller` | build | Geração do executável `.exe` |
| `playwright` | scraper | `tools/coletar_stats.py` (+ `playwright install chromium`) |
| `winsdk` | ocr-win (opcional) | Backend experimental `Windows.Media.Ocr` |
| `PyAutoGUI` | dev | Seletor visual de coordenadas (`tools/resolucao.py`) |

### Dependências de Stdlib

| Biblioteca | Finalidade |
|---|---|
| `msvcrt` | Leitura de tecla sem echo (`ui/roles.py`, Windows only) |
| `ctypes` | Localização da janela do jogo (user32) e identidade na taskbar |
| `tkinter` | Interface gráfica do seletor de área (`tools/resolucao.py`) |
| `unicodedata` | Remoção de acentos para normalização |
| `urllib` | Download de `version.json` e do pacote de update |
| `zipfile`, `shutil`, `subprocess` | Extração e aplicação do pacote de atualização |
| `logging`, `functools`, `threading`, `concurrent.futures` | Log rotativo, caches (`lru_cache`), hotkey/menu em threads e paralelismo do pipeline |

### Dependência Externa (Binária)

| Componente | Localização | Finalidade |
|---|---|---|
| **Tesseract OCR** | `assets/ocr/tesseract.exe` + `assets/ocr/tessdata/` | Reconhecimento óptico de caracteres para identificação do mapa |

O Tesseract está embutido no repositório e no executável. Não é necessário instalá-lo separadamente.

---

## Postura de Anticheat / Termos de Serviço (restrição de arquitetura)

Esta é uma **regra permanente de arquitetura** do OWPick, não uma decisão de uma
versão específica. Toda evolução do projeto deve respeitá-la:

1. **Apenas captura passiva de tela.** O programa lê a imagem da tela (via `mss`
   ou do retângulo do cliente da janela do jogo, tarefa 4.3) exatamente como um
   software de screenshot/streaming faria. Nada além disso.
2. **Zero interação com o processo do jogo.** Sem injeção de código, sem leitura
   de memória do Overwatch, sem hook de DirectX/Vulkan, sem overlay renderizado
   sobre o jogo. O OWPick nunca abre, lê ou escreve no processo do jogo.
3. **Zero automação de input.** O programa **não** move o mouse, não clica e não
   pressiona teclas dentro do jogo. A dependência `keyboard` é usada **somente**
   para *detectar* a hotkey global de captura (entrada do usuário), nunca para
   *emitir* input no jogo.
4. **Escopo permanece "terminal + screenshot".** **Não há planos de overlay.** O
   OWPick continua sendo um terminal que apenas tira print da tela e mostra o
   resultado em outra janela (o console). Qualquer pedido de overlay/ESP/aim está
   fora do escopo por design.
5. **Aviso ao usuário.** README e instalador deixam claro que ferramentas
   externas de terceiros são uma **área cinzenta dos Termos de Serviço** do jogo
   e que o uso é **por conta e risco do usuário**.

Essas restrições existem para manter o programa do lado seguro de anticheat/ToS:
um observador passivo, indistinguível de um software de captura de tela comum.

---

## Pontos de Atenção

### Pontos que podem confundir

1. **Perspectiva invertida em `tools/enemy_mult.py`**: as variáveis `allies` e `enemies` têm semântica invertida — são do ponto de vista do herói inimigo avaliado, não do jogador. O código está correto, mas pode confundir quem lê pela primeira vez sem contexto.
2. **Limite conhecido — bans em 1080p**: um dos 5 slots de ban da fixture 1080p marca MAE 0.152 (> `BAN_MATCH_MAX_SCORE = 0.12`, calibrado em 2K) e é descartado. Subir o limiar não resolve (um slot vazio em 720p marca 0.173). Documentado como `xfail` em `tests/test_matching_golden.py`; requer métrica/critério de margem mais robustos para os bans.

### Adição de Novos Heróis

Para adicionar um novo herói ao sistema, é necessário atualizar dois lugares:
1. A constante `HEROES_ROLES` em `src/owpick/core/heroes.py` (fonte de verdade para nome e role)
2. Os templates de imagem em `assets/heroes/`: retratos do lineup nas resoluções suportadas (`720p` e `2k`) e o ícone 3D oficial em `assets/heroes/bans/` (reconhecimento de bans)

Depois, atualizar as matrizes (`.xlsx` de edição → `tools/xlsx_to_csv.py`) e as
stats (`tools/coletar_stats.py`). O validador (`infra/validation.py`, roda nos
testes e no boot com `--debug`) aponta exatamente o que estiver faltando.
