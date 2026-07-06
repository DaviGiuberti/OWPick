# Changelog — OWPick

Todas as mudanças relevantes de versão são documentadas aqui.

---

## [v1.2.1] — 2026-07-06

### Presets de pesos vinculados ao perfil

- Nova **opção 8 do menu**: escolhe o preset de pesos do modelo
  (Equilibrado/Counter-first/Meta-first/Conforto+) direto do console, sem
  editar `settings.json` na mão.
- A escolha fica **vinculada ao perfil ativo** (opção 7): trocar de perfil
  troca também o preset, e o preset volta ao valor salvo do perfil ao
  reativá-lo. Sem perfil ativo, a troca afeta só o preset corrente.

### Atualização de stats sem dependências externas

- A opção 4 do menu ("atualizar stats de meta") deixou de depender do
  scraper local (Playwright) e agora **baixa** o `stats_inputs.csv`
  publicado no repositório (GitHub raw) e grava no override do usuário.
- Funciona no **executável já instalado, sem Playwright, sem navegador e sem
  o código-fonte** — o usuário só clica em "atualizar stats".
- Validação das colunas mínimas antes de gravar (uma resposta inesperada do
  servidor não corrompe as stats atuais) e mensagens claras em falha de rede.
- O scraper (`tools/coletar_stats.py`) continua existindo como ferramenta de
  publicação: o autor o roda para regenerar `data/stats_inputs.csv` e
  commita na main — a partir daí, todos os usuários baixam essa versão.

---

## [v1.2.0] — 2026-07-05

Versão maior de reengenharia do OWPick. Reúne todo o trabalho das fases 0 a 8:
higiene de código, rede de testes, refatoração arquitetural, performance,
robustez de matching/OCR, dados versionáveis, settings/UX e build/release.

### Arquitetura e qualidade de código

- **Reorganização em `src/owpick/` com três camadas** — `core/` (domínio puro,
  zero I/O), `infra/` (captura, matching, OCR, dados, updater, persistência) e
  `ui/` (console, a única camada que imprime). Casos de uso em `pipeline.py`.
- **Domínio modelado com dataclasses** (`Hero`, `Lineup`, `BanList`,
  `MatchResult`, `MapDetection`, `CaptureResult`, `Recommendation`): a
  normalização de nomes acontece **uma vez**, na fronteira.
- **Pipeline em memória**: cada etapa recebe/devolve objetos NumPy/dataclasses;
  os ~45 PNGs e os `.txt` viram artefatos **apenas de debug** (`--debug`).
- **Renomeações** para nomes consistentes: `comparar.py → matching.py`,
  `map.py → map_detect.py`, `favoriteHero.py → favorites.py`.
- **`paths.py`**: separa os três tipos de dado (app imutável / dados do usuário em
  `%APPDATA%\OWPick` / cache em `%LOCALAPPDATA%\OWPick\cache`) com migração
  automática dos dados de versões antigas. Nenhum módulo usa mais caminho
  relativo/`Path.cwd()`.
- **Layout de captura versionado** (`data/layouts/ow_hero_select.json`): o código
  interpreta o layout; nada de coordenadas hardcoded (`config.json` removido).
- **Tooling**: `pyproject.toml` + `uv.lock` (grupos runtime/dev/build/scraper),
  **Ruff** (lint+format), **Pyright** (0 erros) e **pytest** (rede de testes com
  fixtures golden 720p/1080p/2K).
- Logging estruturado (`logging` + arquivo rotativo em `%APPDATA%\OWPick\logs`),
  exceções disciplinadas (degradações logadas e justificadas) e encoding do
  console corrigido de vez.

### Performance

- Janela deslizante em Python puro trocada por **`cv2.matchTemplate`** (C++/SIMD).
- **Cache de templates escalados** por `(banco, tamanho)`.
- **OCR do mapa em paralelo** ao matching (`ThreadPoolExecutor`), fora do caminho
  crítico.

### Robustez de matching e OCR

- **Limiar de confiança no lineup**: slot acima do limiar vira "não identificado"
  e é excluído das somas de counter/sinergia (fim da recomendação sobre lineup
  fictício).
- Métrica de matching **`TM_CCOEFF_NORMED`** (imune a brilho/HDR/highlight),
  escolhida pelos dados por elevar a margem 1º–2º.
- **Captura da janela do jogo** via Win32 (`ctypes`), com fallback ao monitor
  primário. **Compatível apenas com 16:9** (documentado).
- Fuzzy match do mapa simplificado (`rapidfuzz.token_set_ratio`, fim da explosão
  combinatória) e **suporte ao idioma do cliente** (aliases PT-BR → nome
  canônico; "Rota 66" deixa de virar `UNKNOWN`). Backend de OCR plugável
  (Tesseract padrão; `Windows.Media.Ocr` opcional).
- **Região do nome do mapa recalibrada em 720p** no layout de captura (âncora
  agora consistente com a âncora 2K): o OCR do mapa passa a funcionar também em
  720p — antes lia lixo e podia casar um mapa errado com falsa confiança — e o
  1080p interpolado ficou mais confiável.

### Dados

- Matrizes de counters/sinergias em **CSV versionável** (`data/counters.csv`,
  `data/synergies.csv`); os `.xlsx` viram fonte de edição (conversor
  `tools/xlsx_to_csv.py`, fora do bundle).
- **Validador de matrizes/stats/templates** com aviso claro do que falta.
- Opção no menu para **atualizar as stats de meta** (roda o scraper e grava no
  override do usuário).
- **Melhorias nos counters da Kiriko, Illari e Wuyang.**

### Settings e UX

- **`settings.json`** único, tipado e validado em `%APPDATA%\OWPick` (campo
  inválido cai para o default com aviso; nunca derruba o boot).
- **Hotkey de captura configurável** (captura em tempo real; padrão `TAB+1`).
- **Presets de pesos** do modelo (Equilibrado/Counter-first/Meta-first/Conforto+)
  + modo avançado.
- **Explicabilidade do ranking** (liga/desliga): o "por quê" dos top-3.
- **Console rico** (`rich`): cores por role, top-3 destacado, barras, painel de
  ameaças e spinner.
- **Strings de UI por idioma** (PT-BR/EN) no padrão "o que houve + o que fazer".
- **Modo simulação** (`sim mapa=... inimigos=... aliados=...`, só scoring).
- **Múltiplos perfis** (role + favoritos + preset + tier).

### Build, release e atualização

- **Update seguro com rollback**: o `.bat` renomeia a instalação atual para
  `OWPick.old` antes de aplicar a nova e restaura em caso de falha do `robocopy`;
  o app novo apaga o backup ao subir. O usuário nunca fica sem app.
- **Checagem de update não bloqueante**: o boot é imediato; a checagem roda em
  thread de fundo e avisa sem travar (comando `update` ou aplicação ao fechar).
- **Release automatizado por tag** (GitHub Actions `v*`): build no runner
  Windows, publicação da Release com `.zip` + instalador + `sha256` e commit
  automático do `version.json`. Script local `tools/bump.py X.Y.Z` sincroniza
  `version.txt` e o `CHANGELOG`.

### Postura de anticheat / Termos de Serviço

- Registrada como **restrição permanente de arquitetura**: apenas captura passiva
  de tela; zero interação com o processo do jogo; zero automação de input; sem
  planos de overlay. Aviso claro no README e no instalador de que o uso é por
  conta do usuário.

---

## [v1.1.6] — 2026-07-03

### Distribuição profissional via instalador (Inno Setup)

- Novos usuários passam a baixar **um único arquivo**: `OWPick Installer.exe`.
  A pasta `_internal` do build one-folder do PyInstaller deixa de ficar exposta —
  fica escondida dentro do diretório de instalação.
- **Instalação per-user** em `%LOCALAPPDATA%\Programs\OWPick` (sem admin/UAC),
  escolhida deliberadamente para manter o **auto-updater** atual funcionando:
  o `robocopy` do update continua com permissão de escrita na instalação.
- Novo `installer.iss` (script Inno Setup): atalhos no Menu Iniciar e na Área de
  Trabalho (opcional), desinstalador no Windows, idiomas PT-BR/EN, versão lida
  de `version.txt` (fonte única).
- Novo `build.bat`: build completo em um comando — PyInstaller → zip do
  auto-updater (`OWPick_v<versão>.zip`) → instalador (`OWPick Installer.exe`).
- O fluxo do auto-updater **não mudou**: usuários existentes continuam
  atualizando pelo `.zip` publicado na Release (URL em `version.json`).

### Correção definitiva do ícone na barra de tarefas do Windows 11

- **Causa raiz:** no Windows 11 o host de console padrão é o **Windows
  Terminal**; a janela do app pertence ao Terminal e a barra de tarefas agrupa
  janelas pelo **AppUserModelID (AUMID)**. Sem AUMID explícito, o OWPick herdava
  a identidade do Terminal → ícone genérico. Além disso, `icone.ico` só tinha o
  tamanho 256×256 (a taskbar usa 16–32px).
- **Correções:**
  - `utils.configure_windows_app_identity()` (chamada no início de `main.py`):
    declara o AUMID `DaviGiuberti.OWPick` via
    `SetCurrentProcessExplicitAppUserModelID` e aplica o ícone embutido do exe
    à janela do console via `WM_SETICON`.
  - Os atalhos criados pelo instalador gravam o **mesmo AUMID** — mecanismo
    oficial pelo qual a taskbar do Win10/Win11 resolve o ícone do aplicativo.
  - `icone.ico` regenerado como multi-tamanho (16, 20, 24, 32, 40, 48, 64,
    128 e 256 px).

---

## [v1.1.5] — 2026-07-02

### Terminal mais limpo

- Removidos os prints de diagnóstico/debug do pipeline (execução via TAB+1):
  detecção de resolução/escala, pasta de templates escolhida, score de cada slot
  de ban individualmente e confirmação de escrita de `lineup.txt`. O console
  passa a exibir só o essencial em cada etapa (heróis identificados, bans, mapa
  e o ranking final), sem alterar nenhum comportamento do reconhecimento.

### Atualização de dados — Season 3

- `stats_inputs.csv` atualizado com winrate/pickrate por mapa da **Season 3**,
  fonte do MetaStrength no scoring.

---

## [v1.1.4] — 2026-07-02

### Correção do reconhecimento dos bans (banco de arte dedicado)

- **Causa raiz:** os ícones dos slots de ban usam a **arte 3D oficial** do herói
  (com moldura vermelha da UI), que é **diferente** dos retratos ilustrados de
  `heroes/720p|2k` (arte da tela de seleção). O matching dos bans contra os
  templates do lineup dava ~0/5 de acerto — nenhum ajuste de limiar resolveria.
- **Banco dedicado `heroes/bans/`:** novo banco com o ícone 3D oficial de cada herói
  (52 PNGs de 128px, pasta plana, mesma convenção de nomes dos demais bancos). Fonte
  de alta resolução — um único banco serve **todas** as resoluções.
- **Fluxo de bans separado do TAB+1:**
  - `screenshot.py`: o recorte de ban passa a ser o quadrado **exato** do retrato,
    **sem `VERTICAL_BUFFER`** (o slot de ban é fixo na UI). O TAB+1 continua com
    buffer + janela deslizante, **inalterado**.
  - `comparar.match_bans()` (agora só recebe `watch_dir`): matching **direto** —
    descarta a moldura da UI (`BAN_FRAME_FRACTION`), redimensiona recorte e
    templates para `BAN_COMPARE_SIZE` e calcula o MAE contra o banco inteiro
    (`_best_against_templates`, um ban pode ser de qualquer role), **sem janela
    deslizante**.
- **Simplificações:** removidas as constantes agora sem uso `BASE_BAN_CROP_SIZE`,
  `BASE_BAN_WINDOW_HEIGHT` (`comparar.py`) e `BASE_BAN_PORTRAIT_PX` (`utils.py`). Os
  bans não usam mais a escolha de banco por tamanho de retrato — que permanece
  válida e ativa apenas para o lineup.
- **Validação (captura real 2K, 5 bans):** 5/5 corretos com MAE 0.048–0.077; 2º
  colocado ≥ 0.17; regiões sem ban ≥ 0.13 — separação ampla em relação ao limiar
  `BAN_MATCH_MAX_SCORE = 0.12`.

---

## [v1.1.3] — 2026-07-02

### Suporte aos bans do Competitivo

- **Novo:** o pipeline identifica os heróis banidos nos até 5 slots de ban da parte
  superior da tela e os remove automaticamente do ranking, com o **mesmo tratamento
  de indisponibilidade** dos heróis já presentes no time aliado.
- `screenshot.py`: novos recortes `bans_template` (5 slots) salvos em `print/bans/`.
  As coordenadas foram convertidas da referência 2K (÷2) para a base 1280×720,
  reutilizando `scale_and_clamp` e o `VERTICAL_BUFFER` já existentes. Cada slot tem
  seu próprio `left` (independente das variações de perk) e é capturado uma única vez.
- `comparar.py`: nova função `match_bans()` compara cada slot contra **todos** os
  templates (tank+dps+sup) — um ban pode ser de qualquer role — reutilizando
  `find_best_match_sliding`. Um slot cujo melhor MAE fique acima de
  `BAN_MATCH_MAX_SCORE` é considerado **vazio** e ignorado (modos sem bans / slots
  não preenchidos). Resultado gravado em `bans.txt` (sempre reescrito).
- `choose_ow_hero.py`: novo `read_bans()`; os banidos entram na regra rígida de
  exclusão junto com os aliados. Relata "Excluídos (banidos)" separadamente.
- **Limiar configurável:** `BAN_MATCH_MAX_SCORE` (MAE normalizado) é o único ponto de
  ajuste. O matching imprime o score de cada slot no console para calibração a partir
  de capturas reais. Padrão inicial: `0.12`.

### Escolha do banco de templates pelo tamanho do retrato

- **Antes:** o banco (`720p`/`2k`) era escolhido pela distância de resolução da tela
  (`nearest_resolution_key`).
- **Agora:** a escolha é pelo **tamanho do retrato** que será comparado na resolução
  atual (`utils.pick_template_bank` / `template_bank_for_resolution`). Regra genérica,
  sem `if` por resolução: escolhe o banco de tamanho representativo mais próximo, com
  empate para o banco maior (2K, maior qualidade). O limiar é o ponto médio dos
  tamanhos representativos (≈ 61,5px para 41/82).
- Como cada tipo de retrato tem tamanho-base próprio (`BASE_PORTRAIT_PX = 41`,
  `BASE_BAN_PORTRAIT_PX = 31`), lineup e bans podem usar bancos diferentes na mesma
  resolução — ex.: em **1080p** o lineup usa **2K** (~61,5px) e os bans usam **720p**
  (~46,5px). Toda a regra de resolução permanece centralizada em `utils.py`.

### Melhorias de dados (planilha de counters)

- Ajustes nos counters de **Kiriko**, **Illari** e **Wuyang** em `heroes enemy.xlsx`.

---

## [v1.1.2] — 2026-06-20

### Correção do Meta Strength

- **Estatísticas por role:** `wr̄` e `σ` agora são calculados dentro de cada função
  (DPS/TANK/SUP), não mais de forma global. **Motivo:** comparar um DPS com a média
  global (puxada por tanks/supports) gerava z-score incorreto. (Ex. Shambali:
  wr̄ DPS = 51.03, TANK = 49.47, SUP = 50.10.)
- **Sigma da winrate bruta** (não dos valores encolhidos). **Motivo:** o `σ`
  encolhido (≈ 0.007 no Shambali) explodia artificialmente o z-score até o clamp ±3.
- **Confiança por pickrate:** `conf = pr / (pr + k0)`, com `k0` = pickrate neutra da
  role. Substitui o antigo `kappa = 100 · (prn / pr)`. **Motivo:** o `kappa` antigo
  (o fator `100` somado ao `/pr`) encolhia ~99% da winrate observada e invertia o
  papel da pickrate.
- **Remoção do shrinkage antigo** (`kappa`, média ponderada `(g·wr + κ·wr̄)/(g+κ)`,
  `sigma` sobre valores encolhidos) e da constante `KAPPA_BASE`. O `eps` (EPS) passa a
  ser apenas piso numérico da pickrate, sem papel de proxy de amostra.
- **`ALPHA = 2.25`** (era `1.0`): escala final do Meta Strength, aplicada como
  multiplicador de `clip(conf·z, ±Mmax)`.

### Correção do Threat Weighting

- **Softplus no lugar do piso:** `w_e = softplus(raw) = ln(1 + e^raw)`. **Motivo:** o
  antigo `max(W_MIN, raw)` colapsava ameaças distintas no mesmo valor de piso
  (ex.: Cassidy = Ana = Roadhog cravados no piso). O softplus é monotônico — `raw`
  maior ⟹ `w_e` maior **sempre** — preservando a ordenação na faixa de ameaças baixas.
- `W_MIN` deixa de ser o mecanismo de não-negatividade (fica inerte, mantido por
  compatibilidade de assinatura). O fallback de exibição de um inimigo ausente passa a
  usar o peso neutro `softplus(1) ≈ 1.313`.
- A Meta corrigida (×2.25) flui **automaticamente** para o threat via `μ · m(e,k)`,
  sem duplicar lógica em `compute_threat_weights`.
- `enemy_mult.py` (utilitário de diagnóstico) sincronizado: passa a usar `softplus`
  também, mantendo paridade com o pipeline principal.

---

## [v1.1.1] — 2026-06-18

### Threat Weighting — sempre ativo e ciente do mapa

**Antes (v1.1.0):** O threat weighting considerava apenas counters entre heróis:
```
w_e = max(0.1, 1 + λ · Σ_a C(e, a))
```
O resultado ignorava o desempenho do inimigo no mapa atual. Além disso, o sistema existia como modo opcional ativado/desativado via menu (opção 4 / `prioritize.txt`).

**Agora (v1.1.1):** O threat weighting é comportamento padrão e incorpora o MetaStrength do inimigo no mapa atual:
```
w_e = max(0.1, 1 + λ · Σ_a C(e,a) + μ · m(e,k))
```
- `λ = 0.25` — intensidade do componente counter (sem mudança)
- `μ = 0.3` — novo parâmetro: intensidade do componente mapa
- `m(e,k)` — MetaStrength do herói inimigo `e` no mapa atual `k` (z-score de winrate ajustado por shrinkage)

Um inimigo que countera seus aliados **e** tem alto winrate no mapa atual recebe peso de ameaça maior. Um inimigo fraco no mapa atual tem seu peso atenuado.

### Exibição de ranking de ameaças no terminal

Durante cada análise, o terminal agora exibe um ranking dos inimigos ordenado por nível de ameaça (maior → menor), antes da recomendação final:

```
--- Ranking de Ameaças Inimigas ---
  1º Pharah              Ameaça: 1.85
  2º Roadhog             Ameaça: 1.60
  3º Genji               Ameaça: 1.40
  4º Orisa               Ameaça: 1.20
  5º Moira               Ameaça: 1.10
------------------------------------
```

### Remoção do modo opcional de "Priorizar Counters"

- Removida a função `toggle_prioritize_file()` de `main.py`
- Removida a opção de menu 4 ("Priorizar Counters") de `print_main_menu()`, `print_small_menu()` e `input_loop()`
- O arquivo `prioritize.txt` não é mais lido nem gerado
- O threat weighting agora faz parte integral do pipeline, sem flag de ativação

### Parâmetro novo

- `MU_THREAT = 0.3` adicionado a `choose_ow_hero.py`

---

## [v1.1.0] — 2026-06 (implementação OWPick)

### utils.py — Fonte única de dados

- Criado `utils.py` como fonte canônica de heróis e mapas
- `HEROES_ROLES` e `MAPS_DATA` embutidos como constantes — o programa não lê mais `heroes_roles.json` nem `maps.txt` em runtime
- `normalize_hero_name()`: normalização robusta via NFKD + strip de `: . ' \`` — "D.Va"/"DVa" → "dva"; "Soldier: 76"/"Soldier 76" → "soldier-76"
- `resource_path()` centralizado (antes duplicado em vários módulos)
- Cache `@lru_cache(maxsize=1)` nas 4 funções de leitura de planilha/CSV — eliminadas releituras de disco entre execuções

### map.py — Identificação automática de mapa

- Novo módulo: OCR via Tesseract embutido em `ocr/` + fuzzy match (`rapidfuzz`) → `current_map.txt`
- Pré-processamento da imagem: escala de cinza + autocontraste + upscale 2×
- `TESSDATA_PREFIX` definido via variável de ambiente (fix: evita corrupção de caminho com `--tessdata-dir "..."` no config string do pytesseract)
- Integrado ao pipeline principal em `main.py` entre `comparar` e `choose_ow_hero`

### choose_ow_hero.py — Modelo de scoring

- Modelo completo: `S(h) = β_meta·m(h,k) + β_ctr·T_ctr(h) + T_syn(h)`
- `MetaStrength m(h,k)`: z-score de winrate com shrinkage bayesiano por pickrate relativa (κ_eff = κ_base · pr_neutra / pr)
- Heróis já presentes no time aliado são excluídos do ranking (regra rígida — substitui o hack `-11` na diagonal)
- Planilhas normalizadas em dicionários com chaves `normalize_hero_name`, tolerante a variações de nomenclatura

### Suporte a 1080p e outras resoluções

- Lógica de resolução centralizada em `utils.py` (`get_scaled_map_region`, `nearest_resolution_key`)
- 1080p: interpolação linear entre as âncoras 720p e 2K (sem tabela independente)
- Resoluções fora do intervalo: escala proporcional da âncora mais próxima
- `comparar.py` seleciona pasta de templates pela resolução real de `full.png`

### config.json

- Novo arquivo com coordenadas de captura da região do mapa por resolução (`map_region` + `base_resolution`)
- Âncoras: 720p e 2K; 1080p e outras derivadas matematicamente

### stats_inputs.csv e coletar_stats.py

- `coletar_stats.py` (scraper Playwright): agora usa `utils` como fonte de heróis e mapas
- `stats_inputs.csv`: lido com cache em runtime para MetaStrength

### Correções

- Typos de templates corrigidos: `Illarri.png → Illari.png`, `Rroadhog.png → Roadhog.png`
- Herói Shion adicionado à lista de DPS
- OCR: corrigido caminho `tessdata` corrompido por aspas no config string do pytesseract

### Dependências e empacotamento

- `overwatch.spec`: selenium removido; `map.py`, `utils.py`, `config.json`, `stats_inputs.csv` adicionados; `heroes_roles.json`/`maps.txt` removidos do bundle

---

## [v1.0.6] — anterior

- Planilha enemies/allies com updates
- Correções de bugs nos updates
- Adição de Shion, README e requirements
