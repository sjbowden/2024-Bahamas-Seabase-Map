"""What a build read and what it wrote, kept so that the folder can be held to it.

The pages and the data are made, not copied: nothing in site_build sits beside
the journal, the stories or the placement code to be compared with them. So the
build writes down every file it was made from and every file it made, with
their hashes, and publishing and the suite ask this module whether both still
stand.

    watch()                       at the top of a build, before its imports
    read()                        what has been read since, each as it was then
    changed(seen)                 those that are no longer what was read
    write_record(...)             at the end of a build
    outdated(record, out)         reasons the folder is not current; none if it is

Nothing here builds, and importing it starts nothing: asking the question must
not load the build or leave a watch on the process that asked.
"""
import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(HERE, "out", "photo_index.json")
# Beside the folder and not in it: it names files that are not published.
RECORD = os.path.join(HERE, "out", "build_record.json")
# Not sources: the archives stand behind the index, which is one; the media
# are checked against that index by derive; the rest is not this project's.
NOT_SOURCE = (".venv", ".git", "photos", "node_modules", "site_build", "__pycache__")
# Nor are this machine's caches, nor the record itself. Each cache is named for
# the source it was made from or checked against it when read, and one thrown
# away is not a page gone stale.
CACHES = ("out/derived.json", "out/build_record.json")
CACHE_SUFFIX = ".pkl"
# The vendored library's own notes, which the build leaves where they are.
NOT_COPIED = ("README", "VERSION")

_seen = {}                # path -> what the file was when it was first read
_watching = False
_busy = False


def _rel(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _is_source(path, root=HERE):
    rel = _rel(path, root)
    return not (rel.startswith("../") or rel in CACHES or rel.endswith(CACHE_SUFFIX)
                or any(part in NOT_SOURCE for part in rel.split("/")))


def _first(path):
    """Note a file the first time it is read, as it is at that moment. A
    compiled module stands for its source, which is what was written."""
    if not isinstance(path, str):
        return
    path = os.path.abspath(path)
    if path.endswith(".pyc"):
        try:
            path = importlib.util.source_from_cache(path)
        except ValueError:
            return
    if path not in _seen and _is_source(path) and not os.path.isdir(path):
        _seen[path] = _state(path)


def _note(event, args):
    global _busy
    if event != "open" or _busy:
        return
    path, mode = args[0], args[1]
    if not (isinstance(mode, str) and mode[:1] == "r" and "+" not in mode
            and isinstance(path, (str, os.PathLike))):
        return
    _busy = True                  # hashing the file opens it, which comes here
    try:
        _first(os.fspath(path))
    except OSError:
        pass                      # the open this is watching will say so itself
    finally:
        _busy = False


def watch():
    """Note every file read from now on, and the modules already loaded.

    Called before a build's imports, because a module may read its data as it
    loads. An audit hook cannot be taken off again, which is why it is put on
    here and not when this module is imported.
    """
    global _watching
    if not _watching:
        _watching = True
        for m in list(sys.modules.values()):
            _first(getattr(m, "__file__", None))
        sys.addaudithook(_note)


def watching():
    return _watching


def read():
    """What this run has read so far that a build is made from, within the
    project: {path: what it was when first read}."""
    return dict(_seen)


def states(paths):
    """What each of these is now, as {path: state}: for what a build looked for
    or listed, which no open gave the watch."""
    return {os.path.abspath(p): _state(p) for p in paths}


def changed(seen, root=HERE):
    """Those of a build's sources that are no longer what was read, as names.
    The record vouches for what the build saw; a file saved since is not that."""
    return sorted(_rel(p, root) for p, was in seen.items() if _state(p) != was)


def _state(path):
    """What a source is now: a file's hash, a folder's names, or None for
    something that is not there -- which is a state too, and can change."""
    if os.path.isdir(path):
        names = sorted(n for n in os.listdir(path) if n not in NOT_COPIED)
        return "names " + hashlib.sha256("\n".join(names).encode()).hexdigest()
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


def write_record(path, out, inputs, outputs, root=HERE):
    """Record what a folder was built from and what the build wrote in it.

    `inputs` are {path: state}: files as they were when read, folders whose
    contents were copied, and files looked for and not found. `outputs` are
    names within the folder, and only those: a file an earlier build left
    there is not this build's.
    """
    made = {n: _state(os.path.join(out, n)) for n in sorted(set(outputs))}
    unwritten = [n for n, state in made.items() if state is None]
    if unwritten:
        raise SystemExit(f"[record] the build did not write {_some(unwritten)}; "
                         f"{out} is not recorded as built")
    record = dict(inputs={_rel(p, root): state for p, state in sorted(inputs.items())},
                  outputs=made)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "w") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
    os.replace(path + ".part", path)
    return record


def load(path):
    """A record as written, or None if there is none that can be read."""
    try:
        with open(path) as fh:
            record = json.load(fh)
        if isinstance(record["inputs"], dict) and isinstance(record["outputs"], dict):
            return record
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def strays(out, outputs):
    """Files in a built folder, media apart, that are not among `outputs`."""
    mine = set(outputs)
    return [n for n in _built(out) if n not in mine]


def _some(names):
    return ", ".join(names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")


def outdated(path, out, root=HERE):
    """Reasons a folder is not the build of the sources as they stand; empty if
    it is. The media are not looked at: derive.stale answers for those."""
    if not os.path.exists(path):
        return [f"no record of the build ({_rel(path, root)})"]
    record = load(path)
    if record is None:
        return [f"the record of the build cannot be read ({_rel(path, root)})"]
    was, made = record["inputs"], record["outputs"]

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
