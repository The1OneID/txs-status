FROM python:3.12-alpine3.18
MAINTAINER TheOneID

ENV PYTHONUNBUFFERED 1

COPY ./requirements.txt requirements.txt
# install dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN mkdir /app
WORKDIR /app
COPY . /app

RUN adduser -D user
USER user
CMD python transactions_fetcher.py