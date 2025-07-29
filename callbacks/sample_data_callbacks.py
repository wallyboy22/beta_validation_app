# callbacks/sample_data_callbacks.py

import pandas as pd
from dash import Output, Input, State, callback_context, no_update, html # ADICIONADO: html
import dash_bootstrap_components as dbc
from shapely import wkt

from utils.constants import REASONS_BY_STATUS, STATUS_COLORS, HIGHLIGHT_CLASS
from utils.logger import app_logger

# --- FUNÇÕES AUXILIARES ---
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

        biome_name = sample_data.get('biome_name', 'N/A')
        class_name = sample_data.get('class_name', 'N/A')


        metrics_content = []

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

def register_callbacks(app):
    """
    Registra callbacks para exibição e atualização de dados de amostra.
    """

    # Callback para atualizar opções de motivo conforme definição selecionada
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

    # Callback para atualizar os campos de definição e motivo da amostra selecionada
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

    # Callback para atualizar o contador de validação
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

    # Callback para atualizar os textos de Definição/Motivo exibidos e adiciona highlight
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