# callbacks.py

import dash_leaflet as dl
import dash
import pandas as pd
from shapely import wkt
from dash import Output, Input, State, callback_context, no_update, html
from urllib.parse import urlparse, parse_qs, urlencode
import uuid

from datetime import datetime, timezone
import traceback

import dash_bootstrap_components as dbc # Necessário para dbc.Badge

# Importa funções e constantes de módulos locais
from utils.bigquery import (
    get_unique_column_values,get_sample_coordinates, get_dataset_table, update_sample,
    get_all_validation_tables_for_dataset, ensure_validation_table_exists,
    delete_validation_version, discover_datasets, get_validation_timestamps,
    bq_client # Importar a nova função
)
from utils.constants import (
    BIOMES, CLASSES, REASONS_BY_STATUS, DEFINITION,
    GRID_TILE_SIZE, VISIBLE_COLUMNS, GRID_STYLE, GRAPH_PANEL_HEIGHT,
    AUXILIARY_DATASETS, YEARS_RANGE, LULC_ASSET, CLASS_INFO, HIGHLIGHT_CLASS, STATUS_COLORS, PLOTLY_STATUS_COLORS
)
from utils.logger import app_logger
from utils.gee import plot_land_use_history, get_modis_ndvi, plot_ndvi_series, get_mosaic_url, get_lulc_mapbiomas_url

import plotly.graph_objects as go # Para o gráfico de progresso


# --- FUNÇÕES AUXILIARES ---

def build_info_text(sample_data):
    """
    Constrói o texto informativo sobre a amostra atual com um formato de métricas.
    """
    app_logger.debug("UI_BUILD: Construindo texto de informações da amostra como métricas.")

    if not sample_data or "geometry" not in sample_data or not sample_data["geometry"]:
        app_logger.warning("UI_BUILD: Dados de amostra incompletos ou inválidos para info text.", extra={"details": {"sample_data_keys": list(sample_data.keys()) if sample_data else "None"}})
        return html.Div(
            [
                html.H6("Amostra Não Selecionada", className="text-center text-muted my-3"),
                html.P("Por favor, selecione uma amostra ou digite um ID válido.", className="text-center text-muted small")
            ],
            className="p-3 bg-light rounded shadow-sm text-center"
        )

    try:
        point = wkt.loads(sample_data["geometry"])
        lat, lon = point.y, point.x

        status_value = sample_data.get('status', 'UNDEFINED')
        status_color = STATUS_COLORS.get(status_value, "secondary")

        # Obter nome do bioma e da classe
        biome_name = sample_data.get('biome_name', 'N/A')
        class_name = sample_data.get('class_name', 'N/A')


        metrics_content = []

        # ID e Coordenadas
        metrics_content.append(
            dbc.Row(
                [
                    dbc.Col(html.Div("ID", className="text-muted small"), width=2),
                    dbc.Col(html.Div(f"{sample_data['sample_id']}", className="fw-bold text-start"), width=4),
                    dbc.Col(html.Div("Lat/Lon", className="text-muted small text-end"), width=3),
                    dbc.Col(html.Div(f"{lat:.4f}, {lon:.4f}", className="fw-bold text-end"), width=3)
                ],
                className="mb-1 d-flex align-items-center"
            )
        )
        # Bioma e Classe
        metrics_content.append(
            dbc.Row(
                [
                    dbc.Col(html.Div("Bioma", className="text-muted small"), width=4),
                    dbc.Col(html.Div(f"{biome_name}", className="fw-bold text-end"), width=8)
                ],
                className="mb-1 d-flex align-items-center"
            )
        )
        metrics_content.append(
            dbc.Row(
                [
                    dbc.Col(html.Div("Classe", className="text-muted small"), width=4),
                    dbc.Col(html.Div(f"{class_name}", className="fw-bold text-end"), width=8)
                ],
                className="mb-1 d-flex align-items-center"
            )
        )
        # Status
        metrics_content.append(
            dbc.Row(
                [
                    dbc.Col(html.Div("Status", className="text-muted small"), width=4),
                    dbc.Col(dbc.Badge(f"{status_value.replace('_', ' ')}", color=status_color, className="ms-2"), width=8, className="text-end")
                ],
                className="mb-1 d-flex align-items-center"
            )
        )

        app_logger.debug(f"UI_BUILD: Informações da amostra para ID {sample_data['sample_id']} construídas.")
        return html.Div(metrics_content, className="p-2 border rounded shadow-sm bg-light")

    except Exception as e:
        app_logger.error(f"UI_BUILD: Erro ao parsear geometria ou construir info text. Sample ID: {sample_data.get('sample_id', 'N/A')}. Erro: {e}", exc_info=True)
        return html.Div(
            [
                html.H6("Erro na Amostra", className="text-center text-danger my-3"),
                html.P("Não foi possível carregar as informações. Consulte os logs.", className="text-center text-danger small")
            ],
            className="p-3 bg-light rounded border border-danger shadow-sm text-center"
        )
def get_next_sample(current_id, table_data, only_unvalidated=False): # Adicionado only_unvalidated
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

    # Filtra por amostras não validadas, se a opção for ativada
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

def get_previous_sample(current_id, table_data, only_unvalidated=False): # Adicionado only_unvalidated
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

    # Filtra por amostras não validadas, se a opção for ativada
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


def extract_point(sample):
    app_logger.debug(f"GEOM: Extraindo ponto para sample ID: {sample.get('sample_id', 'N/A')}")
    if not sample or "geometry" not in sample or not sample["geometry"]:
        app_logger.warning(f"GEOM: Amostra {sample.get('sample_id', 'N/A')} sem geometria válida (sample ou geometry ausente/vazio).")
        return None, None

    geometry_wkt = sample["geometry"]
    app_logger.debug(f"GEOM: Geometry WKT para sample {sample.get('sample_id')}: '{geometry_wkt}'")

    try:
        point = wkt.loads(geometry_wkt)
        app_logger.debug(f"GEOM: WKT parseado para ponto: ({point.y}, {point.x})")
        return point.y, point.x # (lat, lon)
    except Exception as e:
        app_logger.error(f"GEOM: Erro ao parsear WKT para amostra {sample.get('sample_id', 'N/A')}. WKT: '{geometry_wkt}'. Erro: {e}", exc_info=True)
        return None, None

def build_maps_panel(sample, years_range=None):
    app_logger.debug(f"UI_BUILD: Construindo painel de mapas para amostra {sample.get('sample_id', 'N/A')}.")
    if not sample:
        app_logger.warning("UI_BUILD: Nenhuma amostra fornecida para construir painel de mapas.")
        return html.Div("Nenhuma amostra selecionada para visualização de grid.", className="text-center text-muted p-4")

    lat, lon = extract_point(sample)
    if lat is None or lon is None:
        app_logger.warning(f"UI_BUILD: Coordenadas inválidas para amostra {sample.get('sample_id', 'N/A')}, não é possível construir painel de mapas.")
        return html.Div("Coordenadas inválidas para esta amostra.", className="text-center text-danger p-4")

    years_to_display = []
    if hasattr(years_range, 'start') and hasattr(years_range, 'stop'):
        years_to_display = list(range(years_range.start, years_range.stop))
    elif isinstance(years_range, (list, tuple)) and len(years_range) >= 2:
        years_to_display = list(range(years_range[0], years_range[1] + 1))
    else:
        years_to_display = list(range(YEARS_RANGE.start, YEARS_RANGE.stop))

    maps_html = []
    for year in years_to_display:
        try:
            tile_url = get_mosaic_url(year)
            maps_html.append(
                html.Div([
                    html.Div(f"{year}", style={"textAlign": "center", "fontWeight": "bold", "color": "#2a9fd6", "fontSize": "14px"}),
                    dl.Map(
                        [
                            dl.TileLayer(url=tile_url, attribution=f"MapBiomas {year}"),
                            dl.CircleMarker(center=[lat, lon], radius=5, color="red", fillOpacity=0.8)
                        ],
                        center=(lat, lon),
                        zoom=14,
                        style={"width": f"{GRID_TILE_SIZE}px", "height": f"{GRID_TILE_SIZE}px", "margin": "0px", "borderRadius": "8px"},
                        zoomControl=False, scrollWheelZoom=False, dragging=False,
                        doubleClickZoom=False, attributionControl=False, preferCanvas=True,
                    )
                ], style={"display": "inline-block", "margin": "2px"}) # Reduzido margin
            )
        except Exception as e:
            app_logger.error(f"UI_BUILD: Erro ao gerar mapa para ano {year} e amostra {sample.get('sample_id')}: {e}", exc_info=True)
            maps_html.append(
                html.Div([
                    html.Div(f"{year}", style={"textAlign": "center", "fontWeight": "bold", "color": "#ff0000"}),
                    html.Div("Erro ao carregar mapa", style={"color": "#ff0000", "fontSize": "12px", "textAlign": "center"})
                ], style={"display": "inline-block", "margin": "2px"}) # Reduzido margin
            )

    return html.Div(maps_html, style=GRID_STYLE)


def register_callbacks(app):

    # 1. CALLBACK: 1 - CÉREBRO PRINCIPAL (SINCRONIZA URL E SELETORES PRINCIPAIS)
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

        # --- Inputs ---
        Input('url', 'pathname'),
        Input('url', 'search'),
        Input('tabs', 'active_tab'), # MANTIDO como INPUT
        Input('dataset-selector', 'value'),
        Input('validation-version-selector', 'value'),
        Input('previous-button', 'n_clicks'),
        Input('next-button', 'n_clicks'),
        Input('reset-button', 'n_clicks'),
        Input('filter-id', 'value'),
        Input('confirm-create-new-version-btn', 'n_clicks'),
        Input('delete-version-button', 'n_clicks'),
        Input('confirm-delete-btn', 'n_clicks'),
        Input('cancel-delete-btn', 'n_clicks'),
        Input('confirm-update-btn', 'n_clicks'),
        Input('confirm-reset-btn', 'n_clicks'),
        Input('toggle-unvalidated-nav', 'value'),

        # --- States ---
        State("filter-id", "value"),
        State("sample-table-store", "data"),
        State('new-version-description-input', 'value'),
        State('new-version-biome-filter', 'value'),
        State('new-version-class-filter', 'value'),
        State('new-version-reset-checkbox', 'value'),
        State('user-id-store', 'data'),
        State('team-id-store', 'data'),
        State('confirm-delete-modal', 'is_open'),

        prevent_initial_call=False
    )
    def synchronize_app_state(
        url_pathname, url_search, active_tab_id,
        selected_dataset_key_input, selected_validation_version_input,
        prev_clicks, next_clicks, reset_clicks, filter_id_input_triggered,
        confirm_create_new_version_n_clicks,
        delete_version_n_clicks, confirm_delete_n_clicks, cancel_delete_n_clicks,
        confirm_update_n_clicks, confirm_reset_n_clicks,
        toggle_unvalidated_nav_value,

        current_filter_id_state, table_data,
        new_version_description,
        new_version_biome_filter_value,
        new_version_class_filter_value,
        new_version_reset_checkbox_value,
        user_id, team_id,
        is_delete_modal_open
    ):
        ctx = callback_context
        triggered_id = ctx.triggered[0]['prop_id'].split(".")[0] if ctx.triggered else 'initial_load'

        # Verifica se o toggle de navegação não validada está ativo
        navigate_unvalidated_only = (toggle_unvalidated_nav_value == ['unvalidated_only'])

        desired_filter_id = current_filter_id_state
        app_logger.info(f"APP_STATE_SYNC: Callback sincronização acionado por: '{triggered_id}'. Navegar só não validadas: {navigate_unvalidated_only}")

        # MODIFICADO: Remover style_hide/show daqui, eles são definidos diretamente nos retornos
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

        desired_active_tab = active_tab_id
        desired_pathname = url_pathname
        desired_url_params = parse_qs(url_search.lstrip('?'))

        desired_dataset_key = desired_url_params.get('dataset', [selected_dataset_key_input])[0]
        desired_validation_table_id = desired_url_params.get('version', [selected_validation_version_input])[0]

        # Trigger para CONFIRMAÇÃO de criação de nova versão
        if triggered_id == 'confirm-create-new-version-btn' and confirm_create_new_version_n_clicks and confirm_create_new_version_n_clicks > 0:
            app_logger.info(f"NEW_VERSION: Botão 'Criar Versão' CONFIRMADO clicado para dataset: '{desired_dataset_key}'.")

            if not desired_dataset_key or desired_dataset_key == "error":
                output_alert_is_open = True
                output_alert_children = "❗ Selecione um dataset válido antes de criar uma nova versão."
                output_alert_color = "warning"
                app_logger.warning("NEW_VERSION: Tentativa de criar versão sem dataset selecionado ou inválido.")
                return (
                    no_update,              # 1
                    no_update,              # 2
                    no_update,              # 3
                    no_update,              # 4
                    no_update,              # 5
                    no_update,              # 6
                    no_update,              # 7
                    no_update,              # 8
                    no_update,              # 9
                    no_update,              # 10
                    no_update,              # 11
                    no_update,              # 12
                    output_alert_is_open,   # 13
                    output_alert_children,  # 14
                    output_alert_color      # 15
                )

            # Extrair o valor do checkbox de reset
            # Será ['reset_data'] se marcado, ou [] se desmarcado
            should_reset_data = 'reset_data' in (new_version_reset_checkbox_value or [])

            try:
                new_version_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                
                full_table_id_created, was_created = ensure_validation_table_exists(
                    original_dataset_key=desired_dataset_key,
                    new_version_timestamp=new_version_timestamp,
                    user_id=user_id,
                    team_id=team_id,
                    description=new_version_description,
                    biome_filter=new_version_biome_filter_value, # PASSANDO OS NOVOS FILTROS
                    class_filter=new_version_class_filter_value, # PASSANDO OS NOVOS FILTROS
                    reset_data=should_reset_data                 # PASSANDO O ESTADO DO CHECKBOX
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

                validation_versions = get_all_validation_tables_for_dataset(desired_dataset_key)
                # O código abaixo de ordenação e formatação das opções de versão
                # já está em seu código e é fundamental para exibir as versões corretas.
                # Certifique-se de que a ordenação por 'created_at' seja robusta.
                validation_versions.sort(key=lambda x: pd.to_datetime(x.get('created_at', '1900-01-01T00:00:00Z')), reverse=True)
                output_validation_version_options = [
                    {
                        "label": f"{v.get('description', 'Versão Padrão')} (Criado em: {pd.to_datetime(v.get('created_at')).strftime('%Y-%m-%d %H:%M')})",
                        "value": v['table_id']
                    } for v in validation_versions
                ]
                output_validation_version_value = desired_validation_table_id
                output_current_validation_table_id_store_data = desired_validation_table_id


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
                return (
                    no_update,              # 1
                    no_update,              # 2
                    no_update,              # 3
                    no_update,              # 4
                    no_update,              # 5
                    no_update,              # 6
                    no_update,              # 7
                    no_update,              # 8
                    no_update,              # 9
                    no_update,              # 10
                    no_update,              # 11
                    no_update,              # 12
                    output_alert_is_open,   # 13
                    output_alert_children,  # 14
                    output_alert_color      # 15
                )

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

                        return (
                            no_update, no_update, no_update, no_update, # <--- 4 no_update
                            '/' + desired_pathname.lstrip('/'),        # <--- Este é o 5º Output (url.pathname)
                            '?' + urlencode(desired_url_params, doseq=True), # <--- Este é o 6º Output (url.search)
                            desired_filter_id,                          # <--- Este é o 7º Output (filter-id.value)
                            output_dataset_selector_options,            # <--- Este é o 8º Output
                            output_dataset_selector_value,              # <--- Este é o 9º Output
                            output_validation_version_options,          # <--- Este é o 10º Output
                            output_validation_version_value,            # <--- Este é o 11º Output
                            output_current_validation_table_id_store_data, # <--- Este é o 12º Output
                            output_alert_is_open,                       # <--- Este é o 13º Output
                            output_alert_children,                      # <--- Este é o 14º Output
                            output_alert_color                          # <--- Este é o 15º Output
                        )
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

            return (
                    no_update,              # 1
                    no_update,              # 2
                    no_update,              # 3
                    no_update,              # 4
                    no_update,              # 5
                    no_update,              # 6
                    no_update,              # 7
                    no_update,              # 8
                    no_update,              # 9
                    no_update,              # 10
                    no_update,              # 11
                    no_update,              # 12
                    output_alert_is_open,   # 13
                    output_alert_children,  # 14
                    output_alert_color      # 15
                )

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


        if triggered_id in ["previous-button", "next-button", "reset-button", "filter-id", "toggle-unvalidated-nav"]: # Adicionado toggle ao trigger
            app_logger.debug(f"APP_STATE_SYNC: Ação de navegação/ID manual disparada por: '{triggered_id}'. Unvalidated Only: {navigate_unvalidated_only}")

            if table_data is None or (isinstance(table_data, pd.DataFrame) and table_data.empty) or (isinstance(table_data, list) and not table_data):
                app_logger.warning("NAV_LOGIC: Tabela de dados vazia, navegação de amostra abortada.")
                desired_filter_id = None
                desired_url_params.pop('id', None)
            else:
                if isinstance(table_data, pd.DataFrame):
                    table_data = table_data.to_dict("records")

                if triggered_id == "previous-button":
                    desired_filter_id = get_previous_sample(current_filter_id_state, table_data, only_unvalidated=navigate_unvalidated_only)
                    app_logger.info(f"NAV_LOGIC: Próximo ID após 'Anterior': {desired_filter_id}")
                elif triggered_id == "next-button":
                    desired_filter_id = get_next_sample(current_filter_id_state, table_data, only_unvalidated=navigate_unvalidated_only)
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
                elif triggered_id == 'toggle-unvalidated-nav': # Se o toggle muda, reposicionar no primeiro/próximo não validado
                    if navigate_unvalidated_only:
                        # Tentar ir para o próximo não validado a partir do ID atual
                        desired_filter_id = get_next_sample(current_filter_id_state, table_data, only_unvalidated=True)
                        app_logger.info(f"NAV_LOGIC: Toggle 'Não validadas' ativado. Indo para o próximo não validado: {desired_filter_id}")
                    else:
                        # Se desativou, pode querer manter o ID atual ou ir para o primeiro da lista completa
                        app_logger.info("NAV_LOGIC: Toggle 'Não validadas' desativado. Mantendo ID atual ou indo para o primeiro da lista completa.")


                if desired_filter_id is not None:
                    desired_url_params['id'] = [str(desired_filter_id)]
                else:
                    desired_url_params.pop('id', None)


        if (triggered_id == 'initial_load' or triggered_id == 'dataset-selector' or triggered_id == 'validation-version-selector' or triggered_id == 'create-new-validation-version-button' or triggered_id == 'confirm-delete-btn') and desired_filter_id is None and table_data and len(table_data) > 0:
            if isinstance(table_data, pd.DataFrame):
                table_data = table_data.to_dict("records")
            if len(table_data) > 0:
                app_logger.info("NAV_LOGIC: Carga inicial/mudança de dataset/versão sem ID na URL/input. Selecionando primeira amostra da tabela.")
                desired_filter_id = table_data[0]["sample_id"]
                desired_url_params['id'] = [str(desired_filter_id)]


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

        app_logger.info(f"ROUTING_FINAL: --- Sincronização Final ---")
        app_logger.info(f"ROUTING_FINAL: Triggered by: {triggered_id}", extra={"details": {"ctx_triggered": ctx.triggered}})
        app_logger.info(f"ROUTING_FINAL: Desired Pathname: {desired_pathname}", extra={"details": {"output_url_pathname": output_url_pathname}})
        app_logger.info(f"ROUTING_FINAL: Desired Active Tab: {desired_active_tab}", extra={"details": {"output_active_tab": output_active_tab}})
        app_logger.info(f"ROUTING_FINAL: Desired Dataset Key: {desired_dataset_key}", extra={"details": {"output_dataset_selector_value": output_dataset_selector_value}})
        app_logger.info(f"ROUTING_FINAL: Desired Validation Table ID: {desired_validation_table_id}", extra={"details": {"store_output": output_current_validation_table_id_store_data}})
        app_logger.info(f"ROUTING_FINAL: Desired Filter ID: {desired_filter_id}", extra={"details": {"output_filter_id_val": output_filter_id_val}})
        app_logger.info(f"ROUTING_FINAL: Desired URL Search: '{new_url_search_str}'", extra={"details": {"output_url_search_val": output_url_search_val}})
        app_logger.info(f"ROUTING_FINAL: Validation Version Options Set: {'True' if output_validation_version_options is not no_update else 'False'}")
        app_logger.info(f"ROUTING_FINAL: Validation Version Value Set: {output_validation_version_value}")

        # MODIFICADO: Definindo os estilos de display com base na aba ativa
        return (
            {'display': 'block'} if desired_active_tab == 'tab-grid' else {'display': 'none'},
            {'display': 'block'} if desired_active_tab == 'tab-table' else {'display': 'none'},
            {'display': 'block'} if desired_active_tab == 'tab-map' else {'display': 'none'},
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
            output_alert_color
        )


    # 2. Callback para selecionar a linha da tabela ao carregar E sincronizar com filter-id
    @app.callback(
        Output("sample-table", "selectedRows"),
        Input("sample-table", "rowData"),
        Input("filter-id", "value"),
        # REMOVIDO: State("tab-table-content", "style"),
        Input("tabs", "active_tab"), # ADICIONADO: Input da aba ativa
        prevent_initial_call=False
    )
    def select_row_on_table_data_or_id_change(rowData, filter_id_value, active_tab_id): # MODIFICADO: Argumento active_tab_id
        app_logger.debug(f"TBL_SEL: Callback select_row_on_table_data_or_id_change acionado. filter_id_value: {filter_id_value}. Aba ativa: {active_tab_id}") # MODIFICADO: Log
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

    # 3. Callback para atualizar opções de motivo conforme definição selecionada
    @app.callback(
        Output("reason-select", "options"),
        Input("definition-select", "value")
    )
    def update_reason_options(definition):
        app_logger.debug(f"DROPDOWN: Callback update_reason_options acionado. Definição: {definition}")
        if not definition:
            app_logger.warning("DROPDOWN: Definição vazia, retornando opções vazias de motivo.")
            return []
        options = REASONS_BY_STATUS.get(definition, [])
        app_logger.debug(f"DROPDOWN: Retornando {len(options)} opções de motivo para definição: {definition}.")
        return options

    # 4. Callback para atualizar os campos de definição e motivo da amostra selecionada
    @app.callback(
        Output("definition-select", "value"),
        Output("reason-select", "value"),
        Output("original-sample-state-store", "data"),
        Input("filter-id", "value"),
        Input("sample-table-store", "data"),
    )
    def update_sample_fields(sample_id, table_data):
        app_logger.info(f"SAMPLE_FIELDS: Callback update_sample_fields acionado. Sample ID: {sample_id}")
        app_logger.debug(f"SAMPLE_FIELDS: table_data tipo: {type(table_data)}, len: {len(table_data) if table_data is not None else 0}")

        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, {}

        if (ctx.triggered[0]['prop_id'] == 'sample-table-store.data' and not table_data) or not sample_id:
            app_logger.warning("SAMPLE_FIELDS: Nenhuma amostra ou dados da tabela para atualizar campos (ainda não carregado). Retornando None.")
            return None, None, {}

        if isinstance(table_data, pd.DataFrame):
            table_data = table_data.to_dict("records")

        sample_data = next((row for row in table_data if row.get("sample_id") == sample_id), None)
        if not sample_data:
            app_logger.warning(f"SAMPLE_FIELDS: Amostra {sample_id} não encontrada na tabela de dados. Retornando None.")
            return None, None, {}

        definition = sample_data.get("definition")
        reason = sample_data.get("reason")

        app_logger.info(f"SAMPLE_FIELDS: Campos para amostra {sample_id}: Definição={definition}, Motivo={reason}.")
        return definition, reason, {'definition': definition, 'reason': reason}

    # 5. Callback para atualizar o painel de mapas e gráfico NDVI/LULC History
    @app.callback(
        Output("grid-maps-panel", "children"),
        Output("ndvi-graph", "figure"),
        Output("lulc-history-graph", "figure"),
        Input("filter-id", "value"),
        # REMOVIDO: Input('tab-grid-content', 'style'), # Removido como Input direto
        Input("sample-table-store", "data"),
        State("dataset-selector", "value"),
        Input('tabs', 'active_tab'), # ADICIONADO: Input da aba ativa
        prevent_initial_call=True
    )
    def update_maps_and_graphs(sample_id, table_data, current_dataset_key, active_tab_id): # ADICIONADO active_tab_id
        app_logger.info(f"GRID_MAPS_AND_GRAPHS: Callback acionado. Sample ID: {sample_id}. Aba Ativa: {active_tab_id}") # MODIFICADO: Log
        app_logger.debug(f"GRID_MAPS_AND_GRAPHS: table_data tipo: {type(table_data)}, len: {len(table_data) if table_data is not None else 0}")

        ctx = callback_context
        triggered_id = ctx.triggered[0]['prop_id'].split(".")[0] if ctx.triggered else 'initial_load'

        # MODIFICADO: Lógica de saída antecipada. Se a aba 'Avaliação' NÃO está ativa
        # E o trigger NÃO veio de filter-id ou sample-table-store (indicando mudança de dados),
        # então retorna no_update para evitar recalculos em abas ocultas.
        if active_tab_id != 'tab-grid' and triggered_id not in ['filter-id', 'sample-table-store']:
            app_logger.debug(f"GRID_MAPS_AND_GRAPHS: Aba 'Avaliação' oculta e trigger '{triggered_id}' não requer atualização. Retornando no_update.")
            return no_update, no_update, no_update

        # Inicializar variáveis de saída com valores padrão (vazios/neutros)
        maps_panel_children = html.Div("Nenhum mapa disponível. Selecione uma amostra válida.", className="text-center text-muted p-4")
        ndvi_graph_figure = {} # Figura Plotly vazia
        lulc_history_graph_figure = {} # Figura Plotly vazia

        # Condição de saída antecipada se não há dados de amostra ou ID
        if (triggered_id == 'sample-table-store' and not table_data) or not sample_id: # MODIFICADO: Condição mais explícita
            app_logger.warning("GRID_MAPS_AND_GRAPHS: Nenhuma amostra ou dados da tabela para construir mapas/gráficos (ainda não carregado). Retornando vazios.")
            return (
                html.Div("Nenhuma amostra selecionada para visualização. Carregando dados...", className="text-center text-muted p-4"),
                ndvi_graph_figure,
                lulc_history_graph_figure
            )

        # Garante que table_data é uma lista de dicionários
        if isinstance(table_data, pd.DataFrame):
            app_logger.debug("GRID_MAPS_AND_GRAPHS: Convertendo table_data de DataFrame para lista de dicts.")
            table_data = table_data.to_dict("records")

        # Encontra a amostra pelo ID
        sample = next((row for row in table_data if row.get("sample_id") == sample_id), None)
        if not sample:
            app_logger.warning(f"GRID_MAPS_AND_GRAPHS: Amostra {sample_id} não encontrada na tabela de dados. Retornando vazios.")
            return (
                html.Div(f"Amostra {sample_id} não encontrada na tabela.", className="text-center text-danger p-4"),
                ndvi_graph_figure,
                lulc_history_graph_figure
            )

        # Extrai coordenadas e verifica validade.
        lat, lon = extract_point(sample)
        if lat is None or lon is None:
            app_logger.error(f"GRID_MAPS_AND_GRAPHS: Coordenadas inválidas para amostra {sample_id}. Não é possível gerar os gráficos. Detalhes da amostra: {sample}")
            return (
                html.Div(f"Coordenadas inválidas para amostra {sample_id}.", className="text-center text-danger p-4"),
                ndvi_graph_figure,
                lulc_history_graph_figure
            )

        app_logger.debug(f"GRID_MAPS_AND_GRAPHS: Coordenadas da amostra {sample_id}: Lat={lat}, Lon={lon}.")
        app_logger.debug(f"GRID_MAPS_AND_GRAPHS: Preparando para buscar e plotar dados de gráficos.")

        # Lógica de geração dos mapas (grid)
        try:
            app_logger.debug(f"GRID_MAPS_AND_GRAPHS: Início da construção do painel de mapas para amostra {sample_id}.")
            years_range_for_dataset = YEARS_RANGE # Assumindo que YEARS_RANGE está definido em constants.py
            maps_panel_children = build_maps_panel(sample, years_range=years_range_for_dataset)
            app_logger.debug(f"GRID_MAPS_AND_GRAPHS: build_maps_panel retornado: {len(maps_panel_children.children) if maps_panel_children and hasattr(maps_panel_children, 'children') else 'Vazio'}")
        except Exception as e:
            app_logger.error(f"ERROR: Erro ao construir painel de mapas para amostra {sample_id}. Erro: {e}", exc_info=True)
            maps_panel_children = html.Div(f"Erro ao carregar mapas para amostra {sample_id}.", className="text-center text-danger p-4")


        # Lógica de geração dos gráficos (NDVI e LULC History)
        try:
            # MODIFICADO: Garante que start_year e end_year para o MODIS são consistentes com a coleção
            # MODIS está disponível a partir de 2000/2001. A função get_modis_ndvi já tem um max(2000, start_year).
            start_year_modis = YEARS_RANGE.start if hasattr(YEARS_RANGE, 'start') else YEARS_RANGE[0]
            end_year_modis = YEARS_RANGE.stop if hasattr(YEARS_RANGE, 'stop') else datetime.now().year # Usar ano atual para o máximo

            app_logger.debug(f"GRID_MAPS_AND_GRAPHS: Buscando dados MODIS NDVI para {sample_id} de {start_year_modis} a {end_year_modis}.")
            ndvi_data = get_modis_ndvi(start_year_modis, end_year_modis, (lat, lon))
            app_logger.debug(f"GRID_MAPS_AND_GRAPHS: Dados NDVI obtidos: {len(ndvi_data)} pontos.")
            ndvi_graph_figure = plot_ndvi_series(ndvi_data)
            app_logger.debug(f"GRID_MAPS_AND_GRAPHS: Gráfico NDVI gerado: {'Sim' if ndvi_graph_figure else 'Não'}")

            app_logger.debug(f"GRID_MAPS_AND_GRAPHS: Buscando e plotando histórico LULC para {sample_id}.")
            lulc_asset_path = LULC_ASSET # Assumindo que LULC_ASSET está definido em constants.py
            years_for_lulc_history = list(range(YEARS_RANGE.start, YEARS_RANGE.stop + 1))
            lulc_history_graph_figure = plot_land_use_history(lulc_asset_path, lat, lon, years_for_lulc_history, CLASS_INFO) # CLASS_INFO de constants.py
            app_logger.debug(f"GRID_MAPS_AND_GRAPHS: Gráfico LULC Histórico gerado: {'Sim' if lulc_history_graph_figure else 'Não'}")


        except Exception as e:
            app_logger.error(f"ERROR: Erro ao gerar um dos gráficos (NDVI ou LULC History) para amostra {sample_id}. Erro: {e}", exc_info=True)
            # Retorna figuras vazias para os gráficos em caso de erro na geração
            ndvi_graph_figure = {}
            lulc_history_graph_figure = {}


        app_logger.info(f"GRID_MAPS_AND_GRAPHS: Mapas e gráficos NDVI/LULC para amostra {sample_id} construídos. Retornando.")
        return maps_panel_children, ndvi_graph_figure, lulc_history_graph_figure

    # 6. Callback para atualizar o contador de validação
    @app.callback(
        Output("validation-counter", "children"),
        Input("sample-table-store", "data"),
    )
    def update_validation_counter(table_data):
        app_logger.debug("COUNTER: Callback update_validation_counter acionado.")
        app_logger.debug(f"COUNTER: table_data tipo: {type(table_data)}, len: {len(table_data) if table_data is not None else 0}")


        if table_data is None:
            app_logger.warning("COUNTER: Dados da tabela são None, retornando no_update.")
            return no_update

        if isinstance(table_data, pd.DataFrame):
            table_data = table_data.to_dict("records")

        validation_count = sum(1 for row in table_data if isinstance(row, dict) and row.get("definition") and row.get("definition") != "UNDEFINED")
        total_count = len(table_data)

        counter_text = html.P(f"Progresso: {validation_count}/{total_count} amostras validadas")

        app_logger.info(f"COUNTER: Contador atualizado: {validation_count}/{total_count}. Retornando.")
        return counter_text

    # 7. Callback para carregar/atualizar dados da tabela (AgGrid)
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
        State("sample-table-store", "data"),
        prevent_initial_call='initial_duplicate'
    )
    def load_and_update_table_data(
        current_full_table_id, update_clicks, reset_clicks, sample_id,
        definition, reason, user_id, team_id, dataset_key,
        current_table_data_for_next
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
            # Retorna valores vazios/default para todos os outputs
            return [], [], False, "", "secondary", no_update

        # Esta flag controla se a tabela precisa ser recarregada do BQ
        # Ela deve ser True se a tabela de validação (current_full_table_id) mudar,
        # ou se uma amostra foi validada/resetada.
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
                should_reload_table = True # Sinaliza para recarregar a tabela após a atualização

                # Lógica para ir para a próxima amostra pendente
                if current_table_data_for_next:
                    # Garantir que current_table_data_for_next é uma lista de dicts para DataFrame
                    df_temp = pd.DataFrame(current_table_data_for_next) 
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
                # Em caso de erro na atualização, não recarrega a tabela automaticamente para não perder dados.
                # A UI permanecerá com o estado anterior até que o usuário resolva o problema.
                return no_update, no_update, output_alert_is_open, output_alert_children, output_alert_color, no_update

        elif triggered_id == "confirm-reset-btn" and reset_clicks and reset_clicks > 0:
            app_logger.info(f"TABLE_DATA: Botão 'Resetar ID' clicado para amostra {sample_id}.")
            try:
                if sample_id is None:
                    raise ValueError("ID da amostra não selecionado. Não é possível resetar.")
                
                # Passa None para limpar definição e motivo
                update_sample(current_full_table_id, sample_id, None, None, "PENDING") 
                output_alert_is_open = True
                output_alert_children = f"🔄 Amostra {sample_id} resetada!"
                output_alert_color = "warning"
                should_reload_table = True # Sinaliza para recarregar a tabela após o reset
            except Exception as e:
                error_msg = str(e).split('message: ')[-1].split(';')[0] if 'message:' in str(e) else str(e)
                app_logger.error(f"ERROR: Erro ao resetar amostra {sample_id}. Erro: {e}", exc_info=True)
                output_alert_is_open = True
                output_alert_children = f"❌ Erro ao resetar: {error_msg}"
                output_alert_color = "danger"
                return no_update, no_update, output_alert_is_open, output_alert_children, output_alert_color, no_update

        # Recarrega os dados da tabela APÓS qualquer atualização bem-sucedida ou se o ID da tabela de validação mudou
        if current_full_table_id and (should_reload_table or triggered_id == "current-validation-table-id-store" or triggered_id == 'initial_load_or_table_switch'):
            try:
                app_logger.debug(f"TABLE_DATA: Buscando dados da tabela '{current_full_table_id}' do BigQuery (recarregando).")
                df = get_dataset_table(current_full_table_id)

                app_logger.debug(f"TABLE_DATA: DataFrame do BigQuery carregado. Linhas: {len(df)}. Colunas: {df.columns.tolist()}")

                missing_cols = [col for col in VISIBLE_COLUMNS if col not in df.columns]
                if missing_cols:
                    # Este erro é crítico para a exibição da tabela, então levanta uma exceção
                    # que será capturada no bloco exterior, se não for já tratada.
                    raise ValueError(f"Colunas esperadas ausentes no DataFrame do BigQuery: {missing_cols}. Verifique VISIBLE_COLUMNS e o esquema da tabela.")
                
                data = df[VISIBLE_COLUMNS].to_dict("records")

                app_logger.debug(f"TABLE_DATA: Dados para AgGrid formatados. Primeiro registro: {data[0] if data else 'Nenhum'}")
                app_logger.info(f"TABLE_DATA: Dados da tabela '{current_full_table_id}' carregados/recarregados ({len(data)} registros). Retornando.")

                return data, data, output_alert_is_open, output_alert_children, output_alert_color, output_go_to_next_sample_trigger
            except Exception as e:
                # Captura qualquer erro durante o carregamento/recarregamento da tabela
                error_msg = str(e).split('message: ')[-1].split(';')[0] if 'message:' in str(e) else str(e)
                app_logger.error(f"ERROR: Erro ao recarregar a tabela '{current_full_table_id}'. Erro: {e}", exc_info=True)
                output_alert_is_open = True
                output_alert_children = f"❌ Erro ao carregar tabela: {error_msg}"
                output_alert_color = "danger"
                # Retorna no_update para os dados da tabela para evitar limpar a tabela existente na UI
                return no_update, no_update, output_alert_is_open, output_alert_children, output_alert_color, no_update
        
        # Se nenhuma atualização/recarregamento foi disparado ou não há current_full_table_id,
        # retorna no_update para os dados da tabela.
        return no_update, no_update, output_alert_is_open, output_alert_children, output_alert_color, no_update

    # NOVO CALLBACK para go-to-next-sample-trigger
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

    # 8. Callback para alternar o tema da aplicação
    @app.callback(
        Output("app-background", "className"),
        Input("theme-toggle", "value"),
    )
    def update_theme_class(theme_value):
        app_logger.debug(f"THEME: Callback update_theme_class acionado. Tema: {theme_value}.")
        if theme_value == "dark":
            return "app-background theme-dark"
        return "app-background"

    # 9. Callback para atualizar o painel de informações da amostra
    @app.callback(
        Output("sample-info", "children"),
        Input("filter-id", "value"),
        Input("sample-table-store", "data"),
    )
    def update_sample_info(sample_id, table_data):
        app_logger.info(f"SAMPLE_INFO: Callback update_sample_info acionado. Sample ID: {sample_id}")
        app_logger.debug(f"SAMPLE_INFO: table_data tipo: {type(table_data)}, len: {len(table_data) if table_data is not None else 0}")

        ctx = callback_context
        if not ctx.triggered:
            app_logger.debug("SAMPLE_INFO: No trigger for update_sample_info, returning no_update.")
            return no_update

        if (ctx.triggered[0]['prop_id'] == 'sample-table-store.data' and not table_data) or not sample_id:
            app_logger.warning("SAMPLE_INFO: Dados da tabela ou ID da amostra ausentes (ainda não carregado). Retornando 'Selecione uma amostra'.")
            return build_info_text(None) # Retorna a versão "nenhuma amostra" do build_info_text

        if isinstance(table_data, pd.DataFrame):
            table_data = table_data.to_dict("records")
        elif not isinstance(table_data, list):
            app_logger.error("ERROR: Formato inesperado para table_data em update_sample_info.", exc_info=True)
            return "Erro: Formato de dados inválido."

        sample_data = next((row for row in table_data if row.get("sample_id") == sample_id), None)
        if not sample_data:
            app_logger.warning(f"SAMPLE_INFO: Amostra {sample_id} não encontrada na tabela de dados. Retornando 'Amostra não encontrada'.")
            return build_info_text(None) # Retorna a versão "nenhuma amostra"

        app_logger.info(f"SAMPLE_INFO: Informações para amostra {sample_id} construídas. Retornando.")
        return build_info_text(sample_data)


# NOVO CALLBACK: Para o gráfico de progresso de validações
# dcc.Interval para disparar a atualização periodicamente
    @app.callback(
        Output("validation-progress-graph", "figure"),
        Input("current-validation-table-id-store", "data"),
        Input("confirm-update-btn", "n_clicks"),
        Input("confirm-reset-btn", "n_clicks"),
        Input("progress-interval", "n_intervals"),
        Input("progress-time-unit-dropdown", "value") # NOVO INPUT
    )
    def update_validation_progress_graph(table_id, update_clicks, reset_clicks, n_intervals, time_unit): # NOVO ARG
        app_logger.debug(f"VALIDATION_PROGRESS: Callback acionado para o gráfico de progresso. Trigger: {callback_context.triggered[0]['prop_id']}. Unidade de Tempo: {time_unit}")

        empty_figure_layout = {
            "title": {"text": "Progresso de Validação (N/A)", "font": {"color": "gray", "size": 12}},
            "xaxis": {"visible": False},
            "yaxis": {"visible": False},
            "height": 160,
            "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
            "margin": {"l": 10, "r": 10, "t": 40, "b": 10}
        }
        empty_figure = {"data": [], "layout": empty_figure_layout}

        if not table_id:
            app_logger.warning("VALIDATION_PROGRESS: Nenhum ID de tabela de validação para o gráfico de progresso.")
            return empty_figure

        try:
            df_validated_timestamps = get_validation_timestamps(table_id)
            
            if df_validated_timestamps.empty:
                app_logger.info("VALIDATION_PROGRESS: Nenhuma amostra validada encontrada para o gráfico de progresso ou coluna 'validation_timestamp' ausente/vazia.")
                empty_figure_layout["title"]["text"] = "Progresso de Validação (0 Validações)"
                return {"data": [], "layout": empty_figure_layout}
            
            df_validated_timestamps['validation_timestamp'] = pd.to_datetime(df_validated_timestamps['validation_timestamp'], errors='coerce', utc=True)
            df_validated_timestamps = df_validated_timestamps.dropna(subset=['validation_timestamp'])
            
            if df_validated_timestamps.empty:
                app_logger.info("VALIDATION_PROGRESS: DataFrame de timestamps vazio após conversão e remoção de NaNs.")
                empty_figure_layout["title"]["text"] = "Progresso de Validação (0 Validações)"
                return {"data": [], "layout": empty_figure_layout}

            now_utc = datetime.now(timezone.utc)

            # Lógica para o gráfico de acordo com a unidade de tempo selecionada
            if time_unit == 'total_accumulated':
                # Gráfico de linha acumulado
                df_validated_timestamps = df_validated_timestamps.sort_values('validation_timestamp')
                df_validated_timestamps['count'] = 1
                df_validated_timestamps['accumulated_count'] = df_validated_timestamps['count'].cumsum()

                fig = go.Figure(data=[
                    go.Scatter(
                        x=df_validated_timestamps['validation_timestamp'],
                        y=df_validated_timestamps['accumulated_count'],
                        mode='lines+markers',
                        marker=dict(color=PLOTLY_STATUS_COLORS['VALIDATED'], size=6),
                        line=dict(color=PLOTLY_STATUS_COLORS['VALIDATED'], width=2)
                    )
                ])
                title_text = "Validações Acumuladas ao Longo do Tempo"
                xaxis_title = "Data/Hora"
                yaxis_title = "Nº de Amostras Validadas"

            else:
                # Gráfico de barras por período (último minuto, hora, dia, etc.)
                
                # Define o intervalo de tempo para filtragem
                if time_unit == 'minute':
                    time_delta = pd.Timedelta(minutes=1)
                    x_labels = ["Último Minuto"]
                elif time_unit == 'hour':
                    time_delta = pd.Timedelta(hours=1)
                    x_labels = ["Última Hora"]
                elif time_unit == 'day':
                    time_delta = pd.Timedelta(days=1)
                    x_labels = ["Último Dia"]
                elif time_unit == 'week':
                    time_delta = pd.Timedelta(weeks=1)
                    x_labels = ["Última Semana"]
                elif time_unit == 'month':
                    time_delta = pd.Timedelta(days=30) # Aproximação para mês
                    x_labels = ["Último Mês"]
                elif time_unit == 'year':
                    time_delta = pd.Timedelta(days=365) # Aproximação para ano
                    x_labels = ["Último Ano"]
                else: # Fallback, embora o dropdown force valores válidos
                    time_delta = pd.Timedelta(days=1)
                    x_labels = ["Último Dia"]

                # Filtra as validações dentro do período
                filtered_df = df_validated_timestamps[df_validated_timestamps['validation_timestamp'] > now_utc - time_delta]
                count_in_period = filtered_df.shape[0]

                fig = go.Figure(data=[
                    go.Bar(
                        x=x_labels,
                        y=[count_in_period],
                        marker_color=PLOTLY_STATUS_COLORS['VALIDATED'],
                        text=[count_in_period],
                        textposition='auto',
                    )
                ])
                title_text = f"Validações na {x_labels[0]}"
                xaxis_title = "" # Não precisa de título para um único item no eixo X
                yaxis_title = "Nº de Amostras"


            fig.update_layout(
                title_text=title_text,
                title_x=0.5,
                xaxis_title=xaxis_title,
                yaxis_title=yaxis_title,
                height=160,
                margin=dict(l=20, r=20, t=40, b=20),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="black"), # Garante que a fonte seja preta para ambos os temas
                showlegend=False,
                xaxis=dict(
                    tickangle=-45 if time_unit != 'total_accumulated' else 0, # Inclina labels apenas para o gráfico de barras
                    automargin=True
                ),
                # Ajustes para o eixo Y para começar em zero e ter ticks inteiros se for contagem
                yaxis=dict(
                    rangemode='tozero', # Força o eixo Y a começar em zero
                    tickformat='d' # Formata os ticks como inteiros (sem casas decimais)
                )
            )
            return fig

        except Exception as e:
            app_logger.error(f"VALIDATION_PROGRESS: Erro ao gerar gráfico de progresso de validações: {e}", exc_info=True)
            empty_figure_layout["title"]["text"] = "Erro no Gráfico de Progresso"
            empty_figure_layout["title"]["font"]["color"] = "red"
            return {"data": [], "layout": empty_figure_layout}

    # 14. Callback para atualizar os pontos no mapa principal conforme filtros
    @app.callback(
        Output("points-layer", "children"),
        Output("main-map", "center"),
        Output("main-map", "zoom"),
        Input("sample-table-store", "data"),
        Input("map-year-dropdown", "value"),
        Input("filter-id", "value"),
        # REMOVIDO: State("tab-map-content", "style"), # Removido como State
        Input("tabs", "active_tab"), # ADICIONADO: Input da aba ativa
    )
    def update_map_points(table_data, map_year, sample_id_for_center, active_tab_id): # MODIFICADO: Argumento active_tab_id
        app_logger.info(f"MAP_POINTS: Callback update_map_points acionado. Ano={map_year}, Sample ID para centro={sample_id_for_center}. Aba Ativa: {active_tab_id}") # MODIFICADO: Log
        app_logger.debug(f"MAP_POINTS: table_data tipo: {type(table_data)}, len: {len(table_data) if table_data is not None else 0}")

        ctx = callback_context
        triggered_id = ctx.triggered[0]['prop_id'].split(".")[0] if ctx.triggered else 'initial_load'

        # MODIFICADO: Lógica de saída antecipada. Se a aba 'Mapa' NÃO está ativa
        # E o trigger NÃO veio de sample-table-store ou filter-id (indicando mudança de dados),
        # então retorna no_update para evitar recalculos em abas ocultas.
        if active_tab_id != 'tab-map' and triggered_id not in ['sample-table-store', 'filter-id']:
            app_logger.debug(f"MAP_POINTS: Aba 'Mapa' oculta e trigger '{triggered_id}' não requer atualização. Retornando no_update.")
            return no_update, no_update, no_update

        if not table_data:
            app_logger.warning("MAP_POINTS: Dados da tabela são None ou vazios, retornando lista vazia de pontos.")
            return [], no_update, no_update

        if isinstance(table_data, pd.DataFrame):
            app_logger.debug("MAP_POINTS: Convertendo table_data de DataFrame para lista de dicts.")
            table_data = table_data.to_dict("records")
        elif not isinstance(table_data, list):
            app_logger.error("ERROR: Formato inesperado para table_data no update_map_points.", exc_info=True)
            return [], no_update, no_update

        data_for_markers = table_data

        app_logger.debug(f"MAP_POINTS: {len(data_for_markers)} pontos para gerar marcadores (sem filtros).")

        markers = []
        for row in data_for_markers:
            if 'geometry' in row and row['geometry']:
                try:
                    point = wkt.loads(row['geometry'])
                    lat = point.y
                    lon = point.x
                    app_logger.debug(f"MAP_POINTS: Geometria para sample_id {row.get('sample_id')} parseada: ({lat},{lon}).")
                except Exception as e:
                    app_logger.error(f"ERROR: Erro ao parsear geometria para sample_id {row.get('sample_id')}: {e}", exc_info=True)
                    continue
            else:
                app_logger.warning(f"WARN: Amostra {row.get('sample_id')} sem geometria válida para mapa.")
                continue

            sample_id_row = row.get("sample_id")

            # Cor da marcação com base no status, se disponível
            status_value = row.get('status', 'UNDEFINED')
            marker_color = PLOTLY_STATUS_COLORS.get(status_value, "#6c757d") # MODIFICADO: Usar PLOTLY_STATUS_COLORS para consistência, fallback cinza

            markers.append(
                dl.CircleMarker(
                    center=[lat, lon],
                    radius=5,
                    color=marker_color,
                    fillColor=marker_color,
                    fillOpacity=0.7,
                    children=[
                        dl.Tooltip(f"Amostra: {sample_id_row}<br>Status: {status_value}"),
                        # NOVO: Adicionar um Output para capturar cliques no marker
                        dl.Popup(
                            html.Div([
                                html.P(f"ID: {sample_id_row}"),
                                html.P(f"Bioma: {row.get('biome_name')}"),
                                html.P(f"Classe: {row.get('class_name')}"),
                                html.P(f"Status: {status_value}"),
                                dbc.Button("Selecionar Amostra", id={'type': 'select-sample-marker', 'index': sample_id_row}, className="btn-sm mt-2")
                            ])
                        )
                    ],
                    id={'type': 'map-marker', 'index': sample_id_row}, # ID para o marker para ser clicável
                )
            )

        map_center = no_update
        map_zoom = no_update
        if sample_id_for_center is not None:
            sample_to_center = next((row for row in table_data if row.get("sample_id") == sample_id_for_center), None)
            if sample_to_center:
                lat_center, lon_center = extract_point(sample_to_center)
                if lat_center is not None and lon_center is not None:
                    map_center = [lat_center, lon_center]
                    map_zoom = 14

        app_logger.info(f"MAP_POINTS: Retornando {len(markers)} marcadores para o mapa.")
        return markers, map_center, map_zoom

    # NOVO CALLBACK: Para o clique no marcador do mapa
    @app.callback(
        Output('filter-id', 'value', allow_duplicate=True),
        Input({'type': 'select-sample-marker', 'index': dash.ALL}, 'n_clicks'),
        prevent_initial_call=True
    )
    def select_sample_from_map_marker(n_clicks):
        ctx = callback_context
        if not ctx.triggered or not n_clicks or not any(n for n in n_clicks if n is not None):
            return no_update

        # Encontra qual botão foi clicado
        for i, click_count in enumerate(n_clicks):
            if click_count is not None and click_count > 0:
                triggered_input = ctx.triggered[i]['prop_id']
                if 'index' in triggered_input:
                    # Extrai o sample_id do ID do componente
                    sample_id_str = triggered_input.split('"index":')[-1].split('}')[0].strip()
                    try:
                        sample_id = int(sample_id_str)
                        app_logger.info(f"MAP_POINTS: Marcador de mapa para sample ID {sample_id} clicado. Definindo filter-id.")
                        return sample_id
                    except ValueError:
                        app_logger.error(f"MAP_POINTS: Não foi possível converter o sample ID '{sample_id_str}' do marcador para inteiro.")
                        return no_update
        return no_update

    # NOVO CALLBACK: Atualiza os textos de Definição/Motivo exibidos e adiciona highlight
    @app.callback(
        Output("definition-output", "children"),
        Output("reason-output", "children"),
        Output("definition-radio-container", "className"),
        Output("reason-radio-container", "className"),
        Input("definition-select", "value"),
        Input("reason-select", "value"),
        Input("original-sample-state-store", "data"),
        prevent_initial_call=False
    )
    def update_definition_reason_display_and_highlight(
        current_selected_definition, current_selected_reason, original_sample_state
    ):
        ctx = callback_context
        triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else 'initial_load'

        app_logger.debug(f"DISPLAY_UPDATE: Callback de display de Definição/Motivo acionado. Trigger: {triggered_id}")
        app_logger.debug(f"DISPLAY_UPDATE: Selecionado Def='{current_selected_definition}', Motivo='{current_selected_reason}'")
        app_logger.debug(f"DISPLAY_UPDATE: Original Sample State: {original_sample_state}")


        original_definition = original_sample_state.get('definition') if original_sample_state else None
        original_reason = original_sample_state.get('reason') if original_sample_state else None

        display_definition = current_selected_definition if current_selected_definition is not None else "N/A"
        display_reason = current_selected_reason if current_selected_reason is not None else "N/A"

        definition_display_text = f"Definição: {display_definition}"
        reason_display_text = f"Motivo: {display_reason}"

        base_class = "d-flex flex-column"
        def_container_class = base_class
        reason_container_class = base_class

        if current_selected_definition != original_definition and current_selected_definition is not None:
            def_container_class += " " + HIGHLIGHT_CLASS
            app_logger.debug("HIGHLIGHT: Definição selecionada diferente da original. Adicionando realce.")

        if current_selected_reason != original_reason and current_selected_reason is not None:
            reason_container_class += " " + HIGHLIGHT_CLASS
            app_logger.debug("HIGHLIGHT: Motivo selecionado diferente do original. Adicionando realce.")

        if triggered_id == 'original-sample-state-store':
            app_logger.debug("HIGHLIGHT: Estado original da amostra mudou. Removendo realces.")
            def_container_class = base_class
            reason_container_class = base_class
            definition_display_text = f"Definição: {original_definition if original_definition is not None else 'N/A'}"
            reason_display_text = f"Motivo: {original_reason if original_reason is not None else 'N/A'}"

        app_logger.debug("DISPLAY_UPDATE: Textos de display e classes de highlight retornados.")
        return definition_display_text, reason_display_text, def_container_class, reason_container_class

    # Callback para exibir o modal de confirmação de validação
    @app.callback(
        Output("confirm-update-modal", "is_open"),
        Input("update-button", "n_clicks"),
        State("confirm-update-modal", "is_open"),
        prevent_initial_call=True
    )
    def toggle_update_modal(n_clicks, is_open):
        if n_clicks:
            app_logger.debug("UI_INTERACTION: Abrindo modal de confirmação de atualização.")
            return not is_open
        return is_open

    # Callback para exibir o modal de confirmação de reset
    @app.callback(
        Output("confirm-reset-modal", "is_open"),
        Input("reset-button", "n_clicks"),
        State("confirm-reset-modal", "is_open"),
        prevent_initial_call=True
    )
    def toggle_reset_modal(n_clicks, is_open):
        if n_clicks:
            app_logger.debug("UI_INTERACTION: Abrindo modal de confirmação de reset.")
            return not is_open
        return is_open

    # Callback para exibir o modal de confirmação de exclusão de versão
    @app.callback(
        Output("confirm-delete-modal", "is_open"),
        Input("delete-version-button", "n_clicks"),
        State("confirm-delete-modal", "is_open"),
        prevent_initial_call=True
    )
    def toggle_delete_modal(n_clicks, is_open):
        if n_clicks:
            app_logger.debug("UI_INTERACTION: Abrindo modal de confirmação de exclusão.")
            return not is_open
        return is_open

    # Callback para fechar os modais após confirmação/cancelamento
    @app.callback(
        Output("confirm-update-modal", "is_open", allow_duplicate=True),
        Output("confirm-reset-modal", "is_open", allow_duplicate=True),
        Output("confirm-delete-modal", "is_open", allow_duplicate=True),
        Input("confirm-update-btn", "n_clicks"),
        Input("cancel-update-btn", "n_clicks"),
        Input("confirm-reset-btn", "n_clicks"),
        Input("cancel-reset-btn", "n_clicks"),
        Input("confirm-delete-btn", "n_clicks"),
        Input("cancel-delete-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def close_modals(confirm_update, cancel_update, confirm_reset, cancel_reset, confirm_delete, cancel_delete):
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update

        triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
        if triggered_id in ["confirm-update-btn", "cancel-update-btn"]:
            app_logger.debug(f"UI_INTERACTION: Fechando modal de atualização por {triggered_id}.")
            return False, no_update, no_update
        elif triggered_id in ["confirm-reset-btn", "cancel-reset-btn"]:
            app_logger.debug(f"UI_INTERACTION: Fechando modal de reset por {triggered_id}.")
            return no_update, False, no_update
        elif triggered_id in ["confirm-delete-btn", "cancel-delete-btn"]:
            app_logger.debug(f"UI_INTERACTION: Fechando modal de exclusão por {triggered_id}.")
            return no_update, no_update, False
        return no_update, no_update, no_update
    
    # Callback para exibir/esconder o modal de criação de nova versão
    @app.callback(
        Output("create-new-version-modal", "is_open"),
        Input("create-new-validation-version-button", "n_clicks"),
        Input("cancel-new-version-btn", "n_clicks"),
        Input("confirm-create-new-version-btn", "n_clicks"),
        State("create-new-version-modal", "is_open"),
        prevent_initial_call=True
    )
    def toggle_create_new_version_modal(n_clicks_open, n_clicks_cancel, n_clicks_confirm, is_open):
        ctx = dash.callback_context
        if not ctx.triggered:
            return is_open

        triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

        if triggered_id == "create-new-validation-version-button" and n_clicks_open:
            app_logger.debug("UI_INTERACTION: Abrindo modal de criação de nova versão.")
            return True
        elif triggered_id in ["cancel-new-version-btn", "confirm-create-new-version-btn"] and (n_clicks_cancel or n_clicks_confirm):
            app_logger.debug(f"UI_INTERACTION: Fechando modal de criação de nova versão por {triggered_id}.")
            return False
        return is_open
    
    # Callback para popular os dropdowns de filtro do modal de criação de nova versão
    @app.callback(
        Output("new-version-biome-filter", "options"),
        Output("new-version-class-filter", "options"),
        Input("dataset-selector", "value"),
        Input("create-new-validation-version-button", "n_clicks"),
        prevent_initial_call=False
    )
    def populate_new_version_filters(selected_dataset_key, n_clicks_create_btn):
        ctx = dash.callback_context
        triggered_id = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else 'initial_load'
        app_logger.debug(f"POPULATE_NEW_VERSION_FILTERS: Callback acionado por {triggered_id}. selected_dataset_key: {selected_dataset_key}")
        
        # Só retorna vazio se o dataset for realmente 'error' OU se não houver um dataset selecionado
        # E o trigger NÃO for o botão de criar nova versão (que pode ser clicado antes do dataset ser totalmente sincronizado)
        if selected_dataset_key == "error" or (triggered_id != "create-new-validation-version-button" and not selected_dataset_key):
             app_logger.warning("POPULATE_NEW_VERSION_FILTERS: Dataset key ausente/inválida ou trigger inadequado. Retornando vazio.")
             return [], []

        # Se o trigger foi o botão de criar e selected_dataset_key ainda é None, aguardamos
        # Se selected_dataset_key é None e não foi o botão de criar, já retornamos acima.
        if not selected_dataset_key: # Se chegou aqui, é porque o botão foi clicado, mas o dataset ainda é None.
            return no_update, no_update # Retorna no_update para não limpar as opções se estiverem carregando.

        try:
            original_table_id_for_filters = f"{bq_client.project}.mapbiomas_brazil_validation.APP_0-original_{selected_dataset_key}"
            
            app_logger.debug(f"POPULATE_NEW_VERSION_FILTERS: Buscando opções para biome_name na tabela: {original_table_id_for_filters}")
            biome_options = get_unique_column_values(original_table_id_for_filters, "biome_name")
            
            app_logger.debug(f"POPULATE_NEW_VERSION_FILTERS: Buscando opções para class_name na tabela: {original_table_id_for_filters}")
            class_options = get_unique_column_values(original_table_id_for_filters, "class_name")
            
            app_logger.info(f"POPULATE_NEW_VERSION_FILTERS: Opções de bioma e classe carregadas para dataset '{selected_dataset_key}': {len(biome_options)} biomas, {len(class_options)} classes.")
            return biome_options, class_options
            
        except Exception as e:
            app_logger.error(f"POPULATE_NEW_VERSION_FILTERS: Erro ao carregar opções de filtro para dataset '{selected_dataset_key}': {e}", exc_info=True)
            return ([{"label": "Erro ao carregar", "value": "error_biome"}], 
                    [{"label": "Erro ao carregar", "value": "error_class"}])