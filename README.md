# MapBiomas Validation App

Este projeto é um aplicativo web interativo desenvolvido com [Dash](https://plotly.com/dash/) para apoiar a **validação de amostras geoespaciais**, com foco em desmatamento e outras mudanças de uso e cobertura da terra. Ele integra-se diretamente com o Google BigQuery para gestão de dados e o Google Earth Engine (GEE) para visualização e processamento de informações de satélite em tempo real.

---

## 🎯 Objetivo

A aplicação visa fornecer uma interface eficiente e intuitiva para analistas realizarem a validação de amostras, permitindo:

- **Gerenciamento de Versões de Validação**: Criar, selecionar e gerenciar diferentes versões de bases de dados de amostras no BigQuery.
- **Análise Geospatial Avançada**: Visualizar séries temporais de índices espectrais (como NDVI MODIS), mosaicos anuais (RGB/infravermelho) e camadas temáticas (MapBiomas LULC).
- **Validação de Amostras**: Definir o rótulo (`definition`) e o motivo (`reason`) de uma amostra, registrando as atualizações no BigQuery.
- **Auditoria e Rastreabilidade**: Manter um registro das validações e do estado das amostras.

---

## 🧭 Jornada do Usuário

1.  **Seleciona um Dataset Base** e uma **Versão de Validação** específica (ou cria uma nova).
2.  **Navega** entre as amostras usando ID manual, botões "Anterior" / "Próximo" ou seleção direta na tabela. Pode optar por **navegar apenas amostras não validadas**.
3.  **Visualiza** os dados da amostra nas abas:
    * **Validação por Amostra (Grid)**: Grid de mini-mapas temporais, gráfico de série temporal (NDVI) e gráfico de histórico LULC.
    * **Visualizar Tabela**: Tabela interativa com todos os dados das amostras.
    * **Visualizar no Mapa**: Mapa interativo com marcadores das amostras e camadas GEE auxiliares.
4.  No painel de validação, **define** o rótulo (`definition`) e o motivo (`reason`).
5.  **Atualiza** a amostra no BigQuery (com confirmação) e avança automaticamente para a próxima amostra pendente.

---

## ⚙️ Componentes do App

### Header

-   Logo do MapBiomas.
-   Título: "Plataforma de Validação MapBiomas".
-   Selector de Tema (claro/escuro).

### Controles de Versão

-   **Dataset de Validação**: Dropdown para selecionar o dataset base.
-   **Versão de Validação**: Dropdown para selecionar uma versão específica (tabela BigQuery), com funcionalidade de deleção.
-   **Nova Versão**: Campo para descrição e botão para criar uma nova versão (copiando do dataset base).

### Sidebar

-   **Controle da Amostra**: (Este é o painel combinado que fizemos)
    * **Buscar Amostra por ID**: Input para buscar por ID.
    * Botões de navegação "Anterior" / "Próximo".
    * Opção "Navegar apenas amostras NÃO validadas" (checkbox).
    * **Detalhes da Amostra Atual**: Exibe ID, coordenadas (Lat/Lon), Bioma, Classe e Status atual da amostra. O status é destacado visualmente com cores.
    * **Contador de Progresso**: Mostra o total de amostras validadas vs. total de amostras.
    * **Progresso Recente**: Gráfico que mostra a quantidade de validações nos últimos períodos (minuto, hora, dia, semana, mês, ano). **NOTA: O gráfico de progresso está atualmente mostrando "Erro no Gráfico de Progresso" e não está populando os dados corretamente devido a inconsistências na coluna de timestamp em tabelas existentes ou na lógica de coleta/visualização. Isso requer investigação e correção.**
-   **Validar Amostra**:
    * Rótulos dinâmicos: "Definição: [valor atual]" e "Motivo: [valor atual]", que se atualizam com a seleção do usuário.
    * RadioItems para seleção de *Definição*.
    * RadioItems para seleção de *Motivo* (opções dependem da definição selecionada).
    * Botões: "Validar Amostra" e "Resetar ID" (ambos com modais de confirmação).
    * **Destaque visual**: Os campos de Definição e Motivo são realçados quando o valor selecionado é diferente do valor original da amostra.
-   **Console Dev**: Área para logs de depuração em tempo real da aplicação.

### Área Central (Abas de Visualização)

-   **Validação por Amostra (`tab-grid`)**:
    * Grid de mini-mapas de mosaicos MapBiomas para diferentes anos.
    * Gráfico de série temporal **NDVI** para a amostra selecionada. **NOTA: O gráfico NDVI está atualmente com problemas para carregar ou exibir os dados. Isso requer investigação e correção.**
    * Gráfico de **Histórico de Uso e Cobertura da Terra (LULC)** para a amostra selecionada.
-   **Visualizar Tabela (`tab-table`)**:
    * Tabela interativa ([Dash AG Grid](https://dash.plotly.com/dash-ag-grid)) exibindo todos os dados da versão de validação selecionada.
    * Permite ordenação e filtragem pelo usuário.
    * Linha selecionada é destacada visualmente.
-   **Visualizar no Mapa (`tab-map`)**:
    * Mapa interativo ([Dash Leaflet](https://dash-leaflet.herokuapp.com/)) que exibe marcadores para todas as amostras.
    * Controles para selecionar o ano do mosaico de fundo e adicionar camadas GEE auxiliares (e controlar opacidade).
    * Centraliza o mapa na amostra selecionada.

---

## 💾 Estado Compartilhado

A aplicação utiliza `dcc.Store` para gerenciar o estado da sessão de forma eficiente e otimizar o fluxo de dados entre os callbacks:

-   `sample-table-store`: Armazena os dados brutos da tabela de validação carregada do BigQuery.
-   `current-validation-table-id-store`: O ID completo da tabela de validação atualmente em uso.
-   `original-sample-state-store`: Armazena a definição e o motivo *originais* da amostra selecionada para fins de comparação e destaque.
-   `user-id-store`, `team-id-store`: Informações do usuário e equipe para auditoria.
-   `console-store`: Mantém o histórico de logs para o painel "Console Dev".
-   `go-to-next-sample-trigger`: Sinalizador para disparar a navegação automática para a próxima amostra pendente após a validação.

### ✅ Personalização visual:

-   Alternância de tema entre **Claro** e **Escuro**, com estilos CSS adaptáveis em `assets/style.css`.
-   Componentes adaptados para boa usabilidade.

---

## 🧱 Estrutura do Projeto

```bash
project/
├── app.py              # Inicializa o app Dash e configura o servidor
├── layout.py           # Define a estrutura visual e os componentes da interface
├── callbacks.py        # Contém toda a lógica de interatividade e comunicação com backend
├── utils/
│   ├── logger.py       # Módulo para logging customizado da aplicação
│   ├── constants.py    # Constantes globais, definições de UI, biomas, classes, etc.
│   ├── gee.py          # Funções para interagir com Google Earth Engine (GEE)
│   ├── bigquery.py     # Funções para leitura e escrita no Google BigQuery
│   └── (outros módulos de utilidade não listados aqui, como filters.py, charts.py, etc., se existirem)
├── assets/             # Contém arquivos estáticos como CSS, imagens (mapbiomas_logo.png)
│   └── style.css       # Estilos CSS globais e customizações de tema
├── README.md           # Este arquivo
└── requirements.txt    # Lista de dependências Python
````

-----

## 📌 Funcionalidades Atuais

  - **Gerenciamento de Versões de Validação**:
      - Descoberta e seleção de datasets base (`APP_0-original_`).
      - Descoberta e seleção de versões de validação (`APP_1-validation_`).
      - Criação de **novas versões de validação** (cópia de uma base original).
      - Exclusão de versões de validação existentes (com confirmação).
  - **Navegação e Seleção de Amostras**:
      - Entrada manual de ID da amostra.
      - Botões "Anterior" / "Próximo" para navegação sequencial.
      - **Opção de "Navegar apenas amostras NÃO validadas"**.
      - Seleção de linha na tabela que sincroniza com o ID da amostra.
      - Auto-avanço para a próxima amostra pendente após a validação.
  - **Visualização da Tabela**:
      - Carregamento de dados de validação do BigQuery para uma tabela interativa (Dash AG Grid).
      - Exibição de 1000 registros com paginação.
      - Seleção de linha com destaque visual.
  - **Painel de Validação**:
      - Campos "Definição" e "Motivo" como RadioItems.
      - Opções de "Motivo" dinâmicas baseadas na "Definição" selecionada.
      - **Exibição dinâmica dos valores selecionados**: "Definição: [valor]" e "Motivo: [valor]".
      - **Realce visual** nos RadioItems quando a seleção atual difere do valor original da amostra.
      - Botões "Validar Amostra" e "Resetar ID" (com modais de confirmação).
  - **Visualização Geospatial**:
      - **Grid de Mini-Mapas**: Exibe mosaicos MapBiomas para a amostra selecionada ao longo do tempo.
      - **Gráfico NDVI**: Gera e exibe a série temporal de NDVI para a amostra selecionada.
          * **STATUS: NÃO FUNCIONANDO CORRETAMENTE. Requer depuração na integração com o Google Earth Engine e/ou Plotly.**
      - **Gráfico Histórico LULC**: Gera e exibe o histórico de uso e cobertura da terra para a amostra selecionada.
      - **Mapa Principal**: Exibe todos os pontos das amostras no mapa.
      - Controle de ano para o mosaico de fundo e adição de camadas GEE auxiliares.
  - **Feedback ao Usuário**: Mensagens de status na interface e no console de desenvolvimento.
  - **Alternância de Tema**: Funcionalidade de claro/escuro.
  - **Gráfico de Progresso de Validações**: Exibe a contagem de validações por períodos de tempo.
      * **STATUS: NÃO FUNCIONANDO CORRETAMENTE. Mostra "Erro no Gráfico de Progresso" ou "0 Validações". Requer depuração na coleta de dados da coluna `validation_timestamp` (especialmente para dados históricos) e/ou na geração do gráfico.**

-----

## 🚀 Planejamento Futuro

  - Depurar e corrigir os problemas de carregamento e exibição dos gráficos NDVI e de Progresso de Validações.
  - Refinamento da lógica de filtragem global (se forem reintroduzidos).
  - Modo colaborativo com sistema de login e gerenciamento de usuários.
  - Funcionalidades de exportação de resultados e relatórios.
  - Integração com outras coleções GEE e índices espectrais.

-----

## 🛠️ Requisitos

Python 3.9+

Conta com acesso e credenciais configuradas para Google Earth Engine.

Acesso a projeto e tabelas no Google BigQuery.

**Bibliotecas Python (requer `pip install -r requirements.txt`):**

  - `dash`
  - `dash-bootstrap-components`
  - `dash-leaflet`
  - `dash_ag_grid`
  - `earthengine-api`
  - `pandas`
  - `plotly`
  - `geopandas`
  - `google-cloud-bigquery`
  - `google-cloud-bigquery-storage`
  - `python-dotenv`
  - `Flask`
  - `watchdog`
  - `gunicorn` (para deploy em produção)

-----

## ✍️ Desenvolvido por `ECODE`

Wallace Silva e João Siqueira

Este app é parte das iniciativas MapBiomas para transparência e validação colaborativa de dados de desmatamento.
