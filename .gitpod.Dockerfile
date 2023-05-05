FROM axonasif/workspace-python:debug2

RUN pyenv install 3.11 \
    && pyenv global 3.11
