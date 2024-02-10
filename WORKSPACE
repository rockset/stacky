workspace(name = "rs_stacky")

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive", "http_file")
http_archive(
    name = "rules_xar",
    sha256 = "77d0ed7c5a8219e42a3197e5a20fddc9795191cf595628cf64a842255fbb7d4d",
    strip_prefix = "rules_xar-0.0.4",
    url = "https://github.com/ekacnet/rules_xar/archive/refs/tags/v0.0.4.zip",
)

#####################
# PYTHON SUPPORT
#####################
RULES_PYTHON_VERSION = "0.26.0"

http_archive(
    name = "rules_python",
    sha256 = "9d04041ac92a0985e344235f5d946f71ac543f1b1565f2cdbc9a2aaee8adf55b",
    strip_prefix = "rules_python-{}".format(RULES_PYTHON_VERSION),
    url = "https://github.com/bazelbuild/rules_python/releases/download/{}/rules_python-{}.tar.gz".format(RULES_PYTHON_VERSION, RULES_PYTHON_VERSION),
)

load("@rules_python//python:repositories.bzl", "py_repositories", "python_register_toolchains")

# Required to prevent errors about @rules_python_internal missing
py_repositories()

python_register_toolchains(
    name = "python3_10",
    # Available versions are listed in @rules_python//python:versions.bzl.
    # We recommend using the same version your team is already standardized on.
    python_version = "3.10",
)

load("@python3_10//:defs.bzl", "interpreter")
load("@rules_python//python:pip.bzl", "pip_parse")

pip_parse(
    name = "pypi",
    python_interpreter_target = interpreter,
    requirements_lock = "//:requirements_lock.txt",
)

load("@pypi//:requirements.bzl", "install_deps")

install_deps()
