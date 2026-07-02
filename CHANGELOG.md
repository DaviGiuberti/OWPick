# Changelog — OWPick

Todas as mudanças relevantes de versão são documentadas aqui.

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
