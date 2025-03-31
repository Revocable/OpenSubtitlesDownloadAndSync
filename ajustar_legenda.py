import os
import re
import argparse
from pathlib import Path
import subprocess
from datetime import datetime, timedelta

def parse_time(time_str):
    """Converte string de tempo SRT para milissegundos"""
    try:
        time_format = "%H:%M:%S,%f"
        time_obj = datetime.strptime(time_str, time_format)
        return int(time_obj.hour * 3600000 + 
                   time_obj.minute * 60000 + 
                   time_obj.second * 1000 + 
                   time_obj.microsecond // 1000)
    except ValueError:
        return None

def to_srt_time(milliseconds):
    """Converte milissegundos para formato de tempo SRT"""
    if milliseconds < 0:
        milliseconds = 0
    hours = milliseconds // 3600000
    milliseconds %= 3600000
    minutes = milliseconds // 60000
    milliseconds %= 60000
    seconds = milliseconds // 1000
    milliseconds %= 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def extract_embedded_subtitle(video_path):
    """Extrai legendas de forma otimizada sem processar o vídeo inteiro"""
    output_path = video_path.parent / "temp_embedded.srt"
    
    # Tenta usar mkvextract para arquivos MKV (já é eficiente por padrão)
    if video_path.suffix.lower() == '.mkv':
        try:
            # Identifica a primeira pista de legenda text-based
            track_info = subprocess.run(
                ['mkvinfo', str(video_path)],
                capture_output=True,
                text=True,
                check=True
            ).stdout
            
            subtitle_track = None
            current_track_number = None
            track_type = None
            codec_id = None
            
            for line in track_info.split('\n'):
                line = line.strip()
                
                if '|+ A track' in line:
                    # Nova pista encontrada, resetar informações
                    current_track_number = None
                    track_type = None
                    codec_id = None
                
                elif '| + Track number: ' in line:
                    # Formato corrigido para extrair apenas o ID do track para mkvextract
                    track_match = re.search(r'Track number: (\d+)', line)
                    if track_match:
                        current_track_number = track_match.group(1)
                
                elif '| + Track type: ' in line and 'subtitles' in line:
                    track_type = 'subtitles'
                
                elif '| + Codec ID: ' in line:
                    codec_id = line.split('Codec ID: ')[1].strip().lower()
                    
                    # Se já temos todas as informações necessárias para uma pista de legenda
                    if current_track_number and track_type == 'subtitles' and codec_id and \
                       any(codec in codec_id for codec in ['srt', 'subrip', 'ass', 'ssa', 's_text']):
                        subtitle_track = current_track_number
                        break
            
            if subtitle_track:
                subprocess.run(
                    ['mkvextract', 'tracks', str(video_path), f'{subtitle_track}:{output_path}'],
                    check=True,
                    capture_output=True
                )
                if output_path.exists():
                    return output_path
            
        except Exception as e:
            print(f"Erro com mkvextract: {str(e)}. Usando ffmpeg...")

    # Otimização para ffmpeg - extrair apenas os metadados e os primeiros segundos
    try:
        # Primeiro verifica a duração do vídeo para calcular um tempo de segmentação adequado
        probe_result = subprocess.run(
            [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 's:0',
                '-show_entries', 'stream=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ],
            capture_output=True,
            text=True,
            check=False
        )
        
        # Determina quanto do vídeo processar - apenas o suficiente para obter as primeiras legendas
        # Por padrão, extrai apenas os primeiros 2 minutos
        duration = 120  # 2 minutos em segundos
        try:
            if probe_result.returncode == 0 and probe_result.stdout.strip():
                full_duration = float(probe_result.stdout.strip())
                # Se o vídeo for muito curto, use a duração completa
                if full_duration < 120:
                    duration = full_duration
        except (ValueError, TypeError):
            pass
            
        # Extrai apenas as legendas dos primeiros minutos do vídeo
        subprocess.run(
            [
                'ffmpeg',
                '-y',
                '-hide_banner',
                '-loglevel', 'error',
                '-ss', '0',  # Começa do início
                '-t', str(duration),  # Processa apenas os primeiros minutos
                '-i', str(video_path),
                '-map', '0:s:0?',
                '-c:s', 'srt',
                str(output_path)
            ],
            check=True,
            capture_output=True
        )
        
        # Se a extração falhar ou não produzir um arquivo válido, tenta uma abordagem alternativa
        if not output_path.exists() or os.path.getsize(output_path) == 0:
            # Tenta extrair usando outra sintaxe
            subprocess.run(
                [
                    'ffmpeg',
                    '-y',
                    '-hide_banner',
                    '-loglevel', 'error',
                    '-i', str(video_path),
                    '-ss', '0',
                    '-t', str(duration),
                    '-map', '0:s:0?',
                    '-c:s', 'srt',
                    str(output_path)
                ],
                check=True,
                capture_output=True
            )
            
        return output_path if output_path.exists() and os.path.getsize(output_path) > 0 else None
    except subprocess.CalledProcessError as e:
        print(f"Erro ao extrair legenda: {e.stderr.decode() if e.stderr else str(e)}")
        return None

def get_first_subtitle_time(srt_path):
    """Obtém o tempo da primeira legenda válida"""
    try:
        with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', line)
                if time_match:
                    return parse_time(time_match.group(1))
        return None
    except Exception as e:
        print(f"Erro ao ler arquivo de legenda {srt_path}: {str(e)}")
        return None

def adjust_subtitle_time(content, offset_ms):
    """Ajusta todos os tempos na legenda com segurança"""
    def adjust_match(match):
        start = parse_time(match.group(1)) or 0
        end = parse_time(match.group(2)) or 0
        new_start = max(start + offset_ms, 0)
        new_end = max(end + offset_ms, 0)
        return f"{to_srt_time(new_start)} --> {to_srt_time(new_end)}"
    
    return re.sub(
        r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})',
        adjust_match,
        content
    )

def process_files(folder_path):
    """Processa todos os arquivos na pasta e em suas subpastas"""
    folder = Path(folder_path)
    
    # Alterado para rglob para busca recursiva
    for video_file in folder.rglob('*.*'):
        if video_file.suffix.lower() not in ['.mkv', '.mp4', '.avi', '.mov']:
            continue
        
        print(f"\nProcessando: {video_file.name}")
        
        # Verifica se há um arquivo SRT com nome correspondente
        srt_path = video_file.with_suffix('.srt')
        
        # Verifica se existe um arquivo SRT alternativo (sem o nome completo)
        if not srt_path.exists():
            # Tenta encontrar uma legenda com nome mais simples
            short_name = re.sub(r'\.([^.]+)$', '', video_file.stem)
            simplified_name = re.sub(r'(\.REPACK|\.RERiP|\.\d+p|\.AMZN|\.WEBRip|\.DD5\.1|\.x264|-.+).*', '', video_file.stem)
            
            alternative_srts = list(folder.glob(f"{simplified_name}*.srt"))
            if not alternative_srts:
                alternative_srts = list(folder.glob(f"{short_name}*.srt"))
            
            if alternative_srts:
                srt_path = alternative_srts[0]
                print(f"Encontrou arquivo de legenda alternativo: {srt_path.name}")
            else:
                print(f"Arquivo de legenda não encontrado: {srt_path.name}")
                continue
        
        # Extrai legendas embutidas de forma otimizada
        embedded_srt = extract_embedded_subtitle(video_file)
        if not embedded_srt:
            print(f"Não foi possível extrair legenda embutida do vídeo.")
            continue
            
        try:
            embedded_time = get_first_subtitle_time(embedded_srt)
            external_time = get_first_subtitle_time(srt_path)
            
            if None in [embedded_time, external_time]:
                print("Não foi possível detectar tempos válidos nas legendas")
                continue
                
            offset = embedded_time - external_time
            print(f"Offset calculado: {offset} ms")
            
            with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            new_content = adjust_subtitle_time(content, offset)
            
            # Cria backup e salva ajustes
            backup_path = srt_path.with_suffix('.srt.bak')
            if backup_path.exists():
                backup_path.unlink()
            srt_path.rename(backup_path)
            
            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            print(f"Legenda ajustada. Backup salvo em: {backup_path.name}")
            
        except Exception as e:
            print(f"Erro durante o processamento: {str(e)}")
        finally:
            if embedded_srt and embedded_srt.exists():
                try:
                    embedded_srt.unlink()
                except Exception as e:
                    print(f"Erro ao remover arquivo temporário: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Sincronizador de Legendas 3.0 - Extração eficiente e ajuste automático de timing',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        'pasta',
        type=str,
        help='Caminho da pasta contendo os arquivos de vídeo e legendas'
    )
    args = parser.parse_args()
    
    if not Path(args.pasta).exists():
        print("Erro: Pasta especificada não existe!")
        exit(1)
        
    process_files(args.pasta)
    print("\nSincronização concluída com sucesso!")
