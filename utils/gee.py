# gee.py
#
# Este script contém funções para interagir com a plataforma Google Earth Engine (GEE).
# Inclui funcionalidades para obter séries temporais de índices (como NDVI MODIS),
# gerar URLs de tiles para visualização de mosaicos e mapas de uso e cobertura da terra,
# e plotar históricos de uso da terra para um ponto específico.
#

import ee
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.constants import AUXILIARY_DATASETS, CLASS_INFO
from utils.logger import app_logger
import traceback
import functools # ADICIONADO: Importar functools para caching

# Inicializa a API do Google Earth Engine
try:
    ee.Initialize(project='mapbiomas-brazil')
    app_logger.info("GEE_INIT: Google Earth Engine inicializado com sucesso.")
except Exception as e:
    app_logger.critical(f"GEE_INIT: Erro ao inicializar Google Earth Engine: {str(e)}", exc_info=True)
    # Se a inicialização do GEE falhar, a aplicação não pode funcionar corretamente.
    # É melhor levantar o erro para que a aplicação falhe e o problema seja investigado.
    raise RuntimeError(f"Falha ao inicializar GEE: {e}")

@functools.lru_cache(maxsize=512) # ADICIONADO: Cache para resultados do NDVI
def get_modis_ndvi(start_year, end_year, coordinates):
    """
    Tenta obter uma série temporal de NDVI de forma mais robusta e depurável.
    """
    # MODIFICADO: Garante que o start_year para MODIS não seja anterior a 2000
    modis_start_year = max(2000, start_year)
    modis_end_year = end_year # Mantém o end_year recebido

    app_logger.info(f"GEE_FETCH: Iniciando busca de NDVI MODIS para {coordinates} de {modis_start_year} a {modis_end_year}.")
    try:
        # 1. Definir o ponto GEE
        point = ee.Geometry.Point(coordinates)

        # 2. Definir o intervalo de datas
        start_date = f'{modis_start_year}-01-01'
        end_date = f'{(modis_end_year)}-12-31' # Para incluir o ano final completo

        # 3. Carregar e filtrar a coleção MODIS (MOD13Q1)
        modis_collection = ee.ImageCollection("MODIS/061/MOD13Q1")
        filtered_collection = modis_collection.filterDate(start_date, end_date).filterBounds(point) # Adicionado filterBounds
        app_logger.debug("GEE_FETCH: ee.ImageCollection MODIS/061/MOD13Q1 obtida e filtrada.")

        # Opcional: Contar quantas imagens existem na coleção filtrada
        num_images = filtered_collection.size().getInfo()
        app_logger.debug(f"GEE_FETCH: Número de imagens na coleção filtrada: {num_images}")
        if num_images == 0:
            app_logger.warning(f"GEE_FETCH: Nenhuma imagem MODIS encontrada para {coordinates} no período {modis_start_year}-{modis_end_year}. Retornando DataFrame vazio.") # MODIFICADO: Log mais específico
            return pd.DataFrame(columns=['time', 'NDVI'])


        # 4. Amostrar a coleção sem máscaras ou processamentos complexos no início, apenas selecionar a banda NDVI

        def get_single_ndvi_value(image):
            # Obtém o NDVI e aplica o fator de escala (0.0001)
            ndvi_value = image.select('NDVI').multiply(0.0001)
            # Adiciona propriedades de tempo para o getRegion
            return ndvi_value.set('system:time_start', image.get('system:time_start'))


        # Processa a coleção e amostra
        processed_col = filtered_collection.map(get_single_ndvi_value).select('NDVI')
        app_logger.debug("GEE_FETCH: Coleção processada (apenas escala NDVI) e pronta para getRegion.")


        # 5. Obter a série temporal do ponto
        # Aumentar o scale para 250m é razoável (resolução nativa do MODIS/MOD13Q1)
        app_logger.debug("GEE_FETCH: Chamando getRegion para GEE. Isso pode demorar.")
        ndvi_time_series_raw = processed_col.getRegion(point, 250).getInfo()
        app_logger.debug(f"GEE_FETCH: getRegion executado. Dados GEE brutos (primeiras 5 linhas): {ndvi_time_series_raw[:5] if ndvi_time_series_raw else 'Vazio'}")
        if ndvi_time_series_raw and len(ndvi_time_series_raw) > 1:
            app_logger.debug(f"GEE_FETCH: Dados GEE brutos COMPLETO (primeira e última linha): {ndvi_time_series_raw[0]} ... {ndvi_time_series_raw[-1]}")
        else:
            app_logger.debug(f"GEE_FETCH: Dados GEE brutos COMPLETO: {ndvi_time_series_raw}")
        
        if not ndvi_time_series_raw or len(ndvi_time_series_raw) <= 1:
            app_logger.warning("GEE_FETCH: NDVI MODIS obteve dados vazios ou apenas cabeçalho do GEE após getRegion. Retornando DataFrame vazio.")
            return pd.DataFrame(columns=['time', 'NDVI'])

        # 6. Converter para DataFrame
        headers = ndvi_time_series_raw[0]
        data = ndvi_time_series_raw[1:]
        df = pd.DataFrame(data, columns=headers)

        # Remover colunas desnecessárias e renomear 'time'
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'], unit='ms')
        if 'NDVI' in df.columns:
            # Forçar a conversão para numérico antes de dropna
            df['NDVI'] = pd.to_numeric(df['NDVI'], errors='coerce')

        # Filtrar apenas as colunas necessárias e remover NaNs
        df = df[['time', 'NDVI']].dropna(subset=['NDVI'])

        app_logger.debug(f"GEE_FETCH: DataFrame final de NDVI criado. Linhas: {len(df)}. Primeiras 5: \n{df.head()}")

        if df.empty:
            app_logger.warning("GEE_FETCH: DataFrame de NDVI está vazio após conversão e dropna (todos os valores foram None/NaN).")
            return pd.DataFrame(columns=['time', 'NDVI'])


        app_logger.info(f"GEE_FETCH: NDVI MODIS obtido com {len(df)} pontos.")
        return df

    except Exception as e:
        app_logger.error(f"GEE_FETCH: Erro crítico em get_modis_ndvi: {str(e)}.", exc_info=True)
        return pd.DataFrame(columns=['time', 'NDVI'])

def plot_ndvi_series(df):
    """
        Plota uma série temporal do NDVI. Cores de fundo serão controladas pelo CSS.

        Parâmetros:
        - df (DataFrame): DataFrame com as colunas 'time' e 'NDVI'.

        Retorno:
        - fig (Figure): Gráfico interativo Plotly.
    """
    app_logger.debug("PLOT_NDVI: Gerando gráfico NDVI.")
    if df.empty or 'time' not in df.columns or 'NDVI' not in df.columns:
        app_logger.warning("PLOT_NDVI: DataFrame vazio ou inválido para plotar NDVI.")
        return {
            "data": [],
            "layout": {
                "title": {"text": "NDVI Temporal (Dados Ausentes)", "font": {"color": "gray"}},
                "xaxis": {"title": "Data", "showgrid": False},
                "yaxis": {"title": "NDVI", "showgrid": False, "range": [-1, 1]},
                "height": 300,
                "autosize": True,
                "margin": {"l": 40, "r": 20, "t": 50, "b": 50},
                # Cores de fundo para tema claro (serão sobrescritas pelo CSS para dark)
                "plot_bgcolor": "white",
                "paper_bgcolor": "white",
                "font": {"color": "black"}
            }
        }

    fig = px.line(df, x="time", y="NDVI", labels={"time": "Data", "NDVI": "NDVI"})
    fig.update_yaxes(range=[-1, 1])

    fig.update_layout(
        xaxis_title="Data",
        yaxis_title="NDVI",
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color="black"),
        autosize=True,
        height=300,
        margin=dict(l=40, r=10, t=40, b=40),
        transition_duration=300,
        title=dict(
            font=dict(color="black"),
            x=0.5, xanchor="center",
        )
    )
    fig.update_traces(line=dict(color="#2a9fd6"))
    fig.update_traces(hovertemplate="<b>%{x|%Y-%m-%d}</b><br>NDVI: %{y:.2f}")

    app_logger.info("PLOT_NDVI: Gráfico NDVI gerado com sucesso.")
    return fig

@functools.lru_cache(maxsize=128) # ADICIONADO: Cache para URLs de mosaicos
def get_mosaic_url(year, bands=["swir1_median", "nir_median", "red_median"], gain=[0.08, 0.06, 0.2], gamma=0.85):
    """
    Gera a URL dos tiles para visualizar mosaicos do MapBiomas com base no ano e parâmetros de visualização.

    Parâmetros:
    - year (int): Ano do mosaico desejado.
    - bands (list): Bandas para a composição (ex: ["swir1_median", "nir_median", "red_median"]).
    - gain (list): Fatores de ganho para as bandas.
    - gamma (float): Valor de gama para o ajuste de cores.

    Retorno:
    - tile_url (str): URL do mosaico em formato de tiles para visualização.
    """
    try:
        mosaic = (
            ee.ImageCollection("projects/nexgenmap/MapBiomas2/LANDSAT/BRAZIL/mosaics-2")
            .filterMetadata("year", "equals", year)
            .median()
        )

        vis_params = {
            "bands": bands,
            "gain": gain,
            "gamma": gamma,
        }

        mosaic_vis = mosaic.visualize(**vis_params)
        map_id_dict = ee.data.getMapId({"image": mosaic_vis})
        tile_url = map_id_dict["tile_fetcher"].url_format

        app_logger.debug(f"GEE_MOSAIC_URL: URL do mosaico para ano {year} gerada: {tile_url[:60]}...") # ADICIONADO: Log de depuração
        return tile_url
    except Exception as e:
        app_logger.error(f"GEE_MOSAIC_URL: Erro ao gerar URL do mosaico para ano {year}: {str(e)}", exc_info=True)
        return ""

@functools.lru_cache(maxsize=128) # ADICIONADO: Cache para URLs de LULC MapBiomas
def get_lulc_mapbiomas_url(year):
    """
    Gera a URL dos tiles para visualizar o mapa de Uso e Cobertura da Terra do MapBiomas.
    """
    try:
        lulc_asset_path = next((d["gee_lulc_asset"] for d in AUXILIARY_DATASETS if d["id"] == "lulc"), None)

        if not lulc_asset_path:
            app_logger.error("GEE_LULC_URL: Caminho do asset LULC não encontrado em AUXILIARY_DATASETS.")
            return ""

        lulc_image = ee.Image(lulc_asset_path).select(f'classification_{year}')

        palette = [c["color"] for c in CLASS_INFO]

        class_ids = [c["id"] for c in CLASS_INFO]
        min_class_id = min(class_ids) if class_ids else 0
        max_class_id = max(class_ids) if class_ids else 100

        vis_params = {
            'min': min_class_id,
            'max': max_class_id,
            'palette': palette
        }

        map_id_dict = ee.data.getMapId({"image": lulc_image, 'vis_params': vis_params})
        tile_url = map_id_dict['tile_fetcher'].url_format
        app_logger.debug(f"GEE_LULC_URL: URL do LULC para ano {year} gerada: {tile_url[:60]}...") # ADICIONADO: Log de depuração
        return tile_url
    except Exception as e:
        app_logger.error(f"GEE_LULC_URL: Erro ao gerar URL do mapa LULC para ano {year}: {str(e)}", exc_info=True)
        return ""


@functools.lru_cache(maxsize=512) # ADICIONADO: Cache para histórico de uso da terra
def plot_land_use_history(lulc_asset, latitude, longitude, years):
    """
    Gera um gráfico de histórico de uso e cobertura da terra para um ponto específico.
    Cores de fundo serão controladas pelo CSS.

    Parâmetros:
    - lulc_asset (str): Caminho do asset de uso e cobertura da terra no Google Earth Engine.
    - latitude (float): Latitude do ponto de interesse.
    - longitude (float): Longitude do ponto de interesse.
    - years (list): Lista de anos disponíveis para análise.
    - class_info (list): Lista de dicionários contendo 'id', 'name' e 'color' para as classes de uso e cobertura da terra.
    """
    app_logger.info(f"PLOT_LULC_HISTORY: Gerando gráfico de histórico de uso da terra para {latitude}, {longitude}.")
    try:
        lulc_map = ee.Image(lulc_asset)
        point = ee.Geometry.Point([longitude, latitude])
        bands = [f'classification_{year}' for year in years]

        pixel_values = lulc_map.select(bands).reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=point,
            scale=30
        ).getInfo()

        class_info_df = pd.DataFrame(CLASS_INFO)

        data = []
        for year in years:
            class_value = pixel_values.get(f'classification_{year}', None)
            if class_value is not None:
                # Encontra a classe pelo ID
                matching_class = class_info_df[class_info_df['id'] == class_value]
                if not matching_class.empty:
                    class_name = matching_class['name'].iloc[0]
                    class_color = matching_class['color'].iloc[0]
                    data.append({
                        'year': year,
                        'pixel_value': class_value,
                        'class_name': class_name,
                        'category': str(class_value),
                        'color': class_color
                    })
                else:
                    app_logger.warning(f"PLOT_LULC_HISTORY: Classe ID {class_value} para ano {year} não encontrada em class_info.", extra={"details": {"class_id": class_value, "year": year}})
                    data.append({
                        'year': year,
                        'pixel_value': class_value,
                        'class_name': "Desconhecido",
                        'category': str(class_value),
                        'color': "#808080"
                    })

        df = pd.DataFrame(data)

        if df.empty:
             app_logger.warning("PLOT_LULC_HISTORY: DataFrame de histórico de uso da terra vazio após processamento.")
             return {
                "data": [],
                "layout": {
                    "title": {"text": "Histórico de Uso da Terra (Dados Ausentes)", "font": {"color": "gray"}},
                    "xaxis": {"title": "Ano"},
                    "yaxis": {"title": ""},
                    "height": 180,
                    "autosize": True,
                    "margin": {"l": 10, "r": 10, "t": 40, "b": 10},
                    "plot_bgcolor": "rgba(0,0,0,0)",
                    "paper_bgcolor": "rgba(0,0,0,0)",
                    "font": {"color": "gray"}
                }
            }

        color_map = dict(zip(df['category'], df['color']))

        fig = px.scatter(
            df,
            x='year',
            y=[1] * len(df),
            color='category',
            hover_name="class_name",
            color_discrete_map=color_map,
            labels={'x': 'Ano', 'y': ''},
            title="Histórico de Uso e Cobertura da Terra"
        )

        fig.update_traces(marker=dict(size=12, symbol="square"))
        fig.update_layout(
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color="black"),
            xaxis=dict(showticklabels=True, showgrid=False, dtick=1),
            yaxis=dict(showticklabels=False, showgrid=False, range=[0.5, 1.5]),
            autosize=True,
            height=180,
            margin=dict(l=10, r=10, t=40, b=10),
            title=dict(
                font=dict(color="black"),
                x=0.5, xanchor="center",
                y=0.95, yanchor='top'
            )
        )
        app_logger.info("PLOT_LULC_HISTORY: Gráfico de histórico de uso da terra gerado com sucesso.")
        return fig
    except Exception as e:
        app_logger.error(f"PLOT_LULC_HISTORY: Erro ao gerar gráfico de histórico de uso da terra: {str(e)}", exc_info=True)
        return {
            "data": [],
            "layout": {
                "title": {"text": "Histórico de Uso da Terra (Dados Ausentes)", "font": {"color": "gray"}},
                "xaxis": {"title": "Ano"},
                "yaxis": {"title": ""},
                "height": 180,
                "autosize": True,
                "margin": {"l": 10, "r": 10, "t": 40, "b": 10},
                "plot_bgcolor": "rgba(0,0,0,0)",
                "paper_bgcolor": "rgba(0,0,0,0)",
                "font": {"color": "gray"}
            }
        }