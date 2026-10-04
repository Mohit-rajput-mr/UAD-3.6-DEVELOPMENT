# Running the platform in Docker (server-side layout and PDF)

On Vercel there is no browser, so the report is laid out in the user's browser
and `report.pdf` answers 503 (see `DEPLOY_VERCEL.md`). The Docker image carries
Chromium for the Playwright version the engine pins, so **the server lays out
the report and prints the PDF itself**.

```bash
docker build -t uad36 .
docker run -p 8765:8765 -v uad36-cases:/data uad36
# open http://localhost:8765 and sign in with the workspace passcode
```

- **Cases** live in `/data` (`URAR_WORK`); mount a volume so they survive a
  restart. To share cases with the Vercel deployment, pass the same store:
  `-e BLOB_READ_WRITE_TOKEN=...` (Vercel Blob) or `-e URAR_DURABLE_DIR=/data/shared`.
- **Passcode**: verified against the PBKDF2 verifier in
  `engine/app/access.json`, which is baked into the image. The passcode itself
  is in no file and is never printed.
- **Port**: `URAR_PORT` (default 8765). `/healthz` is open and drives the
  container `HEALTHCHECK`.
- **Behind a TLS-inspecting proxy** (corporate network, agent sandbox), give
  the build the proxy's CA for the pip step only. It is a BuildKit secret, so
  it never lands in an image layer:

  ```bash
  docker build --network host --build-arg HTTPS_PROXY=$HTTPS_PROXY \
      --secret id=ca,src=/path/to/proxy-ca.crt -t uad36 .
  ```

## Verified (2026-10-04)

The image was built from this repository and run on port 8766. Results:

- `/healthz` returned 200.
- `POST /access` with the passcode returned 303.
- Creating a case from the `sf1_appraisal_v1_4` template worked.
- `GET /api/cases/{id}/report.pdf` returned 200 `application/pdf`: 156,991 bytes, 6 pages, in 8.0 s, on the first, cold render.

To repeat the check: sign in with `POST /access` (form field `code`), `POST /api/cases`, then `GET /api/cases/{id}/report.pdf`.
