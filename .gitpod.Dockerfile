FROM axonasif/workspace-python:debug2

RUN pyenv install 3.11 \
    && pyenv global 3.11

# Install gh CLI
RUN cd /tmp \
    && curl -L "https://github.com/cli/cli/releases/download/v2.32.0/gh_2.32.0_linux_amd64.tar.gz" -o gh.tar.gz \
    && tar -xpf gh.tar.gz && sudo mv gh_*linux_amd64/bin/gh /usr/bin/gh
