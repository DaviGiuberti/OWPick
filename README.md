# OWPick — Overwatch Best Picks

Ferramenta de recomendação automática de heróis para **Overwatch**. O programa captura a tela durante a fase de seleção de personagem, identifica os heróis aliados e inimigos por comparação de imagem, detecta o mapa atual via OCR e calcula qual herói você deveria jogar com base em dados de counters, sinergias e desempenho estatístico no mapa.

---

## Funcionalidades

- **Captura automática** da tela de seleção com hotkey global (`TAB+1`)
- **Captura da janela do jogo** (suporta multi-monitor e modo janela): localiza a janela do Overwatch e captura o retângulo do cliente; se a janela não for encontrada, cai automaticamente para o monitor primário
- **Identificação de heróis** por template matching (janela deslizante com correlação normalizada `TM_CCOEFF_NORMED`, robusta a brilho/HDR/highlight)
- **Suporte aos bans do Competitivo**: heróis banidos são identificados e removidos automaticamente do ranking (tratados como indisponíveis, igual aos heróis já no seu time)
- **Identificação automática do mapa** via OCR (Tesseract embutido) + fuzzy matching
- **Suporte a múltiplas resoluções**: 720p, 1080p e 2K, com escalonamento automático e escolha inteligente do banco de templates pelo tamanho do retrato

> ⚠️ **Somente resolução 16:9.** O OWPick só é compatível com telas/janelas na proporção **16:9** (ex.: 1280×720, 1920×1080, 2560×1440). **Não há suporte a ultrawide (21:9)** nem a outros formatos — a geometria de captura assume 16:9.
- **Ranking de heróis** ordenado por pontuação combinada de MetaStrength + counter + sinergia
- **Threat Weighting integrado**: amplifica automaticamente inimigos perigosos e fortes no mapa atual
- **Ranking de ameaças inimigas**: exibido antes do ranking de heróis, ordenado por periculosidade
- **Gerenciamento de favoritos**: configure quais heróis você joga em cada função
- **Seleção de Role**: DPS, Suporte, Tank ou Fila Aberta
- **Auto-atualização**: verifica e aplica novas versões automaticamente via GitHub Releases

---

## Estrutura do Projeto

```
OWPick/
├── src/owpick/              # Pacote do aplicativo (3 camadas)
│   ├── __main__.py          # Ponto de entrada (python -m owpick)
│   ├── pipeline.py          # Casos de uso (run_pipeline → ranking)
│   ├── paths.py             # Dados do usuário/cache (%APPDATA% / %LOCALAPPDATA%)
│   ├── settings.py          # Settings tipado/validado (settings.json)
│   ├── i18n.py              # Strings de UI por idioma (PT-BR/EN)
│   ├── log.py               # Logging estruturado (arquivo rotativo + console)
│   ├── core/                # Domínio puro (zero I/O)
│   │   ├── heroes.py        # Heróis/mapas + aliases + normalização de nomes
│   │   ├── resolution.py    # Matemática de resolução e recorte
│   │   ├── models.py        # Dataclasses de domínio (Hero, Lineup, ...)
│   │   ├── scoring.py       # MetaStrength + threat + ranking + presets
│   │   └── ports.py         # Protocolos (ScreenCapturer, MetaSource, ...)
│   ├── infra/               # I/O: captura, matching, OCR, dados, updater
│   │   ├── capture.py       # Captura (janela do jogo/mss) + recorte em memória
│   │   ├── matching.py      # Template matching para identificar heróis
│   │   ├── map_detect.py    # OCR + fuzzy match do nome do mapa
│   │   ├── ocr_backends.py  # Backends de OCR (Tesseract padrão)
│   │   ├── datasource.py    # Leitura/cache das matrizes CSV, stats e layout
│   │   ├── validation.py    # Validação de matrizes/stats/templates
│   │   ├── stats_update.py  # Atualização das stats de meta pelo app
│   │   ├── storage.py       # Persistência dos arquivos do usuário
│   │   ├── resources.py     # resource_path + identidade no Windows
│   │   └── updater.py       # Auto-atualização via GitHub (rollback seguro)
│   └── ui/                  # Console: menus, hotkeys, formatação
│       ├── console.py       # Menu principal e hotkey de captura
│       ├── roles.py         # Seleção de função (role)
│       ├── favorites.py     # Gerenciamento de heróis favoritos
│       ├── hotkey.py        # Hotkey configurável (captura em tempo real)
│       ├── sim.py           # Modo manual/simulação (sem captura)
│       ├── profiles.py      # Múltiplos perfis
│       └── ranking_view.py  # Formatação rich do ranking no console
│
├── tools/                   # Ferramentas de desenvolvimento (fora do app)
│   ├── coletar_stats.py     # Scraper externo → data/stats_inputs.csv
│   ├── xlsx_to_csv.py       # Converte as matrizes .xlsx (edição) → .csv (runtime)
│   ├── enemy_mult.py        # Diagnóstico de threat weight (consumidor do core)
│   ├── bump.py              # Sincroniza version.txt + CHANGELOG p/ release
│   └── resolucao.py         # Seletor visual de coordenadas
│
├── assets/                  # Recursos imutáveis empacotados no exe
│   ├── heroes/              # Templates: 720p|2k/dps|sup|tank/ + bans/
│   ├── ocr/                 # Tesseract OCR embutido (tesseract.exe + tessdata/)
│   ├── i18n/                # Strings de UI (pt-BR.json, en.json)
│   └── icone.ico            # Ícone do app
│
├── data/                    # Dados do modelo
│   ├── synergies.csv        # Matriz de sinergias (lida em runtime)
│   ├── counters.csv         # Matriz de counters (lida em runtime)
│   ├── heroes ally.xlsx     # Fonte de EDIÇÃO das sinergias (não empacotada)
│   ├── heroes enemy.xlsx    # Fonte de EDIÇÃO dos counters (não empacotada)
│   ├── layouts/ow_hero_select.json  # Layout de captura versionado
│   └── stats_inputs.csv     # Winrate/pickrate por mapa (fonte do MetaStrength)
│
├── packaging/               # Build e distribuição
│   ├── overwatch.spec       # Configuração do PyInstaller
│   ├── installer.iss        # Script do instalador (Inno Setup)
│   └── build.bat            # Build completo: PyInstaller → zip do updater → instalador
│
├── tests/                   # Testes (pytest) + fixtures golden de matching
├── version.txt              # Versão local (fonte única)
├── version.json             # Versão remota para update
└── pyproject.toml           # Metadados, dependências (uv) e config de tooling
```

---

## Instalação (a partir do código-fonte)

### Pré-requisitos

- Python 3.11+
- A pasta `assets/ocr/` com o Tesseract já está inclusa no repositório — nenhuma instalação adicional de OCR é necessária

### Passos

```bash
# 1. Clone o repositório
git clone https://github.com/DaviGiuberti/OWPick.git
cd OWPick

# 2. Crie e ative o ambiente virtual
python -m venv .venv
.venv\Scripts\activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Execute o programa
python src\owpick\__main__.py
```

> **Windows**: a biblioteca `keyboard` requer execução com privilégios de administrador para capturar hotkeys globais.

---

## Uso

### Iniciando o Programa

```bash
python src\owpick\__main__.py
```

Na primeira execução, o programa solicitará:
1. **Sua Role** (DPS, Tank, Suporte ou Fila Aberta)
2. **Seus heróis favoritos** (quais personagens você joga em cada função)

### Hotkey Principal

Com o jogo aberto na **tela de seleção de heróis**, pressione (padrão;
configurável na opção 5 do menu):

```
TAB + 1
```

O programa irá:
1. Capturar a tela automaticamente
2. Identificar os heróis aliados e inimigos (e os banidos, no Competitivo)
3. Identificar o mapa atual
4. Calcular e exibir o ranking no console (heróis banidos são omitidos)

### Exemplo de Saída

```
>>> Capturando a tela...
>>> Comparando os prints com os heróis do Overwatch...
>>> Identificando o mapa atual...
[map_detect.py] Mapa identificado: 'Route 66' (score=100.0)
>>> Executando escolha de herói...

Role selecionada: DPS
Heróis disponíveis: Tracer, Genji, Sojourn, Cassidy

Aliados: Ana, Reinhardt, Mercy, Zenyatta
Inimigos: Roadhog, Genji, Pharah, Moira, Orisa
Mapa atual: Route 66

--- Ranking de Ameaças Inimigas ---
  1º Pharah              Ameaça: 1.85
  2º Roadhog             Ameaça: 1.60
  3º Genji               Ameaça: 1.40
  4º Orisa               Ameaça: 1.20
  5º Moira               Ameaça: 1.10
------------------------------------

==========================================================================
RANK  | HERO               |    META |      CTR |    SYN |    TOTAL
==========================================================================
1     | Cassidy            |    0.80 |    12.50 |   5.85 |    19.15
2     | Sojourn            |    1.20 |    10.20 |   7.15 |    18.55
3     | Tracer             |    0.50 |     8.00 |   6.50 |    15.00
4     | Genji              |   -0.30 |     7.30 |   4.55 |    11.55
--------------------------------------------------------------------------
```

### Comandos do Menu

| Tecla | Ação |
|---|---|
| `2` + ENTER | Alterar Role/Função |
| `3` + ENTER | Adicionar/remover heróis favoritos |
| `4` + ENTER | Atualizar as stats de meta (avançado; requer Playwright) |
| `5` + ENTER | Configurar a hotkey de captura |
| `6` + ENTER | Ligar/desligar a explicação do ranking |
| `7` + ENTER | Perfis (role + favoritos + preset de pesos + tier) |
| `sim ...` + ENTER | Simular sem captura (ex.: `sim mapa=Ilios inimigos=Tracer,Winston aliados=Mei`) |
| `update` + ENTER | Aplicar uma atualização pendente (quando avisada no boot) |
| `exit` + ENTER | Encerrar o programa |

---

## Instalador (usuário final)

A versão pronta para uso está disponível na página de [Releases do GitHub](https://github.com/DaviGiuberti/OWPick/releases).

**Versão atual**: `1.2.0`

Para instalar:
1. Baixe o arquivo **`OWPick Installer.exe`**
2. Execute o instalador e siga os passos (não requer privilégios de administrador)
3. Abra o **OWPick** pelo atalho do Menu Iniciar ou da Área de Trabalho

O programa é instalado em `%LOCALAPPDATA%\Programs\OWPick`. Python, dependências e Tesseract OCR já estão embutidos — nenhuma instalação adicional é necessária. A verificação de atualização roda em segundo plano no boot (sem travar a inicialização); havendo versão nova, o programa avisa e aplica a atualização de forma segura, com rollback automático caso a cópia falhe (você nunca fica sem app).

> O arquivo `OWPick_v1.2.0.zip` também presente na Release é o pacote consumido pelo sistema de auto-atualização — usuários não precisam baixá-lo manualmente.

---

## Arquitetura

O sistema opera em um **pipeline em memória** acionado pela hotkey de captura
(nenhum arquivo intermediário é escrito fora do modo `--debug`):

```
[hotkey de captura]
   │
   ▼
infra/capture.py     ← Captura a janela do jogo (ou o monitor primário) e recorta
   │                   em memória: retratos (4 variações de perk) + 5 slots de ban
   │  CaptureResult
   ▼
infra/matching.py    ← Template matching (cv2, TM_CCOEFF_NORMED) com limiar de
   │                   confiança por slot          [em paralelo com o OCR ↓]
infra/map_detect.py  ← OCR (Tesseract) + fuzzy match (aliases PT-BR) → mapa
   │  Lineup + BanList + MapDetection
   ▼
core/scoring.py      ← MetaStrength + Threat Weighting + Sinergia → ranking
   │                    (pesos do preset ativo; explicabilidade opcional)
   ▼
ui/ranking_view.py   ← Tabela rich no console
        ├── [Ranking de Ameaças Inimigas]
        └── [Ranking de Heróis Recomendados]
```

O menu e os hotkeys rodam em **threads separadas**, permitindo que o pipeline seja executado sem bloquear a interface. O OCR do mapa roda **em paralelo** ao matching dos heróis.

---

## Tecnologias Utilizadas

| Tecnologia | Uso |
|---|---|
| **Python 3.11** | Linguagem principal |
| **MSS** | Captura de tela de alta performance |
| **Pillow (PIL)** | Manipulação e crop de imagens, pré-processamento para OCR |
| **OpenCV (cv2)** | Template matching (`matchTemplate`, TM_CCOEFF_NORMED) e redimensionamento |
| **NumPy** | Arrays numéricos do matching |
| **Pandas** | Leitura dos CSVs de counters, sinergias e stats por mapa |
| **keyboard** | Hotkeys globais funcionando fora do foco da janela |
| **pytesseract + Tesseract OCR** | Identificação do nome do mapa via OCR |
| **rapidfuzz** | Fuzzy matching do mapa (OCR) e da busca de heróis por nome |
| **rich** | Console rico: tabela do ranking, painel de ameaças, spinner |
| **urllib** | Download do pacote de atualização |
| **PyInstaller** | Empacotamento em `.exe` (one-folder) |
| **Inno Setup 6** | Instalador único (`OWPick Installer.exe`) — ferramenta externa de build, não é dependência Python |

---

## Aviso sobre Termos de Serviço (leia antes de usar)

O OWPick é um **observador passivo**: ele apenas **tira print da tela** e mostra
o resultado no seu terminal. Por design, ele **nunca**:

- injeta código, lê a memória ou faz hook do processo do Overwatch;
- desenha overlay sobre o jogo (não há e não haverá overlay — é só um terminal);
- automatiza mouse/teclado dentro do jogo (a hotkey global só *detecta* que você
  a pressionou; nada é enviado ao jogo).

Ainda assim, **ferramentas externas de terceiros são uma área cinzenta dos Termos
de Serviço** do Overwatch. **O uso é por sua conta e risco.** O autor não se
responsabiliza por eventuais penalidades aplicadas pela publicadora do jogo.

> ℹ️ Detalhes dessa postura estão documentados em
> [`DOCUMENTACAO.md`](DOCUMENTACAO.md) como restrição permanente de arquitetura.

---

## Licença

O código-fonte é de autoria de **Davi Giuberti**. Entre em contato com o autor para informações sobre uso e distribuição.
