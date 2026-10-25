"""First-run welcome screen for SigmaOS-welcome-screen (inspired by mintwelcome).

Principles: the whole flow is a declarative manifest (steps, links, tour) that
is parsed fail-fast before rendering, link URLs are restricted to http(s) so a
manifest can never smuggle in script handlers, the finish state carries an
explicit caller-supplied timestamp (no clock in the pure layer -- tests stay
deterministic), save/load use atomic tempfile writes.
"""
import argparse, json, os, re, sys

ENGINE = {
    "name": "sigma-welcome",
    "summary": "First-run welcome: steps, links, guided tour, finish state",
    "language": "python",
    "verbs": ["steps", "links", "tour-plan", "finish"],
    "principles": ["Declarative Manifests", "Defensive Programming",
                   "Fail-Fast", "Least Astonishment", "KISS",
                   "Deterministic Testing"],
}

cli_doc = """\
$ sigma-welcome steps flow.json
1. [ ] welcome   Welcome to SigmaOS
2. [ ] docs      Read the documentation
$ sigma-welcome steps flow.json --done welcome
1. [x] welcome   Welcome to SigmaOS
$ sigma-welcome links links.json
$ sigma-welcome tour-plan tour.json
[00:30] desktop  Meet the desktop
$ sigma-welcome finish --product SigmaOS --version 1.0 --save ~/.config/welcome.json
"""

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_PAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_CAT_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_STATE_KEYS = {"product", "version", "finished", "timestamp"}


class WelcomeError(ValueError):
    pass


def _load(text, what):
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as e:
        raise WelcomeError(f"{what} manifest is not valid JSON: {e}") from e
    return data


def _line(value, what):
    if not isinstance(value, str) or not value.strip():
        raise WelcomeError(f"empty {what}")
    if "\n" in value or "\x00" in value:
        raise WelcomeError(f"{what} must be a single line")
    return value.strip()


# --------------------------------------------------------------------------- #
#  Welcome steps
# --------------------------------------------------------------------------- #
def parse_steps(text):
    data = _load(text, "steps")
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise WelcomeError('steps manifest needs a "steps" list')
    steps, seen = [], set()
    for i, row in enumerate(data["steps"]):
        if not isinstance(row, dict):
            raise WelcomeError(f"step #{i} is not an object")
        sid = row.get("id")
        if not isinstance(sid, str) or not _ID_RE.match(sid):
            raise WelcomeError(f"step #{i}: bad id {sid!r}")
        if sid in seen:
            raise WelcomeError(f"duplicate step id: {sid!r}")
        seen.add(sid)
        title = _line(row.get("title"), f"step {sid} title")
        page = _line(row.get("page"), f"step {sid} page")
        if not _PAGE_RE.match(page) or " " in page:
            raise WelcomeError(f"step {sid}: bad page {page!r}")
        icon = row.get("icon", "")
        if icon is not None and (not isinstance(icon, str)
                                 or "\n" in icon):
            raise WelcomeError(f"step {sid}: bad icon {icon!r}")
        steps.append({"id": sid, "title": title, "page": page,
                      "icon": icon or ""})
    if not steps:
        raise WelcomeError("steps manifest is empty")
    return steps


def render_steps(steps, done=()):
    done = set(done)
    unknown = sorted(done - {s["id"] for s in steps})
    if unknown:
        raise WelcomeError(f"unknown done step(s): {', '.join(unknown)}")
    lines = []
    for i, s in enumerate(steps, 1):
        mark = "x" if s["id"] in done else " "
        lines.append(f"{i}. [{mark}] {s['id']:<10} {s['title']}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
#  Links (http(s) only -- a manifest cannot inject script handlers)
# --------------------------------------------------------------------------- #
def parse_links(text):
    data = _load(text, "links")
    if not isinstance(data, list) or not data:
        raise WelcomeError("links manifest needs a non-empty JSON list")
    links, seen = [], set()
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            raise WelcomeError(f"link #{i} is not an object")
        label = _line(row.get("label"), f"link #{i} label")
        if label in seen:
            raise WelcomeError(f"duplicate link label: {label!r}")
        seen.add(label)
        url = row.get("url")
        if not isinstance(url, str) or not url.strip():
            raise WelcomeError(f"link {label!r}: empty url")
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            raise WelcomeError(
                f"link {label!r}: only http(s) urls allowed, got {url!r}")
        if any(c in url for c in " \t\n\x00"):
            raise WelcomeError(f"link {label!r}: url contains whitespace")
        category = row.get("category", "general")
        if not isinstance(category, str) or not _CAT_RE.match(category):
            raise WelcomeError(f"link {label!r}: bad category {category!r}")
        links.append({"label": label, "url": url, "category": category})
    return links


def group_links(links):
    """Deterministic grouping: sorted categories, file order within each."""
    groups = {}
    for link in links:
        groups.setdefault(link["category"], []).append(link)
    return {cat: groups[cat] for cat in sorted(groups)}


def render_links(links):
    out = []
    for cat, rows in group_links(links).items():
        out.append(f"[{cat}]")
        for row in rows:
            out.append(f"  {row['label']:<24} {row['url']}")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
#  Guided tour (durations validated, cumulative timeline computed)
# --------------------------------------------------------------------------- #
def build_tour(text):
    data = _load(text, "tour")
    if not isinstance(data, dict) or not isinstance(data.get("stops"), list):
        raise WelcomeError('tour manifest needs a "stops" list')
    stops, seen, at = [], set(), 0
    for i, row in enumerate(data["stops"]):
        if not isinstance(row, dict):
            raise WelcomeError(f"stop #{i} is not an object")
        sid = row.get("id")
        if not isinstance(sid, str) or not _ID_RE.match(sid):
            raise WelcomeError(f"stop #{i}: bad id {sid!r}")
        if sid in seen:
            raise WelcomeError(f"duplicate stop id: {sid!r}")
        seen.add(sid)
        title = _line(row.get("title"), f"stop {sid} title")
        duration = row.get("duration")
        if isinstance(duration, bool) or not isinstance(duration, int):
            raise WelcomeError(f"stop {sid}: duration must be seconds, "
                               f"got {duration!r}")
        if not 5 <= duration <= 600:
            raise WelcomeError(f"stop {sid}: duration must be 5..600 seconds, "
                               f"got {duration}")
        stops.append({"id": sid, "title": title, "duration": duration,
                      "at": at})
        at += duration
    if not stops:
        raise WelcomeError("tour manifest is empty")
    return {"stops": stops, "total": at}


def format_duration(seconds):
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 0:
        raise WelcomeError(f"bad duration: {seconds!r}")
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def format_tour(tour):
    lines = [f"[{format_duration(s['at'])}] {s['id']}  {s['title']}"
             for s in tour["stops"]]
    lines.append(f"total {format_duration(tour['total'])} "
                 f"({len(tour['stops'])} stops)")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
#  Finish state (explicit timestamp -- no clock in the pure layer)
# --------------------------------------------------------------------------- #
def finish_state(product, version, timestamp):
    product = _line(product, "product")
    version = _line(version, "version")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        raise WelcomeError(f"timestamp must be a number, got {timestamp!r}")
    if timestamp < 0:
        raise WelcomeError(f"timestamp must be >= 0, got {timestamp}")
    return {"product": product, "version": version, "finished": True,
            "timestamp": timestamp}


def save_state(path, state):
    _validate_state(state)
    tmp = f"{path}.sigma-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def load_state(path):
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as e:
            raise WelcomeError(f"state is not valid JSON: {e}") from e
    return _validate_state(data)


def _validate_state(data):
    if not isinstance(data, dict):
        raise WelcomeError("state must be a JSON object")
    unknown = set(data) - _STATE_KEYS
    if unknown:
        raise WelcomeError(f"unknown state field(s): {sorted(unknown)}")
    for field in ("product", "version"):
        if field not in data:
            raise WelcomeError(f"state missing {field!r}")
        _line(data[field], f"state {field}")
    if data.get("finished") is not True:
        raise WelcomeError('state must have "finished": true')
    ts = data.get("timestamp")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or ts < 0:
        raise WelcomeError(f"bad timestamp: {ts!r}")
    return data


def is_finished(state, product):
    return bool(state.get("finished")) and state.get("product") == product


def finish_text(state):
    return (f"{state['product']} {state['version']} first-run finished "
            f"(timestamp {state['timestamp']})")


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=ENGINE["name"], description=ENGINE["summary"])
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("steps", help="parse and render the welcome steps")
    st.add_argument("file")
    st.add_argument("--done", action="append", default=[],
                    help="mark a step id as done (repeatable)")
    lk = sub.add_parser("links", help="parse and render the links manifest")
    lk.add_argument("file")
    tr = sub.add_parser("tour-plan", help="build the guided tour timeline")
    tr.add_argument("file")
    fi = sub.add_parser("finish", help="write or read the first-run state")
    fi.add_argument("--product", default="SigmaOS")
    fi.add_argument("--version", default="1.0")
    fi.add_argument("--timestamp", type=float, default=None)
    fi.add_argument("--save", default=None, metavar="FILE")
    fi.add_argument("--load", default=None, metavar="FILE")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "steps":
            steps = parse_steps(_read(args.file))
            print(render_steps(steps, set(args.done)), end="")
        elif args.cmd == "links":
            print(render_links(parse_links(_read(args.file))), end="")
        elif args.cmd == "tour-plan":
            print(format_tour(build_tour(_read(args.file))), end="")
        elif args.cmd == "finish":
            if args.load:
                state = load_state(args.load)
            else:
                ts = args.timestamp
                if ts is None:
                    import time
                    ts = time.time()
                state = finish_state(args.product, args.version, ts)
            if args.save:
                save_state(args.save, state)
            print(finish_text(state))
        return 0
    except (WelcomeError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def self_test() -> None:
    import tempfile

    # --- steps ---------------------------------------------------------------
    FLOW = """{"product": "SigmaOS", "steps": [
      {"id": "welcome", "title": "Welcome to SigmaOS", "page": "welcome.html",
       "icon": "face-smile"},
      {"id": "docs", "title": "Read the documentation", "page": "docs.html"},
      {"id": "apps", "title": "Pick your apps", "page": "pages/apps.html",
       "icon": "grid"}
    ]}"""
    steps = parse_steps(FLOW)
    assert [s["id"] for s in steps] == ["welcome", "docs", "apps"]
    assert steps[0]["icon"] == "face-smile" and steps[1]["icon"] == ""
    assert steps[2]["page"] == "pages/apps.html"
    plain = render_steps(steps)
    assert plain.splitlines()[0] == "1. [ ] welcome    Welcome to SigmaOS"
    assert all("[ ]" in line for line in plain.splitlines())
    partly = render_steps(steps, done={"welcome"})
    assert partly.splitlines()[0].startswith("1. [x] welcome")
    assert partly.splitlines()[1].startswith("2. [ ] docs")
    assert plain == render_steps(steps)              # deterministic
    try:
        render_steps(steps, done={"nope"})
    except WelcomeError:
        pass
    else:
        raise AssertionError("unknown done id not rejected")
    for bad in ('{"steps": []}',
                '{"steps": ["x"]}',
                '{"steps": [{"id": "a", "title": "A", "page": "a.html"},'
                ' {"id": "a", "title": "B", "page": "b.html"}]}',
                '{"steps": [{"id": "Bad", "title": "A", "page": "a.html"}]}',
                '{"steps": [{"id": "a", "page": "a.html"}]}',
                '{"steps": [{"id": "a", "title": "A"}]}',
                '{"steps": [{"id": "a", "title": "A", "page": "has space.html"}]}',
                '{"steps": [{"id": "a", "title": "A", "page": "a.html",'
                ' "icon": "x\\ny"}]}',
                "not json"):
        try:
            parse_steps(bad)
        except WelcomeError:
            pass
        else:
            raise AssertionError(f"steps should have been rejected: {bad}")

    # --- links ---------------------------------------------------------------
    LINKS = """[
      {"label": "Documentation", "url": "https://sigmaos.example/docs",
       "category": "learn"},
      {"label": "Forum", "url": "https://forums.sigmaos.example",
       "category": "community"},
      {"label": "Source", "url": "https://github.com/sigmaos", "category": "learn"}
    ]"""
    links = parse_links(LINKS)
    assert [l["label"] for l in links] == ["Documentation", "Forum", "Source"]
    groups = group_links(links)
    assert sorted(groups) == ["community", "learn"]
    assert [l["label"] for l in groups["learn"]] == ["Documentation", "Source"]
    text = render_links(links)
    assert text.splitlines()[0] == "[community]"     # categories sorted
    assert "https://sigmaos.example/docs" in text
    assert text == render_links(links)               # deterministic
    for bad in ("not json", "[]",
                # script handlers are never accepted
                '[{"label": "X", "url": "javascript:alert(1)"}]',
                '[{"label": "X", "url": "data:text/html,<script>"}]',
                '[{"label": "X", "url": "ftp://files.example"}]',
                '[{"label": "X", "url": "file:///etc/shadow"}]',
                # whitespace in url
                '[{"label": "X", "url": "https://a.example/ b"}]',
                # duplicate label
                '[{"label": "X", "url": "https://a.example"},'
                ' {"label": "X", "url": "https://b.example"}]',
                '[{"label": "", "url": "https://a.example"}]',
                '[{"label": "X", "url": "https://a.example",'
                ' "category": "Big Cat"}]',
                '[{"label": "X"}]'):
        try:
            parse_links(bad)
        except WelcomeError:
            pass
        else:
            raise AssertionError(f"links should have been rejected: {bad}")

    # --- tour ----------------------------------------------------------------
    TOUR = """{"stops": [
      {"id": "desktop", "title": "Meet the desktop", "duration": 30},
      {"id": "apps", "title": "Install an app", "duration": 45},
      {"id": "settings", "title": "Tune your settings", "duration": 60}
    ]}"""
    tour = build_tour(TOUR)
    assert [s["at"] for s in tour["stops"]] == [0, 30, 75]
    assert tour["total"] == 135
    assert format_duration(135) == "02:15"
    assert format_duration(30) == "00:30"
    assert format_duration(9) == "00:09"
    assert format_duration(0) == "00:00"
    plan = format_tour(tour)
    assert plan.splitlines()[0] == "[00:00] desktop  Meet the desktop"
    assert plan.splitlines()[2] == "[01:15] settings  Tune your settings"
    assert plan.splitlines()[3] == "total 02:15 (3 stops)"
    assert plan == format_tour(tour)                 # deterministic
    for bad in ('{"stops": []}',
                '{"stops": "x"}',
                '{"stops": [{"id": "a", "title": "A", "duration": 2}]}',   # < 5s
                '{"stops": [{"id": "a", "title": "A", "duration": 700}]}',  # > 600
                '{"stops": [{"id": "a", "title": "A", "duration": "30"}]}',
                '{"stops": [{"id": "a", "title": "A", "duration": true}]}',
                '{"stops": [{"id": "a", "duration": 30}]}',
                '{"stops": [{"id": "a", "title": "A"}]}',
                '{"stops": [{"id": "a", "title": "A", "duration": 30},'
                ' {"id": "a", "title": "B", "duration": 30}]}'):
        try:
            build_tour(bad)
        except WelcomeError:
            pass
        else:
            raise AssertionError(f"tour should have been rejected: {bad}")
    for bad in (-1, "30", None, True):
        try:
            format_duration(bad)
        except WelcomeError:
            pass
        else:
            raise AssertionError(f"duration should have been rejected: {bad!r}")

    # --- finish state (tempfile only, explicit timestamps) -------------------
    state = finish_state("SigmaOS", "1.0", 1700000000)
    assert state == {"product": "SigmaOS", "version": "1.0", "finished": True,
                     "timestamp": 1700000000}
    assert is_finished(state, "SigmaOS") is True
    assert is_finished(state, "SigmaOS-try") is False
    assert "SigmaOS 1.0" in finish_text(state)
    assert finish_state("SigmaOS", "1.0", 1700000000) == state  # deterministic
    for bad_call in ((finish_state, ("", "1.0", 1)),
                     (finish_state, ("S", "1.0", -1)),
                     (finish_state, ("S", "1.0", "now")),
                     (finish_state, ("S", "1.0", True))):
        try:
            bad_call[0](*bad_call[1])
        except WelcomeError:
            pass
        else:
            raise AssertionError(f"should have rejected: {bad_call}")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "state.json")
        save_state(path, state)
        assert load_state(path) == state
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        assert raw["finished"] is True and raw["timestamp"] == 1700000000
        save_state(path, state)                       # idempotent rewrite
        with open(path, "r", encoding="utf-8") as fh:
            assert json.load(fh) == raw
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("not json")
        try:
            load_state(path)
        except WelcomeError:
            pass
        else:
            raise AssertionError("corrupt state not rejected")
        for bad_state in (
                {"product": "S", "version": "1", "finished": True},  # no ts
                {"product": "S", "version": "1", "finished": True,
                 "timestamp": 1, "extra": 2},                       # unknown
                {"product": "S", "version": "1", "finished": False,
                 "timestamp": 1},                                   # not finished
                {"version": "1", "finished": True, "timestamp": 1},  # no product
                {"product": "S", "version": "1", "finished": True,
                 "timestamp": -5}):
            try:
                _validate_state(bad_state)
            except WelcomeError:
                pass
            else:
                raise AssertionError(f"state should have been rejected: {bad_state}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
