FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir 'aiohttp>=3.10,<4' 'zipstream-ng>=1.8,<2' 'Pillow>=11,<13'
COPY . /app/
EXPOSE 8787
CMD ["python", "-u", "/app/app.py"]
