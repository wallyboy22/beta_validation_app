# utils/bigquery.py
#
# Este script gerencia todas as interações com o Google BigQuery para a aplicação de validação.
# Ele foi simplificado para trabalhar diretamente com a nomenclatura das tabelas no BigQuery,
# sem depender de uma tabela de metadados (como app_metadata_log ou sample_validation_log)
# para gerenciar versões ou logs detalhados.
#

import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
import os
from dotenv import load_dotenv
import uuid
from datetime import datetime, timezone
from utils.logger import app_logger
import re
import functools # ADICIONADO: Importar functools para caching

# --- Autenticação e inicialização do cliente BigQuery ---
if os.getenv("ENV") is None:
    load_dotenv()

try:
    bq_client = bigquery.Client(project="mapbiomas")
    app_logger.info("DB_INIT: Conexão com BigQuery estabelecida com sucesso.")
except Exception as e:
    app_logger.critical(f"DB_INIT: Erro ao conectar ao BigQuery: {str(e)}", exc_info=True)
    raise RuntimeError(f"Falha ao inicializar o cliente BigQuery: {e}")

# --- FUNÇÕES DE INTERAÇÃO COM BIGQUERY ---

def list_tables_in_dataset(project_id, dataset_id):
    full_dataset_id = f"{project_id}.{dataset_id}"
    app_logger.debug(f"DB_LIST: Iniciando listagem de tabelas no dataset: '{full_dataset_id}'...")
    try:
        tables = list(bq_client.list_tables(full_dataset_id))
        app_logger.debug(f"DB_LIST: Listagem concluída: {len(tables)} tabelas encontradas em '{full_dataset_id}'.")
        return tables
    except Exception as e:
        app_logger.error(f"DB_LIST: Erro ao listar tabelas no dataset '{full_dataset_id}': {str(e)}", exc_info=True)
        raise

def get_dataset_table(full_table_id):
    """
    Lê os dados de uma tabela BigQuery com o ID COMPLETO fornecido.
    Retorna um DataFrame do pandas.
    """
    app_logger.info(f"DB_FETCH: Iniciando consulta para carregar dados da tabela: '{full_table_id}'...")

    query = f"""
        SELECT *
        FROM `{full_table_id}`
        ORDER BY sample_id
    """
    try:
        df = bq_client.query(query).to_dataframe(max_results=None)

        app_logger.info(f"DB_FETCH: Tabela '{full_table_id}' carregada com sucesso ({len(df)} registros encontrados).")
        return df
    except Exception as e:
        app_logger.error(f"DB_FETCH: Erro ao consultar tabela '{full_table_id}': {str(e)}", exc_info=True)
        raise

def get_validation_timestamps(full_table_id):
    """
    Busca apenas os timestamps de validação de uma tabela BigQuery.
    Útil para o gráfico de progresso.
    Retorna um DataFrame com a coluna 'validation_timestamp'.
    Lida com a possível ausência da coluna.
    """
    app_logger.info(f"DB_FETCH: Buscando timestamps de validação da tabela: '{full_table_id}'...")
    try:
        # Primeiro, verifica se a coluna existe
        table_ref = bq_client.get_table(full_table_id)
        if not any(field.name == 'validation_timestamp' for field in table_ref.schema):
            app_logger.warning(f"DB_FETCH: Coluna 'validation_timestamp' não encontrada na tabela '{full_table_id}'. Retornando DataFrame vazio.")
            return pd.DataFrame(columns=['validation_timestamp'])

        query = f"""
            SELECT validation_timestamp
            FROM `{full_table_id}`
            WHERE status = 'VALIDATED' AND validation_timestamp IS NOT NULL
        """
        df = bq_client.query(query).to_dataframe(max_results=None)
        app_logger.info(f"DB_FETCH: {len(df)} timestamps de validação encontrados para a tabela '{full_table_id}'.")
        return df
    except Exception as e:
        app_logger.error(f"DB_FETCH: Erro ao buscar timestamps de validação da tabela '{full_table_id}': {str(e)}", exc_info=True)
        # Retorna um DataFrame vazio para evitar quebras no frontend
        return pd.DataFrame(columns=['validation_timestamp'])


def _sanitize_for_bq(text):
    if not text:
        return ""
    text = re.sub(r'[^a-zA-Z0-9_ ]', '', text).strip()
    return re.sub(r'\s+', '_', text)

def ensure_validation_table_exists(
        original_dataset_key, new_version_timestamp, user_id="desconhecido", team_id="desconhecida",
        description="", biome_filter=None, class_filter=None, reset_data=True
    ):
    project_id = bq_client.project
    dataset_id = "mapbiomas_brazil_validation"

    original_table_name_convention = f"APP_0-original_{original_dataset_key}"
    original_table_full_id = f"{project_id}.{dataset_id}.{original_table_name_convention}"

    sanitized_desc = _sanitize_for_bq(description)
    desc_part = f"_{sanitized_desc}" if sanitized_desc else ""

    filter_parts_for_name = [] # Para o nome da tabela
    where_clauses = [] # Para a cláusula WHERE da query

    if biome_filter and isinstance(biome_filter, list) and len(biome_filter) > 0:
        # Para o nome da tabela, use uma versão sanitizada e unida
        filter_parts_for_name.append("biome_" + "_".join([_sanitize_for_bq(str(val)) for val in biome_filter])) # MODIFICADO: str(val) para sanitização
        # Para a query, adicione aspas simples e escape
        biome_values_str = ', '.join([f"'{str(val).replace("'", "''")}'" for val in biome_filter])
        where_clauses.append(f"biome_name IN ({biome_values_str})")
    
    if class_filter and isinstance(class_filter, list) and len(class_filter) > 0:
        # Para o nome da tabela
        filter_parts_for_name.append("class_" + "_".join([_sanitize_for_bq(str(val)) for val in class_filter])) # MODIFICADO: str(val) para sanitização
        # Para a query
        class_values_str = ', '.join([f"'{str(val).replace("'", "''")}'" for val in class_filter])
        where_clauses.append(f"class_name IN ({class_values_str})")
    
    filter_name_part = f"_{'_'.join(filter_parts_for_name)}" if filter_parts_for_name else "" # Usar essa para o nome da tabela

    validation_prefix = f"APP_1-validation_{original_dataset_key}"
    # Use filter_name_part que foi construída para o nome da tabela
    new_validation_table_name = f"{validation_prefix}{filter_name_part}{desc_part}_{new_version_timestamp}" 
    new_validation_table_full_id = f"{project_id}.{dataset_id}.{new_validation_table_name}"

    app_logger.info(f"DB_ENSURE_TABLE: Garantindo a existência da tabela: '{new_validation_table_full_id}'...")

    try:
        bq_client.get_table(new_validation_table_full_id)
        app_logger.info(f"DB_ENSURE_TABLE: Tabela de validação '{new_validation_table_full_id}' já existe. Nenhuma cópia necessária.")
        return new_validation_table_full_id, False
    except Exception as e:
        if "Not found" in str(e) or "404" in str(e):
            app_logger.info(f"DB_ENSURE_TABLE: Tabela de validação '{new_validation_table_full_id}' não encontrada. Copiando da original '{original_table_full_id}'...")
            
            # --- Construção da Query de Criação da Tabela ---
            select_columns_list = []
            
            # Obter esquema da tabela original para verificar colunas existentes
            try:
                original_table_obj = bq_client.get_table(original_table_full_id)
                existing_cols = [field.name for field in original_table_obj.schema]
            except Exception as orig_e:
                app_logger.error(f"DB_ENSURE_TABLE: Erro: Tabela original '{original_table_full_id}' não encontrada para cópia. Detalhes: {str(orig_e)}", exc_info=True)
                raise ValueError(f"Tabela original '{original_table_full_id}' não encontrada. Por favor, verifique se 'APP_0-original_{original_dataset_key}' existe no seu BigQuery.")

            # Define as colunas que podem ter seus valores reiniciados
            reset_cols = ["definition", "reason", "status", "validation_timestamp"]

            for col in existing_cols:
                # Usar backticks em todos os nomes de coluna para compatibilidade máxima no BigQuery
                quoted_col = f"`{col}`" 
                if col in reset_cols and reset_data:
                    if col == "status":
                        select_columns_list.append(f"CAST('PENDING' AS STRING) AS status")
                    elif col == "validation_timestamp":
                        select_columns_list.append(f"CAST(NULL AS TIMESTAMP) AS validation_timestamp") 
                    else: # definition, reason
                        select_columns_list.append(f"CAST(NULL AS STRING) AS {quoted_col}") # Use quoted_col aqui também
                else:
                    select_columns_list.append(quoted_col)

            # Garante que 'validation_timestamp' existe, adicionando-o se não estiver na original
            if 'validation_timestamp' not in existing_cols:
                app_logger.info(f"DB_ENSURE_TABLE: Coluna 'validation_timestamp' não encontrada na original '{original_table_full_id}'. Adicionando como NULL na nova tabela.")
                select_columns_list.append(f"CAST(NULL AS TIMESTAMP) AS validation_timestamp")
            
            where_clause_str = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            create_table_query = f"""
                CREATE TABLE `{new_validation_table_full_id}` AS
                SELECT
                    {', '.join(select_columns_list)}
                FROM `{original_table_full_id}`
                {where_clause_str}
            """
            app_logger.debug(f"DB_ENSURE_TABLE: Executando CREATE TABLE AS SELECT para '{new_validation_table_full_id}'. Query:\n{create_table_query}")
            query_job = bq_client.query(create_table_query)
            query_job.result()
            app_logger.info(f"DB_ENSURE_TABLE: Tabela '{new_validation_table_full_id}' criada com sucesso com filtros e reset_data={reset_data}.")
            
            return new_validation_table_full_id, True
        else:
            app_logger.error(f"DB_ENSURE_TABLE: Erro inesperado ao verificar/criar tabela de validação '{new_validation_table_full_id}': {str(e)}", exc_info=True)
            raise

@functools.lru_cache(maxsize=32) # ADICIONADO: Cache para valores únicos de colunas
def get_unique_column_values(full_table_id, column_name):
    """
    Busca os valores únicos de uma coluna específica em uma tabela BigQuery.
    Retorna uma lista de dicionários no formato {'label': 'Valor', 'value': 'Valor'}
    adequado para dcc.Dropdown.
    """
    app_logger.info(f"DB_FETCH: Buscando valores únicos da coluna '{column_name}' da tabela '{full_table_id}'...")
    
    try:
        table_ref = bq_client.get_table(full_table_id)
        if not any(field.name == column_name for field in table_ref.schema):
            app_logger.warning(f"DB_FETCH: Coluna '{column_name}' não encontrada na tabela '{full_table_id}'. Retornando lista vazia.")
            return []
    except Exception as e:
        app_logger.error(f"DB_FETCH: Erro ao verificar esquema da tabela '{full_table_id}' para coluna '{column_name}': {str(e)}", exc_info=True)
        return []

    # Uso de backticks (`) para nomes de coluna com espaços, como "biome_name" e "class_Name"
    query = f"""
        SELECT DISTINCT `{column_name}`  -- Adicionado backticks para segurança, caso o nome tenha caracteres especiais
        FROM `{full_table_id}`
        WHERE `{column_name}` IS NOT NULL
        ORDER BY `{column_name}`
    """
    try:
        df = bq_client.query(query).to_dataframe(max_results=None)
        
        options = []
        if not df.empty:
            for index, row in df.iterrows():
                # Corrigido aqui: Usar o próprio valor da coluna como 'value'
                options.append({'label': str(row[column_name]), 'value': str(row[column_name])}) 
        app_logger.info(f"DB_FETCH: Valores únicos para '{column_name}' obtidos: {len(options)} opções.")
        return options
    except Exception as e:
        app_logger.error(f"DB_FETCH: Erro ao buscar valores únicos para coluna '{column_name}' na tabela '{full_table_id}': {str(e)}", exc_info=True)
        raise # É importante propagar para que o Dash saiba que o callback falhou.

def update_sample(full_table_id, sample_id, definition, reason, status):
    """
    Atualiza os campos 'definition', 'reason', 'status' e 'validation_timestamp'
    de uma amostra específica em uma tabela de validação no BigQuery.
    """
    app_logger.info(f"DB_UPDATE: Iniciando atualização da amostra {sample_id} na tabela: '{full_table_id}'...")
    try:
        def format_value_for_sql(val):
            if val is None or str(val).strip() == "":
                return "NULL"
            else:
                return f"'{str(val).replace('\'', '\'\'')}'"

        current_utc_timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds') 

        validation_timestamp_update = ""
        if status == "VALIDATED":
            validation_timestamp_update = f", validation_timestamp = TIMESTAMP('{current_utc_timestamp}')" # MODIFICADO: Uso de TIMESTAMP()
        else: 
            validation_timestamp_update = ", validation_timestamp = NULL"

        query = f"""
        UPDATE `{full_table_id}`
        SET
            definition = {format_value_for_sql(definition)},
            reason = {format_value_for_sql(reason)},
            status = {format_value_for_sql(status)}
            {validation_timestamp_update}
        WHERE sample_id = {sample_id}
        """
        app_logger.debug(f"DB_UPDATE: Query de atualização a ser executada: {query}")
        
        job_config = bigquery.QueryJobConfig(use_legacy_sql=False)
        query_job = bq_client.query(query, job_config=job_config)
        query_job.result() 

        app_logger.info(f"DB_UPDATE: Amostra {sample_id} atualizada com sucesso na tabela '{full_table_id}'.")
    except Exception as e:
        app_logger.error(f"DB_UPDATE: Erro CRÍTICO ao atualizar amostra {sample_id} na tabela '{full_table_id}'. Erro: {str(e)}", exc_info=True)
        raise
        
# Vamos ajustar a função execute_query para ser mais genérica
def execute_query(query):
    """
    Executa uma consulta SQL no BigQuery usando Standard SQL.
    Retorna os resultados como lista de dicionários para SELECT,
    ou None para DML (UPDATE, INSERT, DELETE).
    """
    app_logger.debug("DB_EXEC_QUERY: Executando consulta SQL no BigQuery...")
    try:
        job_config = bigquery.QueryJobConfig(use_legacy_sql=False)
        query_job = bq_client.query(query, job_config=job_config)
        
        # Se for uma query DML (UPDATE, INSERT, DELETE), result() não terá to_dataframe
        # Verifica se a query é uma SELECT para tentar converter para DataFrame
        if query.strip().upper().startswith("SELECT"):
            df = query_job.to_dataframe(max_results=None)
            app_logger.debug(f"DB_EXEC_QUERY: Consulta SELECT SQL executada com sucesso ({len(df)} registros retornados).")
            return df.to_dict("records")
        else:
            query_job.result() # Para DML, apenas espera a conclusão
            app_logger.debug("DB_EXEC_QUERY: Consulta DML (UPDATE/INSERT/DELETE) SQL executada com sucesso.")
            return None # Não retorna dados para DML
    except Exception as e:
        app_logger.error(f"DB_EXEC_QUERY: Erro ao executar consulta SQL: {str(e)}", exc_info=True)
        raise

def get_all_validation_tables_for_dataset(dataset_key):
    project_id = bq_client.project
    dataset_id = "mapbiomas_brazil_validation"

    validation_prefix_search = f"APP_1-validation_{dataset_key}_%"

    query = f"""
        SELECT table_name, creation_time
        FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.TABLES`
        WHERE table_name LIKE '{validation_prefix_search}'
        ORDER BY creation_time DESC
    """
    app_logger.debug(f"DB_METADATA_FETCH: QUERY EXECUTADA para listar versões: {query}")

    results = execute_query(query)
    app_logger.debug(f"DB_METADATA_FETCH: RESULTADOS BRUTOS da query de listagem: {results}")

    formatted_results = []
    if results: # ADICIONADO: Verifica se results não é None
        for row in results:
            table_name = row['table_name']
            creation_time_dt = pd.to_datetime(row['creation_time'], utc=True)

            base_prefix = f"APP_1-validation_{dataset_key}"

            description_in_name = ""
            # MODIFICADO: Ajuste na lógica para extrair descrição, lidando com os filtros no nome
            # Ex: APP_1-validation_dataset_biome_Caatinga_class_Floresta_Descricao_20250726120000
            # Extrair o timestamp final e tudo que estiver antes dele é parte do nome/filtro/descrição
            parts_after_base = table_name[len(base_prefix):].strip('_').split('_')

            if len(parts_after_base) > 0:
                timestamp_str = parts_after_base[-1]
                if len(timestamp_str) == 14 and timestamp_str.isdigit(): # Verifica se é um timestamp
                    name_parts_without_timestamp = parts_after_base[:-1]
                    if name_parts_without_timestamp:
                        # Remove partes de filtro para isolar a descrição
                        filtered_name_parts = []
                        skip_next = False
                        for i, part in enumerate(name_parts_without_timestamp):
                            if skip_next:
                                skip_next = False
                                continue
                            if part in ["biome", "class"] and i + 1 < len(name_parts_without_timestamp):
                                # Se for 'biome' ou 'class', pula o próximo que é o valor do filtro
                                skip_next = True
                            else:
                                filtered_name_parts.append(part)
                        description_in_name = ' '.join(filtered_name_parts).replace('_', ' ')
            
            display_description = description_in_name.title() if description_in_name else "Versão Padrão"


            formatted_results.append({
                "table_id": f"{project_id}.{dataset_id}.{table_name}",
                "description": display_description,
                "created_at": creation_time_dt.isoformat(),
                "created_by_user": "N/A",
                "created_by_team": "N/A",
                "status": "N/A"
            })

    app_logger.info(f"DB_METADATA_FETCH: Encontradas {len(formatted_results)} tabelas de validação para o dataset base '{dataset_key}' diretamente do BQ.")
    return formatted_results

def _debug_list_all_tables_in_validation_dataset_and_log():
    project_id = bq_client.project
    dataset_id = "mapbiomas_brazil_validation"

    app_logger.warning(f"DB_DEBUG_ALL_TABLES: INICIANDO DEBUG: Listando TODAS as tabelas em '{project_id}.{dataset_id}'")
    try:
        query = f"""
            SELECT table_name, creation_time
            FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.TABLES`
            ORDER BY table_name
        """
        results = execute_query(query)

        if results:
            app_logger.warning(f"DB_DEBUG_ALL_TABLES: Tabelas encontradas no dataset '{dataset_id}':")
            for row in results:
                app_logger.warning(f"DB_DEBUG_ALL_TABLES:   - {row['table_name']} (Criado em: {row['creation_time']})")
        else:
            app_logger.warning(f"DB_DEBUG_ALL_TABLES: Nenhuma tabela encontrada em '{dataset_id}'.")
    except Exception as e:
        app_logger.error(f"DB_DEBUG_ALL_TABLES: ERRO ao listar todas as tabelas para depuração: {e}", exc_info=True)

def discover_datasets(project_id, dataset_id):
    prefix = "APP_0-original_"
    query = f"""
        SELECT table_name
        FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.TABLES`
        WHERE table_name LIKE '{prefix}%'
        ORDER BY table_name
    """
    app_logger.info(f"DB_DISCOVER: Descobrindo datasets com prefixo '{prefix}'...")

    df = bq_client.query(query).to_dataframe(max_results=None)

    if df.empty:
        app_logger.warning("DB_DISCOVER: Nenhum dataset original encontrado.")
        return []

    options = []
    for table_name in df['table_name']:
        key = table_name.replace(prefix, '')
        label = key.replace('_', ' ').title()
        options.append({'label': label, 'value': key})

    app_logger.info(f"DB_DISCOVER: Datasets originais descobertos: {len(options)}.")
    return options

def get_sample_coordinates(sample_id, full_table_id):
    app_logger.info(f"DB_COORDS: Buscando coordenadas para amostra '{sample_id}' na tabela '{full_table_id}'...")
    query = f"""
    SELECT geometry
    FROM `{full_table_id}`
    WHERE sample_id = {int(sample_id)}
    """
    try:
        result = execute_query(query)
        if not result:
            app_logger.warning(f"DB_COORDS: Amostra '{sample_id}' não encontrada na tabela '{full_table_id}'.")
            return None, None

        import shapely.wkt
        geom = shapely.wkt.loads(result[0]["geometry"])
        app_logger.info(f"DB_COORDS: Coordenadas para amostra '{sample_id}' obtidas: ({geom.y}, {geom.x}).")
        return geom.y, geom.x
    except Exception as e:
        app_logger.error(f"DB_COORDS: Erro ao buscar coordenadas para amostra '{sample_id}' na tabela '{full_table_id}': {str(e)}", exc_info=True)
        return None, None

def delete_validation_version(table_id_to_delete):
    if not table_id_to_delete:
        app_logger.warning("DB_DELETE: Tentativa de apagar versão com ID nulo.")
        return False

    try:
        app_logger.warning(f"DB_DELETE: Iniciando exclusão da tabela: '{table_id_to_delete}'...")
        bq_client.delete_table(table_id_to_delete)
        app_logger.info(f"DB_DELETE: Tabela '{table_id_to_delete}' apagada com sucesso do BigQuery.")
        return True
    except Exception as e:
        app_logger.error(f"DB_DELETE: Erro ao apagar a tabela '{table_id_to_delete}': {e}", exc_info=True)
        return False