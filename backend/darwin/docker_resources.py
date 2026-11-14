"""Read resource limits and counters from the application containers' cgroups."""
import json
import os
from pathlib import Path
import shutil
import subprocess


def docker_executable():
    cli = shutil.which('docker')
    if cli or os.name != 'nt':
        return cli
    for variable, installation in (('LOCALAPPDATA', 'Programs/DockerDesktop'), ('ProgramFiles', 'Docker/Docker')):
        directory = os.environ.get(variable)
        if directory:
            candidate = Path(directory) / installation / 'resources/bin/docker.exe'
            if candidate.is_file():
                return str(candidate)
    return None


def docker_environment(cli, base=None):
    env = dict(os.environ if base is None else base)
    if os.name == 'nt' and cli:
        env['PATH'] = os.pathsep.join((str(Path(cli).parent), env.get('PATH', '')))
    return env


def docker_output(*args):
    cli = docker_executable()
    if not cli:
        raise FileNotFoundError('Docker CLI was not found')
    return subprocess.check_output(
        [cli, *args], env=docker_environment(cli), text=True, timeout=5, stdin=subprocess.DEVNULL,
        stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    ).strip()


def docker_status():
    """Return the version of cgroups on a local Linux engine, or None."""
    try:
        endpoint = (os.environ.get('DOCKER_HOST') if not os.environ.get('DOCKER_CONTEXT') else None)
        endpoint = endpoint or docker_output('context', 'inspect', '--format', '{{.Endpoints.docker.Host}}')
        if not endpoint.startswith(('unix://', 'npipe://')):
            return None
        os_type, cgroups = docker_output('info', '--format', '{{.OSType}} {{.CgroupVersion}}').split()
        docker_output('compose', 'version', '--short')
        return cgroups if os_type == 'linux' else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def cgroup_counters(output, cpu_limit, memory_limit):
    cpu, memory, swap, peak, *stats = output.splitlines()
    quota, period = cpu.split()
    if quota == 'max' or abs(int(quota) / int(period) - cpu_limit) > 1e-6:
        raise RuntimeError('Container CPU limit differs from the requested limit')
    if memory != str(memory_limit) or swap != '0':
        raise RuntimeError('Container memory or swap limit differs from the requested limit')
    usage = int(dict(row.split() for row in stats)['usage_usec'])
    return {'cpu_seconds': usage / 1e6, 'memory_peak_mb': int(peak) / 2**20}


def snapshot_cgroups(manifest):
    specs = json.loads(Path(manifest).read_bytes())
    started = docker_output('inspect', '--format', '{{.State.StartedAt}}', *specs)
    readings = {
        ident: cgroup_counters(docker_output(
            'exec', ident, 'cat', '/sys/fs/cgroup/cpu.max', '/sys/fs/cgroup/memory.max',
            '/sys/fs/cgroup/memory.swap.max', '/sys/fs/cgroup/memory.peak', '/sys/fs/cgroup/cpu.stat',
        ), spec['cpus'], spec['memory_bytes'])
        for ident, spec in specs.items()
    }
    return {
        'cpu_seconds': sum(row['cpu_seconds'] for row in readings.values()),
        'memory_peak_mb': sum(row['memory_peak_mb'] for row in readings.values()),
        'containers': readings, 'started': started,
    }


def check_counter_continuity(before, after):
    if before['started'] != after['started'] or before['containers'].keys() != after['containers'].keys():
        raise RuntimeError('Application containers changed during measurement')
    for ident, reading in before['containers'].items():
        if after['containers'][ident]['cpu_seconds'] < reading['cpu_seconds']:
            raise RuntimeError('A container CPU counter reset during measurement')
