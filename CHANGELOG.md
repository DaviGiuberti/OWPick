# Changelog — OWPick

Todas as mudanças relevantes de versão são documentadas aqui.

---

## [v1.2.11] — 2026-07-24

### Consumo de recursos: o jogo tem prioridade sobre o OWPick

Auditoria de performance do programa inteiro, motivada por travamentos do
Overwatch em notebook fraco enquanto o OWPick está aberto. **Nenhuma mudança de
comportamento**: ranking, detecção de heróis/mapas/bans e textos continuam
idênticos (verificado nas fixtures 720p/1080p/2K — mesmos heróis, mesmos bans,
mesmo mapa e mesmos scores até a 8ª casa decimal).

- **Prioridade do processo abaixo do normal** (novo `infra/perf.py`): no boot o
  OWPick entra em `BELOW_NORMAL_PRIORITY_CLASS`. Em disputa por CPU o Windows
  passa a servir o Overwatch primeiro. Como o pipeline é uma ação manual de
  ~1–2s, a latência não muda de forma perceptível. Desligável em
  `settings.json` (`low_priority: false`).
- **OpenCV limitado a 1 thread e sem GPU**: o OpenCV vinha usando **todos os
  núcleos** (8 nesta máquina) e com **OpenCL LIGADO**, ou seja, podia despachar
  operações para a mesma GPU integrada que renderiza o jogo — exatamente no
  instante do TAB+1. Agora o boot aplica `cv2.setNumThreads(1)` e
  `cv2.ocl.setUseOpenCL(False)`. Como os recortes são minúsculos (~42×57 px em
  720p), o paralelismo quase não compensava a sincronização: medido em rodadas
  repetidas nas fixtures, a latência do matching fica **dentro do ruído** nas
  duas configurações (~±10%) — o ajuste não custa tempo perceptível e devolve
  7 núcleos e a GPU integrada para o jogo. Ajustável em `settings.json`
  (`opencv_threads`; `0` = padrão do OpenCV).
- **Cache de templates só mantém o banco em uso**: `load_all_templates` e
  `load_ban_templates` passaram de `lru_cache(maxsize=8)`/`(maxsize=4)` para
  `maxsize=1`. Alternar entre tela cheia e modo janela numa mesma sessão não
  deixa mais bancos de resoluções antigas residentes em memória.
- **Instrumentação de tempo por etapa** (só com `--debug` / `settings.debug`):
  o `owpick.log` passa a registrar o tempo de parede de cada etapa do pipeline
  (`captura`, `recorte`, `matching`, `ocr-mapa`, `ocr-role`, `ranking`) e a
  memória residente do processo. Custo zero em uso normal — fora do modo debug
  nem o relógio é consultado. Sem dependência nova (`time.perf_counter` +
  `ctypes`).
- Correção de uma armadilha do `ctypes` no novo módulo: sem `argtypes`/`restype`
  explícitos o pseudo-handle de `GetCurrentProcess()` chega **truncado** em 32
  bits e o `SetPriorityClass` falha silenciosamente com `ERROR_INVALID_HANDLE`.
  Coberto por teste de regressão (`tests/test_perf.py`).

### Destaque do ranking por preset (apresentação)

- A tabela do ranking (TAB+1) passa a **destacar em laranja** (`bold orange1`) o
  nome do herói campeão da coluna que o **preset ativo** prioriza:
  - **Counter-first** → maior valor em `COUNTER`;
  - **Meta-first** → maior valor em `MAP META`;
  - **Conforto+** → maior valor em `SYNERGY`;
  - **Equilibrado** → sem destaque especial (exibição inalterada).
- Mudança **exclusivamente visual**, em `ui/ranking_view.py`: nenhuma alteração
  em ordenação, pontuação, pesos, presets ou no algoritmo de scoring. O herói
  destacado permanece na mesma posição do ranking.

### Fixtures de teste 720p adicionais

- A fixture golden `tests/fixtures/720p/full.png` foi renomeada para `full1.png`
  e ganhou duas companheiras reais — `full2.png` e `full3.png` — cada uma com seu
  gabarito (`expected2.json`/`expected3.json`). Ampliam a cobertura do matching de
  lineup e da detecção de mapa em 720p (novos testes em
  `tests/test_matching_golden.py`); lineup e mapa das três fixtures batem 100%.
- Os bans de `full2.png` (Wrecking Ball, MAE 0.152) e `full3.png` (Mercy, 0.141)
  reincidem no **limite conhecido** dos bans fora de 2K — o 4º ban legítimo fica
  acima do `BAN_MATCH_MAX_SCORE` (0.12, calibrado em 2K) e é descartado. Registrado
  como `xfail` (mesma causa do 1080p); **algoritmo inalterado**.

---

## [v1.2.10] — 2026-07-22

### Detecção automática da role no TAB+1

- O pipeline do **TAB+1** passa a **detectar automaticamente a role** (Tank/DPS/
  Support) que o jogador está usando, em vez de depender apenas da role escolhida
  manualmente no menu. Logo após a captura, um novo passo lê o **nome do herói do
  jogador** exibido na scoreboard (região versionada no layout, escalada por
  `resolution.scale_and_clamp` — compatível com 720p/1080p/2K/4K, sem lógica por
  resolução) e identifica o herói por OCR + fuzzy match contra `HEROES_ROLES`. A
  role desse herói é usada em **todo o pipeline** (recorte do lineup, favoritos
  jogáveis e ranking).
- **Fallback preservado**: se o herói do jogador não for identificado com
  confiança, o pipeline mantém exatamente o comportamento anterior — usa a role
  escolhida manualmente pelo usuário (`Roles.txt`). Detecção automática primeiro;
  sistema antigo como fallback.
- Novo módulo `infra/player_hero.py` (`detect(full_img) -> Hero | None`), que
  **reutiliza** o OCR do `map_detect` (mesmo backend e pré-processamento) e a
  matemática de escala já existente — sem lógica de resolução paralela nem
  duplicação de código. A captura da tela passou a ser feita **uma única vez** por
  execução do TAB+1 (a mesma imagem alimenta a detecção da role e o recorte do
  lineup, que precisa da role para pular o slot do próprio jogador).
- **Nota técnica**: a identificação usa o NOME do herói (texto na scoreboard), e
  não template matching do retrato contra `assets/heroes/2k` — a arte do retrato
  grande da scoreboard tem enquadramento diferente do busto do lineup, tornando o
  template matching não confiável para esse fim; o OCR do nome é robusto (validado
  nas fixtures 720p/1080p/2K).

---

## [v1.2.9] — 2026-07-21

### Enemy Threat — sinergia SUP × SUP ignorada

- O componente de sinergia usado no cálculo do **Enemy Threat** (threat
  weightings) `ν · Σ_{e'≠e} Y(e,e')` passa a **ignorar pares Suporte × Suporte**:
  qualquer par em que **ambos** os inimigos são da role SUP contribui **0** para
  o sinal bruto de ameaça. Pares com pelo menos uma role diferente (SUP×DPS,
  SUP×TANK, DPS×TANK, ...) continuam contribuindo normalmente.
- Ajuste interno de balanceamento dos threat weightings (dois suportes juntos
  não tornam o inimigo mais perigoso para efeito de ameaça).
- **Nenhuma alteração no cálculo normal de sinergias**: o score de sinergia do
  ranking principal, o score final, as matrizes, os CSVs e os presets de score
  seguem usando SUP × SUP exatamente como antes. A exceção vale **somente** para
  o termo de sinergia dentro do Enemy Threat.

---

## [v1.2.8] — 2026-07-18

### Recalibração do preset Counter-first

- Novos pesos do preset **Counter-first**: `β_ctr = 1.00` (era 1.50),
  `β_syn = 0.325` (era 0.50), `β_meta = 0.75` (era 1.0), `λ = 0.32` (era 0.45),
  `μ = 0.23` (era 0.30). `ν` permanece 0.10.
- **Sinergia Suporte × Suporte**: no Counter-first, pares em que **ambos** os
  heróis são da role SUP usam peso de sinergia **0.65**; todas as demais
  combinações de roles (SUP×DPS, SUP×TANK, DPS×TANK, ...) usam **0.325**.
  Implementado pelo novo campo opcional `ModelWeights.beta_syn_sup_sup`
  (`None` = usa `beta_syn`), preenchido apenas no preset Counter-first.

### Comportamento alterado

- Como `λ` e `μ` mudaram, o multiplicador de ameaça, o ranking de ameaças, o
  counter score e o ranking final do Counter-first mudam em relação à v1.2.7.
- Os presets **Equilibrado**, **Meta-first** e **Conforto+** permanecem
  inalterados.

---

## [v1.2.7] — 2026-07-18

### Atualização de dados (matriz de sinergias)

- Matriz de sinergias migrada de uma fonte externa em JSON para a planilha
  oficial de edição `data/heroes ally.xlsx`, convertendo a escala do JSON
  (−30..30, em passos de 10) para a escala do projeto (−3..3).
- **Relações Suporte × Suporte preservadas**: os valores já existentes na
  planilha para pares de heróis da role SUP foram mantidos exatamente como
  estavam. Todas as demais relações vieram do JSON. A diagonal (herói × ele
  mesmo) também foi preservada.
- `data/synergies.csv` e `data/counters.csv` regenerados a partir dos `.xlsx`
  via `tools/xlsx_to_csv.py` (fonte lida em runtime).
- Nenhuma mudança de código: modelo de scoring, pipeline e demais módulos
  permanecem idênticos à v1.2.6.

---

## [v1.2.6] — 2026-07-18

### Atualização de dados (counters e stats de meta)

- `data/counters.csv` (e a fonte de edição `data/heroes enemy.xlsx`) atualizada
  com ajustes finos na matriz de counters entre heróis, refletindo o
  balanceamento atual do jogo.
- `data/stats_inputs.csv` atualizado com winrate/pickrate por mapa mais
  recentes, fonte do MetaStrength no scoring.
- Nenhuma mudança de código: modelo de scoring, pipeline e demais módulos
  permanecem idênticos à v1.2.5.

---

## [v1.2.5] — 2026-07-08

### Enemy Threat agora considera a sinergia DENTRO do time inimigo

- O sinal bruto de ameaça de cada inimigo ganhou um **terceiro componente**: além
  de (1) quão bem ele countera o seu time e (2) sua força no mapa, entra agora
  (3) a **sinergia dele com o resto do time inimigo**. A fórmula passa de
  `raw = λ·Σ_a C(e,a) + μ·m(e,k)` para
  **`raw = λ·Σ_a C(e,a) + μ·m(e,k) + ν·Σ_{e'≠e} Y(e,e')`**.
- **Racional**: um inimigo inserido numa composição coesa (bons combos) é mais
  perigoso; um inimigo em anti-sinergia com os companheiros é menos ameaçador. O
  termo usa a **mesma matriz de sinergia `Y`** (`data/synergies.csv`) já usada
  para os aliados, aplicada aos pares de inimigos, com a diagonal `e' == e`
  ignorada.
- **Novo parâmetro `ν` (`nu`)** em `ModelWeights`, diferenciado por preset (o
  Enemy Threat continua obedecendo integralmente o preset ativo):

  | Preset | `λ` | `μ` | `ν` |
  |---|---|---|---|
  | Equilibrado | 0.25 | 0.30 | 0.10 |
  | Counter-first | 0.45 | 0.30 | 0.10 |
  | Meta-first | 0.20 | 0.70 | **0.15** |
  | Conforto+ | 0.18 | 0.20 | **0.06** |

  "Meta-first" valoriza mais a comp coesa (comp forte no mapa é ameaça);
  "Conforto+" de-enfatiza a sinergia inimiga junto com os demais eixos de ameaça.
- `ν` também é ajustável no modo avançado via `custom_weights` no `settings.json`
  (campo `nu`).
- **Compatibilidade**: `compute_threat_weights` recebe a matriz de sinergia por
  parâmetro (`synergy_matrix`, opcional); sem ela o termo `ν` some — os fluxos e
  testes que não a fornecem seguem idênticos.
- `tests/test_scoring.py` ganhou casos para o novo termo (com e sem sinergia).

### Ajuste de peso do MapMeta (β_meta) em dois presets

- **Equilibrado** (padrão): `β_meta` reduzido de **2.0 → 1.5**.
- **Meta-first**: `β_meta` reduzido de **4.0 → 3.0**.
- Nenhum outro peso foi alterado (`λ`, `μ`, `ν`, `β_ctr`, `β_syn` e `α`
  permanecem idênticos). O objetivo é atenuar a influência do desempenho
  estatístico por mapa no score final, mantendo a hierarquia entre presets.
- Snapshots de `tests/test_presets.py` e `tests/test_explain.py` atualizados para
  os novos valores.

### Novo scraper `tools/coletar_stats2.py` (site oficial da Blizzard)

- Ferramenta de desenvolvimento **independente** do `coletar_stats.py` (owtics.gg):
  coleta winrate/pickrate por mapa direto do site OFICIAL da Blizzard
  (`overwatch.blizzard.com/.../rates/`).
- **Sem Playwright**: os dados já vêm embutidos no HTML entregue pelo servidor
  (SSR), como JSON HTML-escapado (`"cells":{"name":...,"winrate":...,"pickrate":...}`).
  Um GET com `urllib` (stdlib) + des-escape de entidades + regex/`json` basta —
  abordagem mais rápida e simples que dirigir um navegador.
- Usa o locale `en-us` para que os nomes de heróis batam com os nomes canônicos
  do projeto (o PT-BR localiza "Soldado: 76"/"Rainha Junker"); percorre todos os
  mapas suportados (`heroes.MAPS_DATA`, cujos slugs já coincidem com os da
  Blizzard). Gera **exatamente** o mesmo formato de `stats_inputs.csv`.
- Aceita `destino.csv`, `região` e `tier` por argv (com aliases dos códigos do
  `settings.json`); detecta mudança de layout de forma robusta (página 200 sem
  blocos reconhecidos vira aviso claro, sem derrubar a coleta dos demais mapas).
- `banrate` é ignorado (o projeto usa apenas winrate e pickrate).

---

## [v1.2.4] — 2026-07-07

### Correção: tabela de ranking inconsistente (TOTAL ≠ MAP META + COUNTER + SYNERGY)

- **Causa raiz**: `calculate_hero_score` (`core/scoring.py`) gravava as colunas
  `MAP META` e `COUNTER` com os valores **brutos** (sem `β_meta`/`β_ctr`),
  enquanto `SYNERGY` já vinha ponderada por `β_syn` e `TOTAL` aplicava todos os
  pesos — misturando escalas. Resultado: a soma das três colunas não batia com
  o `TOTAL` exibido.
- **Correção**: `β_meta` e `β_ctr` passam a ser aplicados **uma única vez,
  dentro** de `calculate_hero_score`. As colunas `MAP META`, `COUNTER` e
  `SYNERGY` agora são exatamente as contribuições **já ponderadas** que entram
  no score, de modo que **`TOTAL = MAP META + COUNTER + SYNERGY`** sempre —
  verificável a olho na tabela.
- As razões da explicabilidade ("por quê" do top-3) passam a usar os mesmos
  valores ponderados das colunas (ex.: a razão "forte em `<mapa>`" agora reflete
  a contribuição de meta já multiplicada por `β_meta`).
- `tests/test_scoring.py` e `tests/test_explain.py` atualizados para os novos
  snapshots.

### Enemy Threat: curva recalibrada + λ/μ diferenciados por preset

- **Causa raiz**: o Enemy Threat já usava os parâmetros do preset ativo (sem
  bug de fiação ou cache), mas dois fatores o tornavam quase invariável:
  1. Só o preset "Counter-first" alterava `λ`; "Meta-first" e "Conforto+" não
     sobrescreviam `λ`/`μ`/`α`, produzindo um multiplicador de ameaça
     **idêntico** ao "Equilibrado".
  2. As âncoras da curva (`w(−6) = 0.5`, `w(8) = 2.5`, da v1.2.3) ficavam a
     ~10σ da faixa real observada de `raw` (medida nas matrizes reais:
     `Σ_a C(e,a)` tem desvio-padrão ≈ 2.31, `m(e,k)` ≈ 0.88 ⇒ `raw` opera em
     `~[−2, +2]`), deixando a curva praticamente reta (`w ∈ ~[0.97, 1.05]`)
     mesmo com `λ`/`μ` diferentes.
- **Correção — recalibração das âncoras** (`THREAT_ANCHOR_LOW`/`THREAT_ANCHOR_HIGH`
  em `core/scoring.py`): de `(−6, 0.5)`/`(8, 2.5)` para **`(−1.5, 0.6)`/`(3.0, 2.5)`**
  — dentro da faixa operacional real. `A` (`THREAT_LOG_CAP`) e `S`
  (`THREAT_SCALE`) recalculados por bisseção: `A ≈ 1.51`, `S ≈ 4.25` (antes
  `3.81`/`32.6`). Curva atualizada:
  `raw −3/−2/−1.5/−1/−0.5/0/0.5/1/1.5/2/3 → 0.40/0.52/0.60/0.71/0.84/1.00/1.19/1.42/1.67/1.94/2.50`.
- **Correção — `λ`/`μ` diferenciados por preset** (antes só `λ` do
  "Counter-first" mudava; `μ` era comum a todos):

  | Preset | `λ` (antes → agora) | `μ` (antes → agora) |
  |---|---|---|
  | Equilibrado | 0.25 → 0.25 | 0.30 → 0.30 |
  | Counter-first | 0.40 → **0.45** | 0.30 → 0.30 |
  | Meta-first | 0.25 → **0.20** | 0.30 → **0.70** |
  | Conforto+ | 0.25 → **0.18** | 0.30 → **0.20** |

- **Efeito**: trocar o preset agora muda de fato o multiplicador de ameaça, o
  ranking de ameaças exibido, o counter score e o ranking final — inclusive
  reordenando quem é a maior ameaça (ex.: "Meta-first" passa a priorizar
  inimigos fortes no mapa atual sobre quem apenas countera bem o time).
- `tests/test_scoring.py` (`TestThreatMultiplier.test_ancoras`) atualizado para
  as novas âncoras.

---

## [v1.2.3] — 2026-07-07

### Enemy Threat: curva re-ancorada em dois pontos escolhidos

- A **forma** da curva do multiplicador de ameaça introduzida na v1.2.2
  (`w(raw) = exp( A · tanh(raw / S) )`) **não muda**. O que muda é **como `A` e
  `S` são obtidos**: em vez de calibrados por percentil sobre a distribuição
  real de `raw` (`THREAT_CAP = 2.5`, `THREAT_SCALE = 2.5` fixados
  diretamente), a curva agora é **ancorada em dois pontos exatos** escolhidos
  — `w(−6) = 0.5` e `w(8) = 2.5` (`THREAT_ANCHOR_LOW`/`THREAT_ANCHOR_HIGH` em
  `core/scoring.py`).
- Como não há forma fechada para `A`/`S` a partir de dois pontos arbitrários,
  eles são **derivados por bisseção** no import do módulo
  (`_fit_log_symmetric`), resultando em `A ≈ 3.81` (`THREAT_LOG_CAP`) e
  `S ≈ 32.6` (`THREAT_SCALE`).
- `w(0) = 1` continua exato; a curva continua contínua, suave (C∞),
  estritamente monotônica e log-simétrica (`w(−raw) = 1 / w(raw)`) — nenhuma
  dessas propriedades muda, só os parâmetros numéricos.
- **Efeito prático:** como o `raw` real observado fica em `~[−2.85, +2.71]`
  (bem aquém da âncora `raw = 8`), a curva ficou **mais suave na faixa de
  operação**: o peso de uma ameaça típica passa a ficar em `~[0.72, 1.37]`
  (era mais agressiva na calibração da v1.2.2, com `raw = ±1` chegando a
  `1.42`/`0.71`; agora `raw = ±1` dá `1.12`/`0.89`). `0.5` e `2.5` deixam de
  ser alcançáveis por ameaças comuns e passam a marcar só os extremos
  ancorados (`raw = −6` e `raw = 8`).
- Curva atualizada:
  `raw −8/−6/−4/−2/−1/0/1/2/4/6/8 → 0.40/0.50/0.63/0.79/0.89/1.00/1.12/1.26/1.59/2.00/2.50`.
- `threat_multiplier` mantém a mesma assinatura; `tools/enemy_mult.py` e os
  testes (`tests/test_scoring.py`) continuam consumindo-a sem alteração —
  só os parâmetros internos (`A`/`S`) mudaram.

---

## [v1.2.2] — 2026-07-07

### Nova curva do multiplicador de Enemy Threat

- **Reformulação completa de como o sinal bruto de ameaça (`raw`) vira peso.**
  O peso de cada inimigo passa a ser
  `w(raw) = CAP ** tanh(raw / SCALE) = exp(ln(CAP) · tanh(raw / SCALE))`, com
  `raw = λ · Σ_a C(e,a) + μ · m(e,k)` (o **offset `+1` foi removido**: agora
  `raw = 0` é literalmente a ameaça neutra).
- **Novo comportamento da curva:**
  - `raw = 0` ⇒ `w = 1` **exatamente** (antes `raw = 0` dava ≈ 1.3 — o
    comportamento que motivou a mudança).
  - `raw < 0` ⇒ `w < 1` (inimigo pouco ameaçador é atenuado);
    `raw > 0` ⇒ `w > 1` (inimigo perigoso é amplificado).
  - **Contínua, suave (C∞) e estritamente monotônica** — preserva a ordenação
    das ameaças.
  - **Limitada a `(1/CAP, CAP) = (0.40, 2.50)` por construção**: `tanh ∈ (−1, 1)`,
    então o peso **nunca explode** nem fica não-positivo. Ficar abaixo de 0.5 ou
    acima de 2.5 exige `raw` extremo (fora da faixa observada nos dados reais),
    representando casos "extremamente extremos".
  - **Log-simétrica:** `w(−raw) = 1 / w(raw)` — um down/upweight de mesma
    magnitude são recíprocos, o comportamento natural de um multiplicador.
- **Escolha técnica** (`exp∘tanh` em vez de softplus/log/exponencial pura):
  o softplus não tinha teto (podia explodir) e dava ≈ 1.3 em `raw = 0`; a
  exponencial pura explode; o `exp(ln(CAP)·tanh(raw/SCALE))` é a única forma
  simples que junta **f(0)=1 exato**, **limites rígidos** e **simetria
  logarítmica** num só passo suave.
- **Parâmetros** calibrados sobre a distribuição real de `raw`
  (Monte Carlo com a matriz de counters + MetaStrength por mapa: `std ≈ 0.64`,
  p1 ≈ −1.44, p99 ≈ +1.50): `THREAT_CAP = 2.5`, `THREAT_SCALE = 2.5`. Nessa
  faixa o peso quase nunca sai de `[0.5, 2.5]`, com boa diferenciação
  (`raw = ±1` ⇒ ≈ 1.42 / 0.71).
- `NEUTRAL_WEIGHT` passou de `softplus(1) ≈ 1.313` para `1.0` (o peso de uma
  ameaça neutra). `enemy_mult.py` (diagnóstico) e os testes foram sincronizados.

### Presets de pesos reajustados

- **Equilibrado:** `β_meta = 2` (era 1). Demais termos inalterados
  (`α = 2.25`, `λ = 0.25`, `μ = 0.3`, `β_ctr = 1.0`, `β_syn = 0.65`).
- **Counter-first:** `β_meta = 1`, mantendo o counter/threat reforçados
  (`λ = 0.40`, `β_ctr = 1.50`, `β_syn = 0.50`).
- **Meta-first:** `β_meta = 4`, `β_ctr = 1`, `β_syn = 0.65`.
- **Conforto+:** parte do Equilibrado e só sobe a sinergia: `β_syn = 1.25`.

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
