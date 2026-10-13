"""What a build read and what it wrote, kept so that the folder can be held to it.

The pages and the data are made, not copied: nothing in site_build sits beside
the journal, the stories or the placement code to be compared with them. So the
build writes down every file it was made from and every file it made, with
their hashes, and publishing and the suite ask this module whether both still
stand.

    watch()                       at the top of a build, before its imports
    look(paths)                   what the build will look for or list, as it is now
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
import threading

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

_seen = {}                # path -> what the file was when it was first read
_watching = False
_root = HERE
# Hashing a file opens it, which comes back to the watch. Each thread has its
# own flag for that: one flag for all would drop whatever another thread first
# opened in the meantime.
_busy = threading.local()


def _rel(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _is_source(path, root):
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
    if path not in _seen and _is_source(path, _root) and not os.path.isdir(path):
        _seen[path] = _state(path)


def _note(event, args):
    if event != "open" or getattr(_busy, "now", False):
        return
    path, mode = args[0], args[1]
    if not (isinstance(mode, str) and mode[:1] == "r" and "+" not in mode
            and isinstance(path, (str, os.PathLike))):
        return
    _busy.now = True
    try:
        _first(os.fspath(path))
    except OSError:
        pass                      # the open this is watching will say so itself
    finally:
        _busy.now = False


def watch(root=HERE):
    """Note every file of the project read from now on, and the modules
    already loaded.

    Called before a build's imports, because a module may read its data as it
    loads. An audit hook cannot be taken off again, which is why it is put on
    here and not when this module is imported.
    """
    global _watching, _root
    if not _watching:
        _watching, _root = True, root
        for m in list(sys.modules.values()):
            _first(getattr(m, "__file__", None))
        sys.addaudithook(_note)


def watching():
    return _watching


def read():
    """What this run has read so far that a build is made from, within the
    project: {path: what it was when first read}."""
    return dict(_seen)


def states(paths, but=()):
    """What each of these is now, as {path: state}. `but` are names a folder
    among them may hold that the build leaves where they are."""
    return {os.path.abspath(p): _state(p, but) for p in paths}


def look(paths, but=()):
    """Note what a build is about to look for or list, as it is now: a file
    that may not be there, a folder whose contents it copies. No open gives
    these to the watch, and what they are at the end is not what was built
    from if a poster was rendered in between. Called where the looking is
    done, as often as it is done: only the first time notes anything."""
    for path in paths:
        path = os.path.abspath(path)
        if path in _seen:
            continue
        _busy.now = True          # this is the noting; the watch need not repeat it
        try:
            state = _state(path, but)
        finally:
            _busy.now = False
        _seen.setdefault(path, state)


def changed(seen, root=HERE):
    """Those of a build's sources that are no longer what was read, as names.
    The record vouches for what the build saw; a file saved since is not that."""
    return sorted(_rel(p, root) for p, was in seen.items() if not _still(p, was))


def _state(path, but=()):
    """What a source is now: a file's hash, a folder's names, or None for
    something that is not there -- which is a state too, and can change.

    A folder's state carries the names that were left out of it, so that
    whoever checks it later leaves out the same ones: which those are is the
    build's rule, and this module has none of its own."""
    if os.path.isdir(path):
        names = sorted(n for n in os.listdir(path) if n not in but)
        return dict(names=hashlib.sha256("\n".join(names).encode()).hexdigest(),
                    but=sorted(but))
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _still(path, was):
    """Whether a source is what it was recorded as."""
    return _state(path, was.get("but", ()) if isinstance(was, dict) else ()) == was


def _walk(out):
    """A built folder, media apart, as (files, folders) of paths within it. A
    link is a file, whatever it points at: it is not gone into, and it is
    taken away as a file is."""
    files, folders = [], []
    for folder, sub, names in os.walk(out):
        if folder == out and "media" in sub:
            sub.remove("media")
        for name in sub:
            path = os.path.join(folder, name)
            (files if os.path.islink(path) else folders).append(_rel(path, out))
        files += [_rel(os.path.join(folder, n), out) for n in names]
    return sorted(files), folders


def _built(out):
    """The files of a built folder, but for its media, as paths within it."""
    return _walk(out)[0]


def write_record(path, out, inputs, outputs, root=HERE):
    """Record what a folder was built from and what the build wrote in it.

    `inputs` are {path: state}: files as they were when read, folders whose
    contents were copied, and files looked for and not found. `outputs` are
    names within the folder, and only those: a file an earlier build left
    there is not this build's.
    """
    made = {n: _state(os.path.join(out, n)) for n in sorted(set(outputs))}
    if unwritten(out, outputs):
        raise SystemExit(f"[record] the build did not write "
                         f"{_some(unwritten(out, outputs))}; {out} is not recorded "
                         "as built")
    record = dict(inputs={_rel(p, root): state for p, state in sorted(inputs.items())},
                  outputs=made)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "w") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
    os.replace(path + ".part", path)
    return record


def _is_state(state, built=False):
    """Whether this is something _state gives: a hash, and for a source also
    nothing at all, or a folder's names with those left out of them."""
    if isinstance(state, str):
        return True
    if built:
        return False
    return state is None or (
        isinstance(state, dict) and isinstance(state.get("names"), str)
        and isinstance(state.get("but"), list)
        and all(isinstance(n, str) for n in state["but"]))


def unwritten(out, outputs):
    """Those of `outputs` that are not files in the folder."""
    return [n for n in sorted(set(outputs)) if not os.path.isfile(os.path.join(out, n))]


def load(path):
    """A record as written, or None if there is none that can be read."""
    try:
        with open(path) as fh:
            record = json.load(fh)
        if (all(_is_state(v) for v in record["inputs"].values())
                and all(_is_state(v, built=True) for v in record["outputs"].values())):
            return record
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return None


def strays(out, outputs):
    """What is in a built folder, media apart, that is not among `outputs`:
    files, and then folders with none of the outputs in them, named with a
    closing slash and deepest first, so that they can be cleared in this order.
    A link the outputs were written through is the build's, as a folder is."""
    mine = set(outputs)
    kept = {n[:i] for n in mine for i, c in enumerate(n) if c == "/"}
    files, folders = _walk(out)
    hollow = [d for d in folders if d not in kept]
    return ([n for n in files if n not in mine and n not in kept]
            + [d + "/" for d in sorted(hollow, key=lambda d: (-d.count("/"), d))])


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
    src = [n for n, state in sorted(was.items())
           if not _still(os.path.join(root, n), state)]
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
