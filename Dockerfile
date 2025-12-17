FROM python:3.12-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY standings.py .

# Create output directory for CSV and HTML files
RUN mkdir -p /app/output

# Run the script and save output
CMD ["python", "standings.py"]
