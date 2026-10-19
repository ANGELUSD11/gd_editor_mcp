# gd-editor-mcp in a Linux container.
#
# What works here: the test suite and the tools that do not touch the game (song listing and analysis, .gmd files).
# What does not: the live editor tools. They attach to GeometryDash.exe running natively on Windows, and a container
# cannot see the host's processes. Use a native install (see README.md) to build levels in the game.
#
#   docker build -t gd-editor-mcp .
#   docker run --rm gd-editor-mcp python tests/run.py
#   docker run --rm -i -v "%LOCALAPPDATA%\GeometryDash:/data/GeometryDash:ro" -e LOCALAPPDATA=/data gd-editor-mcp
#       (MCP server over stdio, with the game's downloaded songs mounted read-only)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Pinned dependencies first, so code changes do not reinstall them.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps .

COPY tests ./tests

RUN useradd --create-home gd
USER gd

CMD ["gd-editor-mcp", "serve"]
