{ pkgs ? import <nixpkgs> { } }:

with pkgs;

mkShell {
  buildInputs = [
    python311
    python311Packages.poetry
    fish
    git
  ];
  shellHook = ''
    # # Tells pip to put packages into $PIP_PREFIX instead of the usual locations.
    # # See https://pip.pypa.io/en/stable/user_guide/#environment-variables.
    # export PIP_PREFIX=$(pwd)/_build/pip_packages
    # export PYTHONPATH="$PIP_PREFIX/${pkgs.python311.sitePackages}:$PYTHONPATH"
    # export PATH="$PIP_PREFIX/bin:$PATH"
    # unset SOURCE_DATE_EPOCH
    # pip install -r requirements.txt
    poetry install
    SHELL=fish exec poetry shell
  '';
}
