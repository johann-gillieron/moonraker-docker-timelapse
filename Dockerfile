FROM python:3.14-slim
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Install the application dependencies
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy in the source code
COPY app/ .

#CMD ["python", "app.py"]
CMD ["gunicorn", "--bind", "0.0.0.0:80", "app:app"]