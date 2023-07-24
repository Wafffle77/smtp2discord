FROM python:3.11

WORKDIR /usr/src/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY smtp2discord.py .

EXPOSE 25

CMD [ "python", "./smtp2discord.py" ]