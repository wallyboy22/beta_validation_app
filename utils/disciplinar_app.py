from dash import Dash, html, Output, Input
from dash_ag_grid import AgGrid
from utils.bigquery import get_dataset_table

import pandas as pd
from utils.constants import BIOMES, CLASSES
from google.cloud import bigquery

def salvar_dataframe_no_bigquery(df, table_name, project_id="mapbiomas"):
    # Converte todas as colunas booleanas para string (ou int, se preferir)
    for col in df.select_dtypes(include=["bool"]).columns:
        df[col] = df[col].astype(str)
    client = bigquery.Client(project=project_id)
    job = client.load_table_from_dataframe(
        df,
        table_name,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    )
    job.result()
    print(f"Tabela salva em {table_name} com {len(df)} linhas.")


def preparar_dataframe(df):
    # 1. Popular biome_name e class_name
    biome_dict = {b["value"]: b["label"] for b in BIOMES}
    class_dict = {c["value"]: c["label"] for c in CLASSES}
    df["biome_name"] = df["biome_id"].map(biome_dict)
    df["class_name"] = df["class_id"].map(class_dict)

    # 2. Ajustar status, validated, definition, reason
    def ajustar_linha(row):
        if row.get("status", "").upper() == "PENDING":
            row["validated"] = ""
            row["reason"] = ""
            row["definition"] = ""
        else:
            if row.get("status", "").upper() != "VALIDATED":
                row["definition"] = row["status"]
                row["status"] = "VALIDATED"
        return row

    df = df.apply(ajustar_linha, axis=1)

    # 3. Reordenar colunas
    ordem = [
        "sample_id","version", "biome_id", "biome_name", "class_id", "class_name", "status", "definition", "reason", "geometry"
    ]
    # Adiciona colunas extras no final, se existirem
    outras = [col for col in df.columns if col not in ordem]
    df = df[ordem]
   
    for col in df.select_dtypes(include=["bool"]).columns:
        df[col] = df[col].astype(str)
    return df

# --- No seu script principal ---
df = get_dataset_table('deforestation')
df = preparar_dataframe(df)

app = Dash(__name__)

app.layout = html.Div([
    html.Div([
        html.H2("Tabela completa do BigQuery", style={"display": "inline-block", "margin-right": "2rem"}),
        html.Button("Salvar no BigQuery", id="save-bq-btn", n_clicks=0, style={"display": "inline-block"}),
        html.Span(id="save-status", style={"margin-left": "1rem", "color": "green"})
    ], style={"margin-bottom": "1rem"}),
    AgGrid(
        id="disciplinar-table",
        columnDefs=[
            {"headerName": col, "field": col, "filter": False} for col in df.columns
        ],
        rowData=df.to_dict("records"),
        defaultColDef={
            "sortable": True,
            "filter": False,
            "resizable": True,
            "floatingFilter": False,
        },
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": 20,
            "domLayout": "autoHeight",
        },
        style={"height": "80vh", "width": "100%"},
        className="ag-theme-alpine",
    )
])

# 2. Callback para salvar ao clicar no botão
@app.callback(
    Output("save-status", "children"),
    Input("save-bq-btn", "n_clicks"),
    prevent_initial_call=True
)
def salvar_no_bq_callback(n_clicks):
    if n_clicks:
        salvar_dataframe_no_bigquery(
            df,
            "mapbiomas_brazil_validation.deforestation_v001"
        )
        return "Tabela salva com sucesso!"
    return ""

if __name__ == "__main__":
    app.run_server(debug=True, port=7070)