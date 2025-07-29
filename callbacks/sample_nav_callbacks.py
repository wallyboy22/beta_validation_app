# callbacks/sample_nav_callbacks.py

import pandas as pd
from dash import Output, Input, State, callback_context, no_update
from utils.logger import app_logger

# --- FUNÇÕES AUXILIARES PARA NAVEGAÇÃO ---
def get_next_sample(current_id, table_data, only_unvalidated=False):
    app_logger.debug(f"NAV: Buscando próxima amostra de {current_id}. Apenas não validadas: {only_unvalidated}")
    if not table_data:
        app_logger.warning("NAV: Tabela vazia para navegação (get_next_sample).")
        return current_id

    if isinstance(table_data, pd.DataFrame):
        df = table_data
    elif isinstance(table_data, list):
        df = pd.DataFrame(table_data)
    else:
        app_logger.error("NAV: Formato de tabela inválido para navegação (get_next_sample).", extra={"details": {"table_data_type": type(table_data)}})
        return current_id

    if df.empty or 'sample_id' not in df.columns:
        app_logger.warning("NAV: Nenhum resultado após aplicar filtros para navegação. Retornando ID atual.")
        return current_id

    if only_unvalidated and 'status' in df.columns:
        df_filtered = df[df['status'] != 'VALIDATED']
        app_logger.debug(f"NAV: {len(df_filtered)} amostras não validadas.")
    else:
        df_filtered = df

    if df_filtered.empty:
        app_logger.info("NAV: Nenhuma amostra não validada encontrada ou tabela filtrada vazia.")
        return current_id

    df_filtered = df_filtered.sort_values("sample_id")
    ids = df_filtered["sample_id"].tolist()

    if current_id in ids:
        idx = ids.index(current_id)
        if idx + 1 < len(ids):
            next_id = ids[idx + 1]
            app_logger.info(f"NAV: Próxima amostra encontrada: {next_id}")
            return next_id
    
    # Se o current_id não está nas amostras não validadas restantes (ex: já foi validado)
    # ou se chegamos ao final da lista de não validadas, volta para a primeira não validada.
    if ids:
        app_logger.info(f"NAV: Retornando a primeira amostra não validada ou reiniciando a lista: {ids[0]}")
        return ids[0]

    app_logger.warning(f"NAV: Não foi possível encontrar a próxima amostra não validada após {current_id} ou lista vazia. Retornando o ID atual.")
    return current_id

def get_previous_sample(current_id, table_data, only_unvalidated=False):
    app_logger.debug(f"NAV: Buscando amostra anterior de {current_id}. Apenas não validadas: {only_unvalidated}")
    if not table_data:
        app_logger.warning("NAV: Tabela vazia para navegação (get_previous_sample).")
        return current_id

    if isinstance(table_data, pd.DataFrame):
        df = table_data
    elif isinstance(table_data, list):
        df = pd.DataFrame(table_data)
    else:
        app_logger.error("NAV: Formato de tabela inválido para navegação (get_previous_sample).", extra={"details": {"table_data_type": type(table_data)}})
        return current_id

    if df.empty or 'sample_id' not in df.columns:
        app_logger.warning("NAV: Nenhum resultado após aplicar filtros para navegação. Retornando ID atual.")
        return current_id

    if only_unvalidated and 'status' in df.columns:
        df_filtered = df[df['status'] != 'VALIDATED']
        app_logger.debug(f"NAV: {len(df_filtered)} amostras não validadas.")
    else:
        df_filtered = df

    if df_filtered.empty:
        app_logger.info("NAV: Nenhuma amostra não validada encontrada ou tabela filtrada vazia.")
        return current_id

    df_filtered = df_filtered.sort_values("sample_id")
    ids = df_filtered["sample_id"].tolist()

    if current_id in ids:
        idx = ids.index(current_id)
        if idx > 0:
            prev_id = ids[idx - 1]
            app_logger.info(f"NAV: Amostra anterior encontrada: {prev_id}")
            return prev_id
    
    # Se o current_id não está nas amostras não validadas restantes (ex: já foi validado)
    # ou se chegamos ao início da lista de não validadas, volta para a última não validada.
    if ids:
        app_logger.info(f"NAV: Retornando a última amostra não validada ou reiniciando a lista: {ids[-1]}")
        return ids[-1]

    app_logger.warning(f"NAV: Não foi possível encontrar a amostra anterior não validada a {current_id} ou lista vazia. Retornando o ID atual.")
    return current_id

def register_callbacks(app):
    """
    Registra callbacks relacionados à navegação entre amostras.
    """
    # Callback para go-to-next-sample-trigger (dispara navegação automática)
    @app.callback(
        Output('filter-id', 'value', allow_duplicate=True),
        Input('go-to-next-sample-trigger', 'data'),
        prevent_initial_call=True
    )
    def go_to_next_sample_from_trigger(next_sample_id):
        if next_sample_id is not None:
            app_logger.info(f"NAV_LOGIC: Trigger para ir para a amostra: {next_sample_id}")
            return next_sample_id
        return no_update