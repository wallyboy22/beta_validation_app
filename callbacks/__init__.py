# callbacks/__init__.py

from .main_sync_callbacks import register_callbacks as register_main_sync_callbacks
from .sample_nav_callbacks import register_callbacks as register_sample_nav_callbacks
from .sample_data_callbacks import register_callbacks as register_sample_data_callbacks
from .table_callbacks import register_callbacks as register_table_callbacks
from .map_callbacks import register_callbacks as register_map_callbacks
from .grid_view_callbacks import register_callbacks as register_grid_view_callbacks
from .progress_graph_callbacks import register_callbacks as register_progress_graph_callbacks
from .theme_callbacks import register_callbacks as register_theme_callbacks
from .modal_callbacks import register_callbacks as register_modal_callbacks # NOVO: Para os modais

def register_all_callbacks(app):
    """
    Registra todos os callbacks da aplicação Dash.
    """
    register_main_sync_callbacks(app)
    register_sample_nav_callbacks(app)
    register_sample_data_callbacks(app)
    register_table_callbacks(app)
    register_map_callbacks(app)
    register_grid_view_callbacks(app)
    register_progress_graph_callbacks(app)
    register_theme_callbacks(app)
    register_modal_callbacks(app) # Registrar os callbacks dos modais