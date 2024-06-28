FROM axonasif/workspace-python:debug2

RUN pyenv install 3.11 \
    && pyenv global 3.11

# Install gh CLI
RUN (curl -Ls --tlsv1.2 --proto "=https" --retry 3 https://cli.doppler.com/install.sh || wget -t 3 -qO- https://cli.doppler.com/install.sh) | sudo sh
