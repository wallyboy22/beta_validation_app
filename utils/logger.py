import logging
import os
from logging.handlers import RotatingFileHandler # Para rotação de arquivos de log

# REMOVEMOS COMPLETAMENTE A LISTA GLOBAL LOGS = []
# E a lógica de salvar JSON por linha que estava acoplada

def setup_app_logger(log_level_env_var='APP_LOG_LEVEL', default_level='INFO', log_file_name='app_events.log', log_dir='logs'):
    """
    Configura o logger principal da aplicação.

    Args:
        log_level_env_var (str): Nome da variável de ambiente para definir o nível de log.
        default_level (str): Nível de log padrão se a variável de ambiente não estiver definida.
        log_file_name (str): Nome do arquivo de log.
        log_dir (str): Diretório onde os arquivos de log serão salvos.
    """
    log_level_str = os.environ.get(log_level_env_var, default_level).upper()
    numeric_level = getattr(logging, log_level_str, None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Nível de log inválido: {log_level_str}')

    # Obtém o logger raiz ou um logger nomeado para sua aplicação.
    # Usar '__name__' é uma boa prática para loggers de módulos,
    # mas para um logger central de aplicação, 'mapbiomas_app' ou algo similar é comum.
    # Se você quer um único logger para tudo, pode usar logging.getLogger() sem nome.
    logger = logging.getLogger("mapbiomas_app") # Nomeia o logger da sua aplicação
    logger.setLevel(numeric_level)

    # Evita que handlers sejam adicionados múltiplas vezes ao recarregar (ex: em debug mode do Dash)
    # Isso é CRÍTICO para evitar log duplicado.
    if not logger.handlers:
        # Handler para o console (terminal)
        console_handler = logging.StreamHandler()
        # Formato para o console: mais conciso
        console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # Handler para arquivo (com rotação)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        log_file_path = os.path.join(log_dir, log_file_name)

        # RotatingFileHandler: Rotaciona o arquivo de log quando ele atinge um certo tamanho
        # maxBytes: 5 MB, backupCount: mantém os 5 últimos arquivos rotacionados
        file_handler = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=5)
        # Formato para o arquivo: pode ser mais detalhado
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s - [file:%(pathname)s, line:%(lineno)d]')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger

# Inicializa o logger principal da aplicação quando o módulo é importado
app_logger = setup_app_logger()
