# Platform documentation

The permanent reference for how the UAD 3.6 Form Filler works. Each page says
where the behaviour lives in the code and which specification governs it.
When the code and a page disagree, the code and the specification win; fix the
page in the same commit.

| Page | Covers |
|---|---|
| [architecture.md](architecture.md) | One canonical document, the pipeline, modules, request flow |
| [data-model.md](data-model.md) | The case as a MISMO document, the field registry, UAD/MISMO mapping, entry formats |
| [rules-and-validation.md](rules-and-validation.md) | Display rules, schema, the 728 H-1 rules, Review Master, sign-off gate |
| [report-and-pdf.md](report-and-pdf.md) | The form from C-1, Appendix E styling, layout, pagination, fonts, PDF |
| [comps-images-maps.md](comps-images-maps.md) | Comparable grids and adjustments, photographs and exhibits, maps, market graphs |
| [import-export.md](import-export.md) | Import of XML / ZIP bundles, MISMO XML, portable XML, the UCDP delivery ZIP, case bundles |
| [persistence-and-deployment.md](persistence-and-deployment.md) | Case storage, the shared durable store, Vercel, Docker, the passcode, the API |
| [testing.md](testing.md) | The harness, the test suites, how to validate a validator |
| [gse-vendor-recognition.md](gse-vendor-recognition.md) | What GSE recognition requires, what is inference, and what this software must not claim |

Also read: `AI_HANDOVER.md` (current position), `knowledge/` (findings and the
error catalog), `DEPLOY_VERCEL.md`, `DEPLOY_DOCKER.md`.
