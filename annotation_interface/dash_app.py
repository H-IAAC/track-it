import yaml
import dash
from dash import Dash, dcc, html, Input, Output, State
from flask import send_file, abort

from layout.project_setup import ProjectSetup
from layout.zoom import LoadZoom
from layout.brush import PlotBrush
from layout.video import VideoPlayer
from layout.controls_load_data import ControlsLoadData
from layout.control_timestamp import ControlsTimestamp
from layout.control_chekpoint import ControlsChekpoint
from layout.header import Header
from layout.session_selector import SessionSelector

import dash_bootstrap_components as dbc

class DashApp:
    def __init__(self, config_path='config.yaml'):
        import os
        self.config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), config_path)) if not os.path.isabs(config_path) else config_path
        self.config = self._load_config(self.config_path)
        self.app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
        self._setup_routes()
        self.app.layout = self._create_layout
        self._register_callbacks()

    def _load_config(self, config_path):
        with open(config_path, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)

    def _setup_routes(self):
        @self.app.server.route('/serve_video/<path:filepath>')
        def serve_video(filepath):
            import os
            from flask import send_file, abort
            if not filepath.startswith('/'):
                filepath = '/' + filepath
            if not os.path.exists(filepath):
                abort(404)
            return send_file(filepath, mimetype='video/mp4')

    def _create_layout(self):
        self.config = self._load_config(self.config_path)
        header = Header()
        session_selector = SessionSelector()
        controls_load_data_sensors = ControlsLoadData(self.config)
        plot_brush = PlotBrush()
        control_chekpoint = ControlsChekpoint(self.config)
        load_zoom_layout = LoadZoom()
        video_player = VideoPlayer(
            id_upload='upload-video', 
            id_output='output-video-player',
            style={'flexGrow': 1, 'display': 'flex', 'flexDirection': 'column', 'minHeight': 0}
        )
        load_data_activities_layout = ProjectSetup()
        controls_timestamp = ControlsTimestamp()

        card_style = {'boxSizing': 'border-box'}
        card = 'hx-card ann-card'
        
        return html.Div([
            header.layout,
            
            # Dataset Flow Panel (Session Selector)
            html.Div(session_selector.layout, id="dataset-flow-container", style={'display': 'block'}),
            
            # Top Section (Graph and Video)
            html.Div([
                html.Div([
                    html.Div(control_chekpoint, className=card, style=card_style),
                    html.Div(load_zoom_layout, className=card, style=card_style)
                ], style={'width': '70%', 'display': 'flex', 'flexDirection': 'column', 'paddingRight': '10px', 'boxSizing': 'border-box'}),
                
                html.Div([
                    html.Div(video_player, className=card, style=dict(card_style, flexGrow=1, display='flex', flexDirection='column', minHeight=0))
                ], style={'width': '30%', 'display': 'flex', 'flexDirection': 'column', 'paddingLeft': '10px', 'boxSizing': 'border-box', 'minHeight': 0})
            ], style={'display': 'flex', 'width': '100%', 'alignItems': 'stretch'}),
            
            # Middle Section (Config Sensor and Load CSV)
            html.Div([
                html.Div([
                    controls_load_data_sensors.config_layout
                ], style={'width': '70%', 'paddingRight': '10px', 'boxSizing': 'border-box'}),
                
                html.Div([
                    html.Div(controls_load_data_sensors.upload_layout, id="standalone-sensor-panel", style={'display': 'none'})
                ], style={'width': '30%', 'paddingLeft': '10px', 'boxSizing': 'border-box'})
            ], style={'display': 'flex', 'width': '100%'}),
            
            # Bottom Section (Load Annotation, Brush Plot, Timeline)
            html.Div([
                html.Div(plot_brush, className=card, style=card_style),
                html.Div(controls_timestamp, style={'display': 'none'}),
                html.Div(load_data_activities_layout, className=card, style=card_style),
            ], style={'display': 'flex', 'flexDirection': 'column'}),
        
            dcc.Store(id='stored_timestamp'),
            dcc.Store(id='filtered_relayout_zoom'),
            dcc.Store(id='filtered_relayout_brush'),
            dcc.Store(id='is-compare-mode', data=False),
            dcc.Store(id='last_clicked_sensor_ref', data=None),
            dcc.Store(id='stored_discordant_windows', data=[]),
            dcc.Input(id='filter-shapes', value="", style={'display': 'none'}),
            dcc.Input(id='compare-user-filter', value="", style={'display': 'none'}),
            html.Div(id="toast-container", style={"position": "fixed", "top": "20px", "right": "20px", "zIndex": 9999}),
            dcc.Store(id="toast-message-store", data=None),
            dcc.Store(id="stored-activity-labels", data=self.config.get('activities', []), storage_type='local'),
            
        ], style={
            'backgroundColor': self.config['layout']['background_color'], 
            'padding': self.config['layout']['padding'], 
            'boxSizing': 'border-box',
            'color': self.config['layout']['font_color']
        })

    def _save_activities_config(self, activities):
        try:
            import os
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    conf = yaml.safe_load(f) or {}
                conf['activities'] = activities
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(conf, f, sort_keys=False)
                self.config['activities'] = activities
                print(f"[DashApp] Saved {len(activities)} activities to config.yaml", flush=True)
        except Exception as e:
            print(f"[DashApp] Warning: Failed to persist activities to config.yaml: {e}", flush=True)

    def _save_session_manifest_labels(self, session_folder, activities):
        if not session_folder:
            return
        try:
            import os, json
            data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
            manifest_path = os.path.join(data_dir, session_folder, "session_manifest.json")
            if os.path.exists(manifest_path):
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                manifest['activity_labels'] = activities
                with open(manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, indent=4)
                print(f"[DashApp] Saved {len(activities)} activity labels to manifest: {manifest_path}", flush=True)
        except Exception as e:
            print(f"[DashApp] Warning: Failed to save labels to session_manifest: {e}", flush=True)

    def _register_callbacks(self):
        controls_load_data_sensors = ControlsLoadData(self.config)
        plot_brush = PlotBrush()
        load_data_activities_layout = ProjectSetup()
        load_zoom_layout = LoadZoom()
        controls_timestamp = ControlsTimestamp()
        video_player = VideoPlayer(
            id_upload='upload-video', 
            id_output='output-video-player',
            style={'flexGrow': 1, 'display': 'flex', 'flexDirection': 'column', 'minHeight': 0}
        )
        session_selector = SessionSelector()

        controls_load_data_sensors.register_callbacks(self.app)  
        plot_brush.register_callbacks(self.app)
        load_data_activities_layout.register_callbacks(self.app)  
        load_zoom_layout.register_callbacks(self.app)  
        controls_timestamp.register_callbacks(self.app)
        video_player.register_callbacks(self.app)
        session_selector.register_callbacks(self.app)

        @self.app.callback(
            Output('dataset-flow-container', 'style'),
            Output('standalone-annotation-panel', 'style'),
            Output('standalone-sensor-panel', 'style'),
            Output('upload-container', 'style'), # Need to ensure VideoPlayer has this ID if we want to hide it
            Input('app-mode-toggle', 'value'),
        )
        def toggle_app_mode(is_flow_mode):
            if is_flow_mode:
                return {'display': 'block'}, {'display': 'none'}, {'display': 'none'}, {'display': 'none'}
            else:
                return {'display': 'none'}, {'width': '100%', 'display': 'flex', 'alignItems': 'center', 'marginBottom': '10px'}, {'display': 'block'}, {'display': 'block'}

        @self.app.callback(
            Output('workflow-video-trigger', 'data'),
            Output('workflow-sensor-trigger', 'data'),
            Output('workflow-annotation-trigger', 'data'),
            Input('selected-workflow-paths', 'data'),
            prevent_initial_call=True
        )
        def route_workflow_paths(wf_data):
            if not wf_data:
                return dash.no_update, dash.no_update, dash.no_update
            return wf_data.get('video_path'), wf_data.get('sensor_path'), wf_data.get('annotation_path')

        @self.app.callback(
            Output('toast-container', 'children'),
            Input('toast-message-store', 'data'),
            prevent_initial_call=True
        )
        def display_toast(data):
            import dash
            import dash_bootstrap_components as dbc
            if not data:
                return dash.no_update
            
            message = data.get('message', '')
            header = data.get('header', 'Notification')
            toast_type = data.get('type', 'info')
            duration = data.get('duration', 1500)
            
            new_toast = dbc.Toast(
                message,
                header=header,
                is_open=True,
                dismissable=True,
                icon=toast_type,
                duration=duration,
                style={
                    "maxWidth": "500px", 
                    "marginBottom": "10px", 
                    "boxShadow": "0 4px 8px rgba(0,0,0,0.1)",
                    "fontSize": "16px",
                    "padding": "10px"
                }
            )
            
            patched_children = dash.Patch()
            patched_children.append(new_toast)
            return patched_children

        @self.app.callback(
            Output('modal-label-settings', 'is_open'),
            Input('btn-open-label-settings', 'n_clicks'),
            Input('btn-close-label-settings', 'n_clicks'),
            State('modal-label-settings', 'is_open'),
            prevent_initial_call=True
        )
        def toggle_label_modal(n_open, n_close, is_open):
            if n_open or n_close:
                return not is_open
            return is_open

        @self.app.callback(
            Output('stored-activity-labels', 'data', allow_duplicate=True),
            Output('input-new-label', 'value'),
            Output('toast-message-store', 'data', allow_duplicate=True),
            Input('btn-add-label', 'n_clicks'),
            State('input-new-label', 'value'),
            State('stored-activity-labels', 'data'),
            State('session-dropdown', 'value'),
            prevent_initial_call=True
        )
        def add_label(n_add, new_label, current_labels, session_folder):
            if not n_add or n_add <= 0:
                return dash.no_update, dash.no_update, dash.no_update
            if not new_label or not new_label.strip():
                return dash.no_update, dash.no_update, {"message": "Please enter a valid label name.", "type": "warning", "header": "Warning"}
            clean_name = new_label.strip().upper().replace(" ", "_")
            labels = list(current_labels or [])
            if clean_name in labels:
                return dash.no_update, dash.no_update, {"message": f"Label '{clean_name}' already exists.", "type": "warning", "header": "Duplicate"}
            labels.append(clean_name)
            self._save_activities_config(labels)
            if session_folder:
                self._save_session_manifest_labels(session_folder, labels)
            msg_target = f"session '{session_folder}' & config" if session_folder else "config.yaml"
            return labels, "", {"message": f"Added label '{clean_name}' (saved to {msg_target})", "type": "success", "header": "Label Created"}

        @self.app.callback(
            Output('stored-activity-labels', 'data', allow_duplicate=True),
            Output('toast-message-store', 'data', allow_duplicate=True),
            Input({'type': 'btn-delete-label', 'index': dash.ALL}, 'n_clicks'),
            State('stored-activity-labels', 'data'),
            State('session-dropdown', 'value'),
            prevent_initial_call=True
        )
        def delete_label(delete_clicks, current_labels, session_folder):
            triggered_id = dash.ctx.triggered_id
            if not isinstance(triggered_id, dict) or triggered_id.get('type') != 'btn-delete-label':
                return dash.no_update, dash.no_update

            # Verify that any click value is > 0
            if not delete_clicks or not any((c or 0) > 0 for c in delete_clicks):
                return dash.no_update, dash.no_update

            label_to_delete = triggered_id.get('index')
            labels = list(current_labels or [])
            if label_to_delete in labels:
                labels.remove(label_to_delete)
                self._save_activities_config(labels)
                if session_folder:
                    self._save_session_manifest_labels(session_folder, labels)
                msg_target = f"session '{session_folder}' & config" if session_folder else "config.yaml"
                return labels, {"message": f"Removed label '{label_to_delete}' (updated {msg_target})", "type": "info", "header": "Label Deleted"}

            return dash.no_update, dash.no_update

        @self.app.callback(
            Output('left-label', 'options'),
            Output('labels-list-container', 'children'),
            Input('stored-activity-labels', 'data')
        )
        def update_labels_display(labels):
            labels = labels or []
            dropdown_opts = [{'label': l, 'value': l} for l in labels]
            
            rows = []
            for idx, label in enumerate(labels):
                row = html.Div([
                    html.Span(f"{idx + 1}. {label}", style={'fontWeight': '500', 'color': 'var(--ink)'}),
                    html.Button(
                        "✕",
                        id={'type': 'btn-delete-label', 'index': label},
                        n_clicks=0,
                        className="hx-btn hx-btn--danger",
                        style={'padding': '2px 8px', 'fontSize': '12px', 'lineHeight': '1'},
                        title=f"Delete {label}"
                    )
                ], style={
                    'display': 'flex',
                    'justifyContent': 'space-between',
                    'alignItems': 'center',
                    'padding': '6px 10px',
                    'borderBottom': '1px solid var(--line, #eee)' if idx < len(labels) - 1 else 'none'
                })
                rows.append(row)

            if not rows:
                rows = [html.Div("No activity labels defined.", style={'padding': '10px', 'color': 'var(--ink-muted)'})]

            return dropdown_opts, rows

    def start(self):
        # Using port and debug mode from the configuration file
        self.app.run(
            host=self.config.get('server', {}).get('host', '127.0.0.1'),
            port=self.config['server']['port'], 
            debug=self.config['server']['debug'],
            dev_tools_hot_reload=False,
        )

    def stop(self):
        # Dash doesn't have a built-in stop method, but you can handle this externally.
        pass

