# Model cards and limitations

All metrics refer to the **same repeatedly examined historical 70-file benchmark**. They are **not new experimental results** from this product build and are not guaranteed on unseen bearings.

| Model | Company | Method | Accuracy | BAD recall | GOOD specificity |
|---|---|---|---:|---:|---:|
| Pulse Vision 1 | NBC | Spectral CNN | 90.0% (27/30) | 96.0% (24/25) | 60.0% (3/5) |
| Pulse Core 3 | NBC | RBF SVM | 86.7% (26/30) | 96.0% (24/25) | 40.0% (2/5) |
| Pulse Core 3 | TIMKEN | CatBoost | 82.5% (33/40) | 84.4% (27/32) | 75.0% (6/8) |
| Pulse Legacy 1 | NBC | Logistic baseline | 73.3% | 72.0% | 80.0% |
| Pulse Legacy 1 | TIMKEN | CatBoost baseline | 62.5% | 56.3% | 87.5% |

**Model output:** GOOD or BAD according to score >=0.80. A high score should not be presented as a calibrated likelihood of defect. False-GOOD outcomes are safety-relevant. Human inspection remains mandatory.

Feature-based model evidence uses feature contributions or local sensitivity; CNN explanation currently displays dominant observed frequency peaks, not a post-hoc causal/SHAP attribution. Do not claim these peaks caused the prediction.

Initial seed files contain 700 CSVs. Training only uses those marked `train`/`val` in the frozen manifest, plus newly uploaded datasets. Holdout test files are reserved and a future, truly blinded dataset is still needed.
