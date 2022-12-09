import sys
import traceback
from argparse import REMAINDER, ArgumentParser
from types import ModuleType

from giving import SourceProxy
from ptera import probing, select

from voir.forward import GiveToFile

from .phase import GivenPhaseRunner
from .utils import exec_node, split_script


class LogStream(SourceProxy):
    def __call__(self, data):
        self._push(data)


class ProbeInstrument:
    def __init__(self, selector):
        self.selector = selector
        self.probe = self.__state__ = probing(self.selector)

    def __call__(self, ov):
        yield ov.phases.load_script(priority=0)
        with self.probe:
            yield ov.phases.run_script(priority=0)


class Overseer(GivenPhaseRunner):
    def __init__(self, instruments, logfile=None):
        self.argparser = ArgumentParser()
        self.argparser.add_argument("SCRIPT")
        self.argparser.add_argument("ARGV", nargs=REMAINDER)
        super().__init__(
            phase_names=["init", "parse_args", "load_script", "run_script", "finalize"],
            args=(self,),
            kwargs={},
        )
        for instrument in instruments:
            self.require(instrument)
        self.logfile = logfile

    def on_overseer_error(self, e):
        self.log(
            {
                "#event": {
                    "type": "overseer_error",
                    "data": {"type": type(e).__name__, "message": str(e)},
                }
            }
        )
        print("=" * 80, file=sys.stderr)
        print(
            "voir: An error occurred in an overseer. Execution proceeds as normal.",
            file=sys.stderr,
        )
        print("=" * 80, file=sys.stderr)
        traceback.print_exception(type(e), e, e.__traceback__)
        print("=" * 80, file=sys.stderr)
        super().on_overseer_error(e)

    def probe(self, selector):
        return self.require(ProbeInstrument(select(selector, skip_frames=1)))

    def run_phase(self, phase):
        self.log({"#event": {"type": "phase", "name": phase.name}})
        return super().run_phase(phase)

    def run(self, argv):
        self.log = LogStream()
        self.given.where("#event") >> self.log
        # self.given.where("$wrap") >> self.log
        if self.logfile is not None:
            self.gtf = GiveToFile(self.logfile, require_writable=False)
            self.log >> self.gtf.log
        else:
            self.gtf = None

        with self.run_phase(self.phases.init):
            pass

        with self.run_phase(self.phases.parse_args):
            self.options = self.argparser.parse_args(argv)
            del self.argparser

        with self.run_phase(self.phases.load_script):
            script = self.options.SCRIPT
            field = "__main__"
            argv = self.options.ARGV
            func = find_script(script, field)

        with self.run_phase(self.phases.run_script) as set_value:
            sys.argv = [script, *argv]
            set_value(func())

    def __call__(self, *args, **kwargs):
        try:
            super().__call__(*args, **kwargs)
        except BaseException as e:
            self.log(
                {
                    "#event": {
                        "type": "error",
                        "data": {"type": type(e).__name__, "message": str(e)},
                    }
                }
            )
            raise
        finally:
            with self.run_phase(self.phases.finalize):
                pass
            if self.gtf:
                self.gtf.close()


def find_script(script, field):
    node, mainsection = split_script(script)
    mod = ModuleType("__main__")
    glb = vars(mod)
    glb["__file__"] = script
    sys.modules["__main__"] = mod
    code = compile(node, script, "exec")
    exec(code, glb, glb)
    glb["__main__"] = exec_node(script, mainsection, glb)
    return glb[field]
