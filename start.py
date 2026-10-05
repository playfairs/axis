import os
import shutil
import sys
from pathlib import Path
from subprocess import run

PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def main() -> int:
    uv = shutil.which("uv")
    if uv is None:
        print("The `uv` executable is required to install Axis dependencies.")
        return 1

    python = shutil.which("python3")
    if python is None:
        print("A `python3` executable is required to create the Axis environment.")
        return 1

    run(
        [uv, "venv", "--python", python, "--clear", ".venv"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(VENV_PYTHON),
            "--upgrade",
            "-r",
            "requirements.txt",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )
    os.execv(VENV_PYTHON, [str(VENV_PYTHON), "-m", "bot.main"])
    os.execv(VENV_PYTHON, [str(VENV_PYTHON), "-m", "bot.main"])


if __name__ == "__main__":
    sys.exit(main())
