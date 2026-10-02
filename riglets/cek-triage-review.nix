# Thin shim. Everything lives in lib/cek-review.nix; rigup derives the
# riglet name from this filename, so this file must define exactly
# `cek-triage-review`.
self:
(import ../lib/cek-review.nix { inherit self; }).cek-triage-review