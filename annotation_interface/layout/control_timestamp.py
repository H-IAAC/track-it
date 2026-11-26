
import dash
from dash import dcc, html, Input, Output, State,callback_context,no_update
import plotly.graph_objs as go
import pandas as pd
import dash_player
import os
import flask

class ControlsTimestamp(html.Div):
    def __init__(self):
        self.isPlaying = False
        super().__init__([
            html.Div([
            
            dcc.Slider(
                id='video-slider',
                min=0,
                #max=data['sec'].max(),
                step=0.1,
                #value=100,
                #marks={i: f'{i}s' for i in range(0, int(data['sec'].max()) + 1, 60)},
                included=False,
                vertical=False
            ),
            html.Div([
                html.Button('<', id='btn-back', n_clicks=0, style={'margin': '0 10px'}),
                html.Button('Play', id='btn-start', n_clicks=0, style={'margin': '0 10px'}),
                html.Button('>', id='btn-front', n_clicks=0, style={'margin': '0 10px'}),
            ], style={'marginTop': '10px', 'textAlign': 'center'}),
           
            
        ], style={'width': '100%', 'display': 'inline-block'})])


    
    
    def  register_callbacks(self,app):

        @app.callback(
            Output('stored_timestamp', 'data'),
            [Input('line-plot_zoom', 'relayoutData')],
            [State('stored_timestamp', 'data')],
            prevent_initial_call=True
        )
        def update_timestamp_from_relayout(relayout_data, current_timestamp):
            if relayout_data and 'shapes[0].x0' in relayout_data:
                # If this relayout came from our JS debounce sync, ignore it to avoid video rewinds!
                if relayout_data.get('is_auto_sync') is True:
                    return dash.no_update
                    
                # Gets the new x position of the shape in the graph
                timestamp = relayout_data['shapes[0].x0']
                return {"timestamp": timestamp, 'type': "plot_zoom"}
                
            return dash.no_update

    # Callback dedicated to the "Back" button
        @app.callback(
            Output('stored_timestamp', 'data', allow_duplicate=True),
            Input('btn-back', 'n_clicks'),
            [State('stored_min_max_data', 'data'),
            State('stored_timestamp', 'data')],
            prevent_initial_call=True
        )
        def update_timestamp_back(n_clicks_back, min_max, current_time):
            if n_clicks_back:
                current_time = current_time['timestamp']
                timestamp = max(current_time - 50, min_max['x0'])
                return {"timestamp": timestamp,'type':"n_clicks_back"}

            return current_time

        # Callback dedicated to the "Front" button
        @app.callback(
            Output('stored_timestamp', 'data', allow_duplicate=True),
            Input('btn-front', 'n_clicks'),
            [State('stored_min_max_data', 'data'),
            State('stored_timestamp', 'data')],
            prevent_initial_call=True
        )
        def update_timestamp_front(n_clicks_front, min_max, current_time):
            if n_clicks_front:
                current_time = current_time['timestamp']
                timestamp = min(current_time + 50, min_max['x1'])
                return {"timestamp": timestamp,'type':"n_clicks_front"}

            return current_time

        # DOM MUTATION STRATEGY: 0 Network Requests for Video Sync!
        app.clientside_callback(
            """
            function(current_time) {
                if (!current_time || current_time.timestamp === undefined) return window.dash_clientside.no_update;
                
                var timestamp = current_time.timestamp;
                
                function moveMarkerDOM(gdId) {
                    var gdContainer = document.getElementById(gdId);
                    if (!gdContainer) return;
                    var gd = gdContainer.classList.contains('js-plotly-plot') ? gdContainer : gdContainer.querySelector('.js-plotly-plot');
                    if (!gd || !gd._fullLayout || !gd._fullLayout.xaxis) return;
                    
                    var xaxis = gd._fullLayout.xaxis;
                    var pixel_x = xaxis.c2p(timestamp);
                    var h = gd._fullLayout._size.h;
                    
                    if (gd.layout && gd.layout.shapes) {
                        var shapeIndex = -1;
                        for (var i = 0; i < gd.layout.shapes.length; i++) {
                            if (gd.layout.shapes[i].name === 'timestamp_id') {
                                shapeIndex = i;
                                break;
                            }
                        }
                        if (shapeIndex !== -1) {
                            var shapeGroup = gd.querySelector('.shapelayer [data-index="' + shapeIndex + '"]');
                            if (shapeGroup) {
                                var path = shapeGroup.querySelector('path');
                                if (path) {
                                    // Updates the SVG <path> position directly without notifying React/Dash!
                                    path.setAttribute('d', 'M' + pixel_x + ',0L' + pixel_x + ',' + h);
                                }
                                var handles = shapeGroup.querySelectorAll('.line-drag-handle');
                                handles.forEach(function(handle) {
                                    handle.setAttribute('cx', pixel_x);
                                });
                            }
                            // Silently syncs Plotly.js state for when there's a full redraw.
                            gd.layout.shapes[shapeIndex].x0 = timestamp;
                            gd.layout.shapes[shapeIndex].x1 = timestamp;
                        }
                    }
                }
                
                // === DIRECT DOM STRATEGY ===
                // If the update came from the VIDEO (60fps), we only update the SVG. 
                // NO relayoutData event is triggered, so the Python server remains idle!
                if (current_time.type === 'video_update' || current_time.type === 'video_player') {
                    moveMarkerDOM('line-plot_zoom');
                    moveMarkerDOM('line-plot_brush');
                    
                    // DEBOUNCE: If the video stops updating for 150ms (paused),
                    // consolidate the position making the shape "real" for Plotly
                    if (window._syncTimeout) clearTimeout(window._syncTimeout);
                    window._syncTimeout = setTimeout(function() {
                        var gdZoomContainer = document.getElementById('line-plot_zoom');
                        var gdZoom = gdZoomContainer ? (gdZoomContainer.classList.contains('js-plotly-plot') ? gdZoomContainer : gdZoomContainer.querySelector('.js-plotly-plot')) : null;
                        if (gdZoom && gdZoom.layout && gdZoom.layout.shapes) {
                            var shapeIndexZoom = -1;
                            for (var i = 0; i < gdZoom.layout.shapes.length; i++) {
                                if (gdZoom.layout.shapes[i].name === 'timestamp_id') {
                                    shapeIndexZoom = i; break;
                                }
                            }
                            if (shapeIndexZoom !== -1) {
                                var updateZoom = {};
                                updateZoom['shapes[' + shapeIndexZoom + '].x0'] = timestamp;
                                updateZoom['shapes[' + shapeIndexZoom + '].x1'] = timestamp;
                                updateZoom['is_auto_sync'] = true;
                                Plotly.relayout(gdZoom, updateZoom);
                            }
                        }
                        
                        var gdBrushContainer = document.getElementById('line-plot_brush');
                        var gdBrush = gdBrushContainer ? (gdBrushContainer.classList.contains('js-plotly-plot') ? gdBrushContainer : gdBrushContainer.querySelector('.js-plotly-plot')) : null;
                        if (gdBrush && gdBrush.layout && gdBrush.layout.shapes) {
                            var shapeIndexBrush = -1;
                            for (var i = 0; i < gdBrush.layout.shapes.length; i++) {
                                if (gdBrush.layout.shapes[i].name === 'timestamp_id') {
                                    shapeIndexBrush = i; break;
                                }
                            }
                            if (shapeIndexBrush !== -1) {
                                var updateBrush = {};
                                updateBrush['shapes[' + shapeIndexBrush + '].x0'] = timestamp;
                                updateBrush['shapes[' + shapeIndexBrush + '].x1'] = timestamp;
                                updateBrush['is_auto_sync'] = true;
                                Plotly.relayout(gdBrush, updateBrush);
                            }
                        }
                    }, 500);
                    
                    return window.dash_clientside.no_update;
                }
                
                // If it was a BUTTON click (front/back), use normal Plotly API to redraw everything
                var gdBrushContainer = document.getElementById('line-plot_brush');
                var gdBrush = gdBrushContainer ? (gdBrushContainer.classList.contains('js-plotly-plot') ? gdBrushContainer : gdBrushContainer.querySelector('.js-plotly-plot')) : null;
                
                if (gdBrush && gdBrush.layout && gdBrush.layout.shapes) {
                    var shapeIndex = -1;
                    for (var i = 0; i < gdBrush.layout.shapes.length; i++) {
                        if (gdBrush.layout.shapes[i].name === 'timestamp_id') {
                            shapeIndex = i;
                            break;
                        }
                    }
                    if (shapeIndex !== -1) {
                        var update = {};
                        update['shapes[' + shapeIndex + '].x0'] = timestamp;
                        update['shapes[' + shapeIndex + '].x1'] = timestamp;
                        
                        if (['n_clicks_front', 'n_clicks_back'].includes(current_time.type)) {
                            if (gdBrush.layout.selections && gdBrush.layout.selections.length > 0) {
                                update['selections[0].x0'] = timestamp - 50;
                                update['selections[0].x1'] = timestamp + 50;
                            }
                        }
                        Plotly.relayout(gdBrush, update);
                    }
                }
                
                var gdZoomContainer = document.getElementById('line-plot_zoom');
                var gdZoom = gdZoomContainer ? (gdZoomContainer.classList.contains('js-plotly-plot') ? gdZoomContainer : gdZoomContainer.querySelector('.js-plotly-plot')) : null;
                if (gdZoom && gdZoom.layout && gdZoom.layout.shapes) {
                    var shapeIndexZoom = -1;
                    for (var i = 0; i < gdZoom.layout.shapes.length; i++) {
                        if (gdZoom.layout.shapes[i].name === 'timestamp_id') {
                            shapeIndexZoom = i;
                            break;
                        }
                    }
                    if (shapeIndexZoom !== -1) {
                        var updateZoom = {};
                        updateZoom['shapes[' + shapeIndexZoom + '].x0'] = timestamp;
                        updateZoom['shapes[' + shapeIndexZoom + '].x1'] = timestamp;
                        Plotly.relayout(gdZoom, updateZoom);
                    }
                }
                
                return window.dash_clientside.no_update;
            }
            """,
            Output('video-slider', 'value'), # Dummy output
            Input('stored_timestamp', 'data'),
            prevent_initial_call=True
        )
 
    
    
    
    
        
        
       