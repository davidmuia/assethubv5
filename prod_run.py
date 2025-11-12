from waitress import serve
from app import create_app

# This is the entry point for the production WSGI server.
if __name__ == "__main__":
    app = create_app()
    # Serve the app on a local-only port. IIS will handle public traffic.
    serve(app, host='0.0.0.0', port=9002)