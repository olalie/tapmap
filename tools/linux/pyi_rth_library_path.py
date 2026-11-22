# Restore the original library path for external processes.
import os

original_library_path = os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
if original_library_path is None:
    os.environ.pop("LD_LIBRARY_PATH", None)
else:
    os.environ["LD_LIBRARY_PATH"] = original_library_path
