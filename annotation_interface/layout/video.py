import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import dash_player

class VideoPlayer(html.Div):
    
    def __init__(self, id_upload, id_output, *args, **kwargs):
        super().__init__([
            html.Details(open=True, children=[
                html.Summary("📂 Load Video", style={
                    'cursor': 'pointer',
                    'fontSize': '11px',
                    'userSelect': 'none',
                    'outline': 'none'
                }),
                html.Div([

                    
                    # Video upload
                    dcc.Upload(
                        id=id_upload,
                        children=html.Button('Upload Local Video', className='hx-btn hx-btn--block hx-btn--lg'),
                        style={'width': '100%'},
                        accept='video/*'
                    ),
                    dcc.Store(id='workflow-video-trigger')
                ], style={'width': '100%', 'padding': '10px', 'backgroundColor': 'transparent', 'marginBottom': '10px'})
            ], id='upload-container', style={
                'marginBottom': '10px', 
                'backgroundColor': 'transparent', 
                'border': 'none',
                'padding': '0'
            }),

            # Video player and "no video" message
            html.Div(id=id_output, style={'flexGrow': 1, 'position': 'relative', 'minHeight': 0}, children=[
                html.Div(id='no-video-message', children="Please upload a video.", style={'position': 'absolute', 'top': '50%', 'left': '50%', 'transform': 'translate(-50%, -50%)'}),
                html.Div(
                    dash_player.DashPlayer(
                        id='video-player',
                        url='',
                        playing=False
                    ), style={'display': 'none'}
                )
            ]),

            # Controls for Video playback
            html.Div(id='extra-video-controls', children=[
                html.Label("Speed:", style={'fontWeight': 'bold', 'marginRight': '10px'}),
                dcc.Dropdown(
                    id='playback-speed-dropdown',
                    options=[
                        {'label': '0.25x', 'value': 0.25},
                        {'label': '0.5x', 'value': 0.5},
                        {'label': '1.0x', 'value': 1.0},
                        {'label': '1.5x', 'value': 1.5},
                        {'label': '2.0x', 'value': 2.0}
                    ],
                    value=1.0,
                    clearable=False,
                    style={'width': '100px', 'marginRight': '15px'}
                ),
                
                html.Button('<< Frame', id='prev-frame-btn', n_clicks=0, className='hx-btn', style={'marginRight': '5px'}),
                html.Button('Frame >>', id='next-frame-btn', n_clicks=0, className='hx-btn', style={'marginRight': '15px'})
            ], style={'display': 'none', 'alignItems': 'center', 'marginTop': '10px', 'flexWrap': 'wrap'}),

            # Dummy elements to prevent callback errors since these were requested to be removed visually
            html.Div(id='controls-container', style={'display': 'none'}, children=[
                html.Div(id='zoom-container', style={'display': 'none'}, children=[
                    dcc.Checklist(id='zoom-loop', options=[], value=[])
                ]),
                html.Div(id='etiquetar-container', style={'display': 'none'}, children=[
                    html.Button(id='btn-etiquetar-video')
                ])
            ])
        ], *args, **kwargs)

        self.id_upload = id_upload
        self.id_output = id_output

    def register_callbacks(self, app):
        @app.callback(
            [Output(self.id_output, 'children'),
             Output('zoom-container', 'style'),
             Output('etiquetar-container', 'style'),
             Output('extra-video-controls', 'style')],
            Input(self.id_upload, 'contents'),
            Input('workflow-video-trigger', 'data')
        )
        def update_video(contents, workflow_video_path):
            ctx = dash.callback_context
            empty_state = (
                html.Div([
                    html.Div(id='no-video-message', children="Please upload a video.", style={'position': 'absolute', 'top': '50%', 'left': '50%', 'transform': 'translate(-50%, -50%)'}),
                    html.Div(dash_player.DashPlayer(id='video-player', url='', playing=False), style={'display': 'none'})
                ]),
                {'display': 'none'},
                {'display': 'none'},
                {'display': 'none'}
            )
            
            if not ctx.triggered:
                return empty_state
            
            trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
            video_url = None

            if trigger_id == 'workflow-video-trigger' and workflow_video_path:
                import os
                if os.path.exists(workflow_video_path):
                    # Dash app routes expect /serve_video/<absolute_path>
                    video_url = f"/serve_video{workflow_video_path}"
                    
            elif trigger_id == self.id_upload and contents is not None:
                video_url = contents

            if video_url:
                zoom_style = {'display': 'block'}
                etiquetar_style = {'display': 'block'}
                extra_controls_style = {'display': 'flex', 'alignItems': 'center', 'marginTop': '10px'}
                
                return (
                    html.Div([
                        dash_player.DashPlayer(
                            id='video-player',
                            url=video_url,
                            controls=True,
                            width='100%',
                            height='100%',
                            intervalCurrentTime=200,
                            style={'position': 'absolute', 'top': 0, 'left': 0, 'width': '100%', 'height': '100%', 'objectFit': 'contain'}
                        )
                    ], id='video-player-container', style={'position': 'absolute', 'top': 0, 'left': 0, 'width': '100%', 'height': '100%'}),
                    zoom_style,
                    etiquetar_style,
                    extra_controls_style
                )

            return empty_state

        @app.callback(
            Output('video-player', 'playbackRate'),
            Input('playback-speed-dropdown', 'value')
        )
        def change_playback_speed(speed):
            if speed is not None:
                return speed
            return 1.0

        @app.callback(
            Output('video-player', 'seekTo'),
            [Input('prev-frame-btn', 'n_clicks'),
             Input('next-frame-btn', 'n_clicks')
             ],
            [State('video-player', 'currentTime'),
             State('video-player', 'duration'), 
             State('video-player', 'url')]
        )
        def control_video_frames(prev_clicks, next_clicks, current_time, video_duration, video_url):
            ctx = dash.callback_context
            if not ctx.triggered or not video_url:
                return dash.no_update
            
            trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
            FRAME_DUR = 1.0 / 30.0
            
            if trigger_id == 'prev-frame-btn':
                if current_time is not None:
                    return max(0, current_time - FRAME_DUR)
            if trigger_id == 'next-frame-btn':
                if current_time is not None and video_duration is not None:
                    return min(video_duration, current_time + FRAME_DUR)
            
            return dash.no_update

        # CLIENTSIDE CALLBACK: Sync video to Plotly clicks or UI buttons instantly without hitting Python
        app.clientside_callback(
            """
            function(current_time) {
                if (current_time && ['plot_zoom', 'n_clicks_back', 'n_clicks_front', 'select_brush', 'timestamp_queue_auto_inc'].includes(current_time.type)) {
                    return current_time.timestamp;
                }
                return window.dash_clientside.no_update;
            }
            """,
            Output('video-player', 'seekTo', allow_duplicate=True),
            Input('stored_timestamp', 'data'),
            prevent_initial_call=True
        )

        app.clientside_callback(
            """
            function(currentTime, current_stored) {
                if (currentTime === undefined || currentTime === null) return window.dash_clientside.no_update;
                var stored_ts = (current_stored && current_stored.timestamp !== undefined) ? current_stored.timestamp : 0;
                // Reduced to 0.016 so the scrubber line moves more smoothly and quickly following the video (~60fps)
                if (Math.abs(currentTime - stored_ts) > 0.016) {
                    return {timestamp: currentTime, type: 'video_update'};
                }
                return window.dash_clientside.no_update;
            }
            """,
            Output('stored_timestamp', 'data', allow_duplicate=True),
            Input('video-player', 'currentTime'),
            State('stored_timestamp', 'data'),
            prevent_initial_call=True
        )
