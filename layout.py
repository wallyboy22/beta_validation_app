import dash_bootstrap_components as dbc
from dash import dcc, html
import dash_leaflet as dl
from dash_ag_grid import AgGrid

from utils.constants import (
    BIOMES, CLASSES, DEFINITION, VISIBLE_COLUMNS,
    GRAPH_PANEL_HEIGHT,
    AUXILIARY_DATASETS, YEARS_RANGE
)
# Importa discover_datasets de utils.bigquery para popular o dataset-selector na inicialização
from utils.bigquery import discover_datasets, bq_client, get_unique_column_values
from utils.logger import app_logger

# Função auxiliar para construir o texto de informações da amostra
def build_sample_control_panel():
    """Constrói um único painel para seleção de ID, informações e progresso da amostra."""
    return html.Div([
        html.H6('Controle da Amostra',className="panel-title mb-2"),
        html.Label("Buscar Amostra por ID", className="form-label fw-bold small"),
        dcc.Input(id="filter-id", type="number", placeholder="Buscar por ID...", debounce=True, className="form-control form-control-sm mb-2"), # form-control-sm, mb-2 
        html.Div([
            dbc.Button("Anterior", id="previous-button", color="secondary", className="me-1 flex-grow-1 btn-sm mb-2"),
            dbc.Button("Próximo", id="next-button", color="secondary", className="flex-grow-1 btn-sm mb-2")
        ]),

        dbc.Checklist(
            options=[
                {"label": "Navegar apenas amostras NÃO validadas", "value": "unvalidated_only"},
            ],
            value=["unvalidated_only"], # Valor inicial (marcado)
            id="toggle-unvalidated-nav",
            inline=False,
            switch=True, # Usando switch para melhor UX
            className="mb-3 small" # mb-3, fonte pequena
        ),
        html.H6("Detalhes da Amostra Atual", className="fw-bold mb-2"), # Novo título
        html.Div(id="sample-info", className="mb-2"), # build_info_text injetará o conteúdo aqui, mb-2
        html.Div(id="validation-counter", className="validation-counter small mb-2"), # mb-2, fonte menor

        html.Hr(className="my-2"),

    ],className="panel mb-2")

def build_sample_validation_panel():
    """Constrói o painel de validação da amostra."""
    return html.Div([
        html.H6('Validar Amostra',className="panel-title mb-2"),
        html.Label("Definição", className="form-label mt-2 fw-bold small"), # mt-2, small
        html.Div(id="definition-output", className="mb-1 text-muted small"), # mb-1, small
        html.Div(
            dcc.RadioItems(
                id="definition-select",
                options=DEFINITION,
                className="list-group list-group-flush",
                inputClassName="form-check-input me-1",
                labelClassName="list-group-item list-group-item-action py-1 px-2 small", # py-1 px-2, small
            ),
            id="definition-radio-container",
            style={"maxHeight": "120px", "overflowY": "auto", "border": "1px solid #dee2e6", "borderRadius": ".375rem"} # Altura menor
        ),

        html.Label("Motivo", className="form-label mt-2 fw-bold small"), # mt-2, small
        html.Div(id="reason-output", className="mb-1 text-muted small"), # mb-1, small
        html.Div(
            dcc.RadioItems(
                id="reason-select",
                options=[],
                className="list-group list-group-flush",
                inputClassName="form-check-input me-1",
                labelClassName="list-group-item list-group-item-action py-1 px-2 small", # py-1 px-2, small
            ),
            id="reason-radio-container",
            style={"maxHeight": "150px", "overflowY": "auto", "border": "1px solid #dee2e6", "borderRadius": ".375rem"} # Altura menor
        ),

        html.Div([
            dbc.Button("Validar Amostra", id="update-button", color="primary", className="me-1 flex-grow-1 btn-sm"), # btn-sm, me-1
            dbc.Button("Resetar ID", id="reset-button", color="warning", className="flex-grow-1 btn-sm"), # btn-sm
        ], className="validation-buttons d-flex justify-content-between mt-2"), # mt-2
    ],className="panel mb-2")

def build_sample_info_panel():
    """Constrói o painel de informações do progresso de validação da versão de validação selecionada."""
    return html.Div([
        html.H6("Progresso Recente", className="panel-title mb-2"),
        # NOVO: Dropdown para selecionar a unidade de tempo
        html.Div([
            html.Label("Exibir por:", className="form-label fw-bold small me-2"),
            dcc.Dropdown(
                id="progress-time-unit-dropdown",
                options=[
                    {'label': 'Último Minuto', 'value': 'minute'},
                    {'label': 'Última Hora', 'value': 'hour'},
                    {'label': 'Último Dia', 'value': 'day'},
                    {'label': 'Última Semana', 'value': 'week'},
                    {'label': 'Último Mês', 'value': 'month'},
                    {'label': 'Último Ano', 'value': 'year'},
                    {'label': 'Acumulado Total', 'value': 'total_accumulated'}, # Opção para acumulado
                ],
                value='day', # Valor padrão
                clearable=False,
                style={'width': '100%'} # Ocupa 100% da largura do div pai
            )
        ], className="d-flex align-items-center mb-2"), # Alinha label e dropdown na mesma linha

        dbc.Spinner( # Adicionado Spinner para o gráfico de progresso
            dcc.Graph(id="validation-progress-graph", style={"height": "160px"}, config={'displayModeBar': False}), # Altura reduzida
            color="primary",
            spinner_style={"width": "2rem", "height": "2rem"} # Spinner menor
        ),
        dcc.Interval( # Intervalo para atualização periódica do gráfico de progresso
            id='progress-interval',
            interval=60*1000, # 1 minuto em milissegundos
            n_intervals=0
        )
    ],className="panel mb-2")

def build_sidebar():
    """Constrói a barra lateral da aplicação."""
    return html.Div([
        build_sample_control_panel(),
        build_sample_validation_panel(),
        build_sample_info_panel()
    ], className="sidebar p-2 d-flex flex-column", style={"minHeight": "100vh"}) # Reduzido padding da sidebar

def create_tab_content(tab_id, content_children):
    """Cria um contêiner para o conteúdo de uma aba."""
    # Reduzido o padding do tab-content-container
    return html.Div(id=tab_id, children=content_children, style={'display': 'none'}, className="tab-content-container p-2")

def build_grid_tab_content():
    """Retorna o conteúdo da aba de Avaliação (mapas de grid e gráficos)."""
    return html.Div([
        html.H3("Visualização da Amostra por grid de imagens", className="text-center mb-3"),
        dbc.Spinner(
            html.Div(id="grid-maps-panel", style={
                "minHeight": "100px",
                # Removido maxHeight e overflowY para evitar scrollbar interna
                "overflowX": "hidden",
                "padding": "0px",
                "width": "100%",
                "display": "flex",
                "flexWrap": "wrap",
                "justifyContent": "center",
                "alignItems": "flex-start"
            }, className="border rounded p-1 mb-3"),
            color="primary",
            spinner_style={"width": "3rem", "height": "3rem"}
        ),
        html.Div([
            dcc.Graph(id="ndvi-graph", style={"height": GRAPH_PANEL_HEIGHT, "width": "100%"}, config={'displayModeBar': False})
        ], className="card p-2 shadow-sm mb-2"), # Reduzido padding e mb-2
        html.Div([
            dcc.Graph(id="lulc-history-graph", style={"height": GRAPH_PANEL_HEIGHT, "width": "100%"}, config={'displayModeBar': False})
        ], className="card p-2 shadow-sm") # Reduzido padding
    ], className="grid-tab-container p-2") # Reduzido padding do container da aba


def build_table_tab_content():
    """Retorna o conteúdo da aba de Tabela com o AgGrid."""
    return html.Div([
        html.H3("Tabela de Validação", className="text-center mb-4"),
        dbc.Spinner(
            AgGrid(
                id="sample-table",
                columnDefs=[{"headerName": col.replace('_', ' ').title(), "field": col} for col in VISIBLE_COLUMNS],
                rowData=[],
                defaultColDef={"sortable": True, "filter": True, "resizable": True, "floatingFilter": True},
                dashGridOptions={"rowSelection": "single", "pagination": True, "paginationPageSize": 20,"getRowId": "params.data.sample_id"},
                className="ag-theme-alpine ag-grid-custom-selection",
                style={"height": "70vh", "width": "100%"},
            ),
            color="primary",
            spinner_style={"width": "3rem", "height": "3rem"}
        ),
    ], className="table-tab-container p-2") # Reduzido padding

def build_map_tab_content():
    """Retorna o conteúdo da aba de Mapa."""
    years_to_use = YEARS_RANGE
    if hasattr(years_to_use, 'start') and hasattr(years_to_use, 'stop'):
        year_options = [{"label": str(y), "value": y} for y in range(years_to_use.start, years_to_use.stop)]
    elif isinstance(years_to_use, (list, tuple)) and len(years_to_use) >= 2:
        year_options = [{"label": str(y), "value": y} for y in range(years_to_use[0], years_to_use[1] + 1)]
    else:
        year_options = [{"label": "Anos Indisponíveis", "value": None}]

    aux_dataset_options = [{"label": d["label"], "value": d["id"]} for d in AUXILIARY_DATASETS]

    return html.Div([
        html.H3("Visualização no Mapa", className="text-center mb-4"),

        dbc.Row([
            dbc.Col([
                html.Label("Ano de Visualização:", className="form-label fw-bold small"),
                dcc.Dropdown(
                    id="map-year-dropdown",
                    options=year_options,
                    value=year_options[-1]['value'] if year_options else None,
                    clearable=False,
                    className="mb-2"
                )
            ], md=3),
            dbc.Col([
                html.Label("Dataset Auxiliar GEE:", className="form-label fw-bold small"),
                dcc.Dropdown(
                    id="aux-gee-dataset-dropdown",
                    options=aux_dataset_options,
                    value=AUXILIARY_DATASETS[0]["id"] if AUXILIARY_DATASETS else None,
                    clearable=True,
                    className="mb-2"
                )
            ], md=3),
            dbc.Col([
                html.Label("Opacidade da Camada GEE:", className="form-label fw-bold small"),
                dcc.Slider(
                    id="gee-layer-opacity-slider",
                    min=0, max=1, step=0.05, value=0.7,
                    marks={0: '0%', 0.5: '50%', 1: '100%'},
                    tooltip={"placement": "bottom", "always_visible": True},
                    className="mt-3"
                )
            ], md=6)
        ], className="map-controls-row mb-3"),

        dbc.Spinner(
            dl.Map(
                id="main-map",
                center=[-8.0, -51.0],
                zoom=5,
                style={'width': '100%', 'height': '70vh', 'borderRadius': '8px', 'border': '1px solid #ddd'},
                children=[
                    dl.TileLayer(url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", attribution="OpenStreetMap"),
                    dl.LayerGroup(id="points-layer"),
                    dl.LayerGroup(id="gee-tile-layer-group")
                ]
            ),
            color="primary",
            spinner_style={"width": "3rem", "height": "3rem"}
        ),
    ], className="map-tab-container p-2")

def build_main_content_area():
    """
    Constrói a área principal de conteúdo com as abas e seus conteúdos.
    """
    return html.Div([
        dbc.Tabs(
            id="tabs",
            active_tab="tab-grid",
            children=[
                dbc.Tab(label="Validação por Amostra", tab_id="tab-grid", className="py-1 px-2 small"),
                dbc.Tab(label="Visualizar Tabela", tab_id="tab-table", className="py-1 px-2 small"),
                dbc.Tab(label="Visualizar no Mapa", tab_id="tab-map", className="py-1 px-2 small"),
            ],
            className="mb-2"
        ),

        create_tab_content("tab-grid-content", build_grid_tab_content()),
        create_tab_content("tab-table-content", build_table_tab_content()),
        create_tab_content("tab-map-content", build_map_tab_content())
    ])

def build_layout(app):
    """
    Constrói o layout completo da aplicação Dash.
    """
    dataset_options = []
    initial_dataset_value = None
    try:
        PROJECT_ID = "mapbiomas"
        DATASET_ID = "mapbiomas_brazil_validation"

        app_logger.debug("LAYOUT_BUILD: Descobrindo datasets para o seletor inicial.")
        discovered_options = discover_datasets(PROJECT_ID, DATASET_ID)
        if discovered_options:
            dataset_options = discovered_options
            if any(opt['value'] == 'deforestation' for opt in discovered_options):
                initial_dataset_value = 'deforestation'
            else:
                initial_dataset_value = discovered_options[0]['value']
        app_logger.info(f"LAYOUT_BUILD: Datasets descobertos: {len(dataset_options)}. Valor inicial: {initial_dataset_value}")
    except Exception as e:
        app_logger.critical(f"ERROR: ERRO CRÍTICO NA DESCOBERTA DE DATASETS para layout: {e}", exc_info=True)
        dataset_options = [{"label": "Erro ao carregar datasets", "value": "error"}]
        initial_dataset_value = "error"


    # ---Buscar opções dinâmicas para Bioma e Classe ---
    # Valores iniciais para os dropdowns de filtro no modal de criação
    # Você precisará definir qual é a tabela "original" padrão para puxar esses valores.
    # Assumindo que você tem uma convenção para o dataset original.
    
    # Determine o dataset original a partir do qual as opções de filtro serão carregadas
    # Se o initial_dataset_value (do discover_datasets) já estiver definido, use-o.
    # Caso contrário, tente um padrão ou o primeiro descoberto.
    
    biome_options = []
    class_options = []
    
    # O dataset original para popular os filtros deve ser um dos 'APP_0-original_...'
    # Usaremos o primeiro dataset descoberto ou um padrão se necessário.
    initial_original_dataset_key_for_filters = None
    if dataset_options:
        # Encontra o primeiro dataset que não seja "error" e seja do tipo original
        for opt in dataset_options:
            if opt['value'] != 'error' and opt['value'].startswith(''): # Já é o 'key', sem o 'APP_0-original_'
                initial_original_dataset_key_for_filters = opt['value']
                break
    
    # Se não houver datasets válidos descobertos, loga o problema.
    if not initial_original_dataset_key_for_filters:
        app_logger.warning("LAYOUT_BUILD: Nenhum dataset original válido encontrado para popular filtros de bioma/classe na inicialização.")
        # Pode definir opções padrão ou deixar vazio se não houver dados.
        # biome_options = [{"label": "Erro ao carregar biomas", "value": "error"}]
        # class_options = [{"label": "Erro ao carregar classes", "value": "error"}]
    else:
        full_original_table_id_for_filters = f"{bq_client.project}.mapbiomas_brazil_validation.APP_0-original_{initial_original_dataset_key_for_filters}"
        try:
            app_logger.debug(f"LAYOUT_BUILD: Buscando opções de bioma para {full_original_table_id_for_filters}.")
            biome_options = get_unique_column_values(full_original_table_id_for_filters, "biome_name")
            app_logger.debug(f"LAYOUT_BUILD: Buscando opções de classe para {full_original_table_id_for_filters}.")
            class_options = get_unique_column_values(full_original_table_id_for_filters, "class_name")
            app_logger.info(f"LAYOUT_BUILD: Biomas/Classes para filtros carregados com sucesso: {len(biome_options)} biomas, {len(class_options)} classes.")
        except Exception as e:
            app_logger.critical(f"ERROR: ERRO CRÍTICO AO CARREGAR OPÇÕES DE BIOMA/CLASSE PARA FILTRO: {e}", exc_info=True)
            biome_options = [{"label": "Erro ao carregar biomas", "value": "error"}]
            class_options = [{"label": "Erro ao carregar classes", "value": "error"}]



    return dbc.Container(fluid=True, id="app-background", className="p-2 app-wrapper", children=[
        dcc.Location(id='url', refresh=False),

        dcc.Store(id="sample-table-store", data=[]),
        dcc.Store(id="current-validation-table-id-store", data=None),
        dcc.Store(id="user-id-store", data="usuario_teste"),
        dcc.Store(id="team-id-store", data="equipe_teste"),
        dcc.Store(id='refresh-trigger-store', data=0),
        dcc.Store(id='go-to-next-sample-trigger', data=None),
        dcc.Store(id='original-sample-state-store', data={}),


        # Modais de Confirmação (mantidos como estão, são funcionais)
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Confirmar Validação")),
            dbc.ModalBody("Você tem certeza que deseja validar esta amostra com as informações atuais?"),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="cancel-update-btn", color="secondary", className="ms-auto"),
                dbc.Button("Confirmar Validação", id="confirm-update-btn", color="primary"),
            ]),
        ], id="confirm-update-modal", centered=True),

        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Confirmar Reset")),
            dbc.ModalBody("Você tem certeza que deseja resetar o ID da amostra atual? Isso limpará os campos de Definição e Motivo."),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="cancel-reset-btn", color="secondary", className="ms-auto"),
                dbc.Button("Confirmar Reset", id="confirm-reset-btn", color="warning"),
            ]),
        ], id="confirm-reset-modal", centered=True),

        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Confirmar Exclusão de Versão")),
            dbc.ModalBody("Você tem certeza que deseja APAGAR a versão de validação selecionada? Esta ação é irreversível."),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="cancel-delete-btn", color="secondary", className="ms-auto"),
                dbc.Button("Confirmar Exclusão", id="confirm-delete-btn", color="danger"),
            ]),
        ], id="confirm-delete-modal", centered=True),

        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Criar Nova Versão de Validação")),
            dbc.ModalBody([
                html.Div([
                    html.Label("Descrição da Versão (opcional)", className="form-label fw-bold small"),
                    dbc.Input(id="new-version-description-input", type="text", placeholder="Ex: Campanha X - Foco Desmatamento", className="form-control-sm mb-3"),
                ]),
                html.Div([
                    html.Label("Filtrar por Bioma(s) (opcional)", className="form-label fw-bold small"),
                    dcc.Dropdown(
                        id="new-version-biome-filter",
                        options=biome_options, # AGORA USANDO AS OPÇÕES CARREGADAS DINAMICAMENTE
                        multi=True,
                        placeholder="Selecionar um ou mais biomas...",
                        className="mb-3"
                    ),
                ]),
                html.Div([
                    html.Label("Filtrar por Classe(s) (opcional)", className="form-label fw-bold small"),
                    dcc.Dropdown(
                        id="new-version-class-filter",
                        options=class_options, # AGORA USANDO AS OPÇÕES CARREGADAS DINAMICAMENTE
                        multi=True,
                        placeholder="Selecionar uma ou mais classes...",
                        className="mb-3"
                    ),
                ]),
                dbc.Checklist(
                    options=[
                        {"label": "Reiniciar dados de validação (status, definição, motivo)", "value": "reset_data"},
                    ],
                    value=["reset_data"],  # Default: marcado (limpar dados)
                    id="new-version-reset-checkbox",
                    switch=True,
                    className="mb-3 small"
                ),
                html.Div(id="new-version-preview-name", className="text-muted small mt-2"),
            ]),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="cancel-new-version-btn", color="secondary", className="me-auto"),
                dbc.Button("Criar Versão", id="confirm-create-new-version-btn", color="primary"),
            ]),
        ], id="create-new-version-modal", centered=True),

        dbc.Row([ # Header: Logo, Título, Tema
            dbc.Col(html.Img(src=app.get_asset_url("mapbiomas_logo.png"), height="50px"), width=1, className="d-flex align-items-center"),
            dbc.Col(html.H2("Plataforma de Validação MapBiomas", className="text-center my-auto fw-bold"), width=9),
            dbc.Col(
                html.Div([
                    html.Span("Tema", className="me-2 text-muted small"),
                    dcc.RadioItems(
                        id="theme-toggle",
                        options=[
                            {'label': html.Span([html.I(className="bi bi-sun-fill me-1"), ' Claro'], className="ms-1"), 'value': 'light'},
                            {'label': html.Span([html.I(className="bi bi-moon-fill me-1"), ' Escuro'], className="ms-1"), 'value': 'dark'},
                        ],
                        value='light',
                        inline=True,
                        labelClassName="me-3 form-check-inline",
                        inputClassName="form-check-input me-1"
                    ),
                ], className="d-flex align-items-center justify-content-end h-100"),
                width=2,
            ),
        ], className="header-row mb-3 border-bottom pb-2"),

        dbc.Row([ # Seletores de Dataset e Versão
            dbc.Col([
                html.Label("Dataset de Validação", className="form-label fw-bold small"),
                dcc.Dropdown(
                    id="dataset-selector",
                    options=dataset_options,
                    value=initial_dataset_value,
                    clearable=False,
                    className="flex-grow-1"
                )
            ], md=3, className="mb-2"),
            dbc.Col([
                html.Label("Versão de Validação", className="form-label fw-bold small"),
                html.Div([ # d-flex align-items-center
                    dcc.Dropdown(
                        id="validation-version-selector",
                        options=[],
                        value=None,
                        clearable=False,
                        # Corrigido 'border-radius' para 'borderRadius' aqui
                        style={'width': 'calc(100% - 32px)', 'display': 'inline-block', 'verticalAlign': 'middle', 'borderRadius': '0.375rem'}
                    ),
                    dbc.Button(
                        html.I(className="bi bi-trash"),
                        id="delete-version-button",
                        color="danger",
                        className="ms-1 btn-sm",
                        outline=True,
                        style={'verticalAlign': 'middle'}
                    )
                ], className="d-flex align-items-center justify-content-between"),
            ], md=6, className="mb-2"),
            dbc.Col([
                html.Label("Criar Nova Versão", className="form-label fw-bold small"),
                dbc.InputGroup([
                    dbc.Button(html.I(className="bi bi-plus-circle"), id="create-new-validation-version-button", color="success", className="ms-1 btn-sm", outline=True),
                ])
            ], md=3, className="mb-2"),
        ], className="version-selection-row mb-3"),

        # ALERTA DE FEEDBACK PARA O USUÁRIO (user-feedback-alert) - Posicionamento Toast
        html.Div(
            dbc.Alert(
                id="user-feedback-alert",
                is_open=False,
                duration=4000,
                className="toast-container position-fixed top-0 end-0 p-3 fade",
                dismissable=True
            ),
            style={"zIndex": 1050}
        ),

        dbc.Row([ # Área Principal de Conteúdo: Sidebar + Tabs
            dbc.Col(build_sidebar(), md=3, className="pe-2 border-end"),
            dbc.Col(build_main_content_area(), md=9, className="ps-2"),
        ], className="main-content-row"),
    ])