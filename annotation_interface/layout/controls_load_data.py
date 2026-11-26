import dash
from dash import dcc
from dash import html
from dash.dependencies import Input, Output, State
import pandas as pd
import io
import base64
import dash_bootstrap_components as dbc

class ControlsLoadData:
    def __init__(self, config=None):
        self.config = config or {}
        
        self.config_layout = html.Div([
            html.Div([
                html.Label('Sensor ref:', style={'marginRight': '5px', 'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id='dropdown_sensor_ref',
                    options=[],
                    value='x',
                    clearable=False,
                    style={'width': '100%'}
                ),
            ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '5px'}),
        ], style={'width': '100%', 'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'padding': '15px'})

        self.upload_layout = html.Div([
            html.Div([
                html.Label('Load Data:', style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                

                
                dcc.Upload(
                    id='upload-data',
                    children=html.Button('Upload Local CSV', className='hx-btn hx-btn--sage hx-btn--block hx-btn--lg'),
                    multiple=False,
                    accept='.csv',
                    style={'width': '100%'}
                ),
            ]),
            dcc.Store(id='stored_data_sensores'),
            dcc.Store(id='stored_min_max_data'),
            dcc.Store(id='workflow-sensor-trigger')
        ], style={'width': '100%', 'padding': '15px'})


    def register_callbacks(self, app):
        
        # Callback to process CSV upload and store data
        @app.callback(
            Output('stored_data_sensores', 'data', allow_duplicate=True),
            Output('toast-message-store', 'data', allow_duplicate=True),
            Input('upload-data', 'contents'),
            Input('workflow-sensor-trigger', 'data'),
            State('upload-data', 'filename'),
            prevent_initial_call=True,
        )
        def update_data(contents, workflow_path, filename):
            ctx = dash.callback_context
            if not ctx.triggered:
                return dash.no_update, dash.no_update
            
            trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
            
            df = None
            file_identifier = ""

            try:
                if trigger_id == 'workflow-sensor-trigger':
                    if not workflow_path or not __import__('os').path.exists(workflow_path):
                        return dash.no_update, {"message": f"Workflow sensor missing: {workflow_path}", "type": "danger", "header": "Error"}
                    df = pd.read_csv(workflow_path)
                    
                    if 'Data Status' in df.columns:
                        df = df[df['Data Status'] != 'INVALID']
                        
                    file_identifier = __import__('os').path.basename(workflow_path)
                    
                elif trigger_id == 'upload-data' and contents is not None:
                    # Decode base64 content
                    content_type, content_string = contents.split(',')
                    decoded = base64.b64decode(content_string)
                    df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
                    
                    if 'Data Status' in df.columns:
                        df = df[df['Data Status'] != 'INVALID']
                        
                    file_identifier = filename
                else:
                    return dash.no_update, {"message": "No file provided", "type": "warning", "header": "Warning"}

                # Fetch schema from config or use defaults
                schema_config = self.config.get('data_schema', {})
                time_col = schema_config.get('time_column', 'VideoTimelapse')
                factor = schema_config.get('time_conversion_factor', 1000)

                if time_col in df.columns:
                    df['sec'] = df[time_col] / factor
                else:
                    return dash.no_update, {"message": f"Time column '{time_col}' not found in '{file_identifier}'.", "type": "danger", "header": "Error"}

                # Convert DataFrame to a dictionary and store in dcc.Store
                data = df.to_dict('records')

                return data, {"message": f"File '{file_identifier}' successfully loaded.", "type": "success", "header": "Success"}
            except Exception as e:
                return dash.no_update, {"message": f"Error processing file '{file_identifier}': {e}", "type": "danger", "header": "Error"}
        



        # Callback to update dropdowns with column names
        @app.callback(
            [Output('dropdown_sensor_ref', 'options'),
             Output('dropdown_sensor_ref', 'value')],
            Input('stored_data_sensores', 'data')
        )
        def update_dropdowns(data):
            if not data:
                return dash.no_update, dash.no_update

            # Create a DataFrame from stored data
            df = pd.DataFrame(data)

            # Get column names
            column_names = df.columns

            # Create options for dropdowns
            options = [{'label': col, 'value': col} for col in column_names]
            
            # Set default value
            value = dash.no_update
            if 'Value 1' in column_names:
                value = 'Value 1'
            elif len(column_names) > 0:
                value = column_names[0]

            return options, value
