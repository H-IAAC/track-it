import dash
from dash import dcc, html, Input, Output, State,callback_context,no_update
import plotly.graph_objs as go
import pandas as pd
import dash_player
import os
import flask

# Controls class for the control menu
class ControlsChekpoint(html.Div):
    def __init__(self,config):
        activities=config.get('activities', [])
        #change_points_name=df_protocol['change_point_name'].unique()
        change_points_time= ['timestamp_server', 'timestamp_local']
        super().__init__([
            html.Div([
                html.Div([
                    html.Label('Left label:', style={'marginRight': '2px'}),
                    dcc.Dropdown(
                        id='left-label',
                        options=[{'label': activity, 'value': activity} for activity in activities],
                        clearable=False,
                    ),
                ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginRight': '2%'}),
                html.Div([
                    html.Label('Change point name:', style={'marginRight': '2px'}),
                    dcc.Dropdown(
                        id='change-point-name',
                        options=[],
                        clearable=False,
                    ),
                    dcc.Input(id='change-point-time', type='hidden', value='timestamp_local')
                ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top'}),
            ], style={'width': '70%', 'display': 'inline-block'}),
            html.Div([
                # DELETE button
                html.Button('DELETE', id='btn-delete', n_clicks=0, disabled=True,
                            className='hx-btn hx-btn--danger', style={'marginRight': '8px', 'marginTop': '22px'}),
                # SAVE button
                html.Button('ADD', id='btn-add', n_clicks=0, disabled=True,
                            className='hx-btn hx-btn--primary', style={'marginTop': '22px'}),
                #html.Button('UPDATE', id='btn-update', n_clicks=0)
            ], style={'width': '30%', 'display': 'inline-block', 'verticalAlign': 'top'}),
            dcc.ConfirmDialog(
                id='confirm-save',
                message='Do you really want to save the data?',
            ),
        ], style={'width': '100%'})
