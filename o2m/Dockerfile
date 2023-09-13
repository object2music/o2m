FROM python:3.10-alpine 

WORKDIR /app

COPY ./ /app/

RUN pip install -r requirements.txt

RUN chmod +x ./entrypoint.sh
RUN chmod +x ./create_conf_files.sh

ENTRYPOINT [ "sh", "./entrypoint.sh" ]