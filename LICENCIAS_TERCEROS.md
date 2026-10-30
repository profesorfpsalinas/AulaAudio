# Licencias de terceros y derechos de la música

## Componentes incluidos en AulaAudio

| Componente | Versión | Licencia | Uso |
|---|---|---|---|
| Python | 3.12 | PSF License | Lenguaje y biblioteca estándar (incluye SQLite, dominio público) |
| PySide6 / Qt for Python (incl. shiboken6, Qt 6) | 6.11.2 | LGPL-3.0 (o GPL-2.0/3.0) | Interfaz gráfica y reproducción de audio (QtMultimedia) |
| FFmpeg (incluido en QtMultimedia) | 7.x (avcodec-61) | LGPL-2.1 o posterior | Decodificación de MP3, OGG, FLAC, AAC… |
| tzdata | 2026.5 | Apache-2.0 | Datos de zonas horarias y cambios de hora |
| PyInstaller (solo para construir) | 6.22.3 | GPL-2.0+ con excepción de distribución | Empaquetado; la excepción permite distribuir el programa resultante |
| pytest, pytest-qt (solo desarrollo) | 9.1.1 / 4.5.0 | MIT | Pruebas automatizadas; no se distribuyen |
| Inno Setup (solo para construir) | 6.x | Licencia propia de Inno Setup (gratuita) | Instalador de Windows |

**Cumplimiento de la LGPL.** AulaAudio enlaza Qt y FFmpeg de forma dinámica (bibliotecas `.dll` /
`.so` separadas en la carpeta del programa), por lo que el usuario puede sustituirlas por otras
versiones compatibles. El código fuente de Qt está disponible en https://download.qt.io y el de
PySide6 en https://code.qt.io/cgit/pyside/pyside-setup.git. El código fuente de AulaAudio se
entrega completo junto con el programa.

Los sonidos de ejemplo y el sonido de prueba los genera el propio programa por síntesis; no
proceden de ninguna obra protegida.

## Derechos de reproducción pública de la música

AulaAudio **no** incluye música ni concede ningún derecho sobre ella. Reproducir música en un
centro educativo (pasillos, patio, entradas y salidas) puede considerarse **comunicación pública**.
El centro es responsable de:

- Disponer de las licencias necesarias para la música que utilice (en España, las gestionan
  entidades como SGAE y AGEDI/AIE; consulte si su administración educativa tiene un convenio), o
- Utilizar música libre de derechos o con licencias que permitan la comunicación pública
  (por ejemplo, determinadas obras con licencia Creative Commons o de dominio público).

Conserve la documentación de las licencias de la música junto con la del equipo.
