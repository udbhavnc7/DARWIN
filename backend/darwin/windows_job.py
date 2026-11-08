"""Keep every application process, including database children, in one Windows job."""
import subprocess
import time

import psutil
import win32api
import win32job as job


EXTENDED = job.JobObjectExtendedLimitInformation
ACCOUNTING = job.JobObjectBasicAccountingInformation


def usage(handle):
    counts = job.QueryInformationJobObject(handle, ACCOUNTING)
    limits = job.QueryInformationJobObject(handle, EXTENDED)
    return {'cpu_seconds': (counts['TotalUserTime'] + counts['TotalKernelTime']) / 10_000_000,
            'memory_peak_mb': limits['PeakJobMemoryUsed'] / 2**20}


class ApplicationJob:
    def __init__(self, name, budget):
        self.name = name
        cpus = psutil.Process().cpu_affinity()[:int(budget.sandbox_cpu_cores)]
        if len(cpus) != budget.sandbox_cpu_cores:
            raise ValueError('Benchmark requires the requested number of available whole logical CPUs')
        self.cpus = cpus
        self.handle = job.CreateJobObject(None, name)
        limits = job.QueryInformationJobObject(self.handle, EXTENDED)
        limits['BasicLimitInformation'].update(
            LimitFlags=job.JOB_OBJECT_LIMIT_AFFINITY | job.JOB_OBJECT_LIMIT_JOB_MEMORY | job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
            Affinity=sum(1 << core for core in cpus))
        limits['JobMemoryLimit'] = budget.sandbox_memory_mb * 2**20
        job.SetInformationJobObject(self.handle, EXTENDED, limits)

    def launch(self, args, **kwargs):
        # Assign before any child code executes, including venv launchers and postgres workers.
        process = subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW | 0x4, **kwargs)
        try:
            handle = win32api.OpenProcess(0x0100 | 0x0001 | 0x0400, False, process.pid)
            try:
                job.AssignProcessToJobObject(self.handle, handle)
            finally:
                handle.Close()
            psutil.Process(process.pid).resume()
        except BaseException:
            process.kill()
            process.wait()
            raise
        return process

    def close(self):
        try:
            job.TerminateJobObject(self.handle, 1)
            deadline = time.monotonic() + 5
            while job.QueryInformationJobObject(self.handle, ACCOUNTING)['ActiveProcesses']:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Benchmark process group has surviving processes')
                time.sleep(.05)
        finally:
            self.handle.Close()
