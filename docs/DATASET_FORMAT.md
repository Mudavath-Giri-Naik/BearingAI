# Upload format for new data

Create a ZIP like:

```text
new-nbc-batch.zip
  GOOD/
    NBC_874005_SIG1.csv
    NBC_874006_SIG1.csv
  BAD/
    NBC_874007_SIG1.csv
    NBC_874008_SIG1.csv
```

Each CSV must use the same 450-point increasing-frequency format as the seed dataset. The archive must contain at least one GOOD and one BAD signal. Metadata and IDs in names are **used only for grouping, not as model input features**. Label validity is the responsibility of the team.

Prefer explicit bearing IDs; new IDs must not match the protected test bearings. The backend rejects byte-identical seed CSVs. For rigorous evaluation, add an operator-reviewed manifest with IDs, acquisition time, test machine, equipment setup and ground truth evidence before the production release.

Do not label arbitrary future out-of-distribution measurements as GOOD merely because the model predicts GOOD.
