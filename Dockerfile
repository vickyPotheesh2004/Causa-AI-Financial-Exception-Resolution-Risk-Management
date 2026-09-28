FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src CAUSE_AI_ENV=demo CAUSE_AI_DEMO=true HOST=127.0.0.1 PORT=8000
WORKDIR /app
RUN addgroup --system causeai && adduser --system --ingroup causeai causeai
COPY src ./src
COPY run.ps1 README.md ./
RUN mkdir -p /app/data && chown -R causeai:causeai /app
USER causeai
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "from urllib.request import urlopen; assert urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200"
CMD ["python", "-m", "cause_ai"]
