import os
import subprocess

here = os.path.dirname(__file__)


class Runner:
    def __init__(self, cmd, interaction=[]):
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
        )
        self.stdout, self.stderr = self.proc.communicate(
            input="\n".join(interaction).encode(),
            timeout=5,
        )
        self.stdout = self.stdout.decode("utf8")
        self.stderr = self.stderr.decode("utf8")
        self.outlines = self.stdout.splitlines()
        self.errlines = self.stderr.splitlines()

    def __contains__(self, text):
        return text in self.stdout

    def has_lines(self, *lines):
        lines = list(lines)
        for line in self.outlines:
            if lines[0] in line:
                lines = lines[1:]
                if not lines:
                    return True
        return False


def run(cmd, interaction=[]):
    return Runner(
        cmd=f"paperoni {cmd} -c {here}/oli.json",
        interaction=interaction,
    )


_bib_expected = """@inproceedings{bergstra2010-compiler26,
    author = {James Bergstra and Olivier Breuleux and Frederic Bastien and Pascal Lamblin and Razvan Pascanu and Guillaume Desjardins and Joseph Turian and David Warde-Farley and Yoshua Bengio},
    title = {Theano: A CPU and GPU Math Compiler in Python},
    year = {2010},
    booktitle = {Proceedings of the 9th Python in Science Conference},
    pages = {18-24},
    publisher = {hgpu.org}
}"""


def test_bibtex1():
    r = run("bibtex -t Theano A CPU and GPU Math Compiler in Python")
    assert _bib_expected in r


def test_bibtex2():
    r = run("search -t Theano A CPU and GPU Math Compiler in Python", ["b"])
    assert _bib_expected in r


def test_html1():
    r = run("html")
    assert r.stdout == open(f"{here}/oli.html", "r").read()


def test_html2():
    r = run("html -t Theano A CPU and GPU Math Compiler in Python")
    assert r.stdout == open(f"{here}/oli-theano.html", "r").read()
