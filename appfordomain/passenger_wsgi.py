import os
import sys
# Añade el directorio de la aplicación a la ruta de Python
sys.path.insert(0, os.path.dirname(__file__))
# Importa la instancia de la aplicación
from app import app as application
