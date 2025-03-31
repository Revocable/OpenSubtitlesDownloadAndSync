import requests
import itertools
import os
import hashlib
import json
import time
import re
import threading # Importar threading
from concurrent.futures import ThreadPoolExecutor # Importar ThreadPoolExecutor
import logging # Usar logging para saída thread-safe

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(threadName)s - %(message)s')

# --- Configurações ---
API_KEY = "SUA_API_KEY_AQUI" # Substitua pela sua chave de API
ACCOUNTS = [
    {"username": "seu_usuario1", "password": "sua_senha1"},
]
API_URL = "https://api.opensubtitles.com/api/v1"
BASE_HEADERS = {
    "User-Agent": "MeuScriptDeLegendasMultiThread V1.3", # V1.3 MultiThread
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Api-Key": API_KEY
}
# ATENÇÃO: A API pode não reconhecer 'pt-br'. 'pb' ou 'pt' são mais comuns.
# Verifique a documentação da API ou teste. Voltando para 'pb,pt' por segurança.
TARGET_LANGUAGES = "pt-br"
RELOGIN_STATUS_CODES = {401, 403, 429}
MAX_WORKERS = 30 # Número de threads concorrentes (ajuste conforme necessário)

# --- Classe Gerenciadora de Token ---
class TokenManager:
    def __init__(self, accounts, api_key, api_url, base_headers):
        if not accounts:
            raise ValueError("Lista de contas não pode ser vazia.")
        self.accounts = accounts
        self.api_key = api_key
        self.api_url = api_url
        self.base_headers = base_headers
        self.account_cycle = itertools.cycle(self.accounts)
        self.current_token = None
        self.current_account = None
        self.lock = threading.Lock() # Lock para proteger acesso ao token/login
        self.max_login_attempts = len(accounts) * 2 # Evitar loop infinito

    def _perform_login(self, account):
        """ Tenta logar com uma conta específica. NÃO usar lock aqui. """
        thread_name = threading.current_thread().name
        logging.info(f"Tentando login como: {account['username']}...")
        payload = {"username": account["username"], "password": account["password"]}
        try:
            # Usa BASE_HEADERS que já tem Api-Key
            response = requests.post(f"{self.api_url}/login", headers=self.base_headers, json=payload, timeout=15)
            if response.status_code == 200:
                data = response.json()
                token = data.get("token")
                if token:
                    logging.info(f"Login bem-sucedido como {account['username']}.")
                    return token, account
                else:
                    logging.warning(f"Erro no login como {account['username']}: Token não encontrado na resposta.")
                    return None, None
            else:
                logging.warning(f"Falha no login como {account['username']}: Código {response.status_code}")
                # Logar detalhes pode ser útil, mas cuidado com verbosidade
                # try: logging.debug(f"Detalhe da API: {response.json()}")
                # except json.JSONDecodeError: logging.debug(f"Detalhe da API: {response.text}")
                return None, None
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro de rede durante o login como {account['username']}: {e}")
            return None, None
        except Exception as e:
            logging.error(f"Erro inesperado durante login como {account['username']}: {e}")
            return None, None

    def get_token(self, force_new=False):
        """ Obtém um token válido, tentando logar se necessário. Thread-safe. """
        with self.lock:
            if self.current_token and not force_new:
                # logging.debug(f"Reutilizando token existente para {self.current_account['username']}")
                return self.current_token, self.current_account # Retorna token e conta associada

            logging.info("Necessário obter novo token/revalidar.")
            self.current_token = None # Invalida token atual antes de tentar novo
            attempts = 0
            while attempts < self.max_login_attempts:
                account_to_try = next(self.account_cycle)
                token, account = self._perform_login(account_to_try)
                if token:
                    self.current_token = token
                    self.current_account = account
                    return self.current_token, self.current_account
                attempts += 1
                time.sleep(0.5) # Pausa entre tentativas falhas

            logging.error("Falha ao obter token válido após todas as tentativas.")
            raise ConnectionError("Não foi possível obter um token válido de nenhuma conta.") # Ou uma exceção customizada

    def force_relogin(self):
        """ Força a obtenção de um novo token, ciclando a conta. """
        logging.warning("Forçando re-login / ciclo de conta devido a erro API.")
        # Chama get_token com force_new=True para garantir que tente logar
        return self.get_token(force_new=True)

# --- Funções de Lógica (adaptadas para logging e receber token) ---

def hash_file(file_path):
    # ... (código mantido, usar logging para erros/avisos) ...
    try:
        if os.path.getsize(file_path) < 128 * 1024:
             # logging.warning(f"Arquivo {os.path.basename(file_path)} muito pequeno para hash.")
             return None
        with open(file_path, "rb") as f:
            data = f.read(64 * 1024); f.seek(-64 * 1024, os.SEEK_END); data += f.read(64 * 1024)
        return hashlib.md5(data).hexdigest()
    except FileNotFoundError:
        logging.error(f"Arquivo não encontrado: {file_path}")
        return None
    except Exception as e:
        logging.error(f"Erro ao calcular hash de {os.path.basename(file_path)}: {e}")
        return None

def clean_filename(filename):
    # ... (código mantido, usar logging para debug se necessário) ...
    name, _ = os.path.splitext(filename)
    patterns_to_remove = [
        r'\b(1080p|720p|2160p|4k|dvdrip|brrip|bluray|web-dl|webrip|hdtv|x264|h264|x265|hevc|ac3|dts|aac|6ch|5\.1|dual|dublado|portuguese|comando\.to|psa)\b',
        r'\b(s\d{1,2}e\d{1,2}|season \d+|episode \d+)\b',
        r'\b(19|20)\d{2}\b',
        r'[-._\s]+'
    ]
    cleaned_name = re.sub(r'[-._]+', ' ', name)
    for pattern in patterns_to_remove:
         if 's\d{1,2}e\d{1,2}' not in pattern:
              cleaned_name = re.sub(pattern, '', cleaned_name, flags=re.IGNORECASE)
    cleaned_name = ' '.join(cleaned_name.split()).strip()
    season_episode_match = re.search(r'(s\d{1,2}e\d{1,2})', name, re.IGNORECASE)
    if season_episode_match:
         base_title_match = re.match(r'^(.*?)(s\d{1,2}e\d{1,2})', name, re.IGNORECASE)
         if base_title_match:
              base_title = re.sub(r'[-._]+', ' ', base_title_match.group(1)).strip()
              cleaned_name = f"{base_title} {season_episode_match.group(1).upper()}"
         else:
              cleaned_name = f"{cleaned_name} {season_episode_match.group(1).upper()}"
    # logging.debug(f"Nome limpo para query: '{cleaned_name}' (Original: '{filename}')")
    return cleaned_name


def search_subtitle_by_hash(token, file_hash):
    # ... (código mantido, usar logging para erros) ...
    headers = {**BASE_HEADERS, "Authorization": f"Bearer {token}"}
    params = {"moviehash": file_hash, "languages": TARGET_LANGUAGES}
    try:
        response = requests.get(f"{API_URL}/subtitles", headers=headers, params=params, timeout=20)
        if response.status_code == 200:
            data = response.json().get("data", [])
            return data, response.status_code
        else:
            # logging.warning(f"Erro HASH (Hash: {file_hash}, Status: {response.status_code})")
            return [], response.status_code
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro Conexão HASH (Hash: {file_hash}): {e}")
        return [], 599

def search_subtitle_by_query(token, query_string):
    # ... (código mantido, usar logging para erros) ...
    if not query_string: return [], 0
    # logging.info(f"Buscando por NOME (Query): '{query_string}'...") # Log movido para worker
    headers = {**BASE_HEADERS, "Authorization": f"Bearer {token}"}
    params = {"query": query_string, "languages": TARGET_LANGUAGES}
    try:
        response = requests.get(f"{API_URL}/subtitles", headers=headers, params=params, timeout=20)
        if response.status_code == 200:
            data = response.json().get("data", [])
            return data, response.status_code
        else:
            # logging.warning(f"Erro QUERY (Query: '{query_string}', Status: {response.status_code})")
            return [], response.status_code
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro Conexão QUERY (Query: '{query_string}'): {e}")
        return [], 599


def download_subtitle(token, subtitle_data, video_filepath):
    # ... (código mantido, usar logging para erros e sucesso) ...
    headers = {**BASE_HEADERS, "Authorization": f"Bearer {token}"}
    video_name = os.path.basename(video_filepath)
    try:
        if 'attributes' not in subtitle_data or 'files' not in subtitle_data['attributes'] or not subtitle_data['attributes']['files']:
             logging.error(f"Dados inválidos para download ({video_name}): {subtitle_data}")
             return False, 0
        file_id = subtitle_data['attributes']['files'][0]['file_id']
        download_link_payload = {'file_id': file_id}
        response_link = requests.post(f"{API_URL}/download", headers=headers, json=download_link_payload, timeout=15)
        if response_link.status_code != 200:
            logging.warning(f"Erro link download ({video_name}, file_id {file_id}): Código {response_link.status_code}")
            return False, response_link.status_code
        download_info = response_link.json()
        download_url = download_info.get('link')
        remaining_downloads = download_info.get('remaining')
        if remaining_downloads is not None:
             logging.info(f"Downloads restantes (conta atual): {remaining_downloads}")
        if not download_url:
            logging.error(f"Link download não encontrado ({video_name}): {download_info}")
            return False, 0
        logging.info(f"Baixando legenda para '{video_name}' de {download_url[:50]}...")
        response_download = requests.get(download_url, stream=True, timeout=60)
        response_download.raise_for_status()
        video_basename = os.path.splitext(video_name)[0]
        subtitle_filename = os.path.join(os.path.dirname(video_filepath), f"{video_basename}.srt")
        with open(subtitle_filename, 'wb') as f:
            for chunk in response_download.iter_content(chunk_size=8192): f.write(chunk)
        logging.info(f"Legenda salva: {subtitle_filename}")
        return True, 200
    except requests.exceptions.Timeout:
         logging.error(f"Timeout download ({video_name}).")
         return False, 599
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro rede download ({video_name}): {e}")
        return False, 599
    except KeyError as e:
        logging.error(f"Erro dados download ({video_name}, chave: {e}). Dados: {subtitle_data}")
        return False, 0
    except Exception as e:
        logging.error(f"Erro inesperado download ({video_name}): {e}")
        return False, 0

def find_videos_in_directory(directory):
    # ... (código mantido, usar logging) ...
    video_extensions = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv")
    video_files = []
    logging.info(f"Procurando vídeos em: {directory}")
    count = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(video_extensions):
                base_name, _ = os.path.splitext(file)
                srt_file = os.path.join(root, base_name + ".srt")
                if not os.path.exists(srt_file):
                    video_files.append(os.path.join(root, file))
                    count +=1
    logging.info(f"Encontrados {count} vídeos sem legenda .srt correspondente.")
    return video_files

# --- Função Worker para Threads ---
def process_video_file(video_path, token_manager):
    """ Processa um único arquivo de vídeo para encontrar e baixar legendas. """
    thread_name = threading.current_thread().name
    video_name = os.path.basename(video_path)
    logging.info(f"Processando: {video_name}")

    try:
        token, account = token_manager.get_token() # Obtém token inicial (pode logar aqui)
        logged_in_username = account['username'] if account else "N/A"
    except ConnectionError as e:
        logging.error(f"Falha ao obter token inicial para {video_name}: {e}. Abortando este arquivo.")
        return # Não pode continuar sem token

    file_hash = hash_file(video_path)
    subtitles = []
    subtitle_found = False
    best_subtitle = None # Guarda a legenda encontrada

    # --- Lógica de Busca com Retentativas e Re-login ---
    if file_hash:
        # logging.info(f"Hash: {file_hash}. Buscando por HASH [{TARGET_LANGUAGES}] com conta '{logged_in_username}'")
        search_attempts = 0
        max_search_attempts = 3 # Evitar loop infinito em caso de erro persistente

        while search_attempts < max_search_attempts:
            # Busca por Hash
            subtitles_hash, status_code_hash = search_subtitle_by_hash(token, file_hash)

            if subtitles_hash: # Encontrou por Hash
                # logging.info(f"Legenda encontrada via HASH para {video_name}.")
                best_subtitle = subtitles_hash[0]
                subtitle_found = True
                break # Sai do loop de tentativas

            elif status_code_hash in RELOGIN_STATUS_CODES: # Erro que pede re-login (Hash)
                logging.warning(f"Erro HASH (Status {status_code_hash}) para {video_name}. Tentando re-login.")
                search_attempts += 1
                try:
                    token, account = token_manager.force_relogin()
                    logged_in_username = account['username'] if account else "N/A"
                    logging.info(f"Re-login OK com '{logged_in_username}'. Retentando busca HASH para {video_name}.")
                    continue # Tenta a busca HASH novamente com novo token
                except ConnectionError:
                    logging.error(f"Falha no re-login para HASH de {video_name}. Abortando busca.")
                    break # Sai do loop de tentativas
            elif status_code_hash == 200: # Hash não encontrou (200 OK, lista vazia)
                # logging.info(f"HASH não encontrou para {video_name}. Tentando NOME.")
                break # Sai do loop de tentativas HASH, vai para NOME
            else: # Outro erro na busca HASH
                logging.error(f"Erro não recuperável na busca HASH para {video_name} (Status: {status_code_hash}). Abortando busca.")
                break # Sai do loop de tentativas

        # Se não encontrou por Hash, Tenta por Nome
        if not subtitle_found and file_hash: # Só tenta nome se hash foi calculado
            cleaned_name = clean_filename(video_name)
            if cleaned_name:
                 logging.info(f"Buscando por NOME '{cleaned_name}' [{TARGET_LANGUAGES}] com conta '{logged_in_username}'")
                 query_attempts = 0
                 while query_attempts < max_search_attempts:
                     subtitles_query, status_code_query = search_subtitle_by_query(token, cleaned_name)

                     if subtitles_query: # Encontrou por Query
                         # logging.info(f"Legenda encontrada via NOME para {video_name}.")
                         best_subtitle = subtitles_query[0]
                         subtitle_found = True
                         break # Sai do loop de tentativas QUERY

                     elif status_code_query in RELOGIN_STATUS_CODES: # Erro que pede re-login (Query)
                         logging.warning(f"Erro NOME (Status {status_code_query}) para {video_name}. Tentando re-login.")
                         query_attempts += 1
                         try:
                             token, account = token_manager.force_relogin()
                             logged_in_username = account['username'] if account else "N/A"
                             logging.info(f"Re-login OK com '{logged_in_username}'. Retentando busca NOME para {video_name}.")
                             continue # Tenta a busca QUERY novamente
                         except ConnectionError:
                             logging.error(f"Falha no re-login para NOME de {video_name}. Abortando busca.")
                             break
                     elif status_code_query == 200: # Query não encontrou (200 OK, lista vazia)
                          logging.info(f"Nenhuma legenda encontrada via NOME para {video_name}.")
                          break # Sai do loop de tentativas QUERY
                     else: # Outro erro na busca QUERY
                          logging.error(f"Erro não recuperável na busca NOME para {video_name} (Status: {status_code_query}).")
                          break # Sai do loop de tentativas
    elif not file_hash:
         logging.warning(f"Não foi possível calcular hash para {video_name}. Pulando busca.")

    # --- Download (se encontrou legenda) ---
    if subtitle_found and best_subtitle:
        subtitle_info = best_subtitle.get('attributes', {})
        lang = subtitle_info.get('language', '?')
        filename_sub = subtitle_info.get('filename', '?.srt')
        logging.info(f"Legenda selecionada para '{video_name}': [{lang.upper()}] {filename_sub}")

        download_attempts = 0
        while download_attempts < max_search_attempts: # Reusa max_search_attempts para download também
            download_success, download_status_code = download_subtitle(token, best_subtitle, video_path)

            if download_success:
                break # Download OK

            elif download_status_code in RELOGIN_STATUS_CODES: # Erro que pede re-login (Download)
                logging.warning(f"Erro Download (Status {download_status_code}) para {video_name}. Tentando re-login.")
                download_attempts += 1
                try:
                    token, account = token_manager.force_relogin()
                    logged_in_username = account['username'] if account else "N/A"
                    logging.info(f"Re-login OK com '{logged_in_username}'. Retentando download para {video_name}.")
                    continue # Tenta o download novamente
                except ConnectionError:
                    logging.error(f"Falha no re-login para DOWNLOAD de {video_name}. Abortando download.")
                    break
            else: # Outro erro no download
                logging.error(f"Falha não recuperável no download para {video_name} (Status: {download_status_code}).")
                break
    elif not subtitle_found and file_hash:
         # Log que não encontrou já foi feito dentro da lógica de busca
         pass


# --- Execução Principal Multithreaded ---
if __name__ == "__main__":
    if not API_KEY or API_KEY == "SUA_API_KEY_AQUI":
        logging.critical("API_KEY não configurada! Saia e configure.")
        exit(1)
    if not ACCOUNTS:
        logging.critical("Lista ACCOUNTS está vazia! Saia e configure.")
        exit(1)

    # Cria o gerenciador de tokens compartilhado
    try:
        token_manager = TokenManager(ACCOUNTS, API_KEY, API_URL, BASE_HEADERS)
        # Tenta obter um token inicial para validar pelo menos uma conta antes de iniciar threads
        logging.info("Validando login inicial...")
        _, initial_account = token_manager.get_token()
        logging.info(f"Login inicial validado com sucesso ({initial_account['username']}).")
        logging.info("-----------------------\n")
    except ConnectionError as e:
        logging.critical(f"Falha no login inicial com todas as contas: {e}")
        exit(1)
    except ValueError as e:
         logging.critical(f"Erro na configuração: {e}")
         exit(1)


    try:
        directory = input("Digite o caminho da pasta para buscar legendas: ")
        if not os.path.isdir(directory):
            logging.error("Diretório inválido!")
        else:
            video_files = find_videos_in_directory(directory)
            if not video_files:
                logging.info("Nenhum arquivo de vídeo (sem legenda .srt) encontrado.")
            else:
                # Cria e gerencia o pool de threads
                # Usar context manager garante que as threads terminem antes de sair
                with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix='SubWorker') as executor:
                    logging.info(f"Iniciando processamento de {len(video_files)} arquivos com {MAX_WORKERS} workers...")
                    # Submete cada tarefa ao executor
                    # executor.map é uma alternativa, mas submit dá mais controle se precisarmos dos Futures
                    futures = [executor.submit(process_video_file, video_path, token_manager) for video_path in video_files]

                    # Aguarda a conclusão de todas as tarefas (opcional, o 'with' já faz isso no exit)
                    # for future in concurrent.futures.as_completed(futures):
                    #     try:
                    #         future.result() # Pega resultado ou exceção da thread
                    #     except Exception as exc:
                    #         logging.error(f'Thread gerou uma exceção: {exc}')

                logging.info("Todas as tarefas foram submetidas e/ou concluídas.")

    except KeyboardInterrupt:
        logging.info("\nOperação cancelada pelo usuário.")
        # O executor tentará terminar as threads em andamento
    except Exception as e:
        logging.critical(f"\nErro inesperado ocorreu fora do loop principal: {e}")
        import traceback
        traceback.print_exc()

    logging.info("\nProcesso principal concluído.")