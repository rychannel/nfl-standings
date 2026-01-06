FROM python:3.12-slim

WORKDIR /app

# Build metadata (optional): pass BUILD_GIT_SHA at build time to label image
ARG BUILD_GIT_SHA
LABEL org.opencontainers.image.revision=$BUILD_GIT_SHA

# Copy requirements and install dependencies

# Copy requirements first and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire repository into the image so builds always include updated files
COPY . .

# Create output directory for CSV and HTML files
RUN mkdir -p /app/output

# Run the script and save output
CMD ["python", "standings.py"]
