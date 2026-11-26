import dash
from dash import dcc, html, Input, Output, State
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import json
import flask

# Path configurations relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SCRIPT_DIR

# Server for serving local video files
server = flask.Flask(__name__)

@server.route('/media')
def serve_media():
    file_path = flask.request.args.get('path')
    if file_path and os.path.exists(file_path):
        return flask.send_file(file_path)
    return "Not found", 404

def get_sessions():
    sessions = []
    data_dir = os.path.abspath(os.path.join(PROJECT_ROOT, "..", "data"))
    if os.path.exists(data_dir):
        for d in sorted(os.listdir(data_dir)):
            p = os.path.join(data_dir, d)
            if os.path.isdir(p):
                man = os.path.join(p, "session_manifest.json")
                if os.path.exists(man) or os.path.exists(os.path.join(p, "clean_sensors")) or os.path.exists(os.path.join(p, "annotations")):
                    sessions.append({'label': f"Session: {d}", 'value': p})
    return sessions

NO_LABEL = '-1'
ANNOTATION_COLUMNS = ["timestamp", "left_label", "change_point_name", "change_point_time", "sensor_ref"]
CONSOLIDATION_MODES = [
    {'label': 'Off', 'value': 'none'},
    {'label': 'Union', 'value': 'union'},
    {'label': 'Intersection', 'value': 'intersection'},
    {'label': 'Majority', 'value': 'majority'},
]


def get_annotator_options(session_path):
    if not session_path:
        return []
    options = []
    seen = set()
    man_path = os.path.join(session_path, "session_manifest.json")
    if os.path.exists(man_path):
        try:
            with open(man_path, "r") as f:
                man = json.load(f)
            for rel in man.get("artifacts", {}).get("annotation_files", []):
                seen.add(rel)
                options.append({'label': os.path.basename(rel).replace('.csv', ''), 'value': rel})
        except Exception:
            pass

    # Direct directory scan so live annotations appear immediately without restarting
    ann_dir = os.path.join(session_path, "annotations")
    if os.path.exists(ann_dir):
        for fname in sorted(os.listdir(ann_dir)):
            if fname.endswith(".csv"):
                rel = os.path.join("annotations", fname)
                if rel not in seen:
                    seen.add(rel)
                    options.append({'label': fname.replace('.csv', ''), 'value': rel})
    return options


def load_segments(ann_path):
    """Annotation CSV (each change point ends the activity in left_label) -> [(start, end, label)]."""
    try:
        df = pd.read_csv(ann_path)
    except Exception:
        return []
    if 'timestamp' not in df.columns or 'left_label' not in df.columns:
        return []
    segments, start = [], 0.0
    for _, row in df.sort_values('timestamp').iterrows():
        end, label = float(row['timestamp']), str(row['left_label'])
        if label != NO_LABEL and end > start:
            segments.append((start, end, label))
        start = end
    return segments


def _label_at(segments, t):
    for start, end, label in segments:
        if start <= t < end:
            return label
    return None


def consolidate(segment_lists, mode):
    """union: labeled by at least one annotator, without conflicting labels;
    intersection: same label from every annotator; majority: label from more than half."""
    bounds = sorted({0.0} | {t for segs in segment_lists for s, e, _ in segs for t in (s, e)})
    result = []
    for a, b in zip(bounds, bounds[1:]):
        labels = [_label_at(segs, (a + b) / 2) for segs in segment_lists]
        given = [l for l in labels if l is not None]
        label = None
        if mode == 'intersection' and len(given) == len(labels) and len(set(given)) == 1:
            label = given[0]
        elif mode == 'union' and given and len(set(given)) == 1:
            label = given[0]
        elif mode == 'majority':
            label = next((c for c in set(given) if given.count(c) * 2 > len(labels)), None)
        if label is None:
            continue
        if result and result[-1][2] == label and abs(result[-1][1] - a) < 1e-9:
            result[-1] = (result[-1][0], b, label)
        else:
            result.append((a, b, label))
    return result


def segments_to_annotation(segments, sensor_ref):
    """Segments -> annotation CSV in the Labeler format (gaps become '-1' change points)."""
    points, t = [], 0.0
    for start, end, label in segments:
        if start > t + 1e-9:
            points.append((start, NO_LABEL))
        points.append((end, label))
        t = end
    return pd.DataFrame([{
        'timestamp': round(ts, 3), 'left_label': label,
        'change_point_name': f'change_point_{i + 1}', 'change_point_time': 'timestamp_local',
        'sensor_ref': sensor_ref,
    } for i, (ts, label) in enumerate(points)], columns=ANNOTATION_COLUMNS)


def consolidated_segments(session_path, annotators, mode):
    if not session_path or mode in (None, 'none') or not annotators or len(annotators) < 2:
        return None
    lists = [load_segments(os.path.join(session_path, rel)) for rel in annotators]
    return consolidate(lists, mode)


app = dash.Dash(__name__, server=server)

CSS_STYLES = """
/* Viewer on top of the shared H.IAAC theme (assets/hiaac/hiaac.css). */
body { margin: 0; font-family: var(--font-mono); background: var(--paper); color: var(--ink); }
#dummy-output, #theme-dummy { display: none !important; }
#main-container { font-family: var(--font-mono) !important; }
.viewer-header { margin: -40px -5.556% 28px; }

.control-label {
    font-size: 9.5px !important; font-weight: 600; letter-spacing: .14em;
    text-transform: uppercase; color: var(--ink-2) !important;
}
input[type="radio"], input[type="checkbox"] { accent-color: var(--orange); }

.viewer-panel {
    background: var(--paper-2); border: 1px solid var(--line);
    border-radius: var(--radius-lg) !important; box-shadow: var(--shadow);
}
.viewer-panel h3 { font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: var(--ink-2); }

.dash-dropdown {
    background: var(--paper) !important; border: 1px solid var(--line-2) !important;
    border-radius: var(--radius) !important; font-size: 12px !important; font-family: var(--font-mono);
}
.dash-dropdown:focus-within { border-color: var(--orange) !important; box-shadow: 0 0 0 3px var(--orange-bg) !important; }
.dash-dropdown-value, .dash-dropdown-value-item, .dash-dropdown-trigger-icon { color: var(--ink) !important; }
.dash-dropdown-value-count { background: var(--orange) !important; color: #1d1a16 !important; border-radius: var(--radius) !important; }
.dash-dropdown-content, .dash-dropdown-options {
    background: var(--paper-2) !important; border: 1px solid var(--line-2) !important;
    border-radius: var(--radius) !important; color: var(--ink) !important;
}
.dash-dropdown-content .dash-dropdown-option, .dash-dropdown-content .dash-options-list-option,
.dash-dropdown-options .dash-dropdown-option, .dash-dropdown-options .dash-options-list-option {
    background: transparent !important; color: var(--ink) !important;
}
.dash-dropdown-content .dash-dropdown-option:hover, .dash-dropdown-content .dash-options-list-option:hover,
.dash-dropdown-content .dash-options-list-option.selected, .dash-dropdown-options .dash-dropdown-option:hover,
.dash-dropdown-options .dash-options-list-option:hover, .dash-dropdown-options .dash-options-list-option.selected {
    background: var(--orange-bg) !important;
}
.dash-dropdown-search-container, .dash-dropdown-search-container:focus-within {
    background: var(--paper-3) !important; border-bottom: 1px solid var(--line) !important;
    outline: none !important; box-shadow: none !important;
}
.dash-dropdown-search {
    background: var(--paper) !important; color: var(--ink) !important;
    border: 1px solid var(--line-2) !important; border-radius: var(--radius) !important;
    outline: none !important; box-shadow: none !important; -webkit-appearance: none;
}
.dash-dropdown-search::placeholder { color: var(--ink-3) !important; opacity: 1 !important; }
.dash-dropdown-search-icon { color: var(--ink-2) !important; }

/* Squared theme switch, same as the other tools */
.theme-switch input[type="checkbox"] {
    appearance: none; -webkit-appearance: none; margin: 0;
    width: 34px; height: 18px; position: relative; cursor: pointer; outline: none;
    background: var(--line-2); border-radius: var(--radius); transition: background .2s;
}
.theme-switch input[type="checkbox"]::after {
    content: ""; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px;
    background: var(--paper-2); border-radius: 2px; transition: transform .2s;
}
.theme-switch input[type="checkbox"]:checked { background: var(--orange); }
.theme-switch input[type="checkbox"]:checked::after { transform: translateX(16px); }

.js-plotly-plot .plotly .modebar-btn path { fill: var(--ink-3); }
.js-plotly-plot .plotly .main-svg { background: transparent !important; }
.js-plotly-plot .bglayer rect.bg { fill: var(--paper) !important; }
.js-plotly-plot .xtick text, .js-plotly-plot .ytick text { fill: var(--ink-2) !important; }
#app-mode-toggle label, #checkbox-container label { color: var(--ink) !important; font-size: 13px; }

.hx-tooltip-wrapper {
    position: relative;
    display: inline-flex;
    align-items: center;
}
.hx-help-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 17px;
    height: 17px;
    border-radius: 50%;
    background: var(--line-2);
    color: var(--ink-2);
    font-size: 11px;
    font-weight: bold;
    cursor: pointer;
    margin-left: 6px;
    user-select: none;
    transition: background 0.2s, color 0.2s;
}
.hx-help-icon:hover, .hx-help-icon:focus {
    background: var(--orange);
    color: #1d1a16;
    outline: none;
}
.hx-tooltip-box {
    visibility: hidden;
    opacity: 0;
    position: absolute;
    top: 24px;
    left: 0;
    z-index: 1000;
    width: 290px;
    background: var(--paper-2);
    border: 1px solid var(--line-2);
    border-radius: var(--radius);
    padding: 10px 12px;
    font-size: 11px;
    line-height: 1.4;
    color: var(--ink);
    box-shadow: 0 4px 14px rgba(0,0,0,0.18);
    transition: opacity 0.2s, visibility 0.2s;
    pointer-events: none;
}
.hx-tooltip-wrapper:hover .hx-tooltip-box,
.hx-tooltip-wrapper:focus-within .hx-tooltip-box {
    visibility: visible;
    opacity: 1;
    pointer-events: auto;
}
"""

app.index_string = f'''
<!DOCTYPE html>
<html>
    <head>
        {{%metas%}}
        <title>{{%title%}}</title>
        {{%favicon%}}
        {{%css%}}
        <style>
{CSS_STYLES}
        </style>
    </head>
    <body>
        {{%app_entry%}}
        <footer>
            {{%config%}}
            {{%scripts%}}
            {{%renderer%}}
        </footer>
    </body>
</html>
'''

# Layout
app.layout = html.Div(
    id="main-container",
    style={'padding': '40px 5%', 'fontFamily': 'var(--font-mono)', 'transition': 'background-color 0.3s, color 0.3s', 'minHeight': '100vh'},
    children=[
        html.Header([
            html.A([
                html.Img(src="/assets/hiaac/hiaac-logo.svg", alt="H.IAAC", className="hx-logo"),
                html.Span(className="hx-sep"),
                html.Span([
                    html.Span("Track-It Viewer", className="hx-tool-title"),
                    html.Span("Sensors + Video Inspection", className="hx-tool-sub"),
                ], className="hx-tool"),
            ], href="/", className="hx-brand"),
        ], className="hx-header viewer-header"),
        
        # Controls Row
        html.Div(
            style={'display': 'flex', 'gap': '15px', 'marginBottom': '45px', 'flexWrap': 'wrap', 'alignItems': 'flex-start'},
            children=[
                # DATASET FLOW PANEL
                html.Div(
                    id='dataset-flow-panel',
                    style={'display': 'flex', 'gap': '15px', 'alignItems': 'flex-start'},
                    children=[
                        html.Div([
                            html.Label("Select Session", className="control-label", style={'fontSize': '13px', 'marginBottom': '5px', 'display': 'block'}),
                            html.Div([
                                dcc.Dropdown(id='session-dropdown', options=get_sessions(), value=get_sessions()[0]['value'] if get_sessions() else None, clearable=False, searchable=True, style={'width': '350px'}, className='dash-dropdown'),
                                html.Button("↻", id='btn-refresh-sessions', className='hx-btn', title="Refresh sessions", style={'height': '36px', 'padding': '0 10px', 'marginLeft': '6px'}),
                            ], style={'display': 'flex', 'alignItems': 'center'})
                        ]),
                    ]
                ),

                # Common Sensor Dropdown
                html.Div([
                    html.Label("Select Sensor", className="control-label", style={'fontSize': '13px', 'marginBottom': '5px', 'display': 'block'}),
                    dcc.Dropdown(id='sensor-dropdown', clearable=False, searchable=False, style={'width': '250px'}, className='dash-dropdown')
                ]),

                # Annotators Dropdown
                html.Div([
                    html.Label("Select Annotators", className="control-label", style={'fontSize': '13px', 'marginBottom': '5px', 'display': 'block'}),
                    dcc.Dropdown(id='annotator-dropdown', multi=True, clearable=True, searchable=False, style={'width': '300px'}, className='dash-dropdown')
                ]),

                # Consolidation Dropdown with Tooltip Helper
                html.Div([
                    html.Div([
                        html.Label("Consolidation", className="control-label", style={'fontSize': '13px', 'marginBottom': '0'}),
                        html.Div([
                            html.Span("?", className="hx-help-icon", tabIndex=0),
                            html.Div([
                                html.Div([
                                    html.B("Consolidation Methods:"),
                                    html.Ul([
                                        html.Li([html.B("Off: "), "Individual annotators without consensus."]),
                                        html.Li([html.B("Union: "), "Interval labeled by at least 1 annotator (conflicts omitted)."]),
                                        html.Li([html.B("Intersection: "), "Strict consensus — 100% agreement on exact same label."]),
                                        html.Li([html.B("Majority: "), "Consensus by vote — labeled if >50% annotators agree."]),
                                    ], style={'paddingLeft': '16px', 'margin': '6px 0 0 0'}),
                                    html.Div("Export CSV saves the consensus in Labeler format.", style={'marginTop': '6px', 'color': 'var(--ink-2)', 'fontSize': '10px'})
                                ])
                            ], className="hx-tooltip-box")
                        ], className="hx-tooltip-wrapper")
                    ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '5px'}),
                    dcc.Dropdown(id='consolidation-dropdown', options=CONSOLIDATION_MODES, value='none', clearable=False, searchable=False, style={'width': '170px'}, className='dash-dropdown')
                ]),

                html.Div([
                    html.Label("Export", className="control-label", style={'fontSize': '13px', 'marginBottom': '5px', 'display': 'block'}),
                    html.Button("Export CSV", id='export-btn', className='hx-btn hx-btn--primary', style={'height': '36px'}),
                    dcc.Download(id='export-download'),
                    html.Div(id='export-status', style={'fontSize': '11px', 'marginTop': '4px', 'maxWidth': '260px', 'color': 'var(--ink-2)'})
                ]),

                html.Div([
                    html.Label("Theme", className="control-label", style={'fontSize': '13px', 'marginBottom': '5px', 'display': 'block'}),
                    html.Div(
                        dcc.Checklist(id='theme-dropdown', options=[{'label': '', 'value': 'Dark'}], value=[], className='theme-switch'),
                        style={'height': '36px', 'display': 'flex', 'alignItems': 'center', 'fontWeight': 'normal'}
                    )
                ])
            ]
        ),
        
        # Main Area
        html.Div(
            style={'display': 'flex', 'width': '100%', 'height': '75vh', 'gap': '20px'},
            children=[
                # Left: Plot
                html.Div(
                    id='plot-container', className='viewer-panel',
                    style={'flex': '3', 'padding': '10px'},
                    children=[
                        dcc.Graph(
                            id='main-plot', 
                            style={'height': '100%'}, 
                            config={
                                'responsive': True, 
                                'edits': {
                                    'shapePosition': True
                                }
                            }
                        )
                    ]
                ),
                
                # Right: Video
                html.Div(
                    id='video-container', className='viewer-panel',
                    style={'flex': '1', 'padding': '10px', 'display': 'flex', 'flexDirection': 'column'},
                    children=[
                        html.H3("Video Sync", style={'marginTop': '0', 'marginBottom': '12px', 'fontWeight': 'normal'}),
                        html.Div(id='video-wrapper', children=[
                            html.Video(id='sync-video', controls=True, style={'width': '100%', 'borderRadius': '4px'})
                        ]),
                        html.Div(id='video-error', style={'color': 'var(--red)', 'marginTop': '10px', 'fontWeight': 'bold'})
                    ]
                )
            ]
        ),
        
        dcc.Store(id='min-time-store'),
        dcc.Interval(id='session-refresh-interval', interval=5000, n_intervals=0),
        html.Div(id='dummy-output'),
        html.Div(id='theme-dummy')
    ]
)

@app.callback(
    Output('session-dropdown', 'options'),
    Output('session-dropdown', 'value'),
    Input('session-refresh-interval', 'n_intervals'),
    Input('btn-refresh-sessions', 'n_clicks'),
    State('session-dropdown', 'options'),
    State('session-dropdown', 'value'),
    prevent_initial_call=True
)
def refresh_sessions(_, n_clicks, current_options, current_value):
    sessions = get_sessions()
    if not sessions:
        return [], None
    valid_values = [s['value'] for s in sessions]
    if sessions == current_options and current_value in valid_values:
        return dash.no_update, dash.no_update
    new_val = current_value if current_value in valid_values else sessions[0]['value']
    return sessions, new_val


@app.callback(
    Output('sensor-dropdown', 'options'),
    Output('sensor-dropdown', 'value'),
    Output('annotator-dropdown', 'options'),
    Output('annotator-dropdown', 'value'),
    Input('session-dropdown', 'value'),
    Input('session-refresh-interval', 'n_intervals'),
    State('sensor-dropdown', 'options'),
    State('sensor-dropdown', 'value'),
    State('annotator-dropdown', 'options'),
    State('annotator-dropdown', 'value')
)
def update_controls(session_path, n_intervals, cur_sensor_opts, cur_sensor_val, cur_ann_opts, cur_ann_val):
    if not session_path:
        return [], None, [], []

    ctx = dash.callback_context
    triggered_prop = ctx.triggered[0]['prop_id'] if ctx.triggered else ''

    sensors_opts = []
    default_sensor = None
    annotators_opts = []
    default_annotators = []

    man_path = os.path.join(session_path, "session_manifest.json")
    if os.path.exists(man_path):
        with open(man_path, "r") as f:
            man = json.load(f)
        
        # Load sensors
        csv_rel = man.get("artifacts", {}).get("clean_sensors", [])
        if isinstance(csv_rel, list) and len(csv_rel) > 0:
            sensors = []
            for rel_path in csv_rel:
                full_path = os.path.join(session_path, rel_path)
                if os.path.exists(full_path):
                    try:
                        df_preview = pd.read_csv(full_path, nrows=0)
                        exclude_cols = ['timestamp', 'window_index', 'label', 'VideoTimelapse', 'FrameTimestamp']
                        for c in df_preview.columns:
                            if c not in exclude_cols and c not in sensors:
                                sensors.append(c)
                    except Exception:
                        pass
            if sensors:
                sensors_opts = [{'label': s, 'value': s} for s in sensors]
                default_sensor = cur_sensor_val if cur_sensor_val in sensors else ('Value 1' if 'Value 1' in sensors else sensors[0])

    annotators_opts = get_annotator_options(session_path)
    valid_ann_vals = [a['value'] for a in annotators_opts]
    
    if cur_ann_val and isinstance(cur_ann_val, list):
        kept = [v for v in cur_ann_val if v in valid_ann_vals]
        default_annotators = kept if kept else ([annotators_opts[0]['value']] if annotators_opts else [])
    else:
        default_annotators = [annotators_opts[0]['value']] if annotators_opts else []

    # On timer refresh, return no_update if options haven't changed to avoid unnecessary re-renders
    if 'session-refresh-interval' in triggered_prop:
        if sensors_opts == cur_sensor_opts and annotators_opts == cur_ann_opts:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    return sensors_opts, default_sensor, annotators_opts, default_annotators


@app.callback(
    Output('main-plot', 'figure'),
    Output('sync-video', 'src'),
    Output('video-error', 'children'),
    Output('min-time-store', 'data'),
    Output('main-container', 'style'),
    Output('plot-container', 'style'),
    Output('video-container', 'style'),
    Output('main-container', 'className'),
    Input('session-dropdown', 'value'),
    Input('sensor-dropdown', 'value'),
    Input('annotator-dropdown', 'value'),
    Input('theme-dropdown', 'value'),
    Input('consolidation-dropdown', 'value')
)
def update_graph(session_path, sensor, annotators, theme, mode):
    main_style = {'padding': '40px 5%', 'fontFamily': 'var(--font-mono)', 'transition': 'background-color 0.3s, color 0.3s', 'minHeight': '100vh'}
    container_style = {'padding': '0px', 'display': 'flex', 'flexDirection': 'column'}
    
    is_dark = ('Dark' in theme) if isinstance(theme, list) else (theme == 'Dark')
    if not is_dark:
        main_style.update({'backgroundColor': 'var(--paper)', 'color': 'var(--ink)'})
        template = "plotly_white"
        grid_color = '#e2dccf'
    else:
        main_style.update({'backgroundColor': 'var(--paper)', 'color': 'var(--ink)'})
        template = "plotly_dark"
        grid_color = '#2c2920'
        
    plot_container_style = container_style.copy()
    plot_container_style['width'] = '75%'
    
    video_container_style = container_style.copy()
    video_container_style['width'] = '25%'
    video_container_style['marginLeft'] = '20px'

    if not sensor or not session_path:
        return dash.no_update, "", "", None, main_style, plot_container_style, video_container_style, dash.no_update

    df = None
    video_src = ""
    video_error = ""
    
    man_path = os.path.join(session_path, "session_manifest.json")
    if os.path.exists(man_path):
        with open(man_path, "r") as f:
            man = json.load(f)
        csv_rel = man.get("artifacts", {}).get("clean_sensors", [])
        vid_rel = man.get("artifacts", {}).get("anonymized_video") or man.get("artifacts", {}).get("raw_video")
        
        if isinstance(csv_rel, list) and len(csv_rel) > 0:
            for rel_path in csv_rel:
                csv_path = os.path.join(session_path, rel_path)
                if os.path.exists(csv_path):
                    df_preview = pd.read_csv(csv_path, nrows=0)
                    if sensor in df_preview.columns:
                        df = pd.read_csv(csv_path)
                        break
        
        if vid_rel:
            vid_path = os.path.join(session_path, vid_rel)
            if os.path.exists(vid_path):
                video_src = f"/media?path={vid_path}"
            else:
                video_error = "Video not found in session."

    if df is None:
        return dash.no_update, "", "CSV not found or invalid", None, main_style, plot_container_style, video_container_style, dash.no_update
        
    time_col = 'VideoTimelapse' if 'VideoTimelapse' in df.columns else 'timestamp'
    
    # Calculate min_time
    min_time = float(df[time_col].min() / 1000.0)

    # Build Figure with dynamic row heights so multiple annotators are never squashed
    num_tracks = len(annotators or []) + (1 if mode not in (None, 'none') else 0)
    if num_tracks <= 1:
        row_heights = [0.75, 0.25]
    elif num_tracks <= 3:
        row_heights = [0.65, 0.35]
    else:
        row_heights = [0.55, 0.45]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=row_heights, vertical_spacing=0.06)

    if time_col in df.columns and sensor in df.columns:
        x_data = df[time_col] / 1000.0
        # Convert sensor column to numeric in case it was parsed as string
        y_data = pd.to_numeric(df[sensor], errors='coerce')
        # Signal Plot
        fig.add_trace(go.Scattergl(x=x_data, y=y_data, mode='lines', name=sensor, line=dict(color='#ff9d1c')), row=1, col=1)

        # Plot Annotations on row 2
        # Annotators color palette
        annotator_colors = ['#5750c4', '#5d7f4c', '#b8392b', '#3a6db0', '#c98a1e', '#8d86f0', '#8fb277', '#6ba0e0', '#e06a5b', '#7d7c7b']
        
        if annotators:
            for ann_idx, ann_rel in enumerate(annotators):
                ann_path = os.path.join(session_path, ann_rel)
                if not os.path.exists(ann_path): continue
                
                try:
                    ann_df = pd.read_csv(ann_path)
                except Exception:
                    continue
                
                if 'timestamp' not in ann_df.columns or 'left_label' not in ann_df.columns:
                    continue
                
                # Logic: ends at
                # [0] to time[0] -> left_label[0]
                # time[0] to time[1] -> left_label[1]
                
                ann_name = os.path.basename(ann_rel).replace('.csv', '')
                color = annotator_colors[ann_idx % len(annotator_colors)]
                
                start_time = 0.0
                for _, row in ann_df.iterrows():
                    end_time = float(row['timestamp'])
                    label = str(row['left_label'])
                        
                    if label == '-1':
                        start_time = end_time
                        continue
                        
                    hover_text = f"Annotator: {ann_name}<br>Label: {label}<br>Time: {start_time:.2f} - {end_time:.2f}"
                    
                    fig.add_trace(
                        go.Scattergl(
                            x=[start_time, end_time, None], 
                            y=[ann_name, ann_name, None], 
                            mode='lines+markers',
                            line=dict(width=10, color=color),
                            marker=dict(size=8, color='#fbf9f4' if not is_dark else '#1d1b15', line=dict(width=1, color='#1d1a16' if not is_dark else '#efe9dc')),
                            name=label, 
                            hoverinfo='text',
                            hovertemplate="%{text}<extra></extra>",
                            text=[hover_text, hover_text, ""]
                        ),
                        row=2, col=1
                    )
                    
                    # Add background block to row 1
                    y_min_val = y_data.min()
                    y_max_val = y_data.max()
                    y_margin = (y_max_val - y_min_val) * 0.05
                    if y_margin == 0: y_margin = 1
                    
                    fig.add_trace(
                        go.Scatter(
                            x=[start_time, end_time, end_time, start_time, start_time],
                            y=[y_min_val - y_margin, y_min_val - y_margin, y_max_val + y_margin, y_max_val + y_margin, y_min_val - y_margin],
                            fill="toself",
                            fillcolor=color,
                            mode="lines",
                            line=dict(width=0),
                            opacity=0.15,
                            hoverinfo="text",
                            hovertemplate="%{text}<extra></extra>",
                            text=[hover_text]*5,
                            name=label,
                            showlegend=False
                        ),
                        row=1, col=1
                    )
                    
                    start_time = end_time

        consolidated = consolidated_segments(session_path, annotators, mode)
        if consolidated is not None:
            row_name = f"{mode.capitalize()}"
            ink = '#efe9dc' if is_dark else '#1d1a16'
            for start_time, end_time, label in consolidated:
                hover_text = f"{row_name}<br>Label: {label}<br>Time: {start_time:.2f} - {end_time:.2f}"
                fig.add_trace(
                    go.Scattergl(
                        x=[start_time, end_time, None], y=[row_name, row_name, None],
                        mode='lines', line=dict(width=10, color=ink), name=label,
                        hoverinfo='text', hovertemplate="%{text}<extra></extra>",
                        text=[hover_text, hover_text, ""]
                    ),
                    row=2, col=1
                )


    fig.update_layout(
        title=f"Sensor: {sensor}",
        xaxis2_title="Time (s)",
        yaxis_title="Sensor Value",
        yaxis2_title="Annotator",
        hovermode="x unified",
        margin=dict(t=40, b=90, l=65, r=20),
        template=template,
        showlegend=False
    )
    if is_dark:
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#15140f', font=dict(color='#a39d8f', family='Helvetica Neue, Helvetica, Arial, sans-serif'), hoverlabel=dict(bgcolor='#26231b', font_color='#efe9dc'))
    else:
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#f4f0e9', font=dict(color='#6c675e', family='Helvetica Neue, Helvetica, Arial, sans-serif'), hoverlabel=dict(bgcolor='#fbf9f4', font_color='#1d1a16'))

    fig.update_xaxes(automargin=True, showgrid=True, gridwidth=1, gridcolor=grid_color, dtick=3, tick0=0, row='all', col=1)
    y2_range = [-0.65, max(num_tracks - 0.35, 0.65)] if num_tracks > 0 else None
    if y2_range:
        fig.update_yaxes(automargin=True, type='category', range=y2_range, row=2, col=1)
    else:
        fig.update_yaxes(automargin=True, row=2, col=1)

    fig.add_shape(
        type="line", x0=0, x1=0, y0=0, y1=1, yref="paper",
        line=dict(color="#5750c4", width=2, dash="dot"), editable=True, opacity=0, name="sync-marker"
    )
    theme_class = 'dark-theme' if is_dark else ''

    return fig, video_src, video_error, min_time, main_style, plot_container_style, video_container_style, theme_class

app.clientside_callback(
    """
    function(theme) {
        var isDark = Array.isArray(theme) ? theme.indexOf('Dark') !== -1 : theme === 'Dark';
        document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
        return '';
    }
    """,
    Output('theme-dummy', 'children'),
    Input('theme-dropdown', 'value')
)

# Clientside callback to sync video and plot natively, and toggle dark theme
app.clientside_callback(
    """
    function(minTime, figData, theme) {
        var isDark = Array.isArray(theme) ? theme.includes('Dark') : theme === 'Dark';
        if (isDark) {
            document.body.classList.add('dark-theme');
        } else {
            document.body.classList.remove('dark-theme');
        }
        
        if (minTime === null || minTime === undefined) return window.dash_clientside.no_update;
        
        // Use a short timeout to ensure the DOM nodes for video and plot exist
        setTimeout(function() {
            var video = document.getElementById('sync-video');
            var plotWrapper = document.getElementById('main-plot');
            
            if(!video || !plotWrapper) return;
            
            var plotDiv = plotWrapper.querySelector('.js-plotly-plot') || plotWrapper;
            
            // Remove previous listeners if they exist to avoid duplication on dropdown changes
            if(window._syncTimeUpdate) {
                video.removeEventListener('timeupdate', window._syncTimeUpdate);
            }
            if(window._syncPlotClick && plotDiv.on) {
                plotDiv.removeListener('plotly_click', window._syncPlotClick);
            }
            if(window._syncPlotRelayout && plotDiv.on) {
                plotDiv.removeListener('plotly_relayout', window._syncPlotRelayout);
            }
            
            var isUpdating = false;
            var isProgrammaticUpdate = false;
            
            window._syncTimeUpdate = function() {
                if(isUpdating) return;
                var currentTime = video.currentTime;
                var plotTime = minTime + currentTime;
                
                if(window.Plotly && plotDiv.layout) {
                    var existingShapes = plotDiv.layout.shapes || [];
                    var markerIndex = existingShapes.findIndex(s => s.name === 'sync-marker');
                    
                    if (markerIndex !== -1) {
                        isProgrammaticUpdate = true;
                        var update = {};
                        update[`shapes[${markerIndex}].x0`] = plotTime;
                        update[`shapes[${markerIndex}].x1`] = plotTime;
                        update[`shapes[${markerIndex}].y0`] = 0;
                        update[`shapes[${markerIndex}].y1`] = 1;
                        update[`shapes[${markerIndex}].opacity`] = 1;
                        Plotly.relayout(plotDiv, update).then(() => {
                            isProgrammaticUpdate = false;
                        });
                    }
                }
            };
            
            window._syncPlotClick = function(data) {
                isUpdating = true;
                var clickX = data.points[0].x;
                var newTime = clickX - minTime;
                if(newTime >= 0) {
                    video.currentTime = newTime;
                }
                setTimeout(() => isUpdating = false, 200);
            };
            
            window._syncPlotRelayout = function(eventData) {
                if(isUpdating || isProgrammaticUpdate) return;
                
                if (eventData && plotDiv.layout && plotDiv.layout.shapes) {
                    var markerIndex = plotDiv.layout.shapes.findIndex(s => s.name === 'sync-marker');
                    if (markerIndex === -1) return;
                    
                    var x0_key = `shapes[${markerIndex}].x0`;
                    var x1_key = `shapes[${markerIndex}].x1`;
                    var y0_key = `shapes[${markerIndex}].y0`;
                    var y1_key = `shapes[${markerIndex}].y1`;
                    
                    var hasXUpdate = eventData[x0_key] !== undefined || eventData[x1_key] !== undefined;
                    var hasYUpdate = eventData[y0_key] !== undefined || eventData[y1_key] !== undefined;
                    
                    if (hasYUpdate) {
                        var revert = {};
                        revert[y0_key] = 0;
                        revert[y1_key] = 1;
                        if (!hasXUpdate) {
                            isProgrammaticUpdate = true;
                            Plotly.relayout(plotDiv, revert).then(() => { isProgrammaticUpdate = false; });
                            return;
                        }
                    }
                    
                    if (hasXUpdate) {
                        isUpdating = true;
                        var newX = eventData[x0_key] !== undefined ? eventData[x0_key] : eventData[x1_key];
                        var newTime = newX - minTime;
                        if(newTime >= 0) {
                            video.currentTime = newTime;
                        }
                        
                        // Force shape to stay completely vertical
                        var fix = {};
                        fix[x0_key] = newX;
                        fix[x1_key] = newX;
                        fix[y0_key] = 0;
                        fix[y1_key] = 1;
                        isProgrammaticUpdate = true;
                        Plotly.relayout(plotDiv, fix).then(() => { isProgrammaticUpdate = false; });
                        
                        setTimeout(() => isUpdating = false, 150);
                    }
                }
            };
            
            video.addEventListener('timeupdate', window._syncTimeUpdate);
            
            if(plotDiv.on) {
                plotDiv.on('plotly_click', window._syncPlotClick);
                plotDiv.on('plotly_relayout', window._syncPlotRelayout);
            }
            
            // Force an initial draw of the marker even if the video hasn't played yet
            window._syncTimeUpdate();
            
        }, 1000); 
        
        return window.dash_clientside.no_update;
    }
    """,
    Output('dummy-output', 'children'),
    Input('min-time-store', 'data'),
    Input('main-plot', 'figure'),
    Input('theme-dropdown', 'value'),
    prevent_initial_call=False
)

@app.callback(
    Output('export-download', 'data'),
    Output('export-status', 'children'),
    Output('annotator-dropdown', 'options', allow_duplicate=True),
    Input('export-btn', 'n_clicks'),
    State('session-dropdown', 'value'),
    State('annotator-dropdown', 'value'),
    State('consolidation-dropdown', 'value'),
    State('sensor-dropdown', 'value'),
    prevent_initial_call=True
)
def export_consolidated(n_clicks, session_path, annotators, mode, sensor):
    if mode in (None, 'none'):
        return dash.no_update, "Choose a consolidation mode first.", dash.no_update
    segments = consolidated_segments(session_path, annotators, mode)
    if segments is None:
        return dash.no_update, "Select at least two annotators.", dash.no_update

    df = segments_to_annotation(segments, sensor or '')
    session_name = os.path.basename(os.path.normpath(session_path))
    filename = f"{session_name}_Ann_{mode}.csv"
    ann_dir = os.path.join(session_path, "annotations")
    os.makedirs(ann_dir, exist_ok=True)
    df.to_csv(os.path.join(ann_dir, filename), index=False)

    man_path = os.path.join(session_path, "session_manifest.json")
    if os.path.exists(man_path):
        with open(man_path, "r") as f:
            man = json.load(f)
        artifacts = man.setdefault('artifacts', {})
        artifacts['annotations_dir'] = 'annotations'
        files = artifacts.setdefault('annotation_files', [])
        if f"annotations/{filename}" not in files:
            files.append(f"annotations/{filename}")
        with open(man_path, "w") as f:
            json.dump(man, f, indent=4)

    status = f"Saved annotations/{filename} ({len(df)} change points)."
    return dcc.send_data_frame(df.to_csv, filename, index=False), status, get_annotator_options(session_path)


if __name__ == '__main__':
    app.run(debug=False, port=8052)
