# app.py
#
# Este é o ponto de entrada principal da aplicação Dash para validação de dados geoespaciais.
# Ele inicializa o aplicativo Dash, define o layout principal e registra todos os callbacks.
# A inicialização do BigQuery foi simplificada, removendo dependências de tabelas de metadados.
#

import dash
import dash_bootstrap_components as dbc
import os

# Importa as funções auxiliares e de BigQuery
from layout import build_layout
# MODIFICADO: Importa de 'callbacks' (o pacote)
from callbacks import register_all_callbacks
from utils.logger import app_logger

# -----------------------------------------------------------
# Inicialização da Aplicação Dash
# -----------------------------------------------------------

app_logger.info("APP_START: Bem-vindo! Aplicação de validação MapBiomas iniciando...")

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css"
    ],
    suppress_callback_exceptions=True
)

server = app.server

# -----------------------------------------------------------
# Configuração do BigQuery (Verificações removidas/simplificadas)
# -----------------------------------------------------------
app_logger.info("APP_START: Preparando BigQuery (verificações de tabelas de log/metadados removidas).")

# -----------------------------------------------------------
# Definição do Layout e Registro de Callbacks
# -----------------------------------------------------------

app_logger.info("APP_START: Construindo layout da aplicação...")
app.layout = build_layout(app)
app_logger.info("APP_START: Layout construído. Registrando callbacks...")

# MODIFICADO: Chama a função principal de registro de todos os callbacks
register_all_callbacks(app)
app_logger.info("APP_START: Callbacks registrados. Aplicação pronta.")

# -----------------------------------------------------------
# Execução da Aplicação (Localmente)
# -----------------------------------------------------------
if __name__ == "__main__":
    os.environ['APP_LOG_LEVEL'] = 'DEBUG'
    app_logger.info("APP_RUN: Executando o servidor Dash localmente...")
    app.run_server(debug=True, port=8080)