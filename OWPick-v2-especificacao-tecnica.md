---
title: Especificação Técnica — OWPick v2
date: 2025-01-01
status: active
type: specification
project: OWPick
version: 2.0
tags: 
  - recomendacao
  - herois
  - ranked
  - modelo-matematico
  - overwatch
---
---

title: Especificação Técnica — OWPick v2 version: 1.7 date: 2026-06-18 status: active type: specification project: OWPick tags:

- overwatch
- recomendacao
- herois
- ranked
- modelo-matematico

---

# Especificação Técnica — OWPick v2

> **Versão 1.7** — Season 2 · 2026  
> Elo: Grandmaster e Champion · Patch: mais recente da Season 2  
> Tipo: Ranked GM · Dados: Winrate e Pickrate públicos por mapa

**Novidades da v1.7:**

- Adicionada a heroína **Shion** ao dicionário de heróis e ao `favoriteHero.py`
- Integração de `MetaStrength` por mapa como componente nativo do scoring
- Modo de priorização de counters promovido a modelo base (não mais opcional)
- Threat weighting substituindo o multiplicador hardcoded `(total/4)+1`
- Novo módulo `map.py` com OCR para identificação automática do mapa
- Novo `heroes_roles.json` como fonte única de heróis e papéis
- Novo `maps.txt` com lista completa de mapas em inglês
- Novo `utils.py` eliminando duplicações de código
- Novo `config.json` externalizando coordenadas de captura
- Correções: typos `Illarri.png` → `Illari.png` e `Rroadhog.png` → `Roadhog.png`
- Remoção de `selenium` do `overwatch.spec`

---

## Índice

- [[#1 Objetivo e Escopo|1. Objetivo e Escopo]]
- [[#2 Decisão de Arquitetura|2. Decisão de Arquitetura]]
- [[#3 Modelo Matemático|3. Modelo Matemático]]
- [[#4 Fontes de Dados|4. Fontes de Dados]]
- [[#5 Novos Módulos|5. Novos Módulos]]
- [[#6 Correções e Refatorações|6. Correções e Refatorações]]
- [[#7 Plano de Implementação|7. Plano de Implementação]]
- [[#8 Dependências|8. Dependências]]

---

## 1. Objetivo e Escopo

OWPick é uma ferramenta desktop que recomenda heróis durante a fase de seleção de personagem em partidas ranqueadas de Overwatch 2. A recomendação considera os heróis do time inimigo (counter score), os heróis aliados (sinergia) e a força do herói no mapa atual da partida (MetaStrength).

### 1.1 Escopo fixo

|Dimensão|Decisão|
|---|---|
|**Elo**|Grandmaster e Champion|
|**Patch**|Season 2 · 2026; sistema parametrizado por mapa atual|
|**Mapa**|Identificado automaticamente via `map.py` + OCR|
|**Tipo**|Ranked GM (solo-queue, coordenação parcial)|
|**Dados**|Winrate e Pickrate públicos por mapa; planilhas editadas manualmente|
|**Legalidade**|Apenas fontes públicas e legais; sem reverse engineering, API privada ou scraping ilegal|

### 1.2 Premissas adotadas

|Premissa|Decisão|
|---|---|
|Counter como escalar par a par|Aceitável para solo-queue; mantido|
|Assimetria nas matrizes de counter|Tolerada por enquanto; planilhas continuam no formato atual|
|Sinergia assimétrica|Tolerada por enquanto; planilhas continuam no formato atual|
|Winrate e Pickrate|Transformados em `MetaStrength`, termo separado do scoring|
|Diagonal `-11` de sinergia|Removida; substituída por regra de exclusão no scoring|
|Multiplicador `(total/4)+1`|Substituído por Threat Weighting derivado da matriz de counters|

> **Nota sobre as planilhas:** a especificação anterior propunha migrar para CSVs com triângulo superior, confiança por célula e estados NA. Essa migração **foi descartada** nesta versão. As planilhas `heroes ally.xlsx` e `heroes enemy.xlsx` permanecem no formato atual. O programa as lê, converte internamente para dicionários e opera normalmente. Qualquer mudança de dados é feita diretamente nas planilhas. Essa decisão reduz a complexidade operacional e respeita o fluxo de trabalho existente.

---

## 2. Decisão de Arquitetura

### 2.1 Componentes: situação por arquivo

|Componente|Arquivo|Veredito|Ação|
|---|---|---|---|
|Orquestrador|`main.py`|**Manter**|Sem alterações|
|Captura de tela|`screenshot.py`|**Manter + config.json**|Coordenadas saem do `config.json`|
|Identificação|`comparar.py`|**Manter**|Sem alterações funcionais|
|Scoring e ranking|`choose_ow_hero.py`|**Modificar**|Integra MetaStrength, threat weighting, lê mapa atual|
|Multiplicador inimigo|`enemy_mult.py`|**Modificar**|Passa a usar threat weighting; nomenclatura corrigida|
|Favoritos|`favoriteHero.py`|**Modificar**|Adiciona Shion; passa a ler `heroes_roles.json`|
|Role|`roles.py`|**Manter**|Sem alterações|
|Updater|`updater.py`|**Manter**|Sem alterações|
|Utilitários comuns|`utils.py`|**Criar**|Centraliza `resource_path()` e leitura de planilhas|
|Identificação de mapa|`map.py`|**Criar**|OCR + fuzzy match contra `maps.txt`|
|Config de captura|`config.json`|**Criar**|Externaliza coordenadas hardcoded do `screenshot.py`|
|Fonte de heróis|`heroes_roles.json`|**Criar**|Lista canônica de heróis por role; substitui dicionário interno do `favoriteHero.py`|
|Lista de mapas|`maps.txt`|**Criar**|Um mapa por linha, em inglês, incluindo Neon Junction|
|Stats de MetaStrength|`stats_inputs.csv`|**Verificar e integrar**|Já criado externamente; formato a confirmar antes de usar|
|Legado mantido|`heroscreenshot.py`|**Manter**|Não usado no pipeline; preservado para uso futuro|
|Spec do PyInstaller|`overwatch.spec`|**Modificar**|Remove `selenium`; mantém OCR (uso futuro próximo)|

### 2.2 Fluxo do sistema (atualizado)

```
[TAB+1 pressionado]
        │
        ├─► screenshot.executar()
        │       Lê config.json para coordenadas
        │       Salva print/full.png + recortes de heróis + print/map/map.png
        │
        ├─► comparar.executar()
        │       Template matching → lineup.txt
        │       (4 aliados, 5 inimigos)
        │
        ├─► map.executar()                        ← NOVO
        │       OCR de print/full.png (região do mapa)
        │       Fuzzy match contra maps.txt
        │       Salva mapa atual em current_map.txt
        │
        └─► choose_ow_hero.run_hero_ranking()
                Lê Roles.txt, {role}.txt, lineup.txt, current_map.txt
                Lê heroes ally.xlsx, heroes enemy.xlsx → dicionários Python
                Carrega MetaStrength do mapa atual (stats_inputs.csv)
                Calcula threat weights (w_e) para cada inimigo
                Para cada herói candidato:
                    S(h) = β_meta·m(h,mapa) + β_ctr·T_ctr(h) + β_syn·T_syn(h)
                Exclui heróis já presentes nos aliados
                Exibe ranking ordenado
```

### 2.3 Módulo utilitário `utils.py`

`resource_path()` estava duplicada em `choose_ow_hero.py`, `enemy_mult.py`, `updater.py` e `comparar.py`. `read_heroes_ally_data()` e `read_heroes_enemy_data()` estavam duplicadas em `choose_ow_hero.py` e `enemy_mult.py`.

Todas essas funções migram para `utils.py`. Todos os outros módulos passam a importar de lá.

```python
# utils.py
import sys, os, pandas as pd

def resource_path(relative_path: str) -> str:
    """Resolve caminho tanto no modo .py quanto no .exe (PyInstaller)."""
    base = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base, relative_path)

def read_heroes_ally_data() -> pd.DataFrame:
    path = resource_path("heroes ally.xlsx")
    return pd.read_excel(path, index_col=0)

def read_heroes_enemy_data() -> pd.DataFrame:
    path = resource_path("heroes enemy.xlsx")
    return pd.read_excel(path, index_col=0)
```

### 2.4 Configuração de captura `config.json`

As coordenadas de recorte de `screenshot.py` estavam hardcoded para 2K. Elas saem para `config.json`:

```json
{
  "2k": {
    "map_region": { "left": 2104, "top": 38, "width": 269, "height": 50 },
    "base_resolution": { "width": 2560, "height": 1440 }
  },
  "720p": {
    "map_region": { "left": 890, "top": 17, "width": 113, "height": 21 },
    "base_resolution": { "width": 1280, "height": 720 }
  }
}
```

O `screenshot.py` detecta a resolução ativa e lê a entrada correta do JSON. Para adicionar uma nova resolução, basta adicionar uma chave ao JSON sem tocar no código.

---

## 3. Modelo Matemático

### 3.1 Notação

|Símbolo|Significado|
|---|---|
|`H`|conjunto de heróis (~52+)|
|`p`|patch atual (Season 2 · 2026)|
|`k`|mapa atual (identificado pelo `map.py`)|
|`wr(h,k)`, `pr(h,k)`|winrate e pickrate do herói `h` no mapa `k`|
|`m(h,k)`|**MetaStrength** de `h` no mapa `k`|
|`C(h,e)`|counter de `h` contra `e` (lido das planilhas)|
|`Y(h,a)`|sinergia de `h` com aliado `a` (lido das planilhas)|
|`A`, `E`|aliados identificados, inimigos identificados|
|`w_e`|peso de ameaça do inimigo `e` (threat weighting)|
|`λ`|intensidade do threat weighting|
|`β_meta`, `β_ctr`, `β_syn`|pesos dos termos no score final|
|`S(h)`|score final do herói candidato `h`|
|`pr(h,k)`|pickrate do herói `h` no mapa `k`|
|`pr_neutra(role)`|pickrate esperada se todos os heróis da role fossem igualmente jogados|
|`κ_base`, `κ_eff(h,k)`|pseudo-contagem base e ajustada por pickrate relativa|

### 3.2 MetaStrength `m(h, k)` — força no mapa

MetaStrength quantifica o quão forte um herói é **no mapa atual da partida**. É calculado a partir de winrate e pickrate públicos, segmentados por mapa. O cálculo ocorre uma única vez no início do pipeline (ao carregar `stats_inputs.csv`) e os valores ficam disponíveis como dicionário `{(herói, mapa): valor}`.

**Passo 1 — Winrate ajustado (shrinkage):**

$$wr_{adj}(h,k) = \frac{g(h,k) \cdot wr(h,k) + \kappa \cdot \overline{wr}(k)}{g(h,k) + \kappa}$$

- `g(h,k)` = número de jogos do herói `h` no mapa `k`
- `wr_bar(k)` = média dos winrates de todos os heróis no mapa `k`
- `κ` = pseudo-contagem; heróis com pouca amostra são puxados para a média (recomendado: `κ = 100`)

O shrinkage evita que heróis raramente jogados em um mapa recebam MetaStrength inflado ou deflado por amostra pequena.

#### Pickrate neutra por role e ajuste de `κ`

Nem todas as roles têm o mesmo número de heróis nem o mesmo número de slots por time. Isso significa que a pickrate "esperada" se todos os heróis fossem igualmente fortes é diferente por role — e ignorar isso faz com que heróis de roles com pool grande (DPS) pareçam sempre sub-representados em relação a roles com pool pequeno (Suporte).

**Pickrate neutra** (`pr_neutra`) é a pickrate que um herói teria se todos os heróis da role fossem escolhidos com igual probabilidade:

$$pr_neutra(role) = \frac{slots_por_time(role)}{|heroes(role)|}$$

Com base no `heroes_roles.json` atual:

| Role     | Heróis no pool | Slots por time | `pr_neutra`         |
| -------- | -------------- | -------------- | ------------------- |
| **DPS**  | 24             | 2              | 2 ÷ 24 ≈ **8,33%**  |
| **TANK** | 14             | 1              | 1 ÷ 14 ≈ **7,7%**   |
| **SUP**  | 14             | 2              | 2 ÷ 14 ≈ **14,28%** |

> Isso explica por que um DPS com 20% de pickrate já é altamente dominante, enquanto um Suporte a 20% está abaixo do que se esperaria de um herói médio da role. Comparar pickrates entre roles sem esse contexto é enganoso.

**Shrinkage ajustado por pickrate relativa:**

Heróis com `pr(h,k)` muito abaixo de `pr_neutra(role(h))` têm amostra proporcionalmente menor naquele mapa — seu winrate pode ser ruído. Para esses heróis, o `κ` efetivo é ampliado, puxando o MetaStrength ainda mais para a média da role:

$$\kappa_{eff}(h,k) = \kappa_{base} \cdot \frac{pr_neutra(role(h))}{\max(pr(h,k),; \epsilon)}$$

- Se `pr(h,k) = pr_neutra` → `κ_eff = κ_base` (sem ajuste)
- Se `pr(h,k) < pr_neutra` → `κ_eff > κ_base` (mais conservador)
- Se `pr(h,k) > pr_neutra` → `κ_eff < κ_base` (mais confiante)
- `ε` é um mínimo para evitar divisão por zero (sugerido: `0.001`)

A fórmula de shrinkage passa a ser:

$$wr_{adj}(h,k) = \frac{g(h,k) \cdot wr(h,k) + \kappa_{eff}(h,k) \cdot \overline{wr}(k)}{g(h,k) + \kappa_{eff}(h,k)}$$

**Implementação — cálculo de `κ_eff`:**

```python
import json

def get_role_neutral_pickrates(heroes_roles_path: str) -> dict[str, float]:
    """
    Lê heroes_roles.json e retorna {role: pr_neutra}.
    Slots por time: DPS=2, TANK=1, SUP=2.
    """
    SLOTS = {"DPS": 2, "TANK": 1, "SUP": 2}
    with open(heroes_roles_path, encoding="utf-8") as f:
        data = json.load(f)
    return {
        role: SLOTS[role] / len(heroes)
        for role, heroes in data["heroes"].items()
    }

def get_hero_role(hero: str, heroes_roles_path: str) -> str | None:
    with open(heroes_roles_path, encoding="utf-8") as f:
        data = json.load(f)
    for role, heroes in data["heroes"].items():
        if hero in heroes:
            return role
    return None

def kappa_eff(hero: str, pickrate: float, pr_neutral: dict,
              kappa_base: float = 100.0, eps: float = 0.001) -> float:
    role = get_hero_role(hero, ...)
    if role is None:
        return kappa_base
    pr_n = pr_neutral.get(role, kappa_base)
    return kappa_base * (pr_n / max(pickrate, eps))
```

**Parâmetros relacionados adicionados à tabela de configuração:**

|Parâmetro|Valor inicial|Ajustar se|
|---|---|---|
|`κ_base`|100.0|Substituído por `κ_eff` por herói|
|`ε`|0.001|Heróis com pickrate zerada causam valores extremos|
|`SLOTS`|`{DPS:2, TANK:1, SUP:2}`|Blizzard mudar formato de composição|

**Passo 2 — Normalização e clamp:**

$$m(h,k) = \text{clamp}!\left(\frac{wr_{adj}(h,k) - \overline{wr}(k)}{\sigma_{wr}(k)},; -M_{max},; +M_{max}\right)$$

- `σ_wr(k)` = desvio-padrão dos `wr_adj` no mapa `k`
- `Mmax` = limite de outliers (recomendado: `3.0`, ou seja, ±3 desvios)
- Resultado em unidades de desvio-padrão, centralizado em zero

**Passo 3 — Escala para unidades do score:**

$$m_{scaled}(h,k) = \alpha \cdot m(h,k)$$

- `α` alinha a magnitude do MetaStrength com os valores de `C` e `Y`
- Valor inicial sugerido: `α = 1.0`; ajustar conforme validação empírica

**Implementação — carregamento no início do programa:**

```python
# No início de choose_ow_hero.run_hero_ranking()
import utils, pandas as pd, numpy as np

def load_meta_strength(mapa_atual: str, kappa: float = 100.0,
                       mmax: float = 3.0, alpha: float = 1.0) -> dict:
    """
    Lê stats_inputs.csv e retorna dicionário {herói: MetaStrength}
    para o mapa atual. Heróis sem dados retornam 0.0.
    """
    df = pd.read_csv(utils.resource_path("stats_inputs.csv"))
    df_mapa = df[df["map"] == mapa_atual].copy()

    if df_mapa.empty:
        return {}  # mapa sem dados → MetaStrength zero para todos

    wr_bar = df_mapa["winrate"].mean()
    df_mapa["wr_adj"] = (
        (df_mapa["games"] * df_mapa["winrate"] + kappa * wr_bar)
        / (df_mapa["games"] + kappa)
    )

    sigma = df_mapa["wr_adj"].std()
    if sigma == 0:
        return {row["hero"]: 0.0 for _, row in df_mapa.iterrows()}

    result = {}
    for _, row in df_mapa.iterrows():
        z = (row["wr_adj"] - wr_bar) / sigma
        z_clamped = float(np.clip(z, -mmax, mmax))
        result[row["hero"]] = alpha * z_clamped

    return result
```

### 3.3 Counter score `T_ctr(h)` — com threat weighting

O threat weighting substitui o multiplicador `(total/4)+1` anterior. Em vez de calcular o multiplicador de forma independente para cada inimigo (relendo planilhas repetidamente), o peso de ameaça é derivado diretamente da matriz de counters já carregada:

**Peso de ameaça do inimigo `e`:**

$$w_e = 1 + \lambda \cdot \sum_{a \in A} C(e, a)$$

- Soma quanto o inimigo `e` countera cada aliado `a`
- Se `e` countera vários aliados → `w_e > 1` (inimigo perigoso)
- Se `e` é countered pelos aliados → `w_e < 1` (inimigo menos ameaçador)
- `λ` controla a intensidade; valor inicial sugerido: `λ = 0.25`
- `w_e` é clamped para não ficar negativo: `w_e = max(0.1, w_e)`

**Termo de counter do herói candidato:**

$$T_{ctr}(h) = \sum_{e \in E} w_e \cdot C(h, e)$$

### 3.4 Sinergia score `T_syn(h)`

Sem alterações em relação ao modelo atual, exceto pela remoção do valor `-11` da diagonal (tratado como regra de exclusão, não como dado de sinergia):

$$T_{syn}(h) = \sum_{a \in A} Y(h, a) \cdot \beta_{syn}$$

O peso `β_syn = 0.65` é mantido do modelo anterior.

A diagonal da planilha de sinergia não é lida. Antes do scoring, qualquer célula diagonal é ignorada (não somada). Isso remove o hack do `-11` sem alterar as planilhas.

### 3.5 Score final `S(h)`

$$S(h) = \beta_{meta} \cdot m_{scaled}(h, k) + \beta_{ctr} \cdot T_{ctr}(h) + T_{syn}(h)$$

- `β_meta` = peso do MetaStrength; valor inicial: `1.0`
- `β_ctr` = peso do counter term; valor inicial: `1.0` (o threat weighting interno já pondera)
- `T_syn` já carrega `β_syn = 0.65` embutido
- Se `h ∈ A` (herói já está no time aliado): herói **excluído do ranking** (regra rígida, não penalidade)

**Parâmetros iniciais sugeridos:**

|Parâmetro|Valor inicial|Ajustar se|
|---|---|---|
|`κ_base`|100.0|Base para cálculo de `κ_eff`; aumentar se MetaStrength ainda instável|
|`ε`|0.001|Heróis com pickrate zerada causam `κ_eff` extremo|
|`SLOTS`|`{DPS:2, TANK:1, SUP:2}`|Blizzard mudar formato de composição|
|`Mmax`|3.0|Outliers dominam o ranking|
|`α`|1.0|MetaStrength parece sub/superponderado vs counters|
|`λ`|0.25|Threat weighting parece exagerado ou inexistente|
|`β_meta`|1.0|MetaStrength domina ou não aparece no resultado|
|`β_ctr`|1.0|Counter term domina ou some|
|`β_syn`|0.65|Mantido do modelo anterior|

### 3.6 Leitura das planilhas — conversão interna

As planilhas `heroes ally.xlsx` e `heroes enemy.xlsx` continuam no formato atual (editadas à mão, matriz quadrada). O programa as converte para dicionários Python logo no início do pipeline:

```python
# Em choose_ow_hero.py (chamado uma única vez)
ally_df  = utils.read_heroes_ally_data()
enemy_df = utils.read_heroes_enemy_data()

ally_dict  = ally_df.to_dict()   # {herói_linha: {herói_coluna: valor}}
enemy_dict = enemy_df.to_dict()
```

A partir daí, todo o scoring opera sobre dicionários em memória. Isso elimina as releituras de disco que ocorriam em cada chamada de `enemy_mult.executar()`.

---

## 4. Fontes de Dados

### 4.1 `stats_inputs.csv` — MetaStrength

Arquivo já criado externamente. O formato exato deve ser verificado antes da integração. Espera-se pelo menos as colunas abaixo; adaptar o carregamento se o CSV diferir:

|Coluna|Tipo|Descrição|
|---|---|---|
|`hero`|string|Nome do herói (deve bater com nomes nas planilhas)|
|`map`|string|Nome do mapa em inglês (deve bater com `maps.txt`)|
|`winrate`|float|Winrate decimal (ex: `0.52` para 52%)|
|`pickrate`|float|Pickrate decimal|
|`games`|int|Número de partidas na amostra|

> **Antes de integrar:** ler o arquivo e confirmar nomes de colunas, codificação e separador. O programa que gera o CSV foi criado após a última atualização da especificação — verificar consistência de nomes de heróis e mapas.

### 4.2 `heroes_roles.json` — fonte canônica de heróis

Elimina o dicionário hardcoded em `favoriteHero.py`. Toda consulta de "quais heróis existem" ou "qual a role de X" passa por este arquivo:

```json
{
  "version": "1.7",
  "patch": "Season 2 · 2026",
  "heroes": {
    "DPS": [
      "Ashe", "Bastion", "Cassidy", "Echo", "Genji", "Hanzo",
      "Junkrat", "Mei", "Pharah", "Reaper", "Shion", "Sojourn",
      "Soldier: 76", "Sombra", "Symmetra", "Torbjörn", "Tracer",
      "Venture", "Widowmaker"
    ],
    "TANK": [
      "D.Va", "Doomfist", "Hazard", "Junker Queen", "Mauga",
      "Orisa", "Ramattra", "Reinhardt", "Roadhog", "Sigma",
      "Winston", "Wrecking Ball", "Zarya"
    ],
    "SUP": [
      "Ana", "Baptiste", "Brigitte", "Illari", "Juno",
      "Kiriko", "Lifeweaver", "Lúcio", "Mercy", "Moira",
      "Zenyatta"
    ]
  }
}
```

> Sempre que um novo herói for adicionado ao jogo, apenas este arquivo precisa ser atualizado (além de adicionar a imagem de template na pasta `heroes/`).

### 4.3 `maps.txt` — lista de mapas

Um mapa por linha, em inglês. Inclui Neon Junction (mapa novo da Season 2):

```
Antarctic Peninsula
Blizzard World
Busan
Circuit Royal
Colosseo
Dorado
Eichenwalde
Esperança
Havana
Hollywood
Ilios
Junkertown
King's Row
Lijiang Tower
Midtown
Nepal
New Junk City
New Queen Street
Neon Junction
Numbani
Oasis
Paraíso
Rialto
Route 66
Samoa
Shambali Monastery
Suravasa
Throne of Anubis
Watchpoint: Gibraltar
```

---

## 5. Novos Módulos

### 5.1 `map.py` — identificação automática de mapa

Responsabilidade: capturar a região do nome do mapa na tela, aplicar OCR, e identificar o mapa mais provável via fuzzy matching contra `maps.txt`. Salva o resultado em `current_map.txt` para ser lido pelo `choose_ow_hero.py`.

**Coordenadas de captura (2K):** `left: 2104, top: 38, width: 269, height: 50` Para outras resoluções, escalar proporcionalmente via `config.json`.

**Algoritmo:**

1. Recortar a região do mapa a partir de `print/full.png` (já capturado pelo `screenshot.py`)
2. Pré-processar a imagem: escala de cinza + threshold para melhorar legibilidade do OCR
3. Rodar Tesseract via `pytesseract.image_to_string()` com `lang='eng'`
4. O texto extraído pode estar incompleto: ex. `"MPETITIVE - ROUTE 66"` em vez de `"COMPETITIVE - ROUTE 66"`
5. Gerar **todas as combinações de substrings** do texto extraído
6. Para cada combinação, calcular similaridade via `rapidfuzz` contra cada nome em `maps.txt`
7. Retornar o mapa com maior score de similaridade

```python
# map.py — estrutura principal
import pytesseract, itertools
from PIL import Image
from rapidfuzz import fuzz
import utils

def load_maps() -> list[str]:
    path = utils.resource_path("maps.txt")
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def extract_text_from_region(img_path: str, region: dict) -> str:
    img = Image.open(img_path).crop((
        region["left"], region["top"],
        region["left"] + region["width"],
        region["top"] + region["height"]
    ))
    img = img.convert("L")  # escala de cinza
    return pytesseract.image_to_string(img, lang="eng").strip()

def get_all_substrings(text: str) -> list[str]:
    """Gera todas as combinações de palavras do texto extraído."""
    words = text.split()
    combos = []
    for r in range(1, len(words) + 1):
        for combo in itertools.combinations(words, r):
            combos.append(" ".join(combo))
    return combos

def identify_map(ocr_text: str, map_list: list[str]) -> tuple[str, float]:
    """Retorna (nome_do_mapa, score_de_confiança)."""
    substrings = get_all_substrings(ocr_text)
    best_map, best_score = "", 0.0

    for mapa in map_list:
        for sub in substrings:
            score = fuzz.ratio(sub.upper(), mapa.upper())
            if score > best_score:
                best_score = score
                best_map = mapa

    return best_map, best_score

def executar():
    """Ponto de entrada chamado pelo pipeline principal."""
    import json, os

    config = json.load(open(utils.resource_path("config.json")))
    # detecta resolução a partir do full.png
    from PIL import Image as PILImage
    full = PILImage.open("print/full.png")
    res_key = "2k" if full.width >= 2000 else "720p"
    region = config[res_key]["map_region"]

    ocr_text = extract_text_from_region("print/full.png", region)
    map_list = load_maps()
    mapa, score = identify_map(ocr_text, map_list)

    with open("current_map.txt", "w", encoding="utf-8") as f:
        f.write(mapa)

    print(f"[map.py] Mapa identificado: '{mapa}' (score={score:.1f})")
```

**`current_map.txt`** é criado/sobrescrito a cada execução do pipeline. Se o OCR falhar ou a confiança for muito baixa (ex: `score < 50`), o arquivo recebe `"UNKNOWN"` e o MetaStrength retorna 0 para todos os heróis (sem quebrar o ranking).

---

## 6. Correções e Refatorações

### 6.1 Bugs corrigidos

**Typos em nomes de arquivo de template:**

- `heroes/2k/sup/Illarri.png` → renomear para `Illari.png`
- `heroes/2k/tank/Rroadhog.png` → renomear para `Roadhog.png`

Esses typos causavam falha silenciosa no matching quando o nome do arquivo era comparado ao nome do herói no dicionário.

**Shion sem entrada em `favoriteHero.py`:**

- Adicionado `"Shion"` à categoria `DPS` do `heroes_roles.json`
- `favoriteHero.py` passa a carregar o dicionário de `heroes_roles.json` em vez de ter a lista hardcoded
- Templates `heroes/2k/dps/Shion.png` já existem; verificar se há versão 720p

### 6.2 Bugs para corrigir

**Leitura invertida de `lineup.txt` em `enemy_mult.py`:**

```python
# choose_ow_hero.py — perspectiva do JOGADOR
allies  = lines[:4]   # aliados do jogador
enemies = lines[4:9]  # inimigos do jogador

# enemy_mult.py — perspectiva DO HERÓI INIMIGO (invertida intencionalmente)
# O módulo avalia quanto o herói inimigo countera o time aliado.
# Por isso, do ponto de vista do herói inimigo:
#   - "seus inimigos" = os aliados do jogador (linhas 0-3)
#   - "seus aliados"  = os inimigos do jogador (linhas 4-8)
opponents_of_enemy = lines[:4]  # quem o herói inimigo enfrenta = aliados do jogador
teammates_of_enemy = lines[4:9] # time do herói inimigo = inimigos do jogador
```

A inversão é intencional e necessária para calcular o multiplicador corretamente. Os nomes de variáveis devem ser renomeados de `allies`/`enemies` para `opponents_of_enemy`/`teammates_of_enemy` para tornar isso explícito.

**Nota:** com a integração do threat weighting diretamente em `choose_ow_hero.py`, a necessidade de chamar `enemy_mult.executar()` separadamente é eliminada. O módulo `enemy_mult.py` pode ser simplificado ou mantido como utilitário.

### 6.3 Eliminação de duplicações — `utils.py` - deve ser corrigido

Funções duplicadas e seus destinos:

|Função|Estava em|Migra para|
|---|---|---|
|`resource_path()`|`choose_ow_hero.py`, `enemy_mult.py`, `updater.py`, `comparar.py`|`utils.py`|
|`read_heroes_ally_data()`|`choose_ow_hero.py`, `enemy_mult.py`|`utils.py`|
|`read_heroes_enemy_data()`|`choose_ow_hero.py`, `enemy_mult.py`|`utils.py`|

### 6.3 Cache de planilhas - deve ser corrigido

Problema: em modo prioritize, `enemy_mult.executar()` é chamado até 5 vezes (um por inimigo), relendo as planilhas do disco a cada chamada.

### 6.4 `overwatch.spec` - deve ser corrigido

- **Remover** `selenium` e todos os seus submódulos de `hiddenimports`
- **Manter** `pytesseract` e a pasta `ocr/` — o OCR será usado pelo `map.py` e potencialmente por outros módulos no futuro próximo
- Adicionar `map.py`, `utils.py`, `heroes_roles.json`, `maps.txt`, `config.json`, `stats_inputs.csv` ao bundle

### 6.5 `heroscreenshot.py e resolucao.py`

Arquivo legado mantido. Não faz parte do pipeline principal e não deve ser removido — reservado para uso futuro.

---

## 7. Plano de Implementação

### Fase 1 — Infraestrutura (sem mudar scoring)

1. Criar `utils.py` com `resource_path()`, `read_heroes_ally_data()`, `read_heroes_enemy_data()`
2. Substituir todas as ocorrências duplicadas nos outros módulos por `import utils`
3. Criar `heroes_roles.json` com todos os heróis (incluindo Shion)
4. Refatorar `favoriteHero.py` para carregar de `heroes_roles.json`
5. Criar `maps.txt` com todos os mapas em inglês (incluindo Neon Junction)
6. Criar `config.json` com coordenadas de captura por resolução
7. Refatorar `screenshot.py` para ler coordenadas do `config.json`
8. Remover `selenium` do `overwatch.spec`
9. Renomear `Illarri.png` → `Illari.png` e `Rroadhog.png` → `Roadhog.png`
10. Leitura invertida de `lineup.txt` em `enemy_mult.py`:
11. Cache de planilhas

### Fase 2 — Identificação de mapa

10. Criar `map.py` com OCR + fuzzy matching
11. Integrar `map.executar()` no pipeline de `main.py` (após `comparar`, antes de `choose_ow_hero`)
12. Testar com capturas reais de diferentes mapas; ajustar threshold de confiança

### Fase 3 — MetaStrength

13. Verificar formato real do `stats_inputs.csv` gerado externamente
14. Implementar `load_meta_strength()` em `choose_ow_hero.py`
15. Adicionar `m_scaled(h, k)` à fórmula de scoring
16. Renomear variáveis de `enemy_mult.py` (`opponents_of_enemy`, `teammates_of_enemy`)
17. Adicionar comentários explicando a perspectiva invertida

### Fase 4 — Threat Weighting e integração final

18. Implementar cálculo de `w_e` diretamente em `choose_ow_hero.py`
19. Eliminar releituras de planilhas do `enemy_mult.py`
20. Remover a diagonal de sinergia do cálculo (ignorar células `h == a`)
21. Atualizar `DOCUMENTACAO.md` com a nova arquitetura
22. Atualizar `requirements.txt` com as dependências corretas
23. Atualizar `version.txt` e version.json para `1.7` e adicionar descrição em version.json

---

## 8. Dependências

### 8.1 `requirements.txt` (atualizado)

```
mss>=10.2.0
Pillow>=12.2.0
opencv-python>=4.13.0
numpy>=2.4.0
pandas>=2.0.0
openpyxl>=3.1.5
keyboard>=0.13.5
rapidfuzz>=3.14.5
unidecode>=1.4.0
pytesseract>=0.3.13
PyInstaller>=6.20.0
```

### 8.2 Dependência externa (binária)

|Componente|Localização|Uso|
|---|---|---|
|**Tesseract OCR**|`ocr/`|Leitura do nome do mapa em `map.py`; mantido no bundle|

### 8.3 Remoção

- `selenium` e todos os seus submódulos: **removidos** do `overwatch.spec`. Não há nenhum uso no código. A remoção reduz o executável em ~50 MB.