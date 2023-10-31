"""Monitor GPU usage."""

import glob
import os
import traceback

from ...tools import instrument_definition
from ..utils import Monitor, MonitorProc
from .common import NotAvailable


def find_monitors():
    """Look for device monitor implementation (AMD or ROCm)"""
    backends = {}
    base = __file__
    base_module = "voir.instruments.gpu"
    module_path = os.path.dirname(os.path.abspath(base))
    pattern = os.path.join(module_path, "[A-Za-z]*")

    for module_path in glob.glob(pattern, recursive=False):
        module_file = module_path.split(os.sep)[-1]

        if module_file in ("__init__.py", "common.py"):
            continue

        module_name = module_file.split(".py")[0]

        try:
            module = __import__(".".join([base_module, module_name]), fromlist=[""])
        except ImportError:
            print(traceback.format_exc())
            continue

        backends[module_name] = module

    return backends


BACKENDS = find_monitors()
DEVICESMI = None


def get_backends():
    global BACKENDS
    return BACKENDS.keys()


def _is_backend_available(backend):
    try:
        smi = backend.DeviceSMI()

        if len(smi.get_gpus_info()) > 0:
            return True

    except NotAvailable:
        return False


def deduce_backend():
    """List the GPU backend that is available on this machine.

    If multiple backends are available, raises an error.
    """
    suitable = []
    for k, backend in BACKENDS.items():
        if backend.is_installed() and _is_backend_available(backend):
            suitable.append(k)

    if len(suitable) > 1:
        options = ", ".join(get_backends())
        raise Exception(
            f"Milabench found multiple vendors ({suitable}) and does not "
            f"know which kind to use. Please set $MILABENCH_GPU_ARCH to one of {options}."
        )

    elif len(suitable) == 0:
        return "cpu"

    return suitable[0]


def select_backend(arch=None):
    global DEVICESMI

    if DEVICESMI is not None:
        if DEVICESMI.arch == arch:
            return DEVICESMI
        DEVICESMI.close()
        DEVICESMI = None

    if arch is None:
        arch = deduce_backend()

    backend = BACKENDS.get(arch)

    if backend is not None and backend.is_installed():
        DEVICESMI = backend.DeviceSMI()
    else:
        raise NotAvailable(f"{arch} is not installed")

    return DEVICESMI


def gpu_info(smi, visible=True):
    selection = None

    # Make sure to only show the visible devices
    if visible:
        selection = _visible_devices(smi)

    return {
        "arch": smi.arch,
        "gpus": smi.get_gpus_info(selection),
    }


def get_gpu_info(arch=None, visible=True):
    return gpu_info(select_backend(arch), visible)


def _visible_devices(smi):
    visible = smi.visible_devices

    if visible:
        ours = visible.split(",")
    else:
        ours = [str(x) for x in range(100)]

    return ours


def _monitor_fn():
    data = {
        gpu["device"]: {
            "memory": [
                gpu["memory"]["used"],
                gpu["memory"]["total"],
            ],
            "load": gpu["utilization"]["compute"],
            "temperature": gpu["temperature"],
            "power": gpu["power"]
        }
        for gpu in get_gpu_info()["gpus"].values()
    }
    return {"task": "main", "gpudata": data, "t": time.time()}


@instrument_definition
def gpu_monitor(ov, poll_interval=10, arch=None):
    """Monitor GPU utilization.

    Supports monitoring CUDA (NVIDIA) and ROCm (AMD) architectures.

    The following data is monitored:

    .. code-block:: javascript

        {
            "memory": [USED, TOTAL],  // In MB
            "load": LOAD,             // Utilization, from 0 to 1
            "temperature": TEMP,      // In celsius
            "power": POWER,
        }

    This data structure is added to the :meth:`~voir.overseer.Overseer.given` stream
    as follows:

    .. code-block:: python

        give(task="main", gpudata=DATA)

    Arguments:
        poll_interval: The polling interval, in seconds. Data will be produced
            every poll_interval seconds.
        arch: The GPU architecture to monitor. If None, the architecture will be
            deduced automatically.
    """
    yield ov.phases.load_script

    smi = select_backend(arch)

    def monitor():
        ov.give(task="main", gpudata=_monitor_fn())

    monitor_thread = Monitor(poll_interval, monitor)
    monitor_thread.start()
    try:
        yield ov.phases.run_script
    finally:
        monitor_thread.stop()
        monitor()


class GPUMonitor:
    def __init__(self, delay, fun) -> None:
        self.monitor = MonitorProc(delay, _monitor_fn, fun)

    def start(self):
        self.monitor.start()

    def stop(self):
        self.monitor.stop()
