# Face Masking Studio — Documentação do Frontend

Interface web de página única (SPA sem framework) para mascarar rostos/cabeças em
vídeos. HTML + CSS + JavaScript puro (vanilla), servida estaticamente pelo backend
FastAPI em `/`. Comunica com o backend por REST (`fetch`) e WebSocket (progresso).

- **Stack:** HTML5, CSS3, JS ES6 (módulos via IIFE, sem bundler).
- **Fonte padrão:** JetBrains Mono, empacotada localmente em `frontend/fonts/` (offline).
- **Tema:** dark por padrão (`<html data-theme="dark">`), alternável para light.
- **Idioma:** pt-BR.

---

## 1. Estrutura de arquivos

```
frontend/
├── index.html            # markup: header, main (player+painel), timeline
├── fonts/                # JetBrains Mono 400/500/700 (.woff2) — offline
├── css/
│   ├── fonts.css         # @font-face local da JetBrains Mono
│   ├── main.css          # tokens de tema, header, layout, player, painel
│   ├── timeline.css      # rodapé/timeline
│   └── editor.css        # estilos da aba de edição
└── js/
    ├── api.js            # wrapper REST (fetch)
    ├── ws_client.js      # cliente WebSocket de progresso
    ├── mask_state.js     # modelo de máscaras em memória (keyframes, interpolação)
    ├── player.js         # <video> + <canvas> overlay, desenho por frame
    ├── timeline.js       # canvas da timeline (barras + dots + playhead)
    ├── editor.js         # ferramentas de edição de máscara no canvas
    └── app.js            # bootstrap: liga tudo, fluxo de telas
```

Ordem de carga dos scripts (fim do `<body>`): `api → ws_client → mask_state →
player → timeline → editor → app`. `app.js` registra `App.init` em
`DOMContentLoaded`.

---

## 2. Layout geral

Três regiões empilhadas em coluna (`body { display:flex; flex-direction:column; height:100vh }`):

```
┌──────────────────────────────────────────────────────────────────────┐
│ HEADER  (barra de config: marca + controles globais + tema)            │
├──────────────────────────────────┬─────────────────────────────────────┤
│ PLAYER COL (70%)                 │ PANEL COL (30%)                      │
│  vídeo + overlay de máscaras     │  abas: Arquivos / Tracking /         │
│  (ou placeholder se sem vídeo)   │        Edição / Render               │
├──────────────────────────────────┴─────────────────────────────────────┤
│ TIMELINE (rodapé: transporte + tempo + velocidade + expandir + canvas) │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Header (`#header`)

Barra horizontal de configuração global. Da esquerda p/ direita:

| Elemento | id / classe | Função |
|---|---|---|
| Avatar "H" | `.avatar` | Logo quadrado-arredondado. Decorativo. |
| Marca | `.brand-title` / `.brand-sub` | "Face Masking Studio" + "H.IAAC · Privacy Tooling". |
| Título do vídeo | `#current-video` | Nome do arquivo carregado (ou "nenhum vídeo"). |
| Spacer | `.hdr-spacer` | `flex:1`, empurra controles p/ direita. |
| **Model** | `#model-select` | Dropdown de modelos ONNX disponíveis (preenchido por `/api/config`). |
| **Mask** | `#mask-style` | Estilo de máscara (fill/blur/pixel). *Visual; ainda não ligado ao backend.* |
| **Detect every** | `#detect-every` | Intervalo de detecção (frames) usado no tracking. |
| **Fallback** | `#fallback` | Checkbox. *Visual; campo enviado mas ignorado pelo backend hoje.* |
| **Head pad** | `#head-pad` | Padding (%) da caixa em volta da cabeça no tracking. |
| **Device** | `#device-indicator` | Indicador CPU/GPU (cor: verde GPU, laranja CPU). Lido de `/api/config`. |
| **Tema** | `#btn-theme` (`◐`) | Alterna `data-theme` dark↔light no `<html>`. |

Labels em maiúsculas pequenas cinza (`.ctrl > label`), estilo barra técnica.

---

## 4. Player (`#player-col`, 70% da largura)

Fundo preto, centralizado. Dois estados:

### 4.1 Placeholder (`#player-placeholder`) — sem vídeo
Exibido até o primeiro vídeo carregar. Centralizado:
- 🎬 ícone
- "Carregue um vídeo para começar"
- "Abra a aba **Arquivos** e selecione um vídeo. Pipeline: **Auto-track** → **Edição** → **Render**."

Escondido (`display:none`) em `loadVideo()`.

### 4.2 Vídeo + overlay (`#video-wrap`)
- `<video id="video">` — elemento HTML5 nativo, sem áudio control.
- `<canvas id="overlay">` — sobreposto (`position:absolute`), tamanho casado ao
  `videoWidth × videoHeight`. Desenha as máscaras a cada frame.

**Loop de render** (`player.js render()`, via `requestAnimationFrame`):
1. limpa canvas;
2. pega frame atual = `round(currentTime × fps)`;
3. `MaskState.getMasksAtFrame(frame)` → desenha cada máscara;
4. desenha overlay do editor (caixa em criação / seleção tracejada);
5. callback `onFrame` (atualiza lista de máscaras se aba Edição ativa).

**Estilos de overlay** (`setOverlayType`, escolhido na aba Edição):
- `box` (padrão): só contorno + id.
- `fill`: retângulo cheio com a cor escolhida.
- `blur` / `pixel`: aproximação de preview (amostra pixels + escurece 35%).
- Contorno sempre desenhado: **azul** = origem `tracked`/interpolada, **laranja** = `manual`. Id desenhado acima da caixa.

`eventToCanvas()` converte coordenadas do mouse → pixels do vídeo (corrige escala
CSS vs. resolução nativa).

---

## 5. Painel lateral (`#panel-col`, ~30%) — abas

Navegação `#tabs` com 4 botões. Clicar troca o `.tab-pane` ativo (`switchTab`),
faz autosave do estado e ativa/desativa o editor.

### 5.1 Aba Arquivos (`#pane-files`)
- **Sync** (`#btn-sync`): `GET /api/videos` → popula `#video-list`.
- Lista `.vlist`: cada item mostra nome + badge de estado (RAW/TRACKED/MANUAL/POST).
  Clicar no item → `loadVideo(id)` (carrega vídeo, metadados, máscaras do pass).

### 5.2 Aba Tracking (`#pane-tracking`)
Detecção automática de cabeças (YOLOv8 ONNX).
- **Start frame** / **End frame** (`#start-frame`, `#end-frame`; 0 = até o fim).
- **`#track-meta`**: resolução, FPS, duração, frames, orientação, estado, passes salvos.
- **`#track-progress`** + **`#track-status`**: barra e texto de progresso (via WS).
- **Track full** (`#btn-track-full`): dispara `POST /api/video/{id}/track` com
  `start/end/detect_every/model/head_pad/fallback`.
- **Cancelar tracking** (`#btn-track-cancel`, vermelho): `POST .../track/cancel`.

**Lógica de concorrência:**
- Ao iniciar: Track desabilita, Cancelar habilita.
- Backend recusa segundo tracking do mesmo vídeo em paralelo (**HTTP 409**).
- Cancelamento é cooperativo (para no próximo frame do loop; **não** grava JSONL parcial).
- Eventos WS resetam a UI: `tracking_done` (concluído), `tracking_cancelled`
  (cancelado), `error` (falha + alert).

### 5.3 Aba Edição (`#pane-edit`)
Edição manual das máscaras sobre o canvas. Ativa o modo edição (`Editor.setActive`),
que torna o `#overlay` clicável (cursor crosshair).

**Ferramentas** (`.tool`):
- **Selecionar**: clica numa caixa p/ selecionar; arrastar redimensiona (canto inf-dir).
- **Criar**: arrasta p/ desenhar nova caixa (cria keyframe manual).
- **Deletar**: clica numa caixa p/ remover a máscara.

**Outros controles:**
- **Overlay** (`#overlay-type`): estilo de preview (box/blur/pixel/fill).
- **Cor fill** (`#fill-color`): cor do preenchimento.
- **Encerrar** (`#btn-kill`): marca máscara selecionada como "dead" no frame atual
  (cabeça saiu de cena).
- **Reativar / Estender** (`#btn-reactivate`): reabre máscara encerrada com caixa
  padrão no centro.
- **Máscaras no frame** (`#mask-list`): lista as máscaras do frame atual com id +
  estado; clicar seleciona.
- **Salvar pass** (`#btn-save-pass`): `POST .../masks/{pass}` com o JSONL atual.
- **Avançar próximo pass** (`#btn-advance`): salva, chama `/advance` (avança o
  estado do pipeline) e recarrega.

**Overlay do editor** (`drawOverlay`): caixa verde durante criação; contorno
branco tracejado na máscara selecionada.

### 5.4 Aba Render (`#pane-render`)
Queima as máscaras no vídeo e exporta MP4.
- **Tipo de mascaramento** (`#render-type`): blur / pixel / fill.
- **Render video** (`#btn-render`): `POST /api/video/{id}/render` com
  `mask_type` + `fill_color` (convertido RGB→do color picker).
- **`#render-progress`** + **`#render-status`**: progresso via WS (`render_progress`).
- **`#render-output`**: caminho do arquivo final (`render_done` → estado POST).

---

## 6. Timeline (`#timeline`, rodapé)

Compacta por padrão (~controles + canvas 64px). Botão expande p/ 240px.

### 6.1 Barra de controles (`#tl-controls`), ordem:
```
|◀ ◀ ▶ ▶ ▶|   0:00.0/0:00.0   [1x ▾]   (f.0/f.0)            ⤢
```
| Controle | Ação |
|---|---|
| `|◀` start | vai ao frame 0 |
| `◀` back | -1 frame |
| `▶` play (`#btn-play`) | play/pause (ícone vira `⏸`) |
| `▶` fwd | +1 frame |
| `▶|` end | último frame |
| `#tl-clock` | tempo atual / duração (`m:ss.s`) |
| `#speed-select` | velocidade de reprodução: 0.1x … 4x (`playbackRate`) |
| `#tl-frames` | frame atual / total (`f.N / f.M`) |
| `#btn-tl-expand` (`⤢`) | expande/recolhe a altura do canvas |

### 6.2 Canvas (`#tl-canvas`)
Desenhado em loop (`requestAnimationFrame`):
- **Barras (metade superior)**: contagem de pessoas/máscaras por frame
  (`getPersonCountPerFrame`); intensidade do azul ∝ densidade.
- **Dots (metade inferior)**: 3 linhas, frames editados por pass (1=azul,
  2=laranja, 3=vermelho).
- **Playhead**: linha branca vertical no frame atual.

**Interação:**
- Clique → busca (seek) para o frame.
- Scroll do mouse → zoom (`pxPerFrame`, 0.05–50).
- Segurar **Espaço** + arrastar → pan horizontal.

### 6.3 Atalhos de teclado (timeline)
| Tecla | Ação |
|---|---|
| Espaço | play/pause |
| ← / → | -1 / +1 frame |
| Shift + ← / → | ∓5 segundos |
| C | centraliza no playhead |

(Ignorados quando o foco está em INPUT/SELECT.)

---

## 7. Módulos JavaScript

| Módulo | Responsabilidade |
|---|---|
| **`api.js`** (`API`) | Wrapper `fetch` REST: config, vídeos, metadata, track (+cancel), masks (get/save/autosave), advance, render. Lança erro em status não-OK. |
| **`ws_client.js`** (`WSClient`) | Conecta `ws(s)://host/ws/progress/{id}`; despacha mensagens por `type` para handlers registrados. |
| **`mask_state.js`** (`MaskState`) | Modelo em memória: `masks` (keyframes por id) + `frameIndex` (denso por frame). Interpola linearmente entre keyframes; estados active/dead; serializa de/para JSONL; autosave a cada 30s. |
| **`player.js`** (`Player`) | Controla `<video>` + canvas overlay; loop de desenho; conversão de coordenadas; play/seek/speed. |
| **`timeline.js`** (`Timeline`) | Canvas da timeline: barras, dots, playhead; zoom/pan/seek; atalhos; expand. |
| **`editor.js`** (`Editor`) | Ferramentas create/select/delete; lifecycle kill/reactivate; lista de máscaras do frame. |
| **`app.js`** (`App`) | Bootstrap: liga abas, header, controles, tracking, edição, render, WS; orquestra `loadVideo`/`loadMasksForPass`. |

---

## 8. Modelo de dados de máscara

- **Máscara**: `{ id, source, deleted, keyframes:[] }`.
  - `source`: `tracked` | `interpolated` | `manual`.
  - `keyframe`: `{ frame, x, y, w, h, state }`, `state` = `active` | `dead`.
- **Interpolação**: entre dois keyframes do mesmo id, caixas intermediárias são
  geradas por `lerp`. Um keyframe `dead` encerra a máscara a partir daquele frame.
- **Persistência (JSONL)**: uma linha por frame —
  `{ frame, ts, masks:[{id,x,y,w,h,state,source}] }`.
- **Passes**: pass 0 = saída do tracking; passes 1–3 = refinamentos manuais.
  `STATE_PASS` mapeia estado→pass (`RAW→null`, `TRACKED→0`, `MANUAL_n→n`, `POST→3`).

---

## 9. Fluxo de uso (pipeline)

```
1. Arquivos → Sync → seleciona vídeo            (estado RAW)
2. Tracking → Track full                        (estado TRACKED, pass 0)
        ↑ máscaras azuis aparecem no player automaticamente
3. Edição  → corrige/cria/encerra máscaras → Salvar pass / Avançar
                                                (estados MANUAL_1..3)
4. Render  → queima máscaras → MP4 final         (estado POST)
```

As máscaras aparecem **automaticamente** no player após o tracking (sem botão
extra): `tracking_done` → `loadVideo` → carrega pass 0 → loop de desenho.

---

## 10. Estados e badges

| Estado | Badge | Significado |
|---|---|---|
| RAW | cinza | vídeo cru, sem máscaras |
| TRACKED | azul | tracking automático concluído (pass 0) |
| MANUAL_1/2/3 | laranja | refinamento manual (passes 1–3) |
| POST | verde | render final exportado |

*(O badge de estado não fica no header atual; o estado aparece na lista de
arquivos e nos metadados de Tracking.)*

---

## 11. Comunicação com o backend

**REST** (prefixo `/api`): `GET /config`, `GET /videos`,
`GET /video/{id}/metadata`, `GET /video/{id}/file`,
`POST /video/{id}/track`, `POST /video/{id}/track/cancel`,
`GET|POST /video/{id}/masks/{pass}`, `POST /video/{id}/masks/tmp`,
`POST /video/{id}/advance`, `POST /video/{id}/render`.

**WebSocket** (`/ws/progress/{id}`) — tipos de mensagem:
`tracking_progress`, `tracking_done`, `tracking_cancelled`,
`render_progress`, `render_done`, `error`.

---

## 12. Notas / pendências conhecidas

- **Mask** (header) e **Fallback** são controles visuais: ainda não ligados ao
  backend (Fallback é enviado mas ignorado; Mask do header é independente do
  `render-type` da aba Render).
- Trocar de vídeo durante um tracking reseta a UI, mas o job do vídeo anterior
  segue no servidor (registro por vídeo).
- Tema padrão é dark; a imagem de referência é clara (toggle disponível).
