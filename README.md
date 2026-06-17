# OWPick — Overwatch Best Picks

Ferramenta de recomendação automática de heróis para **Overwatch 2**. O programa captura a tela durante a fase de seleção de personagem, identifica os heróis aliados e inimigos e calcula qual herói você deveria jogar com base em dados de counters e sinergias.

---

## Funcionalidades

- **Captura automática** da tela de seleção com hotkey global (`TAB+1`)
- **Identificação de heróis** por comparação de imagem (template matching) — sem OCR, sem login
- **Suporte a múltiplas resoluções**: 720p e 2K, com escalonamento automático
- **Ranking de heróis** ordenado por pontuação combinada de counter + sinergia
- **Gerenciamento de favoritos**: configure quais heróis você joga em cada função
- **Seleção de Role**: DPS, Suporte, Tank ou Fila Aberta
- **Modo Priorizar Counters** (experimental): amplifica a importância de inimigos difíceis
- **Auto-atualização**: verifica e aplica novas versões automaticamente via GitHub Releases

---

## Estrutura do Projeto

```
Overwatch-Best-Picks/
├── main.py                  # Ponto de entrada — menu e hotkeys
├── screenshot.py            # Captura e recorte da tela do jogo
├── comparar.py              # Template matching para identificar heróis
├── choose_ow_hero.py        # Cálculo e exibição do ranking
├── enemy_mult.py            # Multiplicador de perigo por herói inimigo
├── favoriteHero.py          # Gerenciamento de heróis favoritos
├── roles.py                 # Seleção de função (role)
├── updater.py               # Auto-atualização via GitHub
├── resolucao.py             # [Utilitário dev] Seletor visual de coordenadas
├── heroscreenshot.py        # [Legado] Script antigo de screenshot
│
├── heroes ally.xlsx         # Planilha de sinergias entre heróis
├── heroes enemy.xlsx        # Planilha de counters entre heróis
├── version.txt              # Versão atual
├── version.json             # Versão remota para update
├── overwatch.spec           # Configuração do PyInstaller
│
├── heroes/                  # Templates de imagem dos heróis
│   ├── 720p/dps|sup|tank/
│   └── 2k/dps|sup|tank/
│
└── ocr/                     # Tesseract OCR embutido
```

---

## Instalação

### Pré-requisitos

- Python 3.11
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) na pasta `ocr/` (já incluso no repositório)

### Passos

```bash
# 1. Clone o repositório
git clone https://github.com/DaviGiuberti/Overwatch-Best-Picks.git
cd Overwatch-Best-Picks

# 2. Crie e ative o ambiente virtual
python -m venv .venv
.venv\Scripts\activate

# 3. Instale as dependências
pip install mss pillow opencv-python numpy pandas openpyxl keyboard rapidfuzz unidecode pytesseract

# 4. Execute o programa
python main.py
```

> **Nota**: O projeto não possui `requirements.txt`. As bibliotecas necessárias estão listadas acima com base na análise do código e do arquivo `overwatch.spec`.

---

## Uso

### Iniciando o Programa

```bash
python main.py
```

Na primeira execução, o programa solicitará:
1. **Sua Role** (DPS, Tank, Suporte ou Fila Aberta)
2. **Seus heróis favoritos** (quais personagens você joga)

### Hotkey Principal

Com o jogo aberto na **tela de seleção de heróis**, pressione:

```
TAB + 1
```

O programa irá:
1. Capturar a tela automaticamente
2. Identificar os heróis aliados e inimigos
3. Calcular e exibir o ranking no console

### Exemplo de Saída

```
>>> Capturando a tela...
>>> Comparando os prints com os heróis do Overwatch...
>>> Executando escolha de herói...

Role selecionada: DPS
Heróis disponíveis: Tracer, Genji, Sojourn, Cassidy

Aliados: Ana, Reinhardt, Mercy, Zenyatta
Inimigos: Roadhog, Genji, Pharah, Moira, Orisa

=================================================================
RANK   | HERO               |    ENEMY |     ALLY |    TOTAL
=================================================================
1      | Cassidy            |    12.50 |     5.85 |    18.35
2      | Sojourn            |    10.20 |     7.15 |    17.35
3      | Tracer             |     8.00 |     6.50 |    14.50
4      | Genji              |     7.30 |     4.55 |    11.85
-----------------------------------------------------------------
```

### Comandos do Menu

| Tecla | Ação |
|---|---|
| `2` + ENTER | Alterar Role/Função |
| `3` + ENTER | Adicionar/remover heróis favoritos |
| `4` + ENTER | Ativar/desativar modo "Priorizar Counters" |
| `exit` + ENTER | Encerrar o programa |

---

## Executável

A versão compilada e pronta para uso está disponível na página de [Releases do GitHub](https://github.com/DaviGiuberti/Overwatch-Best-Picks/releases).

**Versão atual**: `1.0.6`

Para usar o executável:
1. Baixe o arquivo `OWPick_v1.0.6.zip`
2. Extraia em qualquer pasta
3. Execute `OWPick.exe`
4. Nenhuma instalação adicional é necessária — o Tesseract OCR já está embutido

O programa verifica automaticamente por atualizações ao iniciar e oferece a opção de atualizar sem intervenção manual.

---

## Tecnologias Utilizadas

| Tecnologia | Uso |
|---|---|
| **Python 3.11** | Linguagem principal |
| **MSS** | Captura de tela de alta performance |
| **Pillow (PIL)** | Manipulação e crop de imagens |
| **OpenCV (cv2)** | Redimensionamento de imagens para template matching |
| **NumPy** | Cálculo de MAE (Mean Absolute Error) para matching |
| **Pandas + openpyxl** | Leitura das planilhas de counters e sinergias |
| **keyboard** | Hotkeys globais funcionando fora do foco da janela |
| **difflib** | Fuzzy matching para busca de heróis por nome |
| **PyInstaller** | Empacotamento em `.exe` portátil |
| **Tesseract OCR** | Motor OCR embutido (reservado para uso futuro) |
| **urllib** | Download do pacote de atualização |

---

## Arquitetura

O sistema opera em um **pipeline de 3 etapas** acionado por hotkey:

```
[TAB+1]
   │
   ▼
screenshot.py          ← Captura a tela e recorta os retratos dos heróis
   │  print/{perk}/ally1..5.png, enemy1..5.png
   ▼
comparar.py            ← Template matching com sliding window (MAE)
   │  lineup.txt (4 aliados + 5 inimigos)
   ▼
choose_ow_hero.py      ← Calcula score de cada herói favorito e exibe ranking
        │
        └── enemy_mult.py  (opcional, quando "Priorizar Counters" ativo)
```

O menu e os hotkeys rodam em **threads separadas**, permitindo que o pipeline seja executado sem bloquear a interface.

---

## Licença

Nenhuma licença foi identificada no repositório durante a análise. O código-fonte é de autoria de **Davi Giuberti**. Entre em contato com o autor para informações sobre uso e distribuição.
