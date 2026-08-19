#!/usr/bin/env bash
# Publish the generated guide to this repository's GitHub wiki.
#
# The wiki is a SEPARATE repository (`<repo>.wiki.git`), which is the whole
# reason this script exists: nothing in `./test.sh` or `docs/build.py` can see
# it, so it goes stale silently. It has three times already -- once behind by a
# rebuild nobody published, twice diverged because a page had been edited in
# GitHub's web editor. A third way was found later: a page the build STOPS
# generating stayed on the wiki, rendering and answering searches with nothing
# behind it, because copying pages in never removes one. All three are handled
# here rather than left to be noticed.
#
#   ./tools/publish_wiki.sh              rebuild, sync, push
#   ./tools/publish_wiki.sh --dry-run    ...everything but the push
#
# Pages are OUTPUT. Editing one in the web editor works until the next run of
# this script overwrites it -- which is what `_Footer.md` tells every reader.
set -eu
DIR=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

REMOTE=$(git -C "$DIR" remote get-url origin 2>/dev/null || true)
[ -n "$REMOTE" ] || { echo "no 'origin' remote -- publish the repository first"; exit 1; }
WIKI=${REMOTE%.git}.wiki.git

# 1. regenerate. build.py refuses to write if a check fails, so a broken guide
#    never reaches the wiki -- the exit status is what enforces that here.
echo "  building..."
python3 "$DIR/docs/build.py" >/dev/null

# 2. take the wiki as it is NOW, so a page edited in the web editor is a merge
#    base rather than a rejected push. `--depth 1` is enough: this only ever
#    adds one commit on top of whatever is there.
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
echo "  fetching $WIKI"
if ! git clone -q --depth 1 "$WIKI" "$WORK/w" 2>/dev/null; then
    echo "  the wiki repository does not exist yet."
    echo "  GitHub creates it only after the first page is made in the browser:"
    echo "      ${REMOTE%.git}/wiki  ->  Create the first page  ->  save anything"
    exit 1
fi

# 3. the generated pages replace whatever is there, including hand edits -- and a
#    page the build NO LONGER produces is deleted rather than left behind. An
#    orphan still renders, still answers a search and still turns up in the
#    sidebar's neighbours, with nothing generating it and no gate reading it,
#    which is the same silent staleness this script exists to prevent. Only
#    `.md` is managed: an image uploaded through the web editor is not ours.
PAGES=$(ls "$DIR"/wiki/*.md 2>/dev/null | wc -l)
[ "$PAGES" -ge 5 ] || {
    echo "  refusing to publish $PAGES page(s) -- the build looks broken"; exit 1; }
cd "$WORK/w"
for p in *.md; do
    [ -e "$p" ] || continue                  # an empty wiki: nothing to orphan
    [ -e "$DIR/wiki/$p" ] || { echo "  removing orphan: $p"; git rm -q "$p"; }
done
cp "$DIR"/wiki/*.md "$WORK/w/"
git add -A
if git diff --cached --quiet; then
    echo "  already up to date"
    exit 0
fi
git diff --cached --stat | tail -3

[ "$DRY" = 1 ] && { echo "  --dry-run: not pushing"; exit 0; }

git -c user.name="$(git -C "$DIR" log -1 --format='%an')" \
    -c user.email="$(git -C "$DIR" log -1 --format='%ae')" \
    commit -q -m "the guide, generated from docs/"
git push -q origin

# 4. ...and read it back, because "pushed" is not the same as "correct"
cd "$WORK" && rm -rf check && git clone -q --depth 1 "$WIKI" check
bad=0
for f in "$DIR"/wiki/*.md; do
    cmp -s "$f" "check/$(basename "$f")" || { echo "  DIFFERS after push: $(basename "$f")"; bad=1; }
done
# ...and nothing the build does not generate survived the push, which is the
# half a per-page comparison cannot see.
for f in "$WORK"/check/*.md; do
    [ -e "$f" ] || continue
    [ -e "$DIR/wiki/$(basename "$f")" ] || {
        echo "  ORPHAN after push: $(basename "$f")"; bad=1; }
done
[ "$bad" = 0 ] && echo "  published: $PAGES pages, verified against the remote"
exit "$bad"
