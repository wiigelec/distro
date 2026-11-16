#!/usr/bin/env bash
set -euo pipefail

# Executed in the shared Build native recipe sandbox. The payload is independent.
: "${DISTRO_ROOT_DIR:?missing isolated package staging destination}"
root="$DISTRO_ROOT_DIR"
[[ -d "$root" && ! -L "$root" ]] || { echo 'invalid staging root' >&2; exit 1; }

# Selected FS-004 real directories and exact modes.
for rel in etc usr usr/bin usr/lib usr/include usr/share var var/lib var/cache var/log run dev; do
    install -d -m 0755 "$root/$rel"
done
install -d -m 1777 "$root/tmp" "$root/var/tmp"
install -d -m 0555 "$root/proc" "$root/sys"

# Merged-/usr links are target-root-relative, never host absolute links.
ln -s usr/bin "$root/bin"
ln -s usr/bin "$root/sbin"
ln -s usr/lib "$root/lib"
ln -s usr/lib "$root/lib64"
ln -s bin "$root/usr/sbin"
ln -s lib "$root/usr/lib64"
