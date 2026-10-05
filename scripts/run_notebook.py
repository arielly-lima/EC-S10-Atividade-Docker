"""Executa o notebook com o Python ativo e salva suas saidas no repositorio."""

import argparse
import os
import tempfile
from pathlib import Path

import nbformat
from ipykernel.kernelspec import write_kernel_spec
from nbclient import NotebookClient


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", default="notebooks/training.ipynb")
    args = parser.parse_args()
    notebook_path = root / args.notebook
    notebook = nbformat.read(notebook_path, as_version=4)
    # Kernel temporario: usa o venv sem registrar instalacoes na conta do usuario.
    with tempfile.TemporaryDirectory(prefix="btc-notebook-") as temp:
        kernel_path = Path(temp) / "kernels" / "btc-training"
        write_kernel_spec(path=str(kernel_path), overrides={"display_name": "Bitcoin training"})
        previous = {key: os.environ.get(key) for key in ["JUPYTER_PATH", "IPYTHONDIR", "JUPYTER_RUNTIME_DIR"]}
        os.environ["JUPYTER_PATH"] = temp + (os.pathsep + previous["JUPYTER_PATH"] if previous["JUPYTER_PATH"] else "")
        os.environ["IPYTHONDIR"] = str(Path(temp) / "ipython")
        os.environ["JUPYTER_RUNTIME_DIR"] = str(Path(temp) / "runtime")
        try:
            client = NotebookClient(
                notebook,
                timeout=180,
                kernel_name="btc-training",
                resources={"metadata": {"path": str(root)}},
            )
            client.execute()
            nbformat.write(notebook, notebook_path)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    print(f"Notebook executado e salvo: {notebook_path.relative_to(root)}")


if __name__ == "__main__":
    main()
