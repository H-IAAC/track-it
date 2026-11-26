import dash
from dash import dcc, html, Input, Output, State, clientside_callback, ClientsideFunction
import plotly.graph_objs as go
import pandas as pd
import re
import utils as ut




configs={}
configs['line_chekpoint_color']='#5d7f4c'
configs['line_chekpoint_select_color']='#3a6db0'
configs['line_timestamp_color']='#ff9d1c'


class LoadZoom(html.Div):
    def __init__(self):
       
        super().__init__([html.Div([
    dcc.Graph(
        id='line-plot_zoom',        
        config={
            'edits': {'shapePosition': True }
        },
        style={'width': '100%', 'display': 'inline-block'},
        ),
        html.Div(id='output-container'),
        html.Div(id='selected-values'),
        dcc.Store(id='stored_keyboard_shortcut', data={'key': None, 'timestamp': 0}),
        dcc.Store(id='stored_add_queue', data=[]),  # Additions queue: [{label, time, ref}, ...]
        # Hidden button clicked by JS to trigger keyboard shortcut callbacks
        html.Button(id='_kb-hidden-btn', n_clicks=0,
                    style={'display': 'none'}),
        ], style={'padding': '2px'})])


    def  register_callbacks(self,app):
        # ── Keyboard Shortcuts ────────────────────────────────────────────────
        # Strategy: document listener (capture phase, before Plotly) clicks
        # a hidden button and records the key in a dcc.Store. A Python callback reads
        # this store and changes the dragmode of the graphs.
        #
        # Mapping:  Space / P → pan  |  S / E → select  |  Z → zoom
        app.clientside_callback(
            """
            function(id) {
                if (window._kbShortcutRegistered) return window.dash_clientside.no_update;
                window._kbShortcutRegistered = true;

                var keyMap = {
                    ' ' : 'pan',
                    'p' : 'pan',
                    's' : 'select',
                    'e' : 'select',
                    'z' : 'zoom',
                    'a' : 'autorange',
                    'r' : 'reset_axes',
                    '1' : '1',
                    '2' : '2',
                    '3' : '3',
                    '4' : '4',
                    '5' : '5',
                    '6' : '6',
                    '7' : '7',
                    '8' : '8',
                    '9' : '9',
                    "'" : "'"
                };

                var localDragModes = {
                    ' ' : 'pan'
                };

                function getPlotDiv(graphId) {
                    var container = document.getElementById(graphId);
                    if (!container) return null;
                    if (container.classList && container.classList.contains('js-plotly-plot')) return container;
                    return container.querySelector('.js-plotly-plot');
                }

                function applyLocalDragmode(mode) {
                    var gd = getPlotDiv('line-plot_zoom');
                    if (gd && window.Plotly && mode) {
                        window.Plotly.relayout(gd, {'dragmode': mode});
                    }
                }

                function applyAutoscaleToBrushWindow() {
                    var gdZoom = getPlotDiv('line-plot_zoom');
                    var gdBrush = getPlotDiv('line-plot_brush');
                    if (!gdZoom || !window.Plotly) return false;

                    var brushLayout = (gdBrush && (gdBrush.layout || gdBrush._fullLayout)) || {};
                    var selections = brushLayout.selections || [];
                    if (!selections.length) return false;

                    var s = selections[0];
                    var x0 = Math.min(s.x0, s.x1);
                    var x1 = Math.max(s.x0, s.x1);

                    window.Plotly.relayout(gdZoom, {
                        'xaxis.range': [x0, x1],
                        'xaxis.autorange': false,
                        'yaxis.autorange': true
                    });
                    return true;
                }

                function applyResetAxesFullSeries() {
                    var gdZoom = getPlotDiv('line-plot_zoom');
                    if (!gdZoom || !window.Plotly || !gdZoom.data || !gdZoom.data.length) return false;

                    var xAll = [];
                    var yAll = [];
                    gdZoom.data.forEach(function(trace) {
                        var tx = trace.x || [];
                        var ty = trace.y || [];
                        for (var i = 0; i < tx.length; i++) xAll.push(tx[i]);
                        for (var j = 0; j < ty.length; j++) yAll.push(ty[j]);
                    });

                    if (!xAll.length || !yAll.length) return false;

                    var xMin = Math.min.apply(null, xAll);
                    var xMax = Math.max.apply(null, xAll);
                    var yMin = Math.min.apply(null, yAll);
                    var yMax = Math.max.apply(null, yAll);

                    window.Plotly.relayout(gdZoom, {
                        'xaxis.range': [xMin, xMax],
                        'yaxis.range': [yMin, yMax],
                        'xaxis.autorange': false,
                        'yaxis.autorange': false
                    });
                    return true;
                }

                // State to prevent repeated keydown events for the spacebar
                var spacePressed = false;

                document.addEventListener('keydown', function(e) {
                    // Prevent Space/Enter from triggering modebar buttons when focused
                    var active = document.activeElement;
                    if (active && active.classList && active.classList.contains('modebar-btn')) {
                        active.blur();
                    }

                    // Special case: Enter for the ADD button
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        var btnAdd = document.getElementById('btn-add');
                        if (btnAdd && !btnAdd.disabled) {
                            btnAdd.click();
                        }
                        return;
                    }

                    var tag = (e.target || e.srcElement).tagName.toLowerCase();
                    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

                    var key = e.key === ' ' ? ' ' : e.key.toLowerCase();

                    if (!(key in keyMap)) return;

                    // If spacebar is already pressed, ignore to avoid key repeat
                    if (key === ' ' && spacePressed) return;
                    if (key === ' ') spacePressed = true;

                    e.preventDefault();   // Prevent page scroll on Space etc.

                    // Switch mode locally (no server round-trip) to avoid delay/flicker.
                    if (key in localDragModes) {
                        applyLocalDragmode(localDragModes[key]);
                        return;
                    }

                    // Save key in sessionStorage
                    sessionStorage.setItem('_kbLastKey', keyMap[key]);

                    // Click hidden button to trigger Python callback
                    var btn = document.getElementById('_kb-hidden-btn');
                    if (btn) btn.click();

                }, true);

                // Intercept click on modebar Autoscale button and redirect
                // to the same logic as the 'a' shortcut (focus on brush).
                document.addEventListener('click', function(e) {
                    var modebarBtn = e.target && e.target.closest
                        ? e.target.closest('.modebar-btn')
                        : null;
                    if (!modebarBtn) return;

                    var title = (
                        modebarBtn.getAttribute('data-title') ||
                        modebarBtn.getAttribute('aria-label') ||
                        ''
                    ).toLowerCase();

                    var isAutoscaleBtn = (
                        title.includes('autoscale') ||
                        title.includes('auto scale')
                    );

                    var isResetAxesBtn = (
                        title.includes('reset axes') ||
                        title.includes('reset axis') ||
                        title.includes('reset view')
                    );

                    if (!isAutoscaleBtn && !isResetAxesBtn) return;

                    e.preventDefault();
                    e.stopPropagation();

                    if (isAutoscaleBtn) {
                        var okAuto = applyAutoscaleToBrushWindow();
                        if (!okAuto) {
                            sessionStorage.setItem('_kbLastKey', 'autorange');
                            var hiddenBtnAuto = document.getElementById('_kb-hidden-btn');
                            if (hiddenBtnAuto) hiddenBtnAuto.click();
                        }
                        return;
                    }

                    if (isResetAxesBtn) {
                        var okReset = applyResetAxesFullSeries();
                        if (!okReset) {
                            sessionStorage.setItem('_kbLastKey', 'reset_axes');
                            var hiddenBtnReset = document.getElementById('_kb-hidden-btn');
                            if (hiddenBtnReset) hiddenBtnReset.click();
                        }
                    }
                }, true);

                document.addEventListener('keyup', function(e) {
                    var key = e.key === ' ' ? ' ' : e.key.toLowerCase();
                    if (key === ' ') {
                        spacePressed = false;
                        // On releasing space, return to zoom mode immediately on client.
                        e.preventDefault();
                        applyLocalDragmode('zoom');
                    }
                }, true);

                return window.dash_clientside.no_update;
            }
            """,
            Output('_kb-hidden-btn', 'style'),   # inert output — keeps display:none
            Input('line-plot_zoom', 'id'),
            prevent_initial_call=False,
        )

        # Clientside callback that reads sessionStorage and updates the Store
        app.clientside_callback(
            """
            function(n, stored_time, current_queue, left_label_options, change_point_time, sensor_ref, is_compare_mode, compare_user_filter, protocol_file_name) {
                var key = sessionStorage.getItem('_kbLastKey');
                if (!key) return [window.dash_clientside.no_update, window.dash_clientside.no_update, window.dash_clientside.no_update];
                sessionStorage.removeItem('_kbLastKey');  // consume the key
                
                if (!protocol_file_name || protocol_file_name.trim() === "") {
                    return [window.dash_clientside.no_update, window.dash_clientside.no_update, {message: "Blocked: Please load an annotation protocol file first.", type: "danger", header: "Error"}];
                }
                
                var video_ts = (stored_time && stored_time.timestamp !== undefined) ? stored_time.timestamp : null;
                var kb_data = {key: key, ts: Date.now(), video_ts: video_ts};
                
                // Handle numeric annotation shortcuts
                var is_numeric = false;
                if (key === "'" || (!isNaN(parseInt(key)) && parseInt(key) >= 1 && parseInt(key) <= 9)) {
                    is_numeric = true;
                }
                
                if (!is_numeric || video_ts === null) {
                    // Return only kb_data for pan/zoom/etc
                    return [kb_data, window.dash_clientside.no_update, window.dash_clientside.no_update];
                }
                
                var options = left_label_options || [];
                var option_values = [];
                for(var i=0; i<options.length; i++) {
                    if (options[i].value !== undefined) option_values.push(options[i].value);
                }
                
                var shortcut_to_label = {};
                for(var i=0; i<Math.min(9, option_values.length); i++) {
                    shortcut_to_label[(i+1).toString()] = option_values[i];
                }
                shortcut_to_label["'"] = '-1';
                
                var target_label = shortcut_to_label[key];
                if (!target_label) {
                    return [kb_data, window.dash_clientside.no_update, window.dash_clientside.no_update];
                }
                
                if (is_compare_mode) {
                    if (!compare_user_filter || compare_user_filter.length !== 1) {
                        return [kb_data, window.dash_clientside.no_update, window.dash_clientside.no_update];
                    }
                    sensor_ref = compare_user_filter[0];
                }
                
                function uuidv4() {
                    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
                        return v.toString(16);
                    });
                }
                
                var new_item = {
                    label: target_label,
                    change_point_time: change_point_time || 'timestamp_local',
                    sensor_ref: sensor_ref || 'Value 2',
                    exact_ts: video_ts,
                    _id: uuidv4()
                };
                
                var queue = current_queue ? [...current_queue] : [];
                queue.push(new_item);
                
                return [kb_data, queue, window.dash_clientside.no_update];
            }
            """,
            [Output('stored_keyboard_shortcut', 'data'),
             Output('stored_add_queue', 'data', allow_duplicate=True),
             Output('toast-message-store', 'data', allow_duplicate=True)],
            Input('_kb-hidden-btn', 'n_clicks'),
            State('stored_timestamp', 'data'),
            State('stored_add_queue', 'data'),
            State('left-label', 'options'),
            State('change-point-time', 'value'),
            State('dropdown_sensor_ref', 'value'),
            State('is-compare-mode', 'data'),
            State('compare-user-filter', 'value'),
            State('file_name-protocol', 'children'),
            prevent_initial_call=True,
        )

        # Python callback: shortcuts ONLY affect the zoom plot.
        # The brush plot remains fixed in 'select' (never changed here).
        @app.callback(
            Output('line-plot_zoom', 'figure', allow_duplicate=True),
            Input('stored_keyboard_shortcut', 'data'),
            State('line-plot_zoom', 'figure'),
            State('line-plot_brush', 'figure'),
            prevent_initial_call=True,
        )
        def apply_keyboard_dragmode(kb_data, fig_zoom, fig_brush):
            if kb_data is None or kb_data.get('key') is None:
                return dash.no_update

            action = kb_data['key']   # 'pan' | 'select' | 'zoom' | 'autorange' | 'reset_axes'

            if fig_zoom is None:
                return dash.no_update

            fig_zoom = dict(fig_zoom)
            fig_zoom['layout'] = dict(fig_zoom.get('layout', {}))

            if action == 'autorange':
                selections = (
                    fig_brush.get('layout', {}).get('selections', [])
                    if isinstance(fig_brush, dict)
                    else []
                )
                if selections:
                    selection = selections[0]
                    x0, x1 = sorted([selection['x0'], selection['x1']])
                    y0, y1 = sorted([selection['y0'], selection['y1']])
                    fig_zoom['layout']['xaxis'] = dict(fig_zoom['layout'].get('xaxis', {}))
                    fig_zoom['layout']['yaxis'] = dict(fig_zoom['layout'].get('yaxis', {}))
                    fig_zoom['layout']['xaxis']['range'] = [x0, x1]
                    fig_zoom['layout']['yaxis']['range'] = [y0, y1]
                    fig_zoom['layout']['xaxis']['autorange'] = False
                    fig_zoom['layout']['yaxis']['autorange'] = False
                else:
                    fig_zoom['layout']['xaxis'] = dict(fig_zoom['layout'].get('xaxis', {}))
                    fig_zoom['layout']['yaxis'] = dict(fig_zoom['layout'].get('yaxis', {}))
                    fig_zoom['layout']['xaxis']['autorange'] = True
                    fig_zoom['layout']['yaxis']['autorange'] = True
            elif action == 'reset_axes':
                if not fig_zoom.get('data'):
                    return dash.no_update

                x_all = []
                y_all = []
                for trace in fig_zoom.get('data', []):
                    x_all.extend(trace.get('x', []) or [])
                    y_all.extend(trace.get('y', []) or [])

                if len(x_all) == 0 or len(y_all) == 0:
                    return dash.no_update

                fig_zoom['layout']['xaxis'] = dict(fig_zoom['layout'].get('xaxis', {}))
                fig_zoom['layout']['yaxis'] = dict(fig_zoom['layout'].get('yaxis', {}))
                fig_zoom['layout']['xaxis']['range'] = [min(x_all), max(x_all)]
                fig_zoom['layout']['yaxis']['range'] = [min(y_all), max(y_all)]
                fig_zoom['layout']['xaxis']['autorange'] = False
                fig_zoom['layout']['yaxis']['autorange'] = False
            else:
                return dash.no_update
            
            return fig_zoom

        @app.callback(
            Output('left-label', 'value', allow_duplicate=True),
            Input('stored_keyboard_shortcut', 'data'),
            State('left-label', 'options'),
            prevent_initial_call=True,
        )
        def set_left_label_from_numeric_shortcut(kb_data, left_label_options):
            if kb_data is None or kb_data.get('key') is None:
                return dash.no_update

            key = str(kb_data.get('key'))
            options = left_label_options or []
            option_values = [opt.get('value') for opt in options if isinstance(opt, dict)]

            shortcut_to_label = {str(i+1): option_values[i] for i in range(min(9, len(option_values)))}
            shortcut_to_label["'"] = '-1'

            target_label = shortcut_to_label.get(key)
            if target_label is None:
                return dash.no_update

            if target_label in option_values or target_label == '-1':
                selected_label = target_label
            else:
                def normalize(label):
                    return re.sub(r'[^a-z0-9]+', '', str(label).strip().lower())

                normalized_target = normalize(target_label)
                selected_label = next(
                    (value for value in option_values if normalize(value) == normalized_target),
                    None,
                )

            if selected_label is None:
                return dash.no_update
            
            return selected_label

        # ═══════════════════════════════════════════════════════════════════════════════
        # QUEUE SYSTEM: Adds items to the queue and triggers the server reactively
        # ═══════════════════════════════════════════════════════════════════════════════
        @app.callback(
            Output('stored_add_queue', 'data', allow_duplicate=True),
            Output('toast-message-store', 'data', allow_duplicate=True),
            Input('btn-add', 'n_clicks'),  # When btn-add is clicked manually
            State('left-label', 'value'),
            State('change-point-time', 'value'),
            State('dropdown_sensor_ref', 'value'),
            State('stored_add_queue', 'data'),
            State('stored_timestamp', 'data'),
            State('is-compare-mode', 'data'),
            State('compare-user-filter', 'value'),
            State('file_name-protocol', 'children'),
            prevent_initial_call=True,
        )
        def add_to_queue(btn_add_clicks, label, change_point_time, sensor_ref, current_queue, current_time, is_compare_mode, compare_user_filter, protocol_file_name):
            try:
                queue = current_queue if isinstance(current_queue, list) else []
                
                if btn_add_clicks is None:
                    return queue, dash.no_update
                    
                if not protocol_file_name or protocol_file_name.strip() == "":
                    return queue, {"message": "Blocked: Please load an annotation protocol file first.", "type": "danger", "header": "Error"}
                
                if is_compare_mode:
                    if not compare_user_filter or len(compare_user_filter) != 1:
                        return queue, {"message": "In Compare Mode, select EXACTLY ONE annotator in the filter to add points.", "type": "danger", "header": "Error"}
                    sensor_ref = compare_user_filter[0]
                
                if not label or not change_point_time or not sensor_ref:
                    return queue, dash.no_update
                
                exact_ts = current_time['timestamp'] if (current_time and isinstance(current_time, dict) and 'timestamp' in current_time) else None
                
                import uuid
                
                new_item = {
                    'label': label,
                    'change_point_time': change_point_time,
                    'sensor_ref': sensor_ref,
                    'exact_ts': exact_ts,
                    '_id': str(uuid.uuid4())
                }
                queue.append(new_item)
                
                return queue, dash.no_update
            except Exception as e:
                import traceback
                return current_queue if isinstance(current_queue, list) else [], {"message": f"Error in add_to_queue: {e}", "type": "danger", "header": "Error"}
        
        # ═══════════════════════════════════════════════════════════════════════════════
        # REACTIVE QUEUE PROCESSING: Processes ALL queue items at once!
        # ═══════════════════════════════════════════════════════════════════════════════
        @app.callback(
            Output('stored_data_checkpoint', 'data', allow_duplicate=True),
            Output('change-point-name', 'options', allow_duplicate=True),
            Output('toast-message-store', 'data', allow_duplicate=True),
            Output('stored_add_queue', 'data', allow_duplicate=True),
            Output('stored_timestamp', 'data', allow_duplicate=True),
            Input('stored_add_queue', 'data'),
            State('stored_timestamp', 'data'),
            State('stored_data_checkpoint', 'data'),
            State('file_name-protocol', 'children'),
            State('is-compare-mode', 'data'),
            State('video-player', 'playing'),
            prevent_initial_call=True,
        )
        def process_and_finalize_queue(queue, current_time, data_protocol, protocol_file_name, is_compare_mode, is_playing):
            if not queue or len(queue) == 0:
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

            import time
            import utils as ut
            
            t0 = time.time()
            print(f"\\n[TIMING] ⏱️ START process_and_finalize_queue: {t0}")
            
            # Load protocol
            df_protocol = pd.DataFrame(data_protocol) if data_protocol else pd.DataFrame(columns=['timestamp', 'left_label', 'change_point_name', 'change_point_time', 'sensor_ref'])
            
            t1 = time.time()
            print(f"[TIMING] ⏱️ Load DataFrame: {t1 - t0:.4f}s")
            
            new_time = dash.no_update
            processed_labels = []

            print(f"[REACTIVE QUEUE] ⚙️  PROCESSING BATCH OF {len(queue)} ITEM(S)...")
            
            for item in queue:
                label, change_point_time, sensor_ref = item['label'], item['change_point_time'], item['sensor_ref']
                exact_ts = item.get('exact_ts')
                timestamp = exact_ts if exact_ts is not None else (current_time['timestamp'] if current_time and 'timestamp' in current_time else 0)
                
                new_row = pd.DataFrame({
                    'left_label': [label],
                    'change_point_name': ['change_point_X'],
                    'change_point_time': [change_point_time],
                    'sensor_ref': [sensor_ref],
                    'timestamp': [timestamp]
                })
                df_protocol = pd.concat([df_protocol, new_row], ignore_index=True)
                
                if not is_playing:
                    increment_seconds = 1
                    new_timestamp = timestamp + increment_seconds
                    new_time = {"timestamp": new_timestamp, 'type': "timestamp_queue_auto_inc"}
                
                processed_labels.append(label)

            t2 = time.time()
            print(f"[TIMING] ⏱️ Process items and concat: {t2 - t1:.4f}s")

            if not is_compare_mode:
                df_protocol = df_protocol.sort_values(by='timestamp').reset_index(drop=True)
                df_protocol['change_point_name'] = [f'change_point_{i+1}' for i in range(len(df_protocol))]
            else:
                df_protocol = df_protocol.sort_values(by=['sensor_ref', 'timestamp']).reset_index(drop=True)

            t3 = time.time()
            print(f"[TIMING] ⏱️ Sort and rename: {t3 - t2:.4f}s")

            # SAVE CSV
            try:
                df_protocol = ut.save_and_resequence_protocol(df_protocol, protocol_file_name, is_compare_mode)
            except Exception as e:
                print(f"[QUEUE FINALIZE] ❌ Error saving CSV: {e}")
            
            t4 = time.time()
            print(f"[TIMING] ⏱️ Save CSV: {t4 - t3:.4f}s")
            
            df_protocol = df_protocol.where(pd.notnull(df_protocol), None)
            
            unique_names = df_protocol['change_point_name'].unique()
            options = [{'label': name, 'value': name} for name in unique_names]
            
            t5 = time.time()
            print(f"[TIMING] ⏱️ Prepare options: {t5 - t4:.4f}s")
            
            message = {"message": f"Queue processed! {len(processed_labels)} point(s) added.\nTotal points in protocol: {len(df_protocol)}.", "type": "success", "header": "Success"}
            
            print(f"[REACTIVE QUEUE] 🎉 FULL BATCH - Emptying the queue.")
            print(f"[TIMING] ⏱️ TOTAL TIME SPENT IN FUNCTION: {t5 - t0:.4f}s")
            print(f"{'='*80}\\n")
            
            return (
                df_protocol.to_dict('records'),  # stored_data_checkpoint
                options,                       # change-point-name options
                message,                        # zoomplot-logs
                [],                             # EMPTY THE QUEUE reactively
                new_time                        # stored_timestamp auto inc
            )

        # REMOVED: display_df_protocol callback - Queue system (add_to_queue, process_queue, finalize_queue_batch) 
        # handles ALL ADDs now. Previous callback removed here to avoid duplication.



        @app.callback(
            [Output('toast-message-store', 'data', allow_duplicate=True),
            Output('left-label', 'value', allow_duplicate=True),                
            Output('change-point-name', 'value', allow_duplicate=True),
            Output('change-point-time', 'value', allow_duplicate=True),
            Output('line-plot_zoom', 'figure', allow_duplicate=True),
            Output('stored_data_checkpoint', 'data',allow_duplicate=True),
            Output('last_clicked_sensor_ref', 'data', allow_duplicate=True)
            ]
            ,
            [Input('line-plot_zoom', 'relayoutData'),
             State('stored_data_select_range', 'data'),
             State('stored_data_checkpoint', 'data'),
             State('file_name-protocol', 'children'),
             State('is-compare-mode', 'data'),
             State('filter-shapes', 'value'),
             State('compare-user-filter', 'value'),
             State('stored_discordant_windows', 'data')
             ],prevent_initial_call=True
        )
        def update_relayout_zoom(relayout_data, stored_data_select_range, data_protocol, protocol_file_name, is_compare_mode, filter_shapes, compare_user_filter, stored_discordant_windows):
            """
            FIX: Complete validation + try/catch for dragging shapes
            Bugs 17-21 handled here
            """
            if relayout_data is None:
                # FIX: Return object, not string (BUG 21)
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

            try:
                # Detect modebar autoscale and apply special logic
                
                autoscale_keys = {'xaxis.autorange', 'yaxis.autorange'}
                relayout_keys = set(relayout_data.keys()) if isinstance(relayout_data, dict) else set()
                has_autoscale_flag = any(relayout_data.get(key) is True for key in autoscale_keys if key in relayout_keys)
                has_range_update = any('range[' in key for key in relayout_keys)
                is_modebar_autoscale = isinstance(relayout_data, dict) and has_autoscale_flag and not has_range_update

                if is_modebar_autoscale:
                    # Special logic for autoscaling to the brush window
                    if stored_data_select_range:
                        x0, x1 = sorted([stored_data_select_range[0], stored_data_select_range[1]])
                        patched_figure = dash.Patch()
                        patched_figure['layout']['xaxis']['range'] = [x0, x1]
                        patched_figure['layout']['xaxis']['autorange'] = False
                        patched_figure['layout']['yaxis']['autorange'] = True
                        del patched_figure['layout']['yaxis']['range']
                        return {"message": "Autoscaled to brush view", "type": "info", "header": "Info"}, dash.no_update, dash.no_update, dash.no_update, patched_figure, dash.no_update, dash.no_update

                # Process shapes drag
                keys_received = list(relayout_data.keys())
                
                # If it is shapes[0] (orange), silently ignore to prevent screen flicker
                if len(keys_received) == 2 and 'shapes[0].x0' in keys_received:
                    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                
                for key, value in relayout_data.items():
                    if not isinstance(key, str) or '.x0' not in key:
                        continue
                        
                    index = ut.extract_index_from_key(key)
                    if index == 0:
                        continue  # Ignora shape 0 (timestamp_id)
                    
                    if data_protocol is None:
                        return (
                            {"message": "Protocol file not loaded", "type": "danger", "header": "Error"},
                            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                        )
                    
                    df_protocol = pd.DataFrame(data_protocol)
                    
                    # Reconstruct shapes list to find the correct shape name
                    expected_shapes = ['timestamp_id']
                    
                    if is_compare_mode:
                        if stored_discordant_windows:
                            for i in range(len(stored_discordant_windows)):
                                expected_shapes.append(f'discordant_window_{i}')
                        for _, row in df_protocol.iterrows():
                            if compare_user_filter and row['sensor_ref'] not in compare_user_filter:
                                continue
                            shapeName = f"{row['left_label']}__{row['change_point_name']}__{row['change_point_time']}__{row.get('sensor_ref', '')}"
                            expected_shapes.append(shapeName)
                    else:
                        for _, row in df_protocol.iterrows():
                            if filter_shapes:
                                if isinstance(filter_shapes, list) and len(filter_shapes) > 0:
                                    if 'All' not in filter_shapes and row['left_label'] not in filter_shapes:
                                        continue
                                elif isinstance(filter_shapes, str) and filter_shapes != 'All' and row['left_label'] != filter_shapes:
                                    continue
                            sensor_ref_str = row.get('sensor_ref', '')
                            shapeName = f"{row['left_label']}__{row['change_point_name']}__{row['change_point_time']}__{sensor_ref_str}"
                            expected_shapes.append(shapeName)
                    
                    if index >= len(expected_shapes):
                        return ({"message": f"Index {index} out of bounds", "type": "danger", "header": "Error"}, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update)
                        
                    shape_name = expected_shapes[index]
                    
                    # Ignore discordant windows (pastel background)
                    if shape_name.startswith('discordant_window'):
                        continue
                        
                    # FIX 2: Validate shape_name format (BUG 18)
                    parts = shape_name.split('__')
                    if len(parts) != 4:
                        print(f"[UPDATE_RELAYOUT] Invalid shape name: '{shape_name}' (expected 4 parts, got {len(parts)})")
                        return (
                            {"message": f"Invalid shape name ('{shape_name}'). Format: label__name__time__ref", "type": "danger", "header": "Error"},
                            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                        )
                    
                    left_label, change_point_name, change_point_time, sensor_ref = parts
                    
                    # FIX 4: Validate line found using only the name (which is unique)
                    filtered_df = df_protocol[
                        (df_protocol['change_point_name'] == change_point_name) &
                        (df_protocol['sensor_ref'] == sensor_ref)
                    ]
                    
                    if filtered_df.empty:
                        print(f"[UPDATE_RELAYOUT] Point not found: {shape_name}")
                        return (
                            {"message": f"Change point not found ({shape_name})", "type": "danger", "header": "Error"},
                            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                        )
                    
                    index_to_update = filtered_df.index[0]
                    old_timestamp = df_protocol.at[index_to_update, 'timestamp']
                    new_timestamp = value
                    
                    # Update DataFrame
                    df_protocol.at[index_to_update, 'timestamp'] = new_timestamp
                    
                    # Checkpoint movement log
                    time_diff = new_timestamp - old_timestamp
                    print(f"\n{'='*80}")
                    print(f"[MARKER MOVE] ✅ CHECKPOINT MOVED")
                    print(f"{'='*80}")
                    print(f"[MARKER MOVE] Label: '{left_label}'")
                    print(f"[MARKER MOVE] Point: {change_point_name}")
                    print(f"[MARKER MOVE] Timestamp BEFORE: {old_timestamp:.2f}s")
                    print(f"[MARKER MOVE] Timestamp AFTER: {new_timestamp:.2f}s")
                    print(f"[MARKER MOVE] Difference: {time_diff:+.2f}s")
                    print(f"{'='*80}\n")
                    
                    # Reorganize and Save
                    if not protocol_file_name or protocol_file_name.strip() == "":
                        return (
                            {"message": "Protocol file not defined", "type": "danger", "header": "Error"},
                            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                        )
                    
                    try:
                        df_protocol = ut.save_and_resequence_protocol(df_protocol, protocol_file_name, is_compare_mode)
                        print(f"[UPDATE_RELAYOUT] Shape {index} moved to {new_timestamp:.2f}s and saved")
                    except PermissionError:
                        return (
                            {"message": "No permission to save file", "type": "danger", "header": "Error"},
                            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                        )
                    except IOError as e:
                        return (
                            {"message": f"Error saving: {str(e)}", "type": "danger", "header": "Error"},
                            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                        )
                    
                    return (
                        {"message": f"Point moved to {new_timestamp:.2f}s", "type": "success", "header": "Success"},
                        left_label,
                        change_point_name,
                        change_point_time,
                        dash.no_update,
                        df_protocol.to_dict('records'),
                        sensor_ref
                    )
                
                # No shape processed successfully
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                
            except Exception as e:
                import traceback
                print(f"[UPDATE_RELAYOUT] Error: {str(e)}")
                traceback.print_exc()
                return (
                    {"message": f"Error processing: {str(e)}", "type": "danger", "header": "Error"},
                    dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
                )
    


        @app.callback(
            [
            Output('toast-message-store', 'data', allow_duplicate=True),
            Output('stored_data_checkpoint', 'data',allow_duplicate=True),
            Output('left-label', 'value'),
            Output('change-point-name', 'value'),
            Output('change-point-time', 'value')],
            Input('btn-delete', 'n_clicks'),
            State('stored_data_checkpoint', 'data'),
            State('left-label', 'value'),
            State('change-point-name', 'value'),
            State('change-point-time', 'value'),
            State('file_name-protocol', 'children'),
            State('is-compare-mode', 'data'),
            State('compare-user-filter', 'value'),
            State('last_clicked_sensor_ref', 'data')
            ,prevent_initial_call=True
        )
        def delete_elements(n_clicks, data_protocol, left_label, change_point_name, change_point_time, protocol_file_name, is_compare_mode, compare_user_filter, last_clicked_sensor_ref):
            """
            FIX: Corrected logic - uses AND with negation, not OR
            Deletes ONLY the line EXACTLY matching the criteria
            """
            if change_point_name is None:
                return (
                    {"message": "Please select a Change Point Name", "type": "warning", "header": "Warning"},
                    dash.no_update, dash.no_update, dash.no_update, dash.no_update
                )
            
            if data_protocol is None:
                return (
                    {"message": "No data loaded", "type": "warning", "header": "Warning"},
                    dash.no_update, dash.no_update, dash.no_update, dash.no_update
                )
            
            if n_clicks > 0:
                df_protocol = pd.DataFrame(data_protocol)
                
                initial_count = len(df_protocol)
                
                if is_compare_mode:
                    target_sensor = None
                    
                    if compare_user_filter and len(compare_user_filter) == 1:
                        target_sensor = compare_user_filter[0]
                    elif last_clicked_sensor_ref:
                        target_sensor = last_clicked_sensor_ref
                    else:
                        matches = df_protocol[df_protocol['change_point_name'] == change_point_name]
                        if len(matches) == 1:
                            target_sensor = matches.iloc[0]['sensor_ref']
                            
                    if not target_sensor:
                        return (
                            {"message": "Could not determine the annotator for this point. Click the point or filter by 1 annotator.", "type": "danger", "header": "Error"},
                            dash.no_update, dash.no_update, dash.no_update, dash.no_update
                        )
                    
                    df_protocol = df_protocol[
                        ~(
                            (df_protocol['change_point_name'] == change_point_name) &
                            (df_protocol['sensor_ref'] == target_sensor)
                        )
                    ]
                else:
                    df_protocol = df_protocol[df_protocol['change_point_name'] != change_point_name]
                
                deleted_count = initial_count - len(df_protocol)
                
                if deleted_count == 0:
                    return (
                        {"message": "No change point found with this name", "type": "warning", "header": "Warning"},
                        dash.no_update, dash.no_update, dash.no_update, dash.no_update
                    )
                
                try:
                    if not protocol_file_name or protocol_file_name.strip() == "":
                        return (
                            {"message": "Protocol file not defined", "type": "danger", "header": "Error"},
                            dash.no_update, dash.no_update, dash.no_update, dash.no_update
                        )
                    
                    df_protocol = ut.save_and_resequence_protocol(df_protocol, protocol_file_name, is_compare_mode)
                                    
                    print(f"[DELETE] {deleted_count} row(s) deleted. Total remaining: {len(df_protocol)}")
                    
                    return (
                        {"message": f"{deleted_count} point(s) deleted", "type": "success", "header": "Success"},
                        df_protocol.to_dict('records'),
                        '-1',  # Reset labels
                        None,
                        'timestamp_local'
                    )
                    
                except PermissionError:
                    return (
                        {"message": "No permission to save file. Check permissions.", "type": "danger", "header": "Error"},
                        dash.no_update, dash.no_update, dash.no_update, dash.no_update
                    )
                except IOError as e:
                    return (
                        {"message": f"Error saving: {str(e)}", "type": "danger", "header": "Error"},
                        dash.no_update, dash.no_update, dash.no_update, dash.no_update
                    )
            
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

            


        """     @app.callback(
    Output('line-plot_zoom', 'figure', allow_duplicate=True),
    Input('stored_data_select_range', 'data'),
    Input('stored_min_max_data', 'data'),

    
    State('stored_timestamp', 'data'),
    State('stored_data_checkpoint', 'data'),

    State('line-plot_zoom', 'figure'),prevent_initial_call=True,
)
        def update_line_plot2(stored_data_select_range,stored_min_max_data,current_time,stored_chek,fig):

            if fig is None:
                
                fig = {
                        'layout': {
                            'autosize': True,
                            'margin': {'l': 0, 'r': 0, 't': 0, 'b': 24},
                            'plot_bgcolor': 'rgba(0,0,0,0)',
                            'paper_bgcolor': 'rgba(0,0,0,0)',
                            'font': {'family': 'Helvetica Neue, Helvetica, Arial, sans-serif', 'color': '#8a8478', 'size': 13},
                            'title': '',
                            'showlegend': False,
                            'modebar': {
                                'orientation': 'v'
                            },
                            'xaxis': {
                                'showgrid': True,  # Show grid lines on x-axis
                                'gridcolor': 'rgba(138,132,120,0.25)',  # Grid line color
                                'gridwidth': 1  # Grid line width
                            },
                            'yaxis': {
                                'showgrid': True,  # Show grid lines on y-axis
                                'gridcolor': 'rgba(138,132,120,0.25)',  # Grid line color
                                'gridwidth': 1  # Grid line width
                            }
                        }
                    }
            
            fig = go.Figure(fig) 
            if(stored_data_select_range):
                
                    x_data_sensor = stored_data_select_range.get('x', [])
                    y_data_sensor = stored_data_select_range.get('y', [])
            else:
                    x_data_sensor=[0,100]
                    y_data_sensor=[0,10]



                   #            
                        
            if len(fig.data) > 0:
                            # Update the existing trace 0
                            fig.data[0].x = x_data_sensor
                            fig.data[0].y = y_data_sensor
                            df_protocol = pd.DataFrame(stored_chek)
                            shapes=ut.update__line_timestamp(current_time['timestamp'])
                            fig['layout']['shapes'] =shapes+ ut.update_shapes(df_protocol,min(fig.data[0].x), max(fig.data[0].x),0,15)

            else:
                        fig.add_trace(
                            go.Scatter(
                                x=x_data_sensor,
                                y=y_data_sensor,
                                mode='lines+markers'  # Change to 'lines+markers'
                            )
                        )

                
                
            

            return fig
        """
