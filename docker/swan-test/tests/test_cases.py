"""Run test cases shipped with the SWAN src code."""
import os
import shutil
import pytest
import tarfile
import datetime
from subprocess import Popen, CalledProcessError
import numpy as np


TESTDIR = "/tmp/tests"
TESTCASES = {
    "refrac": {"namelist": "a11refr.swn", "output": ["a11ref01.tab"]},
    "shoal": {"namelist": "a21sho01.swn", "output": []},
}


class TestModel:
    """Test that testcases run and results are consistent."""

    @classmethod
    def setup_class(self):
        """Setup class."""
        self.mpiexec = "mpiexec"
        os.chdir(TESTDIR)

    @classmethod
    def teardown_class(self):
        pass

    def print(self, msg):
        sep = 88 * "="
        print(f"\n{sep}\n{msg}\n{sep}")

    def extract(self):
        """Extract tarball and copy files that will be checked into checkdir."""
        with tarfile.open(f"{self.testcase}.tar.gz") as tf:
            tf.extractall()
        self.checkdir = os.path.abspath(os.path.join(self.testcase, "checkdir"))
        os.makedirs(self.checkdir, exist_ok=True)
        for output in self.output:
            shutil.copy(
                os.path.join(self.testcase, output),
                os.path.join(self.checkdir, output)
            )

    def link_input(self):
        """Link INPUT file."""
        assert os.path.isfile(self.namelist), f"File {self.namelist} not in {self.testcase}"
        os.symlink(self.namelist, "TMPFILE")
        os.replace("TMPFILE", "INPUT")

    def run_model(self, cpu):
        """Run SWAN."""
        now = datetime.datetime.now()
        cmd = [self.mpiexec, "-n", str(cpu), "swan.exe"]
        process = Popen(cmd)
        exitcode = process.wait()
        if exitcode != 0:
            raise CalledProcessError(exitcode, cmd)
        elapsed = (datetime.datetime.now() - now).total_seconds()
        print("Model ran in {} s".format(elapsed))
        self.check_output()
        return exitcode

    def check_output(self):
        """Check if output in new run matches those from tarball.

        Only files with no header are checked here.

        """
        for output in self.output:
            print("Checking results from {}".format(output))
            old = np.loadtxt(os.path.join(self.checkdir, output))
            new = np.loadtxt(output)
            assert new == pytest.approx(old, rel=1e-2)

    def cleanup(self):
        """Remove running directory."""
        shutil.rmtree(self.testcase)

    @pytest.mark.parametrize("testcase, model_files", TESTCASES.items())
    def test_case(self, testcase, model_files):
        self.testcase = testcase
        self.namelist = model_files["namelist"]
        self.output = model_files["output"]
        self.extract()
        with cd(self.testcase):
            self.link_input()
            self.print("{}: SERIAL RUN".format(self.testcase.upper()))
            self.run_model(cpu=1)
            self.print("{}: MPI RUN".format(self.testcase.upper()))
            self.run_model(cpu=2)
        self.cleanup()


class cd:
    """Context manager for changing the current working directory"""

    def __init__(self, newPath):
        self.newPath = os.path.expanduser(newPath)

    def __enter__(self):
        self.savedPath = os.getcwd()
        os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.savedPath)
