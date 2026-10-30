# Guía de instalación

AulaAudio **no necesita permisos de administrador** ni conexión a Internet una vez instalado.

## Requisitos

- Windows 10/11 de 64 bits, o Linux de escritorio x86_64 (Ubuntu 22.04+, Debian 12+, Linux Mint 21+
  o similar) con PulseAudio o PipeWire.
- 300 MB libres. Salida de audio (minijack, tarjeta USB o HDMI) conectada al equipo de sonido.

## Windows — con el instalador (recomendado)

1. Ejecute `AulaAudio-1.0.0-Windows-instalador.exe`.
   Si Windows SmartScreen muestra «Windows protegió su PC», pulse *Más información → Ejecutar de
   todas formas* (el instalador no está firmado digitalmente).
2. Siga el asistente. Se instala en `%LOCALAPPDATA%\Programs\AulaAudio` con accesos en el menú Inicio.
3. Al terminar, AulaAudio se abre y muestra la bienvenida.

Versión portable (sin instalar): copie la carpeta `dist\AulaAudio` y ejecute `AulaAudio.exe`.

## Linux — paquete .tar.gz

```bash
tar xzf AulaAudio-1.0.0-Linux-x86_64.tar.gz
cd AulaAudio-1.0.0-Linux-x86_64
./instalar.sh
```

Se instala en `~/.local/opt/aulaaudio` y aparece en el menú de aplicaciones. Si al abrir aparece un
error sobre `xcb`, instale `libxcb-cursor0` (`sudo apt install libxcb-cursor0`, única vez).
En GNOME, para ver el icono en la bandeja instale la extensión «AppIndicator and KStatusNotifierItem».

## Ejecutar desde el código fuente (desarrollo)

```bash
cd AulaAudio
python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate         # Linux
pip install -r requirements-dev.txt
python -m aulaaudio               # abrir la aplicación
python -m pytest                  # pruebas (no emiten sonido)
```

Opciones útiles:

| Orden | Efecto |
|---|---|
| `python -m aulaaudio --datos C:\pruebas\aa` | Usa otra carpeta de datos (no toca los del centro) |
| `python -m aulaaudio --simular 2026-11-02 --desde 08:00 --horas 8` | Muestra en texto lo que sonaría |
| `python -m aulaaudio --modo-simulacion "2026-11-02 08:25" --velocidad 60 --datos C:\pruebas\aa` | Interfaz con reloj virtual 60 veces más rápido |
| `python -m aulaaudio --silencio` | Sin sonido real (salida simulada) |
| `python -m aulaaudio --diagnostico` | Prueba silenciosa del audio; informe en `registros\diagnostico.txt` |
| `python -m aulaaudio --minimizado` | Arranca en la bandeja (lo usa el inicio automático) |

## Construir los instaladores

Un ejecutable construido en Windows **no** funciona en Linux ni al revés: cada paquete se construye
en su sistema.

**Windows** (PowerShell, en la raíz del proyecto):

```powershell
winget install JRSoftware.InnoSetup --scope user     # una sola vez, sin administrador
powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1
```

El script ejecuta las pruebas (si fallan, no construye), genera el icono, construye con PyInstaller
(`dist\AulaAudio`), comprueba el ejecutable con `--diagnostico` y compila el instalador en
`dist\instalador\AulaAudio-1.0.0-Windows-instalador.exe`.

**Linux** (en una máquina Linux x86_64):

```bash
sudo apt install python3-venv libxcb-cursor0 libpulse0 libegl1   # Debian/Ubuntu
bash packaging/linux/build_linux.sh
```

Resultado: `dist-linux/AulaAudio-1.0.0-Linux-x86_64.tar.gz`. Constrúyalo en la versión de Linux
más antigua que vaya a usar (el ejecutable depende de la versión de glibc del sistema donde se crea).
