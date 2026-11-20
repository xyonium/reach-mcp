# bird-search vendor

Source: `mvanhorn/last30days-skill` → `skills/last30days/scripts/lib/vendor/bird-search` (main).

This bundled copy is the offline/first-boot fallback. Production uses
`deploy/update-bird-vendor.sh` to maintain `/config/reach-bird/current` from
upstream with a content-hash cache (unchanged = reuse; changed = download and
atomically swap). No GitHub PR or reach release is needed for that.

Manual fallback refresh: `./scripts/sync_bird_vendor.sh`.
The wrapper is MIT, based on `@steipete/bird` v0.8.0 by Peter Steinberger; see `LICENSE`.
