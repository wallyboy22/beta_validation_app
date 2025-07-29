# callbacks/grid_view_callbacks.py

import pandas as pd
from dash import Output, Input, State, callback_context, no_update, html
import dash_leaflet as dl 
from shapely import wkt
from datetime import datetime

from utils.logger import app_logger
from utils.constants import YEARS_RANGE, LULC_ASSET, CLASS_INFO, GRID_TILE_SIZE, GRID_STYLE, GRAPH_PANEL_HEIGHT
from utils.gee import get_modis_ndvi, plot_ndvi_series, plot_land_use_history, get_mosaic_url
from callbacks.sample_data_callbacks import extract_point # Importa a função auxiliar

# --- FUNÇÕES AUXILIARES ---
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
    else: # Fallback para o caso de YEARS_RANGE não ser um range ou tupla/lista válida
        years_to_display = list(range(1985, datetime.now().year + 1)) # Default range

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
                ], style={"display": "inline-block", "margin": "2px"})
            )
        except Exception as e:
            app_logger.error(f"UI_BUILD: Erro ao gerar mapa para ano {year} e amostra {sample.get('sample_id')}: {e}", exc_info=True)
            maps_html.append(
                html.Div([
                    html.Div(f"{year}", style={"textAlign": "center", "fontWeight": "bold", "color": "#ff0000"}),
                    html.Div("Erro ao carregar mapa", style={"color": "#ff0000", "fontSize": "12px", "textAlign": "center"})
                ], style={"display": "inline-block", "margin": "2px"})
            )

    return html.Div(maps_html, style=GRID_STYLE)

def register_callbacks(app):
    """
    Registra callbacks para a aba de visualização em grade (mini-mapas, NDVI, LULC History).
    """

    # Callback para atualizar o painel de mapas e gráfico NDVI/LULC History
    @app.callback(
        Output("grid-maps-panel", "children"),
        Output("ndvi-graph", "figure"),
        Output("lulc-history-graph", "figure"),
        Input("filter-id", "value"),
        Input("sample-table-store", "data"),
        State("dataset-selector", "value"),
        Input('tabs', 'active_tab'), # NOVO INPUT: Dispara quando a aba muda
        prevent_initial_call=True
    )
    def update_maps_and_graphs(sample_id, table_data, current_dataset_key, active_tab_id):
        app_logger.info(f"GRID_MAPS_AND_GRAPHS: Callback acionado. Sample ID: {sample_id}. Aba Ativa: {active_tab_id}")
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
        if (triggered_id == 'sample-table-store' and not table_data) or not sample_id:
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
            # Garante que start_year e end_year para o MODIS são consistentes com a coleção
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
            lulc_history_graph_figure = plot_land_use_history(lulc_asset_path, lat, lon, years_for_lulc_history) # MODIFICADO: CLASS_INFO removido
            app_logger.debug(f"GRID_MAPS_AND_GRAPHS: Gráfico LULC Histórico gerado: {'Sim' if lulc_history_graph_figure else 'Não'}")


        except Exception as e:
            app_logger.error(f"ERROR: Erro ao gerar um dos gráficos (NDVI ou LULC History) para amostra {sample_id}. Erro: {e}", exc_info=True)
            # Retorna figuras vazias para os gráficos em caso de erro na geração
            ndvi_graph_figure = {}
            lulc_history_graph_figure = {}


        app_logger.info(f"GRID_MAPS_AND_GRAPHS: Mapas e gráficos NDVI/LULC para amostra {sample_id} construídos. Retornando.")
        return maps_panel_children, ndvi_graph_figure, lulc_history_graph_figure