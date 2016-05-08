# maybe - see what a program does before deciding whether you really want it to happen
#
# Copyright (c) 2016 Philipp Emanuel Weidmann <pew@worldwidemann.com>
#
# Nemo vir est qui mundum non reddat meliorem.
#
# Released under the terms of the GNU General Public License, version 3
# (https://gnu.org/licenses/gpl.html)


from os.path import exists
from os import O_WRONLY, O_RDWR, O_APPEND, O_CREAT, O_TRUNC
from stat import S_IFCHR, S_IFBLK, S_IFIFO, S_IFSOCK

from maybe import SyscallFilter, SYSCALL_FILTERS, T, get_full_path


# Start with a large number to avoid collisions with other FDs
# TODO: This approach is extremely brittle!
next_file_descriptor = 1000
file_descriptors = {}


def get_next_file_descriptor():
    global next_file_descriptor
    file_descriptor = next_file_descriptor
    next_file_descriptor += 1
    return file_descriptor


def get_file_descriptor_path(file_descriptor):
    return file_descriptors.get(file_descriptor, "/dev/fd/%d" % file_descriptor)


allowed_files = set(["/dev/null", "/dev/zero", "/dev/tty"])


def format_open(path, flags):
    if path in allowed_files:
        return None
    elif (flags & O_CREAT) and not exists(path):
        return "%s %s" % (T.cyan("create file"), T.underline(path))
    elif (flags & O_TRUNC) and exists(path):
        return "%s %s" % (T.red("truncate file"), T.underline(path))
    else:
        return None


def substitute_open(path, flags):
    if path in allowed_files:
        return None
    elif (flags & O_WRONLY) or (flags & O_RDWR) or (flags & O_APPEND) or (format_open(path, flags) is not None):
        # File might be written to later, so we need to track the file descriptor
        file_descriptor = get_next_file_descriptor()
        file_descriptors[file_descriptor] = path
        return file_descriptor
    else:
        return None


def format_mknod(path, type):
    if exists(path):
        return None
    elif (type & S_IFCHR):
        label = "create character special file"
    elif (type & S_IFBLK):
        label = "create block special file"
    elif (type & S_IFIFO):
        label = "create named pipe"
    elif (type & S_IFSOCK):
        label = "create socket"
    else:
        # mknod(2): "Zero file type is equivalent to type S_IFREG"
        label = "create file"
    return "%s %s" % (T.cyan(label), T.underline(path))


def substitute_mknod(path, type):
    return None if (format_mknod(path, type) is None) else 0


def format_write(file_descriptor, byte_count):
    if file_descriptor in file_descriptors:
        path = file_descriptors[file_descriptor]
        return "%s %s to %s" % (T.red("write"), T.bold("%d bytes" % byte_count), T.underline(path))
    else:
        return None


def substitute_write(file_descriptor, byte_count):
    return None if (format_write(file_descriptor, byte_count) is None) else byte_count


def substitute_dup(file_descriptor_old, file_descriptor_new=None):
    if file_descriptor_old in file_descriptors:
        if file_descriptor_new is None:
            file_descriptor_new = get_next_file_descriptor()
        # Copy tracked file descriptor
        file_descriptors[file_descriptor_new] = file_descriptors[file_descriptor_old]
        return file_descriptor_new
    else:
        return None


SYSCALL_FILTERS["create_write_file"] = [
    SyscallFilter(
        syscall="open",
        format=lambda pid, args: format_open(get_full_path(pid, args[0]), args[1]),
        substitute=lambda pid, args: substitute_open(get_full_path(pid, args[0]), args[1]),
    ),
    SyscallFilter(
        syscall="creat",
        format=lambda pid, args: format_open(get_full_path(pid, args[0]), O_CREAT | O_WRONLY | O_TRUNC),
        substitute=lambda pid, args: substitute_open(get_full_path(pid, args[0]), O_CREAT | O_WRONLY | O_TRUNC),
    ),
    SyscallFilter(
        syscall="openat",
        format=lambda pid, args: format_open(get_full_path(pid, args[1], args[0]), args[2]),
        substitute=lambda pid, args: substitute_open(get_full_path(pid, args[1], args[0]), args[2]),
    ),
    SyscallFilter(
        syscall="mknod",
        format=lambda pid, args: format_mknod(get_full_path(pid, args[0]), args[1]),
        substitute=lambda pid, args: substitute_mknod(get_full_path(pid, args[0]), args[1]),
    ),
    SyscallFilter(
        syscall="mknodat",
        format=lambda pid, args: format_mknod(get_full_path(pid, args[1], args[0]), args[2]),
        substitute=lambda pid, args: substitute_mknod(get_full_path(pid, args[1], args[0]), args[2]),
    ),
    SyscallFilter(
        syscall="write",
        format=lambda pid, args: format_write(args[0], args[2]),
        substitute=lambda pid, args: substitute_write(args[0], args[2]),
    ),
    SyscallFilter(
        syscall="pwrite",
        format=lambda pid, args: format_write(args[0], args[2]),
        substitute=lambda pid, args: substitute_write(args[0], args[2]),
    ),
    SyscallFilter(
        syscall="writev",
        # TODO: Actual byte count is iovcnt * iov.iov_len
        format=lambda pid, args: format_write(args[0], args[2]),
        substitute=lambda pid, args: substitute_write(args[0], args[2]),
    ),
    SyscallFilter(
        syscall="pwritev",
        # TODO: Actual byte count is iovcnt * iov.iov_len
        format=lambda pid, args: format_write(args[0], args[2]),
        substitute=lambda pid, args: substitute_write(args[0], args[2]),
    ),
    SyscallFilter(
        syscall="dup",
        format=lambda pid, args: None,
        substitute=lambda pid, args: substitute_dup(args[0]),
    ),
    SyscallFilter(
        syscall="dup2",
        format=lambda pid, args: None,
        substitute=lambda pid, args: substitute_dup(args[0], args[1]),
    ),
    SyscallFilter(
        syscall="dup3",
        format=lambda pid, args: None,
        substitute=lambda pid, args: substitute_dup(args[0], args[1]),
    ),
]
