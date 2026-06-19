# Changelog — OWPick

Todas as mudanças relevantes de versão são documentadas aqui.

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

## [v1.1.0] — 2026-06 (implementação OWPick v2)

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

### choose_ow_hero.py — Modelo de scoring v2

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
