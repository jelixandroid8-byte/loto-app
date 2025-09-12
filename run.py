
import os
from waitress import serve
from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Servidor de producción iniciado en http://0.0.0.0:{port}")
    serve(app, host='0.0.0.0', port=port)
