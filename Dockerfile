FROM python:3-bullseye

# Set the working directory
WORKDIR /app
COPY ./requirements.txt /app
COPY ./*.py /app
RUN pip install -r requirements.txt

CMD ["python", "-u", "/app/downloader.py"]
