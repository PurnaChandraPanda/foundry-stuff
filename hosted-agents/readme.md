- This hosted-agents is already a cloned repo of path [foundry-samples/samples/python/hosted-agents](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents).

- In every child sample folder, there's a `changes.md` file that explains code changes to follow.

## work with venv

```
cd hosted-agents
```

- in git bash for windows
```
python --version

# Required for Git Bash on Windows so special characters read won't break
export MSYS_NO_PATHCONV=1

python -m venv .haenv

# activate the venv
source .haenv/Scripts/activate

pip install -r requirement.txt
```

- delete venev

From root folder where `.haenv` is created, it needs to be cleaned up from same.

```bash
deactivate
rm -rf .haenv
```
