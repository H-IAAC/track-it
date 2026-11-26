import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import os
import json
import yaml

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))

class SessionSelector:
    def __init__(self):
        self.layout = html.Div([
            html.Div([
                html.Label('Session:', style={'marginRight': '8px', 'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id='session-dropdown',
                    options=self._get_sessions(),
                    placeholder="Select session...",
                    style={'width': '220px', 'marginRight': '15px', 'display': 'inline-block', 'verticalAlign': 'middle'}
                ),
                html.Label('Sensor & Position:', style={'marginRight': '8px', 'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id='sensor-stream-dropdown',
                    placeholder="Select sensor & position...",
                    clearable=False,
                    style={'width': '280px', 'marginRight': '15px', 'display': 'inline-block', 'verticalAlign': 'middle'}
                ),
                html.Label('Annotator:', style={'marginRight': '8px', 'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id='annotator-dropdown',
                    placeholder='Select or type new...',
                    searchable=True,
                    clearable=True,
                    style={'width': '180px', 'marginRight': '15px', 'display': 'inline-block', 'verticalAlign': 'middle'}
                ),
                html.Button('Load Session', id='btn-load-session', n_clicks=0, className='hx-btn hx-btn--primary'),
            ], id="dataset-flow-panel", style={'width': '100%', 'display': 'flex', 'alignItems': 'center', 'padding': '12px 15px', 'flexWrap': 'wrap', 'gap': '6px'}),
            
            dcc.Store(id="selected-workflow-paths"),
            dcc.Interval(id="session-refresh-interval", interval=5000)
        ])

    def _get_sessions(self):
        if not os.path.exists(DATA_DIR):
            return []
            
        sessions = []
        for folder in sorted(os.listdir(DATA_DIR)):
            folder_path = os.path.join(DATA_DIR, folder)
            if os.path.isdir(folder_path):
                manifest_path = os.path.join(folder_path, "session_manifest.json")
                if os.path.exists(manifest_path):
                    sessions.append({'label': folder, 'value': folder})
        return sessions

    def register_callbacks(self, app):
        @app.callback(
            Output('session-dropdown', 'options'),
            Input('session-refresh-interval', 'n_intervals'),
            State('session-dropdown', 'options')
        )
        def refresh_sessions(_, current):
            sessions = self._get_sessions()
            return dash.no_update if sessions == current else sessions

        @app.callback(
            Output('sensor-stream-dropdown', 'options'),
            Output('sensor-stream-dropdown', 'value'),
            Input('session-dropdown', 'value')
        )
        def update_sensor_options(session_folder):
            if not session_folder:
                return [], None
            folder_path = os.path.join(DATA_DIR, session_folder)
            manifest_path = os.path.join(folder_path, "session_manifest.json")
            if not os.path.exists(manifest_path):
                return [], None
            try:
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
            except Exception:
                return [], None

            clean_sensors = manifest.get('artifacts', {}).get('clean_sensors', [])
            if not clean_sensors:
                sensors_dir = os.path.join(folder_path, "sensors")
                if os.path.exists(sensors_dir):
                    clean_sensors = [f"sensors/{f}" for f in sorted(os.listdir(sensors_dir)) if f.endswith(".csv")]
                elif manifest.get('artifacts', {}).get('raw_sensors'):
                    clean_sensors = manifest['artifacts']['raw_sensors']

            def _format_label(s):
                stem = os.path.basename(s).replace(".csv", "")
                if "_" in stem:
                    parts = stem.split("_", 1)
                    return f"{parts[0]} — {parts[1]}"
                return stem

            options = [{'label': _format_label(s), 'value': s} for s in clean_sensors]
            default_val = clean_sensors[0] if clean_sensors else None
            return options, default_val

        @app.callback(
            Output('stored-activity-labels', 'data', allow_duplicate=True),
            Input('session-dropdown', 'value'),
            prevent_initial_call=True
        )
        def sync_session_labels(session_folder):
            if not session_folder:
                return dash.no_update
            manifest_path = os.path.join(DATA_DIR, session_folder, "session_manifest.json")
            if not os.path.exists(manifest_path):
                return dash.no_update
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
            except Exception:
                return dash.no_update

            config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
            default_activities = []
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        conf = yaml.safe_load(f) or {}
                        default_activities = conf.get('activities', [])
                except Exception:
                    pass

            session_labels = manifest.get('activity_labels')
            if not session_labels:
                session_labels = default_activities
                manifest['activity_labels'] = session_labels
                try:
                    with open(manifest_path, 'w', encoding='utf-8') as f:
                        json.dump(manifest, f, indent=4)
                except Exception:
                    pass

            # Sync session labels to config.yaml
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        conf = yaml.safe_load(f) or {}
                    conf['activities'] = session_labels
                    with open(config_path, 'w', encoding='utf-8') as f:
                        yaml.safe_dump(conf, f, sort_keys=False)
                except Exception:
                    pass

            return session_labels

        @app.callback(
            Output('annotator-dropdown', 'options'),
            Input('session-dropdown', 'value'),
            Input('annotator-dropdown', 'search_value'),
            Input('annotator-dropdown', 'value')
        )
        def update_annotator_list(session_folder, search_value, current_value):
            annotators = set()
            if session_folder:
                folder_path = os.path.join(DATA_DIR, session_folder, "annotations")
                if os.path.exists(folder_path):
                    for f in os.listdir(folder_path):
                        if f.endswith(".csv") and "_Ann_" in f:
                            parts = f.replace(".csv", "").split("_Ann_")
                            if len(parts) == 2:
                                annotators.add(parts[1])
            
            if current_value:
                annotators.add(current_value)
            options = [{'label': a, 'value': a} for a in sorted(list(annotators))]
            
            if search_value and search_value not in annotators:
                options.append({'label': f'Create "{search_value}"', 'value': search_value})
                
            return options

        @app.callback(
            Output('selected-workflow-paths', 'data'),
            Output('toast-message-store', 'data', allow_duplicate=True),
            Input('btn-load-session', 'n_clicks'),
            Input('sensor-stream-dropdown', 'value'),
            Input('annotator-dropdown', 'value'),
            State('session-dropdown', 'value'),
            prevent_initial_call=True
        )
        def load_session(n_clicks, selected_sensor, annotator_name, session_folder):
            ctx = dash.callback_context
            triggered_id = ctx.triggered_id if ctx.triggered else None

            # Must have both session and annotator
            if not session_folder or not annotator_name:
                if triggered_id == 'btn-load-session':
                    if not session_folder:
                        return dash.no_update, {"message": "Please select a session.", "type": "warning", "header": "Warning"}
                    if not annotator_name:
                        return dash.no_update, {"message": "Please select or type an annotator name.", "type": "warning", "header": "Warning"}
                return dash.no_update, dash.no_update

            folder_path = os.path.join(DATA_DIR, session_folder)
            manifest_path = os.path.join(folder_path, "session_manifest.json")
            
            if not os.path.exists(manifest_path):
                return dash.no_update, {"message": "Manifest not found.", "type": "danger", "header": "Error"}
                
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            artifacts = manifest.get('artifacts', {})
            video_file = artifacts.get('anonymized_video') or artifacts.get('raw_video')
            
            clean_sensors = artifacts.get('clean_sensors', [])
            sensor_file = selected_sensor
            if not sensor_file:
                if clean_sensors and isinstance(clean_sensors, list):
                    sensor_file = clean_sensors[0]
                elif artifacts.get('raw_sensors'):
                    sensor_file = artifacts['raw_sensors'][0]
                
            ann_folder = os.path.join(folder_path, "annotations")
            os.makedirs(ann_folder, exist_ok=True)
            ann_name = f"{session_folder}_Ann_{annotator_name}.csv"
            ann_path = os.path.join(ann_folder, ann_name)
            
            paths = {
                "video_path": os.path.abspath(os.path.join(folder_path, video_file)) if video_file else None,
                "sensor_path": os.path.abspath(os.path.join(folder_path, sensor_file)) if sensor_file else None,
                "annotation_path": os.path.abspath(ann_path)
            }
            
            sensor_label = os.path.basename(sensor_file).replace(".csv", "").replace("_", " — ") if sensor_file else "Sensor"
            if triggered_id == 'sensor-stream-dropdown':
                msg = f"Switched to sensor: {sensor_label}"
            elif triggered_id == 'annotator-dropdown':
                msg = f"Auto-loaded Annotator: {annotator_name} ({sensor_label})"
            else:
                msg = f"Loaded Session: {session_folder} ({annotator_name})"
                
            return paths, {"message": msg, "type": "success", "header": "Session Loaded"}
