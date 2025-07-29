# callbacks/modal_callbacks.py

from dash import Output, Input, State, callback_context, no_update
from utils.logger import app_logger

def register_callbacks(app):
    """
    Registra callbacks para o controle de modais de confirmação.
    """

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