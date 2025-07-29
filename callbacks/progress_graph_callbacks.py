# callbacks/progress_graph_callbacks.py

import pandas as pd
import plotly.graph_objects as go
from dash import Output, Input, State, callback_context, no_update
from datetime import datetime, timezone

from utils.bigquery import get_validation_timestamps
from utils.constants import PLOTLY_STATUS_COLORS
from utils.logger import app_logger

def register_callbacks(app):
    """
    Registra callbacks para o gráfico de progresso de validações.
    """

    @app.callback(
        Output("validation-progress-graph", "figure"),
        Input("current-validation-table-id-store", "data"),
        Input("confirm-update-btn", "n_clicks"),
        Input("confirm-reset-btn", "n_clicks"),
        Input("progress-interval", "n_intervals"),
        Input("progress-time-unit-dropdown", "value")
    )
    def update_validation_progress_graph(table_id, update_clicks, reset_clicks, n_intervals, time_unit):
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

            if time_unit == 'total_accumulated':
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
                    time_delta = pd.Timedelta(days=30)
                    x_labels = ["Último Mês"]
                elif time_unit == 'year':
                    time_delta = pd.Timedelta(days=365)
                    x_labels = ["Último Ano"]
                else:
                    time_delta = pd.Timedelta(days=1)
                    x_labels = ["Último Dia"]

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
                xaxis_title = ""
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
                font=dict(color="black"),
                showlegend=False,
                xaxis=dict(
                    tickangle=-45 if time_unit != 'total_accumulated' else 0,
                    automargin=True
                ),
                yaxis=dict(
                    rangemode='tozero',
                    tickformat='d'
                )
            )
            return fig

        except Exception as e:
            app_logger.error(f"VALIDATION_PROGRESS: Erro ao gerar gráfico de progresso de validações: {e}", exc_info=True)
            empty_figure_layout["title"]["text"] = "Erro no Gráfico de Progresso"
            empty_figure_layout["title"]["font"]["color"] = "red"
            return {"data": [], "layout": empty_figure_layout}