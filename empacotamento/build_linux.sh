#!/usr/bin/env bash
# Gera o executável Linux do Banco de Questões:
#   saida/BancoQuestoes-linux-x86_64.tar.gz   (pasta portátil)
#   saida/BancoQuestoes-x86_64.AppImage       (se o appimagetool estiver disponível)
#
# Uso:  ./empacotamento/build_linux.sh
# Variáveis opcionais:
#   PYTHON=python3.12   Python usado para criar o ambiente de build
#   VENV=caminho        reaproveita um ambiente virtual já pronto
#   SEM_TESTES=1        não roda o pytest antes do build
#   SEM_APPIMAGE=1      não gera a AppImage
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
SAIDA="$RAIZ/empacotamento/saida"
cd "$RAIZ"

PYTHON="${PYTHON:-python3}"
VENV="${VENV:-$RAIZ/.venv-build}"
if [ ! -x "$VENV/bin/python" ]; then
  echo ">> Criando ambiente virtual em $VENV"
  "$PYTHON" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements-dev.txt

if [ -z "${SEM_TESTES:-}" ]; then
  echo ">> Rodando os testes"
  python -m pytest -q
fi

echo ">> PyInstaller"
rm -rf "$SAIDA/dist" "$SAIDA/build"
pyinstaller --noconfirm --clean --distpath "$SAIDA/dist" --workpath "$SAIDA/build" empacotamento/bancoq.spec

VERSAO="$(python -c 'import bancoq; print(bancoq.__version__)')"
echo ">> Pasta portátil"
tar -czf "$SAIDA/BancoQuestoes-$VERSAO-linux-x86_64.tar.gz" -C "$SAIDA/dist" BancoQuestoes
echo "   $SAIDA/BancoQuestoes-$VERSAO-linux-x86_64.tar.gz"

if [ -n "${SEM_APPIMAGE:-}" ]; then
  exit 0
fi

echo ">> AppImage"
FERRAMENTAS="$RAIZ/empacotamento/ferramentas"
APPIMAGETOOL="$(command -v appimagetool || true)"
if [ -z "$APPIMAGETOOL" ]; then
  APPIMAGETOOL="$FERRAMENTAS/appimagetool-x86_64.AppImage"
  if [ ! -x "$APPIMAGETOOL" ]; then
    mkdir -p "$FERRAMENTAS"
    echo "   baixando o appimagetool (só é usado para gerar a AppImage)…"
    if ! curl -fL -o "$APPIMAGETOOL" \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage; then
      echo "   não foi possível baixar o appimagetool; a pasta portátil já foi gerada."
      exit 0
    fi
    chmod +x "$APPIMAGETOOL"
  fi
fi

APPDIR="$SAIDA/BancoQuestoes.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib"
cp -a "$SAIDA/dist/BancoQuestoes" "$APPDIR/usr/lib/BancoQuestoes"
cp empacotamento/appimage/AppRun "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"
cp empacotamento/appimage/bancoquestoes.desktop "$APPDIR/bancoquestoes.desktop"
cp bancoq/recursos/icone.png "$APPDIR/bancoquestoes.png"
ln -sf bancoquestoes.png "$APPDIR/.DirIcon"

DESTINO="$SAIDA/BancoQuestoes-$VERSAO-x86_64.AppImage"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$DESTINO"
chmod +x "$DESTINO"
echo "   $DESTINO"
