FROM python:3.12-alpine
WORKDIR /app
COPY server.py ./
COPY index.html admin.html login.html privacy.html app.js admin.js login.js admin.css styles.css favicon.svg reviews.json ./static/
RUN mkdir /app/data && adduser -D -u 10001 app && chown -R app:app /app
USER app
ENV HOST=0.0.0.0 PORT=8080 DATA_DIR=/app/data PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "server.py"]
