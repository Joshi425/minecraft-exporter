FROM python:3.8.12-alpine3.14

COPY requirements.txt minecraft_exporter.py /
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

ENTRYPOINT ["python","minecraft_exporter.py"]
