import pandas as pd
import dash
from dash import dcc, html, Input, Output,State
import pandas as pd
import utils as ut
import plotly.graph_objects as go

def get_selected_data(figure_brush,x_range,y_range):
        
        x_original = figure_brush['data'][0]['x']
        y_original = figure_brush['data'][0]['y']

        mask = [
                    (x >= x_range[0]) & (x <= x_range[1])
                    for x in x_original
                ]
                
        x_data = [x for x, include in zip(x_original, mask) if include]
        y_data = [y for y, include in zip(y_original, mask) if include]

        return x_data,y_data



def create_plot_zoom(x_data, y_data, selected_sensor_ref, x_range=None):
    layout = {
        'autosize': True,
        'margin': {'l': 0, 'r': 10, 't': 0, 'b': 28},
        'plot_bgcolor': 'rgba(0,0,0,0)',
        'paper_bgcolor': 'rgba(0,0,0,0)',
        'font': {'family': 'Helvetica Neue, Helvetica, Arial, sans-serif', 'color': '#8a8478', 'size': 13},
        'yaxis': {'gridcolor': 'rgba(138,132,120,0.25)'},
        'xaxis': {'autorange': False} if x_range else {'autorange': True},
    }
    if x_range:
        layout['xaxis']['range'] = x_range
        
    fig = {
        'data': [
            {
                'x': x_data,
                'y': y_data,
                'type': 'line',
                'name': selected_sensor_ref,
                'line': {
                    'color': '#5750c4',
                    'width': 2,
                }
            }
        ],
        'layout': layout
    }
    return fig


def create_plot_brush(x0,x1,y0,y1,x_data,y_data,selected_sensor_ref):
    layout = go.Layout(
                dragmode='select',
                selectdirection='h',
                margin={'l': 0, 'r': 0, 't': 0, 'b': 0},
                hovermode='closest',
                xaxis={'title': 'Time (s)', 'range': [x0, x1]},
                yaxis={'title': 'Values', 'range': [y0, y1]},
                newselection=dict(line=dict(color='#5750c4')),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font={'family': 'Helvetica Neue, Helvetica, Arial, sans-serif', 'color': '#8a8478', 'size': 11},
                selections=[
                    dict(
                        x0=x0 + (x1 - x0)/2 - min(100, x1 - x0)/2,
                        x1=x0 + (x1 - x0)/2 + min(100, x1 - x0)/2,
                        y0=y0,
                        y1=y1,
                        yref='paper',
                        type='rect',
                        line=dict(color='#5750c4')
                    )
                ],
                height=100
            )

            # Create the graph
    figure = {
                'data': [
                    {
                        'x': x_data,
                        'y': y_data,
                        'type': 'line',
                        'name': selected_sensor_ref,
                        'line': {
                'color': '#5750c4',  # Color for the main line
                'width': 2,       # Thickness of the main line
            }
                    }
                ],
                'layout': layout
            }
    return figure




class PlotBrush(html.Div):
    def __init__(self):
        super().__init__([
            dcc.Graph(
                id='line-plot_brush',style={'width': '100%','height':'100px','display': 'inline-block'}
            ),
        dcc.Store(id='stored_data_select_range'),
            
        ], style={'width': '100%', 'display': 'inline-block'})


    def  register_callbacks(self,app):
        # Callback to update the graph based on dropdown selection
        @app.callback(
           [ Output('stored_min_max_data', 'data',allow_duplicate=True),
            Output('line-plot_brush', 'figure',allow_duplicate=True),
            Output('line-plot_zoom', 'figure',allow_duplicate=True),
            ],
            Input('dropdown_sensor_ref', 'value'),
            Input('stored_data_sensores', 'data'),
            State('line-plot_zoom', 'figure'),
            prevent_initial_call=True,
        )
        def create_graph(selected_sensor_ref, data, zoom_state):
            if selected_sensor_ref is None or data is None:
                return dash.no_update,dash.no_update,dash.no_update

            df = pd.DataFrame(data)
            if selected_sensor_ref not in df.columns:
                return dash.no_update,dash.no_update,dash.no_update

            x_data = df['sec']
            y_data = df[selected_sensor_ref]
 
            x0 = min(x_data)
            x1 = max(x_data)
            y0 = min(y_data)
            y1 = max(y_data)
            data_values_min_max={'x0': x0,'x1':x1,'y0': y0,'y1':y1  }
            
            figure_brush=create_plot_brush(x0,x1,y0,y1,x_data,y_data,selected_sensor_ref)

            span = min(100, x1 - x0)
            x_range=[x0 + (x1 - x0)/2 - span/2, x0 + (x1 - x0)/2 + span/2]
            y_range_float = [float(y0), float(y1)]
            x_data_,y_data_=get_selected_data(figure_brush,x_range,y_range_float)
            figure_zoom=create_plot_zoom(x_data_,y_data_,selected_sensor_ref, x_range)
            
            # Restore existing shapes (annotations) to prevent wiping them out due to callback race conditions
            if zoom_state and 'layout' in zoom_state and 'shapes' in zoom_state['layout']:
                existing_shapes = zoom_state['layout']['shapes']
                if existing_shapes:
                    if 'shapes' not in figure_zoom['layout']:
                        figure_zoom['layout']['shapes'] = []
                    # Filter out any old timestamp line before adding the rest
                    shapes_to_keep = [s for s in existing_shapes if not str(s.get('name', '')).startswith('timestamp_id')]
                    figure_zoom['layout']['shapes'].extend(shapes_to_keep)

            figure_brush['layout']['shapes']=ut.update__line_timestamp(x0+(x1-x0)/2,y0,y1)
            
            if 'shapes' not in figure_zoom['layout'] or not figure_zoom['layout']['shapes']:
                figure_zoom['layout']['shapes'] = []
            
            # Make sure timestamp is added
            ts_shape = ut.update__line_timestamp(x0+(x1-x0)/2,y0,y1)
            # Remove old timestamp if it got copied somehow
            figure_zoom['layout']['shapes'] = [s for s in figure_zoom['layout']['shapes'] if not str(s.get('name', '')).startswith('timestamp_id')]
            # Insert timestamp at the beginning (index 0) so expected_shapes matches
            figure_zoom['layout']['shapes'] = list(ts_shape) + figure_zoom['layout']['shapes']
            
            figure_zoom['layout']['shapes']=tuple(figure_zoom['layout']['shapes'])
            

            return data_values_min_max,figure_brush,figure_zoom
            
        @app.callback(
            Output('line-plot_zoom', 'figure', allow_duplicate=True),
            Output('stored_timestamp', 'data', allow_duplicate=True),
            Input('line-plot_brush', 'selectedData'),
            State('stored_data_checkpoint', 'data'),
            State('line-plot_brush', 'figure'),
            State('stored_min_max_data', 'data'),
           
            
            prevent_initial_call=True
        )
        def store_selected_data(selectedData,stored_chek, figure,min_max):
            if selectedData and  'range'  in selectedData:
                x_range = selectedData['range']['x']
                y_range = [float(min_max['y0']), float(min_max['y1'])]

                selected_sensor_ref=figure['data'][0]['name']                
                x_data_,y_data_=get_selected_data(figure,x_range,y_range)
                figure_zoom=create_plot_zoom(x_data_,y_data_,selected_sensor_ref, x_range)
                #figure_zoom['layout']['shapes'] =figure['layout']['shapes']
                timestamp = x_range[0] + (x_range[1] - x_range[0]) / 2
                shapes=ut.update__line_timestamp(timestamp,y_range[0],y_range[1])
                df_protocol = pd.DataFrame(stored_chek)
                figure_zoom['layout']['shapes'] =shapes+ut.update_shapes(df_protocol,x_range[0], x_range[1],y_range[0],y_range[1])
                figure_zoom['layout']['annotations'] =ut.update_annotation(df_protocol,x_range[0], x_range[1],y_range[0],y_range[1]) 


                

                return figure_zoom, {"timestamp":timestamp,'type':"select_brush"}
            else:
                return dash.no_update, {"timestamp":min_max['x1']/2,'type':"select_brush"}



        

        @app.callback(
        [Output('toast-message-store', 'data', allow_duplicate=True),
        Output('line-plot_brush', 'figure', allow_duplicate=True),
        Output('line-plot_zoom', 'figure', allow_duplicate=True),
        Output('change-point-name', 'options', allow_duplicate=True)],
        [Input('stored_data_checkpoint', 'data')],
        [State('stored_timestamp', 'data'),
        State('line-plot_brush', 'figure'),
        State('line-plot_zoom', 'figure'),
        State('stored_min_max_data', 'data')],prevent_initial_call=True,
    )
        def display_df_protocol(data_checkpoint,current_time,figure_brush,figure_zoom,min_max):
            if data_checkpoint is None:
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update
            
            import time
            t0 = time.time()
            
            df_protocol = pd.DataFrame(data_checkpoint)
            
            if not df_protocol.empty and 'change_point_name' in df_protocol.columns:
                unique_names = df_protocol['change_point_name'].unique()
            else:
                unique_names = []
                
            options = [{'label': name, 'value': name} for name in unique_names]
            
            return dash.no_update, dash.no_update, dash.no_update, options

        # CLIENTSIDE CALLBACK: Fast render of shapes directly in JS to bypass Python entirely
        app.clientside_callback(
            """
            function(data_checkpoint, min_max, current_time) {
                if (!data_checkpoint) return [window.dash_clientside.no_update, window.dash_clientside.no_update];
                
                var df = data_checkpoint;
                var video_ts = (current_time && current_time.timestamp !== undefined) ? current_time.timestamp : null;
                
                function updateGraphShapes(graphId, isBrush) {
                    var container = document.getElementById(graphId);
                    if (!container) return;
                    var gd = container.querySelector('.js-plotly-plot');
                    if (!gd || !gd.layout) return;
                    
                    var currentShapes = gd.layout.shapes || [];
                    var orangeShape = null;
                    
                    for (var i = 0; i < currentShapes.length; i++) {
                        if (currentShapes[i].name === 'timestamp_id') {
                            orangeShape = currentShapes[i];
                            break;
                        }
                    }
                    if (!orangeShape && currentShapes.length > 0) {
                        orangeShape = currentShapes[0];
                    }
                    
                    var newShapes = [];
                    var newAnnotations = [];
                    if (orangeShape) {
                        if (video_ts !== null) {
                            orangeShape.x0 = video_ts;
                            orangeShape.x1 = video_ts;
                        }
                        newShapes.push(orangeShape);
                    }
                    
                    for (var i = 0; i < df.length; i++) {
                        var row = df[i];
                        var shapeName = row.left_label + '__' + row.change_point_name + '__' + row.change_point_time + '__' + (row.sensor_ref || '');
                        
                        newShapes.push({
                            type: 'line',
                            editable: true,
                            x0: row.timestamp,
                            x1: row.timestamp,
                            y0: 0,
                            y1: 1,
                            yref: 'paper',
                            line: {color: '#5d7f4c', width: 2, dash: 'dash'},
                            name: shapeName
                        });
                        
                        if (!isBrush) {
                            newAnnotations.push({
                                x: row.timestamp,
                                y: 0.5,
                                xref: 'x',
                                yref: 'paper',
                                text: shapeName,
                                showarrow: false,
                                xshift: 5,
                                xanchor: 'left',
                                font: {size: 10, color: '#5d7f4c'},
                                textangle: -90
                            });
                        }
                    }
                    Plotly.relayout(gd, {'shapes': newShapes, 'annotations': newAnnotations});
                }
                
                updateGraphShapes('line-plot_brush', true);
                updateGraphShapes('line-plot_zoom', false);
                
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }
            """,
            [Output('line-plot_brush', 'id', allow_duplicate=True),
             Output('line-plot_zoom', 'id', allow_duplicate=True)],
            Input('stored_data_checkpoint', 'data'),
            State('stored_min_max_data', 'data'),
            State('stored_timestamp', 'data'),
            prevent_initial_call=True
        )
            

            