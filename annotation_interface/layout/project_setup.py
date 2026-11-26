import dash
from dash import dcc, html, Input, Output, State, callback_context
import pandas as pd
import os
import io
import base64
import dash_bootstrap_components as dbc

# Folder where standalone annotations will be saved
ANNOTATIONS_DIR = "annotations"

class ProjectSetup(html.Div):
    def __init__(self):
        if not os.path.exists(ANNOTATIONS_DIR):
            os.makedirs(ANNOTATIONS_DIR)
            
        super().__init__([
            html.Div([
                html.Label('Annotation File:', style={'marginRight': '10px', 'fontWeight': 'bold'}),
                dbc.Input(id="standalone-annotation-filename", placeholder="e.g. my_annotation.csv", style={'width': '200px', 'marginRight': '10px'}),
                html.Button('Create', id='btn-standalone-create', n_clicks=0, className='hx-btn hx-btn--primary', style={'marginRight': '10px'}),
                dcc.Upload(
                    id='upload-annotation',
                    children=html.Button('Upload', className='hx-btn'),
                    multiple=False,
                    accept='.csv',
                    style={'marginRight': '10px'}
                ),
                html.Button('Download', id='btn-download-csv', n_clicks=0, className='hx-btn hx-btn--sage'),
                dcc.Download(id="download-dataframe-csv"),
            ], id="standalone-annotation-panel", style={'width': '100%', 'display': 'none', 'alignItems': 'center', 'marginBottom': '10px'}),
            
            html.Div(id='file_name-protocol', style={'fontStyle': 'italic'}),
            
            dcc.Store(id='stored_data_checkpoint'),
            dcc.Store(id='stored_custom_classes'),
            dcc.Store(id='workflow-annotation-trigger')
        ], style={'width': '100%', 'padding': '10px', 'backgroundColor': 'transparent', 'marginBottom': '15px'})

    def register_callbacks(self, app):
        @app.callback(
            Output('toast-message-store', 'data', allow_duplicate=True),
            Output('file_name-protocol', 'children'),
            Output('stored_data_checkpoint', 'data'),
            Output('stored_custom_classes', 'data'),
            Output('btn-delete', 'disabled', allow_duplicate=True),
            Output('btn-add', 'disabled', allow_duplicate=True),
            Output('standalone-annotation-filename', 'value'),
            [Input('btn-standalone-create', 'n_clicks'),
             Input('workflow-annotation-trigger', 'data'),
             Input('upload-annotation', 'contents')],
            [State('standalone-annotation-filename', 'value'),
             State('upload-annotation', 'filename')],
            prevent_initial_call=True
        )
        def process_annotation(n_create, workflow_path, upload_contents, filename, upload_name):
            return _process_annotation(n_create, workflow_path, upload_contents, filename, upload_name) + (dash.no_update,) \
                if dash.callback_context.triggered_id != 'upload-annotation' else _process_upload(upload_contents, upload_name)

        def _process_upload(contents, upload_name):
            expected_columns = ["timestamp", "left_label", "change_point_name", "change_point_time", "sensor_ref"]
            nu = dash.no_update
            if not contents or not upload_name:
                return nu, nu, nu, nu, nu, nu, nu
            safe_name = os.path.basename(upload_name)
            if not safe_name.lower().endswith('.csv'):
                return {"message": "Please upload a .csv annotation file.", "type": "warning", "header": "Warning"}, nu, nu, nu, nu, nu, nu
            try:
                _, content_string = contents.split(',', 1)
                df = pd.read_csv(io.StringIO(base64.b64decode(content_string).decode('utf-8')))
            except Exception as e:
                return {"message": f"Could not read {safe_name}: {e}", "type": "danger", "header": "Error"}, nu, nu, nu, nu, nu, nu
            missing = [c for c in ("timestamp", "left_label", "change_point_name") if c not in df.columns]
            if missing:
                return {"message": f"{safe_name} is not an annotation file (missing: {', '.join(missing)}).", "type": "danger", "header": "Error"}, nu, nu, nu, nu, nu, nu
            for col in expected_columns:
                if col not in df.columns:
                    df[col] = None
            path = os.path.join(ANNOTATIONS_DIR, safe_name)
            df.to_csv(path, index=False)
            return ({"message": f"Uploaded {safe_name} ({len(df)} change points)", "type": "success", "header": "Success"},
                    path, df.to_dict('records'), [], False, False, safe_name)

        def _process_annotation(n_create, workflow_path, upload_contents, filename, upload_name):
            ctx = dash.callback_context
            if not ctx.triggered:
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                
            trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
            expected_columns = ["timestamp", "left_label", "change_point_name", "change_point_time", "sensor_ref"]
            custom_classes = []

            # 1. LOAD VIA DATASET FLOW (Absolute Path)
            if trigger_id == 'workflow-annotation-trigger':
                if not workflow_path:
                    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                    
                path = workflow_path
                try:
                    if os.path.exists(path):
                        df = pd.read_csv(path)
                        for col in expected_columns:
                            if col not in df.columns:
                                df[col] = None
                        return {"message": f"Loaded workflow annotation: {os.path.basename(path)}", "type": "success", "header": "Success"}, path, df.to_dict('records'), custom_classes, False, False
                    else:
                        df = pd.DataFrame(columns=expected_columns)
                        df.to_csv(path, index=False)
                        return {"message": f"Created workflow annotation: {os.path.basename(path)}", "type": "success", "header": "Success"}, path, df.to_dict('records'), custom_classes, False, False
                except Exception as e:
                    return {"message": f"Error loading workflow annotation: {e}", "type": "danger", "header": "Error"}, dash.no_update, dash.no_update, custom_classes, True, True

            # 2. CREATE/LOAD VIA STANDALONE MODE
            if trigger_id == 'btn-standalone-create':
                if not filename or filename.strip() == "":
                    return {"message": "Please enter a valid file name.", "type": "warning", "header": "Warning"}, dash.no_update, dash.no_update, custom_classes, True, True
                
                safe_name = filename.strip()
                if not safe_name.endswith('.csv'):
                    safe_name += '.csv'
                    
                path = os.path.join(ANNOTATIONS_DIR, safe_name)
                
                try:
                    if os.path.exists(path):
                        df = pd.read_csv(path)
                        for col in expected_columns:
                            if col not in df.columns:
                                df[col] = None
                        return {"message": f"Loaded existing file: {safe_name}", "type": "success", "header": "Success"}, path, df.to_dict('records'), custom_classes, False, False
                    else:
                        df = pd.DataFrame(columns=expected_columns)
                        df.to_csv(path, index=False)
                        return {"message": f"File created: {safe_name}", "type": "success", "header": "Success"}, path, df.to_dict('records'), custom_classes, False, False
                except Exception as e:
                    return {"message": f"Error loading/creating file: {e}", "type": "danger", "header": "Error"}, dash.no_update, dash.no_update, custom_classes, True, True
                    
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        @app.callback(
            Output("download-dataframe-csv", "data"),
            Input("btn-download-csv", "n_clicks"),
            State("file_name-protocol", "children"),
            prevent_initial_call=True
        )
        def download_annotation(n_clicks, file_path):
            if file_path and os.path.exists(file_path):
                return dcc.send_file(file_path)
            return dash.no_update