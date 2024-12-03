FROM axonasif/workspace-python:debug2

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Install gh CLI
RUN (curl -Ls --tlsv1.2 --proto "=https" --retry 3 https://cli.doppler.com/install.sh || wget -t 3 -qO- https://cli.doppler.com/install.sh) | sudo sh
