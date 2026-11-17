# A clean Linux box for reproduction: no GPU, no API key, nothing from the host.
#   docker build -t op06-triage .
#   docker run --rm -p 8000:8000 op06-triage                        # serve
#   docker run --rm op06-triage scripts/reproduce.sh all             # tests, eval, hostile, bench
FROM python:3.12.10-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 WORKERS=2
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --chown=app:app . /app
USER app
RUN scripts/reproduce.sh setup
EXPOSE 8000
CMD ["scripts/reproduce.sh", "serve"]
