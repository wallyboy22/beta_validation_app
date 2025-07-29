# callbacks/table_callbacks.py

import pandas as pd
from dash import Output, Input, State, callback_context, no_update
import dash_bootstrap_components as dbc

from utils.bigquery import get_dataset_table, update_sample
from utils.constants import VISIBLE_COLUMNS
from utils.logger import app_logger

def register_callbacks(app):
    """
    Registra callbacks relacionados à tabela (AgGrid) da aplicação.
    """

    # Callback para selecionar a linha da tabela ao carregar E sincronizar com filter-id
    @app.callback(
        Output("sample-table", "selectedRows"),
        Input("sample-table", "rowData"),
        Input("filter-id", "value"),
        Input("tabs", "active_tab"), # ADICIONADO: Input da aba ativa para controlar execução
        prevent_initial_call=False
    )
    def select_row_on_table_data_or_id_change(rowData, filter_id_value, active_tab_id):
        app_logger.debug(f"TBL_SEL: Callback select_row_on_table_data_or_id_change acionado. filter_id_value: {filter_id_value}. Aba ativa: {active_tab_id}")
        app_logger.debug(f"TBL_SEL: rowData tipo: {type(rowData)}, len: {len(rowData) if rowData is not None else 0}")

        ctx = callback_context
        # MODIFICADO: Lógica de saída antecipada. Se a aba não é a da tabela E o trigger não é o filter-id.
        if active_tab_id != 'tab-table' and ctx.triggered[0]['prop_id'] != 'filter-id.value':
             app_logger.debug("TBL_SEL: Aba da tabela oculta e não disparado por filter-id. Retornando no_update.")
             return no_update

        if not rowData:
            app_logger.warning("TBL_SEL: rowData é None ou vazio. Não é possível selecionar uma linha.")
            return []

        if isinstance(rowData, pd.DataFrame):
            rowData = rowData.to_dict("records")

        selected_row_data = []
        if filter_id_value is not None:
            for row in rowData:
                if row.get("sample_id") == filter_id_value:
                    app_logger.info(f"TBL_SEL: Selecionando linha para ID: {filter_id_value} com base no filter-id.")
                    selected_row_data = [row]
                    break

        if not selected_row_data and rowData:
            app_logger.info("TBL_SEL: Nenhuma filter_id ou ID não encontrado, ou filter_id é None. Selecionando a primeira linha da tabela.")
            selected_row_data = [rowData[0]]
        elif not selected_row_data and not rowData:
            app_logger.warning("TBL_SEL: Nenhuma dado na tabela para selecionar linha.")
            selected_row_data = []

        app_logger.debug(f"TBL_SEL: Retornando selectedRows: {selected_row_data[0].get('sample_id') if selected_row_data else 'Nenhum'}")
        return selected_row_data

    # Callback para carregar/atualizar dados da tabela (AgGrid)
    @app.callback(
        Output("sample-table-store", "data"),
        Output("sample-table", "rowData"),
        Output('user-feedback-alert', 'is_open', allow_duplicate=True),
        Output('user-feedback-alert', 'children', allow_duplicate=True),
        Output('user-feedback-alert', 'color', allow_duplicate=True),
        Output('go-to-next-sample-trigger', 'data', allow_duplicate=True),

        Input("current-validation-table-id-store", "data"),
        Input("confirm-update-btn", "n_clicks"),
        Input("confirm-reset-btn", "n_clicks"),
        State("filter-id", "value"),
        State("definition-select", "value"),
        State("reason-select", "value"),
        State("user-id-store", "data"),
        State("team-id-store", "data"),
        State("dataset-selector", "value"),
        State("sample-table-store", "data"), # Renomeado de current_table_data_for_next para consistência
        prevent_initial_call='initial_duplicate'
    )
    def load_and_update_table_data(
        current_full_table_id, update_clicks, reset_clicks, sample_id,
        definition, reason, user_id, team_id, dataset_key,
        current_table_data_stored # MODIFICADO: Nome do argumento
    ):
        ctx = callback_context
        triggered_id = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else 'initial_load_or_table_switch'

        app_logger.info(f"TABLE_DATA: Callback load_and_update_table_data acionado por: '{triggered_id}'")
        app_logger.debug(f"TABLE_DATA: current_full_table_id recebido: '{current_full_table_id}' (tipo: {type(current_full_table_id)})")

        output_alert_is_open = False
        output_alert_children = ""
        output_alert_color = "success"
        output_go_to_next_sample_trigger = no_update

        if not current_full_table_id and triggered_id == 'initial_load_or_table_switch':
            app_logger.warning("TABLE_DATA: Nenhum ID de tabela de validação ativa no carregamento inicial. Retornando vazios para tabela.")
            return [], [], False, "", "secondary", no_update

        should_reload_table = False 

        if triggered_id == "confirm-update-btn" and update_clicks and update_clicks > 0:
            app_logger.info(f"TABLE_DATA: Botão 'Validar Amostra' clicado para amostra {sample_id}.")
            try:
                if sample_id is None:
                    raise ValueError("ID da amostra não selecionado. Não é possível validar.")
                
                definition_str = str(definition) if definition is not None else None
                reason_str = str(reason) if reason is not None else None

                update_sample(current_full_table_id, sample_id, definition_str, reason_str, "VALIDATED")
                output_alert_is_open = True
                output_alert_children = f"✔️ Amostra {sample_id} validada!"
                output_alert_color = "success"
                should_reload_table = True

                if current_table_data_stored:
                    df_temp = pd.DataFrame(current_table_data_stored) 
                    next_pending_sample_df = df_temp[
                        (df_temp["status"] == "PENDING") & 
                        (df_temp["sample_id"] > sample_id)
                    ].sort_values("sample_id")

                    if not next_pending_sample_df.empty:
                        output_go_to_next_sample_trigger = next_pending_sample_df.iloc[0]["sample_id"]
                        app_logger.info(f"NAV_LOGIC: Pulando para próxima amostra pendente: {output_go_to_next_sample_trigger}")
                    else:
                        next_pending_sample_df = df_temp[df_temp["status"] == "PENDING"].sort_values("sample_id")
                        if not next_pending_sample_df.empty:
                            output_go_to_next_sample_trigger = next_pending_sample_df.iloc[0]["sample_id"]
                            app_logger.info(f"NAV_LOGIC: Pulando para a primeira amostra pendente restante: {output_go_to_next_sample_trigger}")
                        else:
                            app_logger.info("NAV_LOGIC: Nenhuma próxima amostra pendente encontrada.")
                            output_alert_is_open = True
                            output_alert_children = "✅ Todas as amostras validadas!"
                            output_alert_color = "info"
            except Exception as e:
                error_msg = str(e).split('message: ')[-1].split(';')[0] if 'message:' in str(e) else str(e)
                app_logger.error(f"ERROR: Erro ao validar amostra {sample_id}. Erro: {e}", exc_info=True)
                output_alert_is_open = True
                output_alert_children = f"❌ Erro ao validar: {error_msg}"
                output_alert_color = "danger"
                return no_update, no_update, output_alert_is_open, output_alert_children, output_alert_color, no_update

        elif triggered_id == "confirm-reset-btn" and reset_clicks and reset_clicks > 0:
            app_logger.info(f"TABLE_DATA: Botão 'Resetar ID' clicado para amostra {sample_id}.")
            try:
                if sample_id is None:
                    raise ValueError("ID da amostra não selecionado. Não é possível resetar.")
                
                update_sample(current_full_table_id, sample_id, None, None, "PENDING") 
                output_alert_is_open = True
                output_alert_children = f"🔄 Amostra {sample_id} resetada!"
                output_alert_color = "warning"
                should_reload_table = True
            except Exception as e:
                error_msg = str(e).split('message: ')[-1].split(';')[0] if 'message:' in str(e) else str(e)
                app_logger.error(f"ERROR: Erro ao resetar amostra {sample_id}. Erro: {e}", exc_info=True)
                output_alert_is_open = True
                output_alert_children = f"❌ Erro ao resetar: {error_msg}"
                output_alert_color = "danger"
                return no_update, no_update, output_alert_is_open, output_alert_children, output_alert_color, no_update

        if current_full_table_id and (should_reload_table or triggered_id == "current-validation-table-id-store" or triggered_id == 'initial_load_or_table_switch'):
            try:
                app_logger.debug(f"TABLE_DATA: Buscando dados da tabela '{current_full_table_id}' do BigQuery (recarregando).")
                df = get_dataset_table(current_full_table_id)

                app_logger.debug(f"TABLE_DATA: DataFrame do BigQuery carregado. Linhas: {len(df)}. Colunas: {df.columns.tolist()}")

                missing_cols = [col for col in VISIBLE_COLUMNS if col not in df.columns]
                if missing_cols:
                    raise ValueError(f"Colunas esperadas ausentes no DataFrame do BigQuery: {missing_cols}. Verifique VISIBLE_COLUMNS e o esquema da tabela.")
                
                data = df[VISIBLE_COLUMNS].to_dict("records")

                app_logger.debug(f"TABLE_DATA: Dados para AgGrid formatados. Primeiro registro: {data[0] if data else 'Nenhum'}")
                app_logger.info(f"TABLE_DATA: Dados da tabela '{current_full_table_id}' carregados/recarregados ({len(data)} registros). Retornando.")

                return data, data, output_alert_is_open, output_alert_children, output_alert_color, output_go_to_next_sample_trigger
            except Exception as e:
                error_msg = str(e).split('message: ')[-1].split(';')[0] if 'message:' in str(e) else str(e)
                app_logger.error(f"ERROR: Erro ao recarregar a tabela '{current_full_table_id}'. Erro: {e}", exc_info=True)
                output_alert_is_open = True
                output_alert_children = f"❌ Erro ao carregar tabela: {error_msg}"
                output_alert_color = "danger"
                return no_update, no_update, output_alert_is_open, output_alert_children, output_alert_color, no_update
        
        return no_update, no_update, output_alert_is_open, output_alert_children, output_alert_color, no_update