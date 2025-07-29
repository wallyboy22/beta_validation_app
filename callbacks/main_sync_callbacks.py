# callbacks/main_sync_callbacks.py

import dash
import pandas as pd
from dash import Output, Input, State, callback_context, no_update, html # ADICIONADO: html
from urllib.parse import parse_qs, urlencode
from datetime import datetime, timezone

import dash_bootstrap_components as dbc

from utils.bigquery import (
    discover_datasets, get_all_validation_tables_for_dataset,
    ensure_validation_table_exists, delete_validation_version, bq_client,
    get_unique_column_values # ADICIONADO: get_unique_column_values
)
from utils.logger import app_logger

def register_callbacks(app):
    """
    Registra callbacks para sincronização do estado principal da aplicação (URL, seletores de dataset/versão).
    """

    @app.callback(
        Output('tab-grid-content', 'style'),
        Output('tab-table-content', 'style'),
        Output('tab-map-content', 'style'),
        Output('tabs', 'active_tab'),
        Output('url', 'pathname'),
        Output('url', 'search'),
        Output('filter-id', 'value'),
        Output('dataset-selector', 'options'),
        Output('dataset-selector', 'value'),
        Output('validation-version-selector', 'options'),
        Output('validation-version-selector', 'value'),
        Output('current-validation-table-id-store', 'data'),
        Output('user-feedback-alert', 'is_open'),
        Output('user-feedback-alert', 'children'),
        Output('user-feedback-alert', 'color'),
        Output('new-version-biome-filter', 'options'), # NOVO: Output para opções de filtro de bioma
        Output('new-version-class-filter', 'options'), # NOVO: Output para opções de filtro de classe
        # Output para o preview do nome da nova versão
        Output("new-version-preview-name", "children"), 

        Input('url', 'pathname'),
        Input('url', 'search'),
        Input('tabs', 'active_tab'),
        Input('dataset-selector', 'value'),
        Input('validation-version-selector', 'value'),
        # Callbacks que podem afetar o ID da amostra
        Input('previous-button', 'n_clicks'),
        Input('next-button', 'n_clicks'),
        Input('reset-button', 'n_clicks'),
        Input('filter-id', 'value'),
        Input('toggle-unvalidated-nav', 'value'), # Trigger para navegação não validada

        # Callbacks que afetam a versão/dataset
        Input('confirm-create-new-version-btn', 'n_clicks'),
        Input('delete-version-button', 'n_clicks'), # Apenas para trigger do modal
        Input('confirm-delete-btn', 'n_clicks'),
        Input('cancel-delete-btn', 'n_clicks'), # Para fechar modal sem ação

        # Callbacks que podem gerar feedback ao usuário
        Input('confirm-update-btn', 'n_clicks'), # Da validação
        Input('confirm-reset-btn', 'n_clicks'), # Do reset

        State("filter-id", "value"), # current_filter_id_state
        State("sample-table-store", "data"), # table_data
        State('new-version-description-input', 'value'), # new_version_description
        State('new-version-biome-filter', 'value'),      # new_version_biome_filter_value
        State('new-version-class-filter', 'value'),      # new_version_class_filter_value
        State('new-version-reset-checkbox', 'value'),    # new_version_reset_checkbox_value
        State('user-id-store', 'data'), # user_id
        State('team-id-store', 'data'), # team_id
        State('confirm-delete-modal', 'is_open'), # is_delete_modal_open

        # States para preview do nome da nova versão
        State('new-version-description-input', 'value'),
        State('new-version-biome-filter', 'value'),
        State('new-version-class-filter', 'value'),

        prevent_initial_call=False
    )
    def synchronize_app_state(
        url_pathname, url_search, active_tab_id,
        selected_dataset_key_input, selected_validation_version_input,
        prev_clicks, next_clicks, reset_clicks, filter_id_input_triggered,
        toggle_unvalidated_nav_value,
        confirm_create_new_version_n_clicks,
        delete_version_n_clicks, confirm_delete_n_clicks, cancel_delete_n_clicks,
        confirm_update_n_clicks, confirm_reset_n_clicks,

        current_filter_id_state, table_data,
        new_version_description,
        new_version_biome_filter_value,
        new_version_class_filter_value,
        new_version_reset_checkbox_value,
        user_id, team_id,
        is_delete_modal_open,
        
        # States para preview do nome da nova versão
        preview_description_state, preview_biome_filter_state, preview_class_filter_state
    ):
        ctx = dash.callback_context
        triggered_id = ctx.triggered[0]['prop_id'].split(".")[0] if ctx.triggered else 'initial_load'

        navigate_unvalidated_only = (toggle_unvalidated_nav_value == ['unvalidated_only'])

        desired_filter_id = current_filter_id_state
        app_logger.info(f"APP_STATE_SYNC: Callback sincronização acionado por: '{triggered_id}'. Navegar só não validadas: {navigate_unvalidated_only}")

        # Outputs iniciais
        output_style_grid = no_update
        output_style_table = no_update
        output_style_map = no_update
        output_active_tab = no_update
        output_url_pathname = no_update
        output_url_search_val = no_update
        output_filter_id_val = no_update
        output_dataset_selector_options = no_update
        output_dataset_selector_value = no_update
        output_validation_version_options = no_update
        output_validation_version_value = no_update
        output_current_validation_table_id_store_data = no_update
        output_alert_is_open = False
        output_alert_children = ""
        output_alert_color = "success"
        output_biome_filter_options = no_update # NOVO
        output_class_filter_options = no_update  # NOVO
        output_new_version_preview_name = no_update # NOVO

        # Estado URL atual
        desired_active_tab = active_tab_id
        desired_pathname = url_pathname
        desired_url_params = parse_qs(url_search.lstrip('?'))

        # Tenta obter o dataset/versão da URL ou dos inputs
        desired_dataset_key = desired_url_params.get('dataset', [selected_dataset_key_input])[0]
        desired_validation_table_id = desired_url_params.get('version', [selected_validation_version_input])[0]

        # Lógica para criação de nova versão
        if triggered_id == 'confirm-create-new-version-btn' and confirm_create_new_version_n_clicks and confirm_create_new_version_n_clicks > 0:
            app_logger.info(f"NEW_VERSION: Botão 'Criar Versão' CONFIRMADO clicado para dataset: '{desired_dataset_key}'.")

            if not desired_dataset_key or desired_dataset_key == "error":
                output_alert_is_open = True
                output_alert_children = "❗ Selecione um dataset válido antes de criar uma nova versão."
                output_alert_color = "warning"
                app_logger.warning("NEW_VERSION: Tentativa de criar versão sem dataset selecionado ou inválido.")
                return (no_update,) * 12 + (output_alert_is_open, output_alert_children, output_alert_color, no_update, no_update, no_update)

            should_reset_data = 'reset_data' in (new_version_reset_checkbox_value or [])

            try:
                new_version_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                
                full_table_id_created, was_created = ensure_validation_table_exists(
                    original_dataset_key=desired_dataset_key,
                    new_version_timestamp=new_version_timestamp,
                    user_id=user_id,
                    team_id=team_id,
                    description=new_version_description,
                    biome_filter=new_version_biome_filter_value,
                    class_filter=new_version_class_filter_value,
                    reset_data=should_reset_data
                )
                app_logger.info(f"NEW_VERSION: Tabela de validação '{full_table_id_created}' {'criada' if was_created else 'garantida'}.")

                desired_validation_table_id = full_table_id_created
                desired_filter_id = None # Reinicia o ID ao criar nova versão

                desired_url_params['dataset'] = [desired_dataset_key]
                desired_url_params['version'] = [full_table_id_created]
                desired_url_params.pop('id', None)

                output_alert_is_open = True
                output_alert_children = f"✔️ Nova versão '{full_table_id_created.split('.')[-1]}' criada e selecionada!"
                output_alert_color = "success"

            except Exception as e:
                error_msg_full = str(e)
                error_msg_display = error_msg_full.split('message:')[-1].split(';')[0].strip() if 'message:' in error_msg_full else error_msg_full
                
                if "Already Exists" in error_msg_full or "already exists" in error_msg_full:
                    error_msg_display = "Uma versão com esta nomenclatura já existe. Tente uma descrição diferente ou aguarde um momento e tente novamente."
                elif "Table original" in error_msg_full and "not found" in error_msg_full:
                    error_msg_display = f"Dataset original '{desired_dataset_key}' não encontrado. Verifique se ele existe no BigQuery."
                
                output_alert_is_open = True
                output_alert_children = f"❌ Erro ao criar nova versão: {error_msg_display}"
                output_alert_color = "danger"
                app_logger.error(f"NEW_VERSION: Erro crítico ao criar nova versão. Erro: {e}", exc_info=True)
                return (no_update,) * 12 + (output_alert_is_open, output_alert_children, output_alert_color, no_update, no_update, no_update)
        
        # Lógica para exclusão de versão
        elif triggered_id == 'confirm-delete-btn' and confirm_delete_n_clicks and confirm_delete_n_clicks > 0 and is_delete_modal_open:
            if desired_validation_table_id:
                try:
                    success = delete_validation_version(desired_validation_table_id)
                    if success:
                        output_alert_is_open = True
                        output_alert_children = f"🗑️ Versão '{desired_validation_table_id.split('.')[-1]}' apagada com sucesso."
                        output_alert_color = "success"

                        desired_validation_table_id = None
                        desired_filter_id = None
                        desired_url_params.pop('version', None)
                        desired_url_params.pop('id', None)
                    else:
                        raise Exception("Falha desconhecida ao apagar a versão.")
                except Exception as e:
                    error_msg = str(e).split('message: ')[-1].split(';')[0] if 'message:' in str(e) else str(e)
                    output_alert_is_open = True
                    output_alert_children = f"❌ Erro ao apagar versão: {error_msg}"
                    output_alert_color = "danger"
                    app_logger.error(f"DELETE_VERSION: Erro ao apagar versão. Erro: {e}", exc_info=True)
            else:
                output_alert_is_open = True
                output_alert_children = "⚠️ Nenhuma versão selecionada para apagar."
                output_alert_color = "warning"

            # Após deletar, precisamos atualizar as opções e o valor selecionado do dropdown de versão
            # E garantir que o dataset_selector tenha um valor para repopular
            if desired_dataset_key and desired_dataset_key != "error":
                try:
                    validation_versions = get_all_validation_tables_for_dataset(desired_dataset_key)
                    validation_versions.sort(key=lambda x: pd.to_datetime(x.get('created_at', '1900-01-01T00:00:00Z')), reverse=True)
                    output_validation_version_options = [
                        {
                            "label": f"{v.get('description', 'Versão Padrão')} (Criado em: {pd.to_datetime(v.get('created_at')).strftime('%Y-%m-%d %H:%M')})",
                            "value": v['table_id']
                        } for v in validation_versions
                    ]
                    if output_validation_version_options:
                        output_validation_version_value = output_validation_version_options[0]['value']
                        output_current_validation_table_id_store_data = output_validation_version_options[0]['value']
                    else:
                        output_validation_version_value = None
                        output_current_validation_table_id_store_data = None
                except Exception as e:
                    app_logger.error(f"ERROR: Erro ao repopular versões após exclusão: {e}", exc_info=True)
                    output_validation_version_options = []
                    output_validation_version_value = None
                    output_current_validation_table_id_store_data = None
            else:
                output_validation_version_options = []
                output_validation_version_value = None
                output_current_validation_table_id_store_data = None
            
            # Retorna todos os outputs, incluindo os de alerta e os de versão
            return (
                no_update, no_update, no_update, no_update,
                '/' + desired_pathname.lstrip('/'),
                '?' + urlencode(desired_url_params, doseq=True),
                desired_filter_id,
                no_update, # dataset_selector_options não muda aqui
                no_update, # dataset_selector_value não muda aqui
                output_validation_version_options,
                output_validation_version_value,
                output_current_validation_table_id_store_data,
                output_alert_is_open,
                output_alert_children,
                output_alert_color,
                no_update, no_update, no_update # Retornos para bioma, classe, preview
            )

        # Lógica de sincronização de URL
        if triggered_id == 'url' or triggered_id == 'initial_load':
            app_logger.debug(f"APP_STATE_SYNC: Processando URL: pathname='{url_pathname}', search='{url_search}'")

            if url_pathname == '/tabela':
                desired_active_tab = 'tab-table'
                desired_pathname = '/tabela'
            elif url_pathname == '/mapa':
                desired_active_tab = 'tab-map'
                desired_pathname = '/mapa'
            elif url_pathname == '/avaliacao' or url_pathname == '/':
                desired_active_tab = 'tab-grid'
                desired_pathname = '/avaliacao'
            else:
                desired_active_tab = 'tab-grid'
                desired_pathname = '/avaliacao'

            id_from_url = desired_url_params.get('id', [None])[0]
            if id_from_url is not None and str(id_from_url).isdigit():
                desired_filter_id = int(id_from_url)

            dataset_from_url = desired_url_params.get('dataset', [None])[0]
            if dataset_from_url:
                desired_dataset_key = dataset_from_url

            version_from_url = desired_url_params.get('version', [None])[0]
            if version_from_url:
                desired_validation_table_id = version_from_url

            app_logger.debug(f"APP_STATE_SYNC: URL parsed: Dataset='{desired_dataset_key}', Version='{desired_validation_table_id}', ID='{desired_filter_id}'")

        elif triggered_id == 'dataset-selector':
            app_logger.debug(f"APP_STATE_SYNC: Dataset Selector mudou para: '{selected_dataset_key_input}'")
            desired_dataset_key = selected_dataset_key_input
            desired_validation_table_id = None
            desired_filter_id = None
            desired_url_params = {'dataset': [desired_dataset_key]}
            desired_url_params.pop('version', None)
            desired_url_params.pop('id', None)

        elif triggered_id == 'validation-version-selector':
            app_logger.debug(f"APP_STATE_SYNC: Validation Version Selector mudou para: '{selected_validation_version_input}'")
            desired_validation_table_id = selected_validation_version_input
            desired_filter_id = None
            desired_url_params['version'] = [desired_validation_table_id]
            desired_url_params.pop('id', None)

        elif triggered_id == 'tabs':
            app_logger.debug(f"APP_STATE_SYNC: Aba mudou para: '{active_tab_id}'")
            if active_tab_id == 'tab-table':
                desired_pathname = '/tabela'
            elif active_tab_id == 'tab-map':
                desired_pathname = '/mapa'
            elif active_tab_id == 'tab-grid':
                desired_pathname = '/avaliacao'
            else:
                desired_pathname = '/avaliacao'

            desired_active_tab = active_tab_id
            
        # Lógica de navegação de amostras (Anterior/Próximo/ID manual/Toggle)
        if triggered_id in ["previous-button", "next-button", "reset-button", "filter-id", "toggle-unvalidated-nav"]:
            # IMPORTANTE: A lógica de get_next_sample e get_previous_sample está no sample_nav_callbacks.
            # Aqui, apenas garantimos que `desired_filter_id` é atualizado corretamente para a URL.
            # O `filter-id` input/output gerenciará a amostra atual.
            if table_data is None or (isinstance(table_data, pd.DataFrame) and table_data.empty) or (isinstance(table_data, list) and not table_data):
                app_logger.warning("NAV_LOGIC: Tabela de dados vazia, navegação de amostra abortada.")
                desired_filter_id = None
                desired_url_params.pop('id', None)
            else:
                if isinstance(table_data, pd.DataFrame):
                    table_data_list = table_data.to_dict("records")
                else:
                    table_data_list = table_data

                from callbacks.sample_nav_callbacks import get_next_sample, get_previous_sample # Importa aqui para evitar circular

                if triggered_id == "previous-button":
                    desired_filter_id = get_previous_sample(current_filter_id_state, table_data_list, only_unvalidated=navigate_unvalidated_only)
                    app_logger.info(f"NAV_LOGIC: Próximo ID após 'Anterior': {desired_filter_id}")
                elif triggered_id == "next-button":
                    desired_filter_id = get_next_sample(current_filter_id_state, table_data_list, only_unvalidated=navigate_unvalidated_only)
                    app_logger.info(f"NAV_LOGIC: Próximo ID após 'Próximo': {desired_filter_id}")
                elif triggered_id == "reset-button":
                    app_logger.info("NAV_LOGIC: Botão 'Reset ID' clicado. Limpando ID da amostra.")
                    desired_filter_id = None
                elif triggered_id == 'filter-id':
                    try:
                        desired_filter_id = int(filter_id_input_triggered) if filter_id_input_triggered is not None else None
                    except ValueError:
                        app_logger.warning(f"NAV_LOGIC: Input de ID inválido: '{filter_id_input_triggered}'. Ignorando.")
                        desired_filter_id = current_filter_id_state
                        output_alert_is_open = True
                        output_alert_children = f"❗ ID '{filter_id_input_triggered}' inválido. Digite um número."
                        output_alert_color = "danger"
                elif triggered_id == 'toggle-unvalidated-nav':
                    if navigate_unvalidated_only:
                        desired_filter_id = get_next_sample(current_filter_id_state, table_data_list, only_unvalidated=True)
                        app_logger.info(f"NAV_LOGIC: Toggle 'Não validadas' ativado. Indo para o próximo não validado: {desired_filter_id}")
                    else:
                        app_logger.info("NAV_LOGIC: Toggle 'Não validadas' desativado. Mantendo ID atual ou indo para o primeiro da lista completa.")


                if desired_filter_id is not None:
                    desired_url_params['id'] = [str(desired_filter_id)]
                else:
                    desired_url_params.pop('id', None)

        # Lógica para popular filter-id na carga inicial/mudança de contexto
        if (triggered_id == 'initial_load' or triggered_id == 'dataset-selector' or triggered_id == 'validation-version-selector' or triggered_id == 'confirm-create-new-version-btn' or triggered_id == 'confirm-delete-btn') and desired_filter_id is None and table_data and len(table_data) > 0:
            if isinstance(table_data, pd.DataFrame):
                table_data_list = table_data.to_dict("records")
            else:
                table_data_list = table_data

            if len(table_data_list) > 0:
                app_logger.info("NAV_LOGIC: Carga inicial/mudança de dataset/versão sem ID na URL/input. Selecionando primeira amostra da tabela.")
                desired_filter_id = table_data_list[0]["sample_id"]
                desired_url_params['id'] = [str(desired_filter_id)]

        # Lógica para atualizar opções de dataset e versão
        PROJECT_ID = "mapbiomas"
        DATASET_ID = "mapbiomas_brazil_validation"
        try:
            temp_discovered_options = discover_datasets(PROJECT_ID, DATASET_ID)
            output_dataset_selector_options = temp_discovered_options
            if temp_discovered_options and not desired_dataset_key:
                desired_dataset_key = temp_discovered_options[0]['value']
            elif desired_dataset_key == "error" and temp_discovered_options:
                desired_dataset_key = temp_discovered_options[0]['value']
        except Exception as e:
            app_logger.error(f"DB_DISCOVERY: Erro ao descobrir datasets: {e}", exc_info=True)
            output_dataset_selector_options = [{"label": "Erro ao carregar datasets", "value": "error"}]
            desired_dataset_key = "error"

        if desired_dataset_key and desired_dataset_key != "error":
            try:
                validation_versions = get_all_validation_tables_for_dataset(desired_dataset_key)
                app_logger.debug(f"APP_STATE_SYNC: validation_versions obtido para {desired_dataset_key}: {len(validation_versions)} versões.")

                for v in validation_versions:
                    if isinstance(v.get('created_at'), str):
                        try:
                            v['created_at'] = datetime.fromisoformat(v['created_at'].replace('Z', '+00:00'))
                        except ValueError:
                            app_logger.error(f"ERROR: Erro de formato de data para created_at em registro de versão: {v.get('created_at')}. Usando fallback.", exc_info=True)
                            v['created_at'] = datetime(1900,1,1, tzinfo=timezone.utc)

                validation_versions.sort(key=lambda x: x.get('created_at', datetime(1900,1,1, tzinfo=timezone.utc)), reverse=True)

                output_validation_version_options = [
                    {
                        "label": f"{v.get('description', 'Versão Padrão')} (Criado em: {pd.to_datetime(v.get('created_at')).strftime('%Y-%m-%d %H:%M')})",
                        "value": v['table_id']
                    } for v in validation_versions
                ]

                if (desired_validation_table_id is None or desired_validation_table_id not in [v['value'] for v in output_validation_version_options]) and output_validation_version_options:
                    app_logger.warning(f"APP_STATE_SYNC: Versão '{desired_validation_table_id}' não encontrada ou ausente. Selecionando a mais recente: {output_validation_version_options[0]['value']}.")
                    desired_validation_table_id = output_validation_version_options[0]['value']
                elif not output_validation_version_options:
                    app_logger.warning(f"APP_STATE_SYNC: Nenhuma versão de validação encontrada para '{desired_dataset_key}'.")
                    desired_validation_table_id = None

                output_validation_version_value = desired_validation_table_id

                if (triggered_id == 'initial_load' or triggered_id == 'dataset-selector' or triggered_id == 'confirm-delete-btn') and 'dataset' not in desired_url_params and desired_dataset_key:
                     desired_url_params['dataset'] = [desired_dataset_key]
                     if desired_validation_table_id:
                         desired_url_params['version'] = [desired_validation_table_id]
            except Exception as e:
                app_logger.error(f"ERROR: Erro ao popular versões de validação ou obter ID da tabela: {e}", exc_info=True)
                output_validation_version_options = []
                output_validation_version_value = None
                desired_validation_table_id = None
                output_alert_is_open = True
                output_alert_children = f"❌ Erro ao carregar versões: {str(e)}"
                output_alert_color = "danger"

        else:
            app_logger.warning(f"APP_STATE_SYNC: Dataset '{desired_dataset_key}' inválido ou não selecionado. Limpando opções de versão.")
            output_validation_version_options = []
            output_validation_version_value = None
            desired_validation_table_id = None


        new_url_search_str = '?' + urlencode(desired_url_params, doseq=True) if desired_url_params else ''
        if url_search != new_url_search_str:
            output_url_search_val = new_url_search_str
        else:
            output_url_search_val = no_update

        if filter_id_input_triggered != desired_filter_id:
            output_filter_id_val = desired_filter_id

        if triggered_id == 'initial_load':
            output_dataset_selector_value = desired_dataset_key
        elif selected_dataset_key_input != desired_dataset_key:
            output_dataset_selector_value = desired_dataset_key

        output_current_validation_table_id_store_data = desired_validation_table_id

        # Lógica para popular os dropdowns de filtro do modal de criação de nova versão
        # Este bloco foi movido do layout.py e adicionado ao main_sync_callbacks
        current_original_dataset_key_for_filters = None
        if output_dataset_selector_options and output_dataset_selector_options is not no_update:
            for opt in output_dataset_selector_options:
                if opt['value'] != 'error' and opt['value'].startswith(''):
                    current_original_dataset_key_for_filters = opt['value']
                    break
        
        if not current_original_dataset_key_for_filters:
            app_logger.warning("LAYOUT_BUILD: Nenhum dataset original válido encontrado para popular filtros de bioma/classe na inicialização.")
            output_biome_filter_options = []
            output_class_filter_options = []
        else:
            full_original_table_id_for_filters = f"{bq_client.project}.mapbiomas_brazil_validation.APP_0-original_{current_original_dataset_key_for_filters}"
            try:
                app_logger.debug(f"LAYOUT_BUILD: Buscando opções de bioma para {full_original_table_id_for_filters}.")
                output_biome_filter_options = get_unique_column_values(full_original_table_id_for_filters, "biome_name")
                app_logger.debug(f"LAYOUT_BUILD: Buscando opções de classe para {full_original_table_id_for_filters}.")
                output_class_filter_options = get_unique_column_values(full_original_table_id_for_filters, "class_name")
                app_logger.info(f"LAYOUT_BUILD: Biomas/Classes para filtros carregados com sucesso: {len(output_biome_filter_options)} biomas, {len(output_class_filter_options)} classes.")
            except Exception as e:
                app_logger.critical(f"ERROR: ERRO CRÍTICO AO CARREGAR OPÇÕES DE BIOMA/CLASSE PARA FILTRO: {e}", exc_info=True)
                output_biome_filter_options = [{"label": "Erro ao carregar biomas", "value": "error"}]
                output_class_filter_options = [{"label": "Erro ao carregar classes", "value": "error"}]

        # Lógica para o preview do nome da nova versão
        sanitized_desc = new_version_description if new_version_description else ""
        biome_part_preview = ""
        if preview_biome_filter_state and len(preview_biome_filter_state) > 0:
            biome_part_preview = "_biome_" + "_".join([str(s).replace(' ', '_') for s in preview_biome_filter_state]) # ADICIONADO: str(s)
        
        class_part_preview = ""
        if preview_class_filter_state and len(preview_class_filter_state) > 0:
            class_part_preview = "_class_" + "_".join([str(s).replace(' ', '_') for s in preview_class_filter_state]) # ADICIONADO: str(s)
        
        timestamp_preview = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") # Use um timestamp dinâmico para preview
        
        preview_name = f"APP_1-validation_{desired_dataset_key}{biome_part_preview}{class_part_preview}_{sanitized_desc.replace(' ', '_')}_{timestamp_preview}"
        output_new_version_preview_name = html.Small(f"Nome da nova tabela (previsão): {preview_name.strip('_')}", className="text-muted")


        # Definindo os estilos de display das abas com base na aba ativa
        # Esta parte é importante para o comportamento atual com dcc.Tabs
        output_style_grid = {'display': 'block'} if desired_active_tab == 'tab-grid' else {'display': 'none'}
        output_style_table = {'display': 'block'} if desired_active_tab == 'tab-table' else {'display': 'none'}
        output_style_map = {'display': 'block'} if desired_active_tab == 'tab-map' else {'display': 'none'}

        app_logger.info(f"ROUTING_FINAL: --- Sincronização Final ---")
        # Logs de depuração
        app_logger.info(f"ROUTING_FINAL: Triggered by: {triggered_id}")
        app_logger.info(f"ROUTING_FINAL: Desired Pathname: {desired_pathname}")
        app_logger.info(f"ROUTING_FINAL: Desired Active Tab: {desired_active_tab}")
        app_logger.info(f"ROUTING_FINAL: Desired Dataset Key: {desired_dataset_key}")
        app_logger.info(f"ROUTING_FINAL: Desired Validation Table ID: {desired_validation_table_id}")
        app_logger.info(f"ROUTING_FINAL: Desired Filter ID: {desired_filter_id}")
        app_logger.info(f"ROUTING_FINAL: Desired URL Search: '{new_url_search_str}'")
        app_logger.info(f"ROUTING_FINAL: Validation Version Options Set: {'True' if output_validation_version_options is not no_update else 'False'}")
        app_logger.info(f"ROUTING_FINAL: Validation Version Value Set: {output_validation_version_value}")

        return (
            output_style_grid,
            output_style_table,
            output_style_map,
            desired_active_tab,
            desired_pathname,
            output_url_search_val,
            output_filter_id_val,
            output_dataset_selector_options,
            output_dataset_selector_value,
            output_validation_version_options,
            output_validation_version_value,
            output_current_validation_table_id_store_data,
            output_alert_is_open,
            output_alert_children,
            output_alert_color,
            output_biome_filter_options, # NOVO: Retorna as opções de filtro de bioma
            output_class_filter_options, # NOVO: Retorna as opções de filtro de classe
            output_new_version_preview_name # NOVO: Retorna o preview do nome
        )