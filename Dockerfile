FROM python:3-slim
WORKDIR /app
COPY . /app
RUN pip3 install -r requirements.txt && apt update && apt install libimage-exiftool-perl -y
CMD ["python3", "main.py"]
