# UAD 3.6 Form Filler -- the full server, with Chromium, so the report is laid
# out and the PDF is printed on the server (on Vercel there is no browser and
# PDF answers 503; see DEPLOY_VERCEL.md).
#
#   docker build -t uad36 .
#   docker run -p 8765:8765 -v uad36-cases:/data uad36
#   open http://localhost:8765  (passcode: the one engine/app/access.json verifies)
#
# The base image carries Chromium for exactly the Playwright version the
# engine pins, so nothing is downloaded at start-up.
FROM mcr.microsoft.com/playwright/python:v1.56.0-noble

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    URAR_HOST=0.0.0.0 URAR_PORT=8765 URAR_WORK=/data

COPY requirements.txt .
# Behind a TLS-inspecting proxy, pass its CA for this step only (never baked
# into the image):  docker build --secret id=ca,src=/path/ca.crt ...
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install --no-cache-dir --break-system-packages -r requirements.txt uvicorn playwright==1.56.0

# what the server reads at run time: the engine, the GSE samples it starts
# reports from (XML and their pictures) and the subschema it validates against
COPY engine ./engine
COPY specs ./specs
COPY run_server.py ./

VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/healthz'%os.environ.get('URAR_PORT','8765'),timeout=4)"
CMD ["python", "engine/app/main.py"]
