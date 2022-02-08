FROM python:3.8-alpine

RUN adduser -D diagnosticator

RUN apk add --no-cache bash mariadb-dev mariadb-client python3-dev build-base libffi-dev openssl-dev sqlite


WORKDIR /home/diagnosticator

COPY requirements.txt requirements.txt
RUN python -m venv venv
RUN venv/bin/pip install -U pip
RUN venv/bin/pip install wheel
RUN venv/bin/pip install -r requirements.txt
RUN venv/bin/pip install gunicorn pymysql

RUN mkdir DB

COPY app app
COPY DB/OMIM DB/OMIM
COPY upload upload
COPY variant_dependencies variant_dependencies
COPY main.py config.py boot.sh ./
COPY convert_VCF_REDIS.py asilo_variant_functions.py cloud_bigtable_functions.py mongodb_functions.py redis_functions.py ./
COPY docker_functions.py ./
RUN chmod a+x boot.sh

ENV FLASK_APP main.py

RUN chown -R diagnosticator:diagnosticator ./
USER diagnosticator

EXPOSE 5000
ENTRYPOINT ["./boot.sh"]
