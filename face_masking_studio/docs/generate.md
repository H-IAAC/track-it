# Face Masking Studio — Prompt Mestre de Desenvolvimento

> Use este documento como contexto completo ao iniciar cada fase. Ao começar uma nova fase, forneça este prompt + o código já produzido nas fases anteriores.

---

## Visão Geral do Projeto

Ferramenta web para mascaramento/censura de rostos em vídeos, com o objetivo de atender leis de proteção de imagem. A ferramenta roda como **servidor local + interface web** (FastAPI no backend, HTML/CSS/JS puro no frontend), sem autenticação, para uso pessoal em equipe pequena com fluxo de revisão sequencial.

---

## Stack Tecnológica

### Backend
- **Python 3.11+** com **FastAPI**
- **Ultralytics YOLO** (modelo padrão: `yolov7-tiny-head` em ONNX; opcionais: MediaPipe, YOLO11x-pose, YOLO26m-pose e YOLO11m)
- **OpenCV** (`cv2`) para manipulação de frames
- **FFmpeg** via `ffmpeg-python` para render final e correção de metadados
- **NumPy** para operações matriciais
- **WebSocket** (FastAPI nativo) para progresso em tempo real
- Detecção automática de dispositivo: `torch.cuda.is_available()` → GPU (CUDA) ou CPU

### Frontend
- **HTML5 / CSS3 / JavaScript puro** (sem frameworks)
- **Canvas API** para overlay de máscaras sobre o vídeo
- **HTML5 `<video>`** como player base
- **WebSocket client** nativo do browser para receber progresso do backend

### Armazenamento
- **JSONL** (JSON Lines) como formato principal de dados de máscaras
  - Uma linha por frame: `{"frame": N, "ts": 0.000, "masks": [...]}`
  - Cada máscara: `{"id": "t_003", "x": 120, "y": 80, "w": 60, "h": 72, "state": "active", "source": "tracked"}`
  - `state`: `"active"` | `"dead"` (keyframe de encerramento)
  - `source`: `"tracked"` | `"manual"` | `"interpolated"`
- **tmp/** para autosave durante edição (a cada 30s e ao sair da aba)
- Cada pass de edição cria um novo JSONL baseado no anterior, nunca sobrescreve

### Estrutura de Pastas do Projeto
```
face-masking-studio/
├── backend/
│   ├── main.py                  # FastAPI app, rotas, WebSocket
│   ├── tracker.py               # YOLO inference, propagação backward
│   ├── interpolator.py          # Interpolação linear entre keyframes
│   ├── renderer.py              # Aplicação de máscaras + FFmpeg render
│   ├── metadata_fixer.py        # Detecção e correção de orientação
│   ├── session_manager.py       # Estado do vídeo por pass
│   └── requirements.txt
├── frontend/
│   ├── index.html               # Shell principal
│   ├── css/
│   │   ├── main.css
│   │   ├── timeline.css
│   │   └── editor.css
│   └── js/
│       ├── app.js               # Bootstrap, roteamento de abas
│       ├── player.js            # HTML5 video + canvas overlay
│       ├── timeline.js          # Timeline engine completo
│       ├── editor.js            # Ferramenta de edição de máscaras
│       ├── mask_state.js        # Gerenciador de estado das máscaras
│       ├── ws_client.js         # WebSocket client
│       └── api.js               # Wrapper fetch para rotas REST
└── videos/                      # Pasta base padrão (configurável)
    ├── raw/                     # Vídeos originais
    ├── masks_data/              # JSONL por vídeo e por pass
    ├── tmp/                     # Autosave de edição em andamento
    └── output/                  # Vídeos finais mascarados
```

---

## Estrutura de Dados Principal

### JSONL de máscaras (por arquivo, por pass)
**Nome do arquivo:** `{video_stem}_pass{N}.jsonl`
**Exemplo:** `entrevista_01_pass0.jsonl` (pass 0 = tracking automático)

```jsonl
{"frame": 0, "ts": 0.000, "masks": []}
{"frame": 1, "ts": 0.033, "masks": [{"id": "t_001", "x": 120, "y": 80, "w": 60, "h": 72, "state": "active", "source": "tracked"}]}
{"frame": 2, "ts": 0.066, "masks": [{"id": "t_001", "x": 122, "y": 81, "w": 60, "h": 72, "state": "active", "source": "interpolated"}]}
{"frame": 150, "ts": 5.000, "masks": [{"id": "t_001", "x": 200, "y": 90, "w": 60, "h": 72, "state": "dead", "source": "manual"}]}
```

### Regras de ID de máscaras
- Formato: `t_NNN` onde NNN é um inteiro sequencial com zero-padding (ex: `t_001`, `t_042`)
- IDs são **globais ao vídeo**, nunca reutilizados mesmo após `dead`
- O próximo ID disponível é sempre `max(id_existentes) + 1`
- IDs gerados pelo YOLO no tracking recebem prefixo `t_`
- IDs criados manualmente recebem prefixo `m_`

### Sistema de Keyframes e Ciclo de Vida das Máscaras
- Cada máscara existe como uma lista de keyframes `{frame, x, y, w, h, state}`
- A interpolação linear preenche os frames entre dois keyframes `active`
- Um keyframe com `state: "dead"` encerra a máscara naquele frame
- Para **reativar** uma máscara encerrada: adicionar novo keyframe `active` após o `dead`
  - A ferramenta pergunta: "Reativar máscara `t_001` ou criar nova?"
  - Se reativar: novo keyframe `active` adicionado, interpolação retomada
  - Se criar nova: novo ID gerado, máscara independente
- Para **estender** uma máscara além do fim do tracking: adicionar keyframe `active` no frame desejado

---

## Layout da Interface

### Header (barra superior fixa)
Campos visíveis da esquerda para direita:
1. **Logo / Nome:** "Face Masking Studio"
2. **Vídeo atual:** caminho truncado do arquivo + botão `Load`
3. **Modelo:** dropdown seletor do modelo YOLO (ex: `yolov7-tiny-head`, `mediapipe-face`, `yolo11x-pose.pt`)
4. **Etapa atual:** badge colorido — `RAW` | `TRACKED` | `MANUAL 1` | `MANUAL 2` | `MANUAL 3` | `POST`
5. **Detectar a cada:** spinner numérico (frames), com checkbox `Propagação backward`
6. **Pad de cabeça:** spinner numérico — margem extra ao redor da bounding box (%)
7. **Device:** indicador `● GPU` (verde) ou `● CPU` (laranja)
8. **Tema:** toggle claro/escuro

### Área central — duas colunas
**Coluna esquerda (~70% da largura):** player de vídeo
- Elemento `<video>` com `<canvas>` sobreposto (position absolute, mesmo tamanho)
- O canvas renderiza as máscaras em tempo real lendo o `mask_state.js`
- Orientação corrigida via CSS transform baseado nos metadados (sem reencoding no preview)

**Coluna direita (~30% da largura):** painel de abas
- **Aba 1 — Arquivos:** explorador da pasta base, botão Sync, lista de vídeos com badge de etapa
- **Aba 2 — Tracking:** configurações de inferência, intervalo start/end (padrão: vídeo todo), metadados do vídeo carregado (resolução, duração, FPS, pass atual, status do JSONL), botão "Track region" e "Track full"
- **Aba 3 — Edição manual:** ferramentas de edição (criar máscara, selecionar, redimensionar, deletar, reativar), tipo de máscara (blur / pixel / fill), cor do fill, lista de máscaras ativas no frame atual com seus IDs
- **Aba 4 — Render:** toggle de normalização de orientação, seletor de tipo de mascaramento para o render final, botão "Render video", barra de progresso, caminho do arquivo de saída

### Timeline (barra inferior fixa)

**Controles (linha de botões acima do gráfico):**
- `|◀` (ir ao início) `▶` (play/pause) `▶|` (ir ao fim)
- `◀` (frame -1) `▶` (frame +1)
- Seletor de velocidade: `0.1× 0.25× 0.5× 1× 1.5× 2× 4×`
- Label `REVIEW` com spinner de zoom da timeline
- Tempo atual: `6:16.4 / 17:12.9` e frame atual entre parênteses: `(f.11234 / f.30890)`

**Atalhos de teclado:**
| Tecla | Ação |
|---|---|
| `Espaço` | Play / Pause |
| `Espaço` (segurar) | Pan horizontal na timeline |
| `←` | Retroceder 1 frame |
| `→` | Avançar 1 frame |
| `Shift + ←` | Retroceder 5 segundos |
| `Shift + →` | Avançar 5 segundos |
| `C` | Centralizar timeline no frame atual |
| `Scroll` (sobre timeline) | Zoom in/out na timeline |

**Gráfico da timeline (duas faixas verticais):**

Faixa superior (0–50% da altura):
- Barras verticais por frame mostrando contagem de pessoas detectadas
- Cor: escala de intensidade (0 pessoas = cinza, N pessoas = cor primária proporcional)
- Escala Y normalizada pelo máximo do vídeo

Faixa inferior (50–100% da altura):
- Dividida em 3 linhas horizontais iguais
- Linha 1: bolinhas dos frames editados no Pass 1 (cor azul)
- Linha 2: bolinhas dos frames editados no Pass 2 (cor âmbar)
- Linha 3: bolinhas dos frames editados no Pass 3 (cor coral/vermelho)
- Bolinhas são persistentes: passes anteriores sempre visíveis em passes futuros

---

## Fluxo de Estados do Vídeo

```
RAW → [Auto Track] → TRACKED → [Manual Pass 1] → MANUAL_1 → [Manual Pass 2] → MANUAL_2 → [Manual Pass 3] → MANUAL_3 → [Render] → POST
```

- Cada transição só é permitida na sequência acima (sem pular etapas)
- O estado é persistido no backend (`session_manager.py`)
- Ao entrar em qualquer etapa MANUAL, o JSONL do pass anterior é copiado como base
- O render final sempre usa o JSONL do pass mais avançado disponível

---

## Módulos do Backend — Contratos de API

### REST endpoints

```
GET  /api/videos                          → lista vídeos na pasta base
GET  /api/video/{video_id}/metadata       → resolução, fps, duração, orientação, estado atual
POST /api/video/{video_id}/track          → inicia tracking (body: {start_frame, end_frame, detect_every, model, head_pad})
GET  /api/video/{video_id}/masks/{pass}   → retorna JSONL completo de um pass
POST /api/video/{video_id}/masks/{pass}   → salva JSONL editado (pass manual)
POST /api/video/{video_id}/masks/tmp      → autosave parcial (tmp/)
POST /api/video/{video_id}/render         → inicia render final (body: {mask_type, normalize_orientation})
GET  /api/config                          → pasta base, modelos disponíveis, device atual
POST /api/config                          → atualiza configurações
```

### WebSocket

```
WS /ws/progress/{video_id}
```

Mensagens do servidor → cliente:
```json
{"type": "tracking_progress", "frame": 1042, "total": 30890, "detections": 3}
{"type": "tracking_done", "pass": 0, "jsonl_path": "masks_data/video_pass0.jsonl"}
{"type": "render_progress", "frame": 1042, "total": 30890}
{"type": "render_done", "output_path": "output/video_masked.mp4"}
{"type": "error", "message": "..."}
```

---

## Módulos do Frontend — Responsabilidades

### `mask_state.js`
Responsável por toda a lógica de estado das máscaras em memória:
- Carrega JSONL do backend ao abrir um vídeo/pass
- Mantém índice frame → lista de máscaras
- Interpola posições entre keyframes (linear)
- Expõe `getMasksAtFrame(n)` para o player e timeline
- Gerencia criação, edição, deleção e reativação de máscaras
- Rastreia frames "sujos" (editados) para autosave e para as bolinhas da timeline
- Serializa estado para JSONL ao salvar

### `player.js`
- Sincroniza o `<canvas>` com o `<video>` frame a frame via `requestAnimationFrame`
- Chama `mask_state.getMasksAtFrame()` a cada frame renderizado
- Desenha as máscaras no canvas com o tipo selecionado (blur, pixel, fill)
- Delega eventos de mouse ao `editor.js` quando a aba de edição está ativa
- Aplica correção de orientação via CSS transform lendo os metadados

### `timeline.js`
- Renderiza as duas faixas via Canvas
- Mantém estado de zoom (px por frame), offset de pan, e frame atual
- Sincroniza posição com `<video>.currentTime`
- Recebe contagens de pessoas do `mask_state.js` para a faixa superior
- Recebe frames editados por pass do `mask_state.js` para a faixa inferior
- Gerencia todos os atalhos de teclado descritos acima

### `editor.js`
- Gerencia o modo de ferramenta ativo: `create | select | delete`
- No modo `create`: captura drag no canvas para definir bounding box, chama `mask_state.createMask()`
- No modo `select`: detecta clique em máscara existente, exibe handles de redimensionamento
- Ao soltar após resize: chama `mask_state.updateKeyframe()`
- Botão "Encerrar máscara": chama `mask_state.killMask(id, frame)` — adiciona keyframe `dead`
- Botão "Reativar / Estender": lógica de reativação descrita acima

---

## Módulos do Backend — Detalhes de Implementação

### `tracker.py`
```python
# Pseudocódigo das responsabilidades
def run_tracking(video_path, start_frame, end_frame, detect_every, model_path, head_pad, ws_callback):
    # 1. Abre vídeo com cv2.VideoCapture
    # 2. Para cada frame em range(start_frame, end_frame, detect_every):
    #    - Roda YOLO inference
    #    - Aplica head_pad às bounding boxes
    #    - Associa IDs por IoU com frame anterior (tracking simples)
    #    - Chama ws_callback com progresso
    # 3. Preenche frames intermediários via propagação backward:
    #    - Se frame N e frame N+detect_every têm mesma máscara (mesmo ID por IoU):
    #      interpola linearmente os frames entre eles
    #    - Se não há correspondência: os frames intermediários ficam sem detecção
    # 4. Escreve JSONL linha a linha (não acumula em memória)
```

### `metadata_fixer.py`
```python
# Responsabilidades
def get_rotation(video_path) -> int:
    # Lê tag rotate dos metadados via ffprobe
    # Retorna 0, 90, 180 ou 270

def get_css_transform(rotation: int) -> str:
    # Converte rotação para CSS transform string
    # Ex: 90 → "rotate(90deg)" para aplicar no <video> do frontend

def normalize_video(input_path, output_path):
    # FFmpeg: reencoda com -vf transpose e -metadata:s:v rotate=0
    # Só executa se toggle de normalização estiver ativo no render
```

### `renderer.py`
```python
# Responsabilidades
def render_video(video_path, jsonl_path, output_path, mask_type, normalize_orientation, ws_callback):
    # 1. Se normalize_orientation: roda metadata_fixer.normalize_video() primeiro
    # 2. Lê JSONL linha a linha (streaming, sem carregar tudo em memória)
    # 3. Para cada frame:
    #    - Aplica máscaras do tipo selecionado:
    #      - blur: cv2.GaussianBlur na ROI
    #      - pixel: reduz resolução da ROI e amplia de volta (efeito mosaico)
    #      - fill: cv2.rectangle com cor sólida
    # 4. Escreve frame processado via FFmpeg pipe
    # 5. Chama ws_callback com progresso
```

### `interpolator.py`
```python
def interpolate_masks(keyframes: list[dict]) -> dict[int, list[dict]]:
    # Recebe lista de keyframes de uma máscara (ordenados por frame)
    # Para cada par de keyframes consecutivos ambos "active":
    #   - Gera frames intermediários com x, y, w, h interpolados linearmente
    # Para keyframe "dead": não gera frames após ele
    # Retorna dict {frame_number: mask_dict}
```

---

## Decisões de Design Importantes

### Por que JSONL e não CSV?
- Leitura streamada frame a frame — não carrega o arquivo inteiro em memória
- Suporta estruturas aninhadas (lista de máscaras por frame) sem escapamento complexo
- Append eficiente durante o tracking (escreve uma linha por vez)
- Legível por humanos e parseável por qualquer linguagem

### Por que não SQLite?
- JSONL é mais simples de versionar (diff legível)
- Mais fácil de inspecionar manualmente em caso de problema
- Sem dependência de driver; copia/move com `cp`

### Correção de orientação em dois momentos
1. **Preview (sem reencoding):** CSS `transform: rotate(Ndeg)` no `<video>`, baseado nos metadados lidos pelo backend via ffprobe
2. **Render final (com reencoding):** toggle explícito no usuário; FFmpeg reencoda com transpose correto e zera a tag de rotação

### IDs de máscaras únicos e contínuos
- O tracking YOLO gera IDs por associação de IoU entre frames consecutivos
- IDs nunca são reutilizados no mesmo vídeo
- Ao deletar uma máscara na edição, o ID some mas não é realocado
- Isso garante que referências históricas (bolinhas nos passes anteriores) sempre sejam rastreáveis

### Autosave e segurança de dados
- Autosave em `tmp/{video_stem}_pass{N}_autosave.jsonl` a cada 30s
- Autosave também disparado ao: trocar de aba, fechar janela (`beforeunload`), iniciar render
- Ao abrir um vídeo em edição, verificar se existe autosave mais recente que o JSONL salvo; se sim, oferecer recuperação
- O JSONL "oficial" do pass só é escrito ao clicar em "Salvar pass" ou "Avançar para próximo pass"

---

## Guia de Desenvolvimento por Fase

---

### FASE 1 — Fundação

**Objetivo:** Projeto rodando localmente com player funcional e correção de orientação.

**Entregáveis:**
1. Estrutura de pastas completa criada
2. `requirements.txt` com todas as dependências
3. `main.py` com FastAPI básico servindo o frontend estático e rotas `/api/videos` e `/api/video/{id}/metadata`
4. `metadata_fixer.py` implementado (leitura de rotação via ffprobe + geração de CSS transform)
5. `index.html` com layout base: header, área central (player + painel direito com 4 abas), timeline (estrutura vazia)
6. `player.js`: carrega vídeo, aplica correção de orientação via CSS, sincroniza canvas
7. **Aba 1** funcional: lista vídeos da pasta base, botão Sync, clique carrega vídeo no player
8. Metadados visíveis na **Aba 2**: resolução, FPS, duração, orientação detectada

**Não implementar nesta fase:** tracking, edição de máscaras, timeline interativa.

---

### FASE 2 — Auto-tracking

**Objetivo:** YOLO detecta cabeças, gera JSONL de tracking, progresso em tempo real.

**Entregáveis:**
1. `tracker.py` completo com YOLO inference, propagação backward e associação de IDs por IoU
2. `interpolator.py` com interpolação linear entre keyframes
3. Rota `POST /api/video/{id}/track` com WebSocket de progresso
4. `ws_client.js` recebendo progresso e atualizando barra na Aba 2
5. **Aba 2** com: seletor de modelo, spinner detect_every, checkbox propagação backward, campos start/end (default: vídeo todo), head_pad, botões "Track region" / "Track full"
6. Ao finalizar, JSONL escrito em `masks_data/` e estado do vídeo atualizado para `TRACKED`
7. `player.js` atualizado: chama `mask_state.getMasksAtFrame()` e desenha bboxes simples no canvas

**Detalhe da propagação backward:**
- Detectar a cada N frames cria "âncoras"
- Entre duas âncoras com mesma máscara (mesmo ID): interpolar linearmente
- Se uma máscara aparece numa âncora mas não na anterior: marcar como `active` apenas a partir da âncora de aparição
- Se uma máscara some numa âncora: marcar como `dead` na âncora anterior + 1 frame

---

### FASE 3 — Timeline Engine

**Objetivo:** Timeline interativa completa com todos os atalhos e os dois gráficos.

**Entregáveis:**
1. `timeline.js` completo:
   - Canvas com duas faixas (superior: contagem de pessoas; inferior: 3 linhas de bolinhas)
   - Scrubber arrastável que sincroniza com `<video>.currentTime`
   - Zoom com scroll (mín: 1 frame por pixel, máx: depende do vídeo)
   - Pan com espaço segurado + arrastar
   - Todos os atalhos de teclado da spec
   - Label de tempo e frame atualizando em tempo real
   - Seletor de velocidade funcionando
2. `timeline.css` com estilos da timeline
3. Integração com `mask_state.js` para dados da faixa inferior (bolinhas por pass)

**Detalhe do gráfico superior:**
- Dados: `mask_state.getPersonCountPerFrame()` → array de inteiros
- Normalizar pelo máximo para escalar as barras
- Renderizar apenas os frames visíveis na viewport atual (performance)

**Detalhe do gráfico inferior:**
- Dados: `mask_state.getEditedFramesByPass()` → `{1: [frame, ...], 2: [...], 3: [...]}`
- Linha 1 (pass 1): bolinhas azuis, y = 62.5% da altura total da timeline
- Linha 2 (pass 2): bolinhas âmbar, y = 75% da altura total
- Linha 3 (pass 3): bolinhas coral, y = 87.5% da altura total
- Bolinhas de passes anteriores sempre renderizadas (apenas nova bolinha adicionada, não substituída)

---

### FASE 4 — Editor Manual

**Objetivo:** Edição completa de máscaras no canvas com ciclo de vida e autosave.

**Entregáveis:**
1. `mask_state.js` completo:
   - Carrega JSONL, mantém índice frame→máscaras, expõe API de edição
   - `createMask(frame, {x,y,w,h})` → gera novo ID, cria keyframe `active`
   - `updateKeyframe(id, frame, {x,y,w,h})` → upsert no keyframe daquele frame
   - `killMask(id, frame)` → adiciona keyframe `dead`
   - `reactivateMask(id, frame, {x,y,w,h})` → adiciona keyframe `active` após `dead`
   - `deleteMask(id)` → remove todos os keyframes (soft delete com flag)
   - `getMasksAtFrame(n)` → retorna lista interpolada de máscaras no frame N
   - `getPersonCountPerFrame()` → array com contagem por frame
   - `getEditedFramesByPass()` → frames editados por pass
   - Autosave a cada 30s e em `beforeunload`
2. `editor.js` completo com ferramentas create/select/delete e UI de reativação
3. **Aba 3** com: toolbar de ferramentas, seletor de tipo de overlay (para preview), lista de máscaras no frame atual, botões encerrar/reativar
4. `player.js` atualizado: renderiza blur/pixel/fill no canvas baseado no tipo selecionado
5. Botão "Salvar pass" e lógica de avanço de estado

---

### FASE 5 — Fluxo de Passes Sequenciais

**Objetivo:** Controle de estado completo, passes sequenciais, histórico visual.

**Entregáveis:**
1. `session_manager.py` com máquina de estados do vídeo
2. Badge de etapa no header atualiza conforme estado
3. Ao entrar em MANUAL_N: copia JSONL do pass N-1 como base para edição
4. Verificação de autosave ao abrir: oferece recuperação se autosave > JSONL salvo
5. Timeline mostra bolinhas de todos os passes já realizados, mesmo durante passes futuros
6. Aba 2 mostra histórico de passes (qual JSONL existe para cada pass)
7. Bloqueio de ações não permitidas no estado atual (ex: não pode editar se está em RAW)

---

### FASE 6 — Render Final

**Objetivo:** Aplicar máscaras no vídeo raw e exportar MP4 final.

**Entregáveis:**
1. `renderer.py` completo com suporte a blur, pixel e fill via OpenCV + FFmpeg
2. Rota `POST /api/video/{id}/render` com WebSocket de progresso
3. `metadata_fixer.py` atualizado com `normalize_video()`
4. **Aba 4** funcional:
   - Toggle de normalização de orientação (aplica reencoding antes das máscaras)
   - Seletor de tipo de mascaramento para o render
   - Botão "Render video"
   - Barra de progresso em tempo real via WebSocket
   - Caminho do arquivo de saída ao concluir
5. Estado do vídeo atualizado para `POST` ao concluir render
6. Arquivo salvo em `videos/output/{video_stem}_masked.mp4`

**Detalhe do render:**
- Se `normalize_orientation = true`: roda FFmpeg para corrigir orientação → arquivo temporário → aplica máscaras → output final
- Máscaras aplicadas com coordenadas relativas ao frame (0.0–1.0) para serem resolução-agnósticas
- FFmpeg pipe: `cv2 → stdout → ffmpeg stdin` para não criar arquivo intermediário de frames

---

## Notas para o Assistente ao Usar Este Prompt

- Ao iniciar cada fase, releia as seções relevantes e implemente **somente** o que está especificado para aquela fase
- Não antecipe implementações de fases futuras
- Para cada arquivo criado, siga os contratos de API e as responsabilidades definidas acima
- Use type hints em todo o código Python
- No JavaScript, use `const`/`let`, sem `var`; prefira funções nomeadas a arrow functions anônimas para melhor rastreabilidade
- Nomes de variáveis e comentários em inglês; strings de UI em português
- Sempre que uma rota REST for implementada, implemente também o wrapper correspondente em `api.js`
- Ao final de cada fase, liste os arquivos criados/modificados e quais endpoints/funções foram implementados