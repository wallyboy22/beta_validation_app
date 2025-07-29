# utils/constants.py

import datetime

YEARS_RANGE = range(1985, 2023)

# Colunas visíveis padrão para exibição em tabelas AgGrid
VISIBLE_COLUMNS = ["sample_id", "biome_name", "class_name", "status", "definition", "reason", "geometry"]

HIGHLIGHT_CLASS = "radio-selection-changed"

# Configurações para o grid de mini-mapas na aba de Avaliação
GRID_DEFAULT_COLS = 5 # Aumentado para 5 para aproveitar o espaço lateral
GRID_TILE_SIZE = 150   # Pixels, tamanho de cada tile/mini-mapa (DIMINUÍDO AINDA MAIS)
GRAPH_PANEL_HEIGHT = "25vh" # Altura do painel do gráfico (Mais compacto)

# Estilo CSS inline para o contêiner do grid de mini-mapas
GRID_STYLE = {
    "display": "flex",
    "flexWrap": "wrap",
    "gap": "2px", # Espaçamento mínimo
    "justifyContent": "center",
    "alignItems": "flex-start",
    "padding": "2px",
    "width": "100%",
}

# Informações sobre Biomas (IDs e nomes amigáveis)
BIOMES = [
    {"label": "Amazônia", "value": 1},
    {"label": "Caatinga", "value": 2},
    {"label": "Cerrado", "value": 3},
    {"label": "Mata Atlântica", "value": 4},
    {"label": "Pantanal", "value": 5},
    {"label": "Pampa", "value": 6},
]

# Informações sobre Classes de Uso e Cobertura da Terra (IDs, nomes e cores para GEE/Plotly)
CLASS_INFO = [
    {"id": 0, "name": "Não Observado", "color": "#000000"},
    {"id": 1, "name": "Floresta", "color": "#1f8d49"},
    {"id": 3, "name": "Formação Florestal", "color": "#1f8d49"},
    {"id": 4, "name": "Formação Savânica", "color": "#7dc975"},
    {"id": 5, "name": "Mangue", "color": "#04381d"},
    {"id": 6, "name": "Floresta Alagável", "color": "#007785"},
    {"id": 49, "name": "Restinga Arbórea", "color": "#02d659"},
    {"id": 10, "name": "Vegetação Herbácea e Arbustiva", "color": "#d6bc74"},
    {"id": 11, "name": "Campo Alagado e Área Pantanosa", "color": "#519799"},
    {"id": 12, "name": "Formação Campestre", "color": "#d6bc74"},
    {"id": 32, "name": "Apicum", "color": "#fc8114"},
    {"id": 29, "name": "Afloramento Rochoso", "color": "#ffaa5f"},
    {"id": 50, "name": "Restinga Herbácea", "color": "#ad5100"},
    {"id": 14, "name": "Agropecuária", "color": "#ffefc3"},
    {"id": 15, "name": "Pastagem", "color": "#edde8e"},
    {"id": 18, "name": "Agricultura", "color": "#E974ED"},
    {"id": 19, "name": "Lavoura Temporária", "color": "#C27BA0"},
    {"id": 39, "name": "Soja", "color": "#f5b3c8"},
    {"id": 20, "name": "Cana", "color": "#db7093"},
    {"id": 40, "name": "Arroz", "color": "#c71585"},
    {"id": 62, "name": "Algodão (beta)", "color": "#ff69b4"},
    {"id": 41, "name": "Outras Lavouras Temporárias", "color": "#f54ca9"},
    {"id": 36, "name": "Lavoura Perene", "color": "#d082de"},
    {"id": 46, "name": "Café", "color": "#d68fe2"},
    {"id": 47, "name": "Citrus", "color": "#9932cc"},
    {"id": 35, "name": "Dendê", "color": "#9065d0"},
    {"id": 48, "name": "Outras Lavouras Perenes", "color": "#e6ccff"},
    {"id": 9, "name": "Silvicultura", "color": "#7a5900"},
    {"id": 21, "name": "Mosaico de Usos", "color": "#ffefc3"},
    {"id": 22, "name": "Área não Vegetada", "color": "#d4271e"},
    {"id": 23, "name": "Praia, Duna e Areal", "color": "#ffa07a"},
    {"id": 24, "name": "Área Urbanizada", "color": "#d4271e"},
    {"id": 30, "name": "Mineração", "color": "#9c0027"},
    {"id": 25, "name": "Outras Áreas não Vegetadas", "color": "#db4d4f"},
    {"id": 26, "name": "Corpo D'água", "color": "#2532e4"},
    {"id": 33, "name": "Rio, Lago e Oceano", "color": "#2532e4"},
    {"id": 31, "name": "Aquicultura", "color": "#091077"},
    {"id": 27, "name": "Não observado", "color": "#ffffff"}
]

# Classes para filtros (subconjunto de CLASS_INFO, apenas id e label)
CLASSES = [
    {"label": c["name"], "value": c["id"]} for c in CLASS_INFO if c["id"] != 0
]

# Status de validação possíveis para amostras
STATUS = [
    {"label": "Pendente", "value": "PENDING"},
    {"label": "Validado", "value": "VALIDATED"},
    {"label": "Erro de Validação", "value": "VALIDATION_ERROR"}
]
# Definições de desmatamento possíveis
DEFINITION = [
  {
    "label": "Indefinido",
    "value": "UNDEFINED"
  },
  {
    "label": "Não é desmatamento",
    "value": "NOT_DEFORESTATION"
  },
  {
    "label": "Desmatamento",
    "value": "DEFORESTATION"
  },

];
# Razões para cada status de validação
REASONS_BY_STATUS = {
  "UNDEFINED": [
    {
      "label": "Não definido", 
      "value": "NO_DEFINITION"
    }
  ],
  "PENDING": [
    {
      "label": "Aguardando validação",
      "value": "AWAITING_VALIDATION"
    }
  ],
  "NOT_DEFORESTATION": [
      {
        "label": "Não era vegetação natural em 1985", 
        "value": "NOT_NATURAL_IN_2008"
      },
      {
        "label": "Não houve desmatamento no período", 
        "value": "NO_DEFORESTATION_IN_PERIOD"
      },
      {
        "label": "Uso anterior consolidado", 
        "value": "PREVIOUSLY_CONSOLIDATED_USE"
      },
      {
        "label": "Outra razão (Não Desmatamento)", 
        "value": "OTHER_NOT_DEFORESTATION"
      },
  ],
  "DEFORESTATION": [
      
      # todos os anos
      {"label": f"Desmatamento em {year}", "value": f"DEFORESTATION_IN_{year}"}
      for year in range(1985, datetime.datetime.now().year + 1)
  ]
}

# Cores para Status (pode ser usado com dbc.Badge ou texto)
STATUS_COLORS = {
    "PENDING": "info",    # Azul claro (Bootstrap)
    "VALIDATED": "success", # Verde (Bootstrap)
    "VALIDATION_ERROR": "danger", # Vermelho (Bootstrap)
    "UNDEFINED": "secondary" # Cinza (Bootstrap)
}

# Cores correspondentes para Plotly (usando hex codes)
PLOTLY_STATUS_COLORS = {
    "PENDING": "#17a2b8",    # Cor info do Bootstrap
    "VALIDATED": "#28a745", # Cor success do Bootstrap
    "VALIDATION_ERROR": "#dc3545", # Cor danger do Bootstrap
    "UNDEFINED": "#6c757d" # Cor secondary do Bootstrap
}

# Caminho do asset LULC padrão no GEE
LULC_ASSET = "projects/mapbiomas-public/assets/brazil/lulc/collection9/mapbiomas_collection90_integration_v1"

# Ativos auxiliares GEE (para visualização no mapa)
AUXILIARY_DATASETS = [
    {
        "id": "modis_ndvi",
        "gee_modis_asset": "MODIS/061/MOD13Q1",
        "label": "NDVI MODIS",
        "type": "index",
        "years": list(range(2000, 2024)),
        "get_data_function": "get_modis_ndvi",
    },
    {
        "id": "lulc",
        "gee_lulc_asset": "projects/mapbiomas-public/assets/brazil/lulc/collection9/mapbiomas_collection90_integration_v1",
        "label": "Uso e Cobertura (MapBiomas)",
        "type": "lulc",
        "years": list(range(1985, 2024)),
        "get_data_function": "get_lulc_mapbiomas",
    }
]