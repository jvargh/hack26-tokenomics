# Vendored wheels

`openai` and `azure-identity` (plus their transitive dependencies) are vendored
here as `.whl` files so the Docker build can install them **offline**. The
Docker build network in this environment cannot complete a TLS handshake with
`files.pythonhosted.org`, so `pip install openai azure-identity` fails inside
`docker build`. Downloading the wheels on the host (which has working network
access) and installing them with `pip install --no-index --find-links=...`
avoids that.

Regenerate this folder after bumping the pinned versions:

```powershell
Remove-Item -Recurse -Force tokenos\vendor-wheels\*.whl
python -m pip download --dest tokenos\vendor-wheels openai azure-identity `
  --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 `
  --python-version 3.13 --implementation cp --abi cp313 --only-binary=:all:
```

Keep the `README.md` file; only the `*.whl` files need to change.
