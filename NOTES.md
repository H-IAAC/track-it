# NOTES (trabalho em andamento)

Pendências do repositório temporário. São notas de trabalho, não o README principal. O checklist completo está em `MIGRATION_CHECKLIST.md`.

## Feito
- [x] Versão do Android confirmada como a tag `v3.0.1` e importada em `android_app/`.
- [x] Annotation Interface, Viewer, Face Masking Studio e server-processing trazidos e integrados no modo Dual-Mode (Standalone + Dataset Flow com `session_manifest.json`).
- [x] Mascaramento automático do servidor via API do Face Masking Studio (`auto-anonymize`), que gera o "mask 0" (Pass 0) e o vídeo mascarado em `data/<sessão>/videos/`.
- [x] Identidade visual única (`shared/hiaac-theme`) em todas as ferramentas web e no Android, com logo, botões quadrados e tema claro/escuro.
- [x] Pipeline completo testado com dados mock (`mock_coleta`): servidor, mascaramento automático, edição manual em 2 passes, anotação com 3 anotadores e Viewer.
- [x] Requirements alinhados em Python 3.12.

## android_app
- [ ] Rodar num celular físico e confirmar que é a mesma versão usada nos experimentos e na coleta (até agora só foi testado no emulador).
- [ ] Trocar `jcenter()` por `mavenCentral()` e atualizar o Android Gradle Plugin (7.4.2).

## face_masking_studio
- [ ] Garantir suporte a MediaPipe, YOLOv11x-pose, YOLOv26m-pose, YOLOv11m e YOLOv7-tiny-head. Hoje só o YOLOv7-tiny-head (ONNX) está ligado.
- [ ] Usar esses mesmos modelos no processamento automático (`auto-anonymize`) e deixar escolher o modelo ou nenhum.
- [ ] Testar cada modelo no automático e no refino.

## annotation_interface
- [ ] Melhorar a performance (opcional).
- [ ] Deixar a ferramenta menos especializada sem perder o uso atual. Ex.: avaliar a "Caixa de texto 7 e 3" que o Marcos comentou.

## server-processing
- [ ] Decidir se ainda vale trazer algo do repositório da Bia.
- [ ] Permitir escolher o modelo de mascaramento (ou nenhum) no envio da sessão.

## validation
- [ ] face_anonymization: tirar o caminho local fixo (`DATA_ROOT`) e publicar os dados agregados. Responsável: Gustavo.
- [ ] synchronization: separar código, dados brutos e resultados, e conferir se o notebook roda do zero.
