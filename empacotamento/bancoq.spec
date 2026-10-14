# -*- mode: python ; coding: utf-8 -*-
# Especificação do PyInstaller para o Banco de Questões (pasta portátil, "onedir").
# Uso: pyinstaller --noconfirm empacotamento/bancoq.spec
import sys
from pathlib import Path

raiz = Path(SPECPATH).resolve().parent
windows = sys.platform.startswith("win")

# Módulos do Qt que o app não usa (diminui o tamanho). Os que o QtWebEngine
# precisa (QtQml, QtQuick, QtPositioning, QtWebChannel, QtPdf…) continuam.
excluir_qt = [
    "Qt3DAnimation", "Qt3DCore", "Qt3DExtras", "Qt3DInput", "Qt3DLogic", "Qt3DRender", "QtBluetooth",
    "QtCharts", "QtConcurrent", "QtDataVisualization", "QtDesigner", "QtGraphs", "QtHelp", "QtHttpServer",
    "QtLocation", "QtMultimedia", "QtMultimediaWidgets", "QtNfc", "QtQuick3D", "QtRemoteObjects",
    "QtScxml", "QtSensors", "QtSerialBus", "QtSerialPort", "QtSpatialAudio", "QtSql", "QtStateMachine",
    "QtTest", "QtTextToSpeech", "QtUiTools", "QtWebSockets", "QtWebView", "QtAxContainer",
    "QtCanvasPainter", "QtGraphsWidgets",
]

a = Analysis(
    [str(raiz / "executar.py")],
    pathex=[str(raiz)],
    binaries=[],
    datas=[(str(raiz / "bancoq" / "recursos"), "bancoq/recursos")],
    hiddenimports=[
        "bancoq.nucleo.importador.exam",
        "bancoq.nucleo.importador.enumerate",
        "bancoq.nucleo.importador.titulos",
        "bancoq.nucleo.importador.manual",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtSvg",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pytest", "pydoc_data", "test"] + [f"PySide6.{m}" for m in excluir_qt],
    noarchive=False,
)


# ---- poda do que o Qt arrasta e o app não usa --------------------------------------------
import re as _re

_LIBS_FORA = _re.compile(
    r"Qt6(3D|Charts|DataVisualization|Graphs|Quick3D|Multimedia|SpatialAudio|Labs|Location|Sensors|"
    r"Bluetooth|Nfc|SerialPort|SerialBus|RemoteObjects|Scxml|StateMachine|TextToSpeech|VirtualKeyboard|"
    r"WebView|Test|QuickTest|Designer|Help|Sql|QuickControls2|QuickTemplates2|QuickDialogs2|QuickLayouts|"
    r"QuickShapes|QuickParticles|QuickTimeline|QuickEffects|QuickVectorImage|ShaderTools|WebEngineQuick|"
    r"HttpServer|NetworkAuth|PdfQuick|PdfWidgets|CanvasPainter|Grpc|Protobuf|Quick3D)"
)
_IDIOMAS_QT = ("pt_BR", "pt_PT")
_LOCALES_WEB = ("pt-BR.pak", "pt-PT.pak", "en-US.pak")


def _manter(entrada) -> bool:
    destino = entrada[0].replace("\\", "/")
    nome = destino.rsplit("/", 1)[-1]
    # plugins QML (Linux: PySide6/Qt/qml/…, Windows: PySide6/qml/…); o app só usa widgets
    if _re.search(r"(^|/)qml/", destino) or "/qmltooling/" in destino:
        return False
    if _LIBS_FORA.search(nome):
        return False
    # plugins/bibliotecas que dependem do que foi retirado (e que o app não usa)
    if any(x in nome for x in ("virtualkeyboard", "position_nmea", "QmlLocalStorage", "WaylandCompositor")):
        return False
    if destino.endswith("qtwebengine_devtools_resources.pak"):
        return False
    if "qtwebengine_locales/" in destino or "/locales/" in destino and nome.endswith(".pak"):
        return nome in _LOCALES_WEB
    if "/translations/" in destino and nome.endswith(".qm"):
        return any(nome.endswith(f"_{i}.qm") for i in _IDIOMAS_QT)
    return True


a.binaries = [e for e in a.binaries if _manter(e)]
a.datas = [e for e in a.datas if _manter(e)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BancoQuestoes",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(raiz / "bancoq" / "recursos" / ("icone.ico" if windows else "icone.png")),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="BancoQuestoes",
)
