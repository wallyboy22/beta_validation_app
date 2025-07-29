# callbacks/map_callbacks.py

import dash_leaflet as dl
# MODIFICADO: Importar ALL diretamente de dash
from dash import Output, Input, State, callback_context, no_update, html, ALL 
from shapely import wkt
import pandas as pd
import dash_bootstrap_components as dbc 

from utils.logger import app_logger
from utils.gee import get_mosaic_url, get_lulc_mapbiomas_url
from utils.constants import AUXILIARY_DATASETS, PLOTLY_STATUS_COLORS
from callbacks.sample_data_callbacks import extract_point

def register_callbacks(app):
    """
    Registra callbacks para o mapa principal da aplicação.
    """

    # Callback para adicionar/remover camadas GEE no mapa principal
    @app.callback(
        Output("gee-tile-layer-group", "children"),
        Input("map-year-dropdown", "value"),
        Input("aux-gee-dataset-dropdown", "value"),
        Input("gee-layer-opacity-slider", "value"),
        Input("tabs", "active_tab"),
        prevent_initial_call=True
    )
    def update_gee_layers(selected_year, selected_aux_dataset_id, opacity, active_tab_id):
        app_logger.info(f"MAP_LAYERS: Callback update_gee_layers acionado. Ano={selected_year}, Aux Dataset={selected_aux_dataset_id}, Opacidade={opacity}. Aba ativa: {active_tab_id}")
        app_logger.debug(f"MAP_LAYERS: ctx.triggered: {callback_context.triggered}")

        # MODIFICADO: Ajuste na lógica de trigger para evitar no_update desnecessário
        # Se a aba 'Mapa' não está ativa E o trigger NÃO veio dos controles do mapa,
        # então retorna no_update.
        triggered_id = callback_context.triggered[0]['prop_id'].split(".")[0] if callback_context.triggered else 'initial_load'
        map_control_triggers = ["map-year-dropdown", "aux-gee-dataset-dropdown", "gee-layer-opacity-slider"]

        if active_tab_id != 'tab-map' and triggered_id not in map_control_triggers:
            app_logger.debug("MAP_LAYERS: Aba 'Mapa' oculta e trigger não relacionado a controles de mapa. Retornando no_update.")
            return no_update

        layers = []

        # Camada de mosaico MapBiomas (base)
        if selected_year:
            try:
                mosaic_url = get_mosaic_url(selected_year)
                if mosaic_url:
                    layers.append(
                        dl.TileLayer(
                            url=mosaic_url,
                            attribution=f"MapBiomas {selected_year}",
                            opacity=1.0
                        )
                    )
                    app_logger.debug(f"MAP_LAYERS: Camada de mosaico {selected_year} adicionada.")
                else:
                    app_logger.warning(f"MAP_LAYERS: URL de mosaico vazia para ano {selected_year}.")
            except Exception as e:
                app_logger.error(f"MAP_LAYERS: Erro ao adicionar camada de mosaico para ano {selected_year}: {e}", exc_info=True)

        # Camada auxiliar GEE
        if selected_aux_dataset_id:
            aux_dataset_info = next((d for d in AUXILIARY_DATASETS if d["id"] == selected_aux_dataset_id), None)
            if aux_dataset_info and aux_dataset_info["type"] == "lulc" and selected_year:
                try:
                    lulc_url = get_lulc_mapbiomas_url(selected_year)
                    if lulc_url:
                        layers.append(
                            dl.TileLayer(
                                url=lulc_url,
                                attribution=aux_dataset_info["label"],
                                opacity=opacity
                            )
                        )
                        app_logger.debug(f"MAP_LAYERS: Camada LULC para ano {selected_year} adicionada.")
                    else:
                        app_logger.warning(f"MAP_LAYERS: URL de LULC vazia para ano {selected_year}.")
                except Exception as e:
                    app_logger.error(f"MAP_LAYERS: Erro ao adicionar camada LULC para ano {selected_year}: {e}", exc_info=True)

        app_logger.info(f"MAP_LAYERS: Retornando {len(layers)} camadas GEE para o mapa principal.")
        return layers

    # Callback para atualizar os pontos no mapa principal conforme filtros
    @app.callback(
        Output("points-layer", "children"),
        Output("main-map", "center"),
        Output("main-map", "zoom"),
        Input("sample-table-store", "data"),
        Input("map-year-dropdown", "value"),
        Input("filter-id", "value"),
        Input("tabs", "active_tab"),
        prevent_initial_call=True
    )
    def update_map_points(table_data, map_year, sample_id_for_center, active_tab_id):
        app_logger.info(f"MAP_POINTS: Callback update_map_points acionado. Ano={map_year}, Sample ID para centro={sample_id_for_center}. Aba Ativa: {active_tab_id}")
        app_logger.debug(f"MAP_POINTS: table_data tipo: {type(table_data)}, len: {len(table_data) if table_data is not None else 0}")

        ctx = callback_context
        triggered_id = ctx.triggered[0]['prop_id'].split(".")[0] if ctx.triggered else 'initial_load'

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
                    lat, lon = extract_point(row)
                    if lat is None or lon is None: continue
                    app_logger.debug(f"MAP_POINTS: Geometria para sample_id {row.get('sample_id')} parseada: ({lat},{lon}).")
                except Exception as e:
                    app_logger.error(f"ERROR: Erro ao parsear geometria para sample_id {row.get('sample_id')}: {e}", exc_info=True)
                    continue
            else:
                app_logger.warning(f"WARN: Amostra {row.get('sample_id')} sem geometria válida para mapa.")
                continue

            sample_id_row = row.get("sample_id")

            status_value = row.get('status', 'UNDEFINED')
            marker_color = PLOTLY_STATUS_COLORS.get(status_value, "#6c757d")

            markers.append(
                dl.CircleMarker(
                    center=[lat, lon],
                    radius=5,
                    color=marker_color,
                    fillColor=marker_color,
                    fillOpacity=0.7,
                    children=[
                        dl.Tooltip(f"Amostra: {sample_id_row}<br>Status: {status_value}"),
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
                    id={'type': 'map-marker', 'index': sample_id_row},
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

    # Callback para o clique no marcador do mapa
    @app.callback(
        Output('filter-id', 'value', allow_duplicate=True),
        Input({'type': 'select-sample-marker', 'index': ALL}, 'n_clicks'), # Corrigido aqui
        prevent_initial_call=True
    )
    def select_sample_from_map_marker(n_clicks):
        ctx = callback_context
        if not ctx.triggered or not n_clicks or not any(n for n in n_clicks if n is not None):
            return no_update

        for i, click_count in enumerate(n_clicks):
            if click_count is not None and click_count > 0:
                triggered_input = ctx.triggered[i]['prop_id']
                if 'index' in triggered_input:
                    sample_id_str = triggered_input.split('"index":')[-1].split('}')[0].strip()
                    try:
                        sample_id = int(sample_id_str)
                        app_logger.info(f"MAP_POINTS: Marcador de mapa para sample ID {sample_id} clicado. Definindo filter-id.")
                        return sample_id
                    except ValueError:
                        app_logger.error(f"MAP_POINTS: Não foi possível converter o sample ID '{sample_id_str}' do marcador para inteiro.")
                        return no_update
        return no_update