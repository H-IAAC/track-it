from dash_app import DashApp

if __name__ == '__main__':
    # Initialize and run the Dash application
    app = DashApp(config_path='config.yaml')
    app.start()
