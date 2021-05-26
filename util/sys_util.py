import platform


def sys_name():
    return platform.system().lower()


def is_windows():
    return sys_name() == "windows"


def arch():
    machine = platform.machine()
    if machine == "x86_64" or machine == "x64":
        return "amd64"
    elif machine == "aarch64":
        return "arm64"
    return machine
