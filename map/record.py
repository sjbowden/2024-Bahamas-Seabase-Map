"""What a build read and what it wrote, kept so that the folder can be held to it.

The pages and the data are made, not copied: nothing in site_build sits beside
the journal, the stories or the placement code to be compared with them. So the
build writes down every file it was made from and every file it made, with
their hashes, and publishing and the suite ask this module whether both still
stand.

    watch()                       at the top of a build, before its imports
    sources(out)                  what has been read since
    write_record(...)             at the end of a build
    outdated(record, out)         reasons the folder is not current; none if it is

Nothing here builds, and importing it starts nothing: asking the question must
not load the build or leave a watch on the process that asked.
"""
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(HERE, "out", "photo_index.json")
# Beside the folder and not in it: it names files that are not published.
RECORD = os.path.join(HERE, "out", "build_record.json")
# Not sources: the archives stand behind the index, which is one; the media
# are checked against that index by derive; the rest is not this project's.
NOT_SOURCE = (".venv", ".git", "photos", "node_modules", "site_build", "__pycache__")
# Nor are this machine's caches. Each is named for the source it was made from
# or checked against it when read, and one thrown away is not a page gone stale.
CACHES = ("out/derived.json",)
CACHE_SUFFIX = ".pkl"

_opened = set()
_started = None


def _note(event, args):
    if event == "open" and isinstance(args[1], str) and args[1][:1] == "r" \
            and "+" not in args[1] and isinstance(args[0], (str, os.PathLike)):
        _opened.add(os.fspath(args[0]))


def watch():
    """Note every file opened for reading from now on, and when now was.

    Called before a build's imports, because a module may read its data as it
    loads. An audit hook cannot be taken off again, which is why it is put on
    here and not when this module is imported.
    """
    global _started
    if _started is None:
        _started = time.time()
        sys.addaudithook(_note)
    return _started


def watching():
    return _started is not None


def _rel(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def sources(out, root=HERE):
    """What this run has read so far that a build is made from: the modules
    loaded and the files opened, within the project."""
    out = os.path.abspath(out)
    seen = set(_opened) | {getattr(m, "__file__", None) or ""
                           for m in list(sys.modules.values())}
    keep = set()
    for path in seen:
        path = os.path.abspath(path)
        rel = _rel(path, root)
        if (rel.startswith("../") or path.startswith(out + os.sep)
                or any(part in NOT_SOURCE for part in rel.split("/"))
                or rel in CACHES or rel.endswith(CACHE_SUFFIX)
                or not os.path.isfile(path)):
            continue
        keep.add(path)
    return sorted(keep)


def _state(path):
    """What a source is now: a file's hash, a folder's names, or None for
    something that is not there -- which is a state too, and can change."""
    if os.path.isdir(path):
        return "names " + hashlib.sha256("\n".join(sorted(os.listdir(path))).encode()
                                         ).hexdigest()
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _built(out):
    """The files of a built folder, but for its media, as paths within it."""
    found = []
    for folder, sub, names in os.walk(out):
        if folder == out and "media" in sub:
            sub.remove("media")
        found += [_rel(os.path.join(folder, n), out) for n in names]
    return sorted(found)


def touched(inputs, since, root=HERE):
    """Those of a build's sources changed after it began, as their names. The
    record is written at the end, and would vouch for bytes the build never saw."""
    return [_rel(p, root) for p in sorted(set(inputs))
            if os.path.exists(p) and os.path.getmtime(p) > since]


def write_record(path, out, inputs, outputs, root=HERE):
    """Record what a folder was built from and what the build wrote in it.

    `inputs` are paths: files read, folders whose contents were copied, and
    files looked for and not found. `outputs` are names within the folder, and
    only those: a file an earlier build left there is not this build's.
    """
    record = dict(
        inputs={_rel(p, root): _state(p) for p in sorted(set(inputs))},
        outputs={n: _state(os.path.join(out, n)) for n in sorted(set(outputs))})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "w") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
    os.replace(path + ".part", path)
    return record


def strays(out, outputs):
    """Files in a built folder, media apart, that are not among `outputs`."""
    return [n for n in _built(out) if n not in set(outputs)]


def _some(names):
    return ", ".join(names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")


def outdated(path, out, root=HERE):
    """Reasons a folder is not the build of the sources as they stand; empty if
    it is. The media are not looked at: derive.stale answers for those."""
    if not os.path.exists(path):
        return [f"no record of the build ({_rel(path, root)})"]
    try:
        with open(path) as fh:
            record = json.load(fh)
        was, made = record["inputs"], record["outputs"]
        if not isinstance(was, dict) or not isinstance(made, dict):
            raise ValueError("not a record")
    except (OSError, ValueError, KeyError, TypeError):
        return [f"the record of the build cannot be read ({_rel(path, root)})"]

    why = []
    src = [n for n, state in sorted(was.items()) if _state(os.path.join(root, n)) != state]
    if src:
        why.append(f"changed since the build: {_some(src)}")
    changed = [n for n, state in sorted(made.items())
               if _state(os.path.join(out, n)) != state]
    if changed:
        why.append(f"not as the build left it: {_some(changed)}")
    extra = strays(out, made)
    if extra:
        why.append(f"not written by the build: {_some(extra)}")
    return why
