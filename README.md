# OWPick — Overwatch Best Picks

Ferramenta de recomendação automática de heróis para **Overwatch**. O programa captura a tela durante a fase de seleção de personagem, identifica os heróis aliados e inimigos por comparação de imagem, detecta o mapa atual via OCR e calcula qual herói você deveria jogar com base em dados de counters, sinergias e desempenho estatístico no mapa.

---

## Funcionalidades

- **Captura automática** da tela de seleção com hotkey global (`TAB+1`)
- **Identificação de heróis** por template matching (janela deslizante com MAE normalizado)
- **Suporte aos bans do Competitivo**: heróis banidos são identificados e removidos automaticamente do ranking (tratados como indisponíveis, igual aos heróis já no seu time)
- **Identificação automática do mapa** via OCR (Tesseract embutido) + fuzzy matching
- **Suporte a múltiplas resoluções**: 720p, 1080p e 2K, com escalonamento automático e escolha inteligente do banco de templates pelo tamanho do retrato
- **Ranking de heróis** ordenado por pontuação combinada de MetaStrength + counter + sinergia
- **Threat Weighting integrado**: amplifica automaticamente inimigos perigosos e fortes no mapa atual
- **Ranking de ameaças inimigas**: exibido antes do ranking de heróis, ordenado por periculosidade
- **Gerenciamento de favoritos**: configure quais heróis você joga em cada função
- **Seleção de Role**: DPS, Suporte, Tank ou Fila Aberta
- **Auto-atualização**: verifica e aplica novas versões automaticamente via GitHub Releases

---

## Estrutura do Projeto

```
Overwatch-Best-Picks/
├── main.py                  # Ponto de entrada — menu e hotkeys
├── screenshot.py            # Captura e recorte da tela do jogo
├── comparar.py              # Template matching para identificar heróis
├── map.py                   # OCR + fuzzy match do nome do mapa
├── choose_ow_hero.py        # Cálculo e exibição do ranking de heróis
├── utils.py                 # Fonte única de dados: heróis, mapas, planilhas, utilitários
├── enemy_mult.py            # Utilitário de diagnóstico de threat weight
├── favoriteHero.py          # Gerenciamento de heróis favoritos
├── roles.py                 # Seleção de função (role)
├── updater.py               # Auto-atualização via GitHub
├── coletar_stats.py         # Scraper externo para atualizar stats_inputs.csv
├── resolucao.py             # [Utilitário dev] Seletor visual de coordenadas
├── heroscreenshot.py        # [Legado] Script antigo de screenshot
│
├── heroes ally.xlsx         # Planilha de sinergias entre heróis
├── heroes enemy.xlsx        # Planilha de counters entre heróis
├── stats_inputs.csv         # Winrate/pickrate por mapa (fonte do MetaStrength)
├── config.json              # Coordenadas de captura do mapa por resolução
├── version.txt              # Versão local
├── version.json             # Versão remota para update
├── requirements.txt         # Dependências Python
├── overwatch.spec           # Configuração do PyInstaller
│
├── heroes/                  # Templates de imagem dos heróis
│   ├── 720p/dps|sup|tank/   # Retratos do lineup (TAB+1)
│   ├── 2k/dps|sup|tank/     # Retratos do lineup (TAB+1)
│   └── bans/                # Ícones 3D oficiais (reconhecimento de bans)
│
└── ocr/                     # Tesseract OCR embutido (tesseract.exe + tessdata/)
```

---

## Instalação (a partir do código-fonte)

### Pré-requisitos

- Python 3.11+
- A pasta `ocr/` com o Tesseract já está inclusa no repositório — nenhuma instalação adicional de OCR é necessária

### Passos

```bash
# 1. Clone o repositório
git clone https://github.com/DaviGiuberti/Overwatch-Best-Picks.git
cd Overwatch-Best-Picks

# 2. Crie e ative o ambiente virtual
python -m venv .venv
.venv\Scripts\activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Execute o programa
python main.py
```

> **Windows**: a biblioteca `keyboard` requer execução com privilégios de administrador para capturar hotkeys globais.

---

## Uso

### Iniciando o Programa

```bash
python main.py
```

Na primeira execução, o programa solicitará:
1. **Sua Role** (DPS, Tank, Suporte ou Fila Aberta)
2. **Seus heróis favoritos** (quais personagens você joga em cada função)

### Hotkey Principal

Com o jogo aberto na **tela de seleção de heróis**, pressione:

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
[map.py] Mapa identificado: 'Route 66' (score=100.0)
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
| `exit` + ENTER | Encerrar o programa |

---

## Executável (sem instalação)

A versão compilada e pronta para uso está disponível na página de [Releases do GitHub](https://github.com/DaviGiuberti/Overwatch-Best-Picks/releases).

**Versão atual**: `1.1.5`

Para usar o executável:
1. Baixe o arquivo `OWPick_v1.1.5.zip`
2. Extraia em qualquer pasta
3. Execute `OWPick.exe`

Nenhuma instalação adicional é necessária — Python, dependências e Tesseract OCR já estão embutidos no pacote. O programa verifica automaticamente por atualizações ao iniciar.

---

## Arquitetura

O sistema opera em um **pipeline de 4 etapas** acionado por hotkey:

```
[TAB+1]
   │
   ▼
screenshot.py      ← Captura a tela e recorta os retratos (4 perks) + 5 slots de ban
   │  print/{perk}/ally1..5.png, enemy1..5.png, print/bans/ban1..5.png, print/full.png
   ▼
comparar.py        ← Template matching com sliding window (MAE normalizado)
   │  lineup.txt (4 aliados + 5 inimigos) + bans.txt (0-5 banidos)
   ▼
map.py             ← OCR (Tesseract) + fuzzy match → nome do mapa
   │  current_map.txt
   ▼
choose_ow_hero.py  ← MetaStrength + Threat Weighting + Sinergia → ranking
        │
        ├── [Ranking de Ameaças Inimigas]
        └── [Ranking de Heróis Recomendados]
```

O menu e os hotkeys rodam em **threads separadas**, permitindo que o pipeline seja executado sem bloquear a interface.

---

## Tecnologias Utilizadas

| Tecnologia | Uso |
|---|---|
| **Python 3.11** | Linguagem principal |
| **MSS** | Captura de tela de alta performance |
| **Pillow (PIL)** | Manipulação e crop de imagens, pré-processamento para OCR |
| **OpenCV (cv2)** | Redimensionamento de imagens para template matching |
| **NumPy** | Cálculo de MAE (Mean Absolute Error) para matching |
| **Pandas + openpyxl** | Leitura das planilhas de counters, sinergias e stats por mapa |
| **keyboard** | Hotkeys globais funcionando fora do foco da janela |
| **pytesseract + Tesseract OCR** | Identificação do nome do mapa via OCR |
| **rapidfuzz** | Fuzzy matching do texto OCR contra a lista de mapas |
| **difflib** | Fuzzy matching para busca de heróis por nome |
| **urllib** | Download do pacote de atualização |
| **PyInstaller** | Empacotamento em `.exe` portátil |

---

## Licença

O código-fonte é de autoria de **Davi Giuberti**. Entre em contato com o autor para informações sobre uso e distribuição.
