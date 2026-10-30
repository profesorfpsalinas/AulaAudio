"""Lanzador de AulaAudio (doble clic en Windows sin consola; también lo usa el ejecutable empaquetado).

Al ejecutarse como script, su carpeta (la raíz del proyecto) queda en sys.path, por lo que
funciona desde cualquier directorio de trabajo, incluido el inicio automático del sistema.
"""
import sys

from aulaaudio.app import main

if __name__ == "__main__":
    sys.exit(main())
