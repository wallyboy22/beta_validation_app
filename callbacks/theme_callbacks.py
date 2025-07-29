# callbacks/theme_callbacks.py

from dash import Output, Input, callback_context
from utils.logger import app_logger

def register_callbacks(app):
    """
    Registra callbacks para alternância de tema da aplicação.
    """

    @app.callback(
        Output("app-background", "className"),
        Input("theme-toggle", "value"),
    )
    def update_theme_class(theme_value):
        app_logger.debug(f"THEME: Callback update_theme_class acionado. Tema: {theme_value}.")
        if theme_value == "dark":
            return "app-background theme-dark"
        return "app-background"