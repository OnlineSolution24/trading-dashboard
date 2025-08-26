import os
import sys

# Füge das Root-Verzeichnis zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importiere die Original-App
from web_dashboard import app

# Vercel handler
def handler(request):
    return app(request.environ, lambda status, headers: None)

# Für lokale Entwicklung
if __name__ == '__main__':
    app.run(debug=True)
