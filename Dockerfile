FROM python:3.12-slim
WORKDIR /app
RUN useradd --system --uid 1001 aplicacion
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY proveedor_simulado ./proveedor_simulado
USER aplicacion
EXPOSE 8201 8202
CMD ["uvicorn", "--factory", "app.main:crear_app", "--host", "0.0.0.0", "--port", "8201"]
