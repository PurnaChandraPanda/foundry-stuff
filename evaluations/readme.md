## create/ activate conda env for local test

```
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

conda create -n v2foundry python=3.13 -y
```

```
```

```
pip install azure-ai-projects
pip install python-dotenv
```

---

## remove conda env

```
conda deactivate
conda remove --name v2foundry --all -y
```

├── python sample_eval_catalog.py
├── python run_custom_evaluator_eval.py


├── sample_eval_catalog_code_based_evaluators.py
└── sample_evaluations_graders.py