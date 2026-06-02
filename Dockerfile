# Multi-stage build: install Node deps, build frontend, then assemble final image.
FROM python:3.11-slim AS base

# Install Node.js 20 (alongside Python) so we can run both in one container
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached unless requirements.txt changes)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Install Node dependencies (cached unless package files change)
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

# Copy the rest of the application code
COPY . .

# Build the Next.js frontend
RUN cd frontend && npm run build

# Ensure start.sh is executable
RUN chmod +x start.sh

# Railway sets PORT at runtime; expose for documentation
EXPOSE 3000

CMD ["bash", "start.sh"]
