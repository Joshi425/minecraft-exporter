FROM python:3.10-alpine

COPY requirements.txt minecraft_exporter.py /
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

ENTRYPOINT ["python","minecraft_exporter.py"]
