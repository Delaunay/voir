from dataclasses import dataclass, field

import pytest

from voir.argparse_ext import ExtendedArgumentParser


@dataclass
class Muffin:
    __help__ = "Lovely muffinness"

    class RedHerring:
        def hello(x):
            # wow!
            z = x * x
            return z

    moistness: int = 10
    has_chocolate: bool = True


@dataclass
class Configuration:
    # Hello there
    helloes: int = 3

    # Flag this
    flag: bool = True

    flog: bool = False  # Flog this

    # Mystery.
    x: int = 0

    greeting: str = "hello"
    """The greeting to use!"""

    scone: Muffin = field(default_fatory=Muffin())


@pytest.fixture
def configuration():
    p = ExtendedArgumentParser()
    p.add_from_model("cfg", Configuration())

    def run(args):
        return p.parse_args(args.split()).cfg

    run.parser = p

    return run


@pytest.fixture
def based_configuration():
    p = ExtendedArgumentParser()
    p.merge_base_config({"cfg": {"helloes": 77, "scone": {"has_chocolate": False}}})
    p.merge_base_config(
        {
            "cfg": {
                "helloes": 88,
                "flag": False,
            }
        }
    )
    p.add_from_model("cfg", Configuration)

    def run(args):
        return p.parse_args(args.split()).cfg

    run.parser = p

    return run


def test_parser(configuration):
    assert configuration("") == Configuration()
    assert configuration("--helloes 5") == Configuration(helloes=5)
    assert configuration("--flag") == Configuration(flag=True)
    assert configuration("--no-flag") == Configuration(flag=False)
    assert configuration("--flog") == Configuration(flog=True)
    assert configuration("--no-flog") == Configuration(flog=False)
    assert configuration("--scone.moistness 33") == Configuration(
        scone=Muffin(moistness=33)
    )
    with pytest.raises(Exception):
        configuration.parser.merge_base_config(Configuration())


def test_parser_with_base(based_configuration):
    assert based_configuration("") == Configuration(
        helloes=88, flag=False, scone=Muffin(has_chocolate=False)
    )
    assert based_configuration("--scone.has-chocolate") == Configuration(
        helloes=88, flag=False, scone=Muffin(has_chocolate=True)
    )


def test_help(configuration, file_regression, capsys):
    with pytest.raises(SystemExit):
        configuration("-h")

    file_regression.check(
        capsys.readouterr().out.replace("options:", "optional arguments:")
    )


def test_help_with_base(based_configuration, file_regression, capsys):
    with pytest.raises(SystemExit):
        based_configuration("-h")

    file_regression.check(
        capsys.readouterr().out.replace("options:", "optional arguments:")
    )
