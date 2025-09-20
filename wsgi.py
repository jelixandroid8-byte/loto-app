from app import app
from flask import send_from_directory

@app.route('/.well-known/assetlinks.json')
def assetlinks():
    # Serve the Digital Asset Links file from the static folder so hosting platforms
    # that import wsgi.py as the entrypoint will still expose the file at
    # https://<your-domain>/.well-known/assetlinks.json
    return send_from_directory('static/.well-known', 'assetlinks.json')

if __name__ == "__main__":
    app.run()
