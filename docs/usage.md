

\---



\## `docs/usage.md`



```markdown

\# Usage



\## Purpose



This repository provides a reference implementation of selective deployment for Azure Data Factory (ADF).



The example content is intentionally sanitized and simplified. The goal is to help users understand the workflow and adapt it to their own repository structure.



\---



\## Repository Layout



.

├── README.md

├── LICENSE

├── .gitignore

├── docs/

│   ├── architecture.md

│   └── usage.md

├── scripts/

│   └── selective\_deploy.py

├── adf-sample/

│   ├── pipeline/

│   ├── dataset/

│   ├── linkedService/

│   └── trigger/

├── config/

│   └── config.sample.json

├── examples/

│   └── sample-output/

└── .github/

&#x20;   └── workflows/

&#x20;       ├── build-and-deploy-adf-subset.yml

&#x20;       └── adf-validate-develop-pr.yml



\### Key folders



\- `scripts/`  

&#x20; Contains the Python utility used to generate the selective deployment subset.



\- `adf-sample/`  

&#x20; Contains sanitized sample ADF artifacts used to demonstrate the dependency model.



\- `config/`  

&#x20; Contains sample configuration files. Users should create environment-specific copies locally.



\- `docs/`  

&#x20; Contains architecture and usage documentation.



\- `examples/`  

&#x20; Contains sample input/output structures to help understand expected results.



\- `.github/workflows/`  

&#x20; Contains CI/CD workflows used to:

&#x20; - build selective deployment subsets

&#x20; - validate artifacts

&#x20; - deploy curated ADF resources



&#x20; These workflows demonstrate how selective deployment can be integrated into automated pipelines.

