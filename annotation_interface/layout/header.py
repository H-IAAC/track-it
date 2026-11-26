from dash import html
import dash_bootstrap_components as dbc


class Header:
    def __init__(self):
        self.layout = html.Header([
            html.A([
                html.Img(src="/assets/hiaac/hiaac-logo.svg", alt="H.IAAC", className="hx-logo"),
                html.Span(className="hx-sep"),
                html.Span([
                    html.Span("Track-It Labeler", className="hx-tool-title"),
                    html.Span("Activity Labeling", className="hx-tool-sub"),
                ], className="hx-tool"),
            ], href="/", className="hx-brand"),
            html.Span(className="hx-header-spacer"),
            html.Div([
                html.Div([
                    html.Span("Standalone Mode", className="hx-label ann-mode-label"),
                    dbc.Switch(
                        id="app-mode-toggle",
                        value=True,  # False = Standalone, True = Dataset Flow
                        className="custom-switch ann-switch"
                    ),
                    html.Span("Dataset Flow", className="hx-label ann-mode-label"),
                ], className="ann-mode"),
                html.Button("⚙", id="btn-open-label-settings", className="hx-icon-btn", title="Manage Activity Labels", style={'marginRight': '8px'}),
                html.Button("◐", className="hx-icon-btn", title="Toggle theme", **{"data-hx-theme-toggle": ""}),
            ], className="hx-header-actions"),

            # Settings Modal for Dynamic Label Management
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle("Manage Activity Labels"), close_button=True),
                dbc.ModalBody([
                    html.P("Create or delete activity labels for annotation.", style={'fontSize': '14px', 'color': 'var(--ink-muted)', 'marginBottom': '15px'}),
                    html.Div([
                        dbc.Input(
                            id="input-new-label",
                            placeholder="Type new label name (e.g. JUMPING)...",
                            type="text",
                            style={'flex': '1', 'marginRight': '10px'}
                        ),
                        html.Button("+ Add Label", id="btn-add-label", n_clicks=0, className="hx-btn hx-btn--primary"),
                    ], style={'display': 'flex', 'marginBottom': '20px'}),
                    html.Div([
                        html.Label("Current Activity Labels:", style={'fontWeight': 'bold', 'marginBottom': '8px', 'display': 'block'}),
                        html.Div(id="labels-list-container", style={
                            'maxHeight': '320px',
                            'overflowY': 'auto',
                            'border': '1px solid var(--line, #ddd)',
                            'borderRadius': '6px',
                            'padding': '8px'
                        }),
                    ]),
                ]),
                dbc.ModalFooter([
                    html.Button("Close", id="btn-close-label-settings", className="hx-btn", n_clicks=0)
                ]),
            ], id="modal-label-settings", is_open=False, size="lg"),
        ], className="hx-header ann-header")
