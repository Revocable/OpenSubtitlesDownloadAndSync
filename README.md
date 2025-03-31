# OpenSubtitles Downloader

Este projeto contém duas funcionalidades principais:

1. **Download de Legendas (main.py)**
   - Gerencia a autenticação e o ciclo de contas para acessar a API do OpenSubtitles.
   - Utiliza múltiplas threads para processar vídeos de forma concorrente e segura.
   - Realiza buscas de legendas tanto por hash do arquivo quanto por query com base no nome do vídeo.
   - Lida com tentativas de re-login em caso de erros na API e garante a robustez do download das legendas.
   - Configuração feita via variáveis, como API_KEY, lista de ACCOUNTS, e a especificação de idiomas.

2. **Ajuste de Tempo de Legendas (ajustar_legenda.py)**
   - Extrai legendas embutidas de vídeos, utilizando ferramentas como mkvextract e ffmpeg.
   - Calcula o offset (diferença de tempo) entre a legenda extraída e uma legenda externa existente.
   - Ajusta os tempos das legendas para sincronizá-las corretamente com o vídeo.
   - Cria um backup do arquivo de legenda original antes de salvar as alterações.
   
## Requisitos
- Python 3.x
- Bibliotecas: requests, itertools, logging, threading, argparse, etc.
- Ferramentas externas: ffmpeg, mkvextract, mkvinfo, ffprobe

## Como Usar

### main.py
1. Configure a variável `API_KEY` e a lista `ACCOUNTS` com suas credenciais da API do OpenSubtitles.
2. Execute o script e informe o diretório contendo os arquivos de vídeo (sem legenda .srt correspondente).
3. O script utilizará múltiplas threads para buscar e baixar as legendas dos vídeos.

### ajustar_legenda.py
1. Informe o caminho da pasta contendo os vídeos e as legendas.
2. O script identificará os arquivos de legenda, extrairá legendas embutidas (se disponíveis) e ajustará o timing das legendas com base no offset calculado.
3. Um backup do arquivo original será criado antes de salvar as alterações.

## Notas
- Certifique-se de ter instalados os utilitários externos (ffmpeg, mkvextract, etc.) e que estejam configurados no PATH do sistema.
- Verifique as configurações de idioma, pois alguns parâmetros podem variar conforme a API ou o formato do vídeo.
