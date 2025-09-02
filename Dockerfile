FROM python:3.12-slim

WORKDIR /app
COPY . /app

RUN python -m pip install --upgrade pip &&     pip install --no-cache-dir -r requirements.txt

EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
