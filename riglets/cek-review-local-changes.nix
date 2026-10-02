# Thin shim. Everything lives in lib/cek-review.nix; rigup derives the
# riglet name from this filename, so this file must define exactly
# `cek-review-local-changes`.
self:
(import ../lib/cek-review.nix { inherit self; }).cek-review-local-changes