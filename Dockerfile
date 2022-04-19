FROM python:3.9

WORKDIR /usr/src/app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

COPY run.sh .

RUN chmod +x ./run.sh

CMD ["./run.sh"]
