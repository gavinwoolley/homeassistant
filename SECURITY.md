# Security

This is a **read-only mirror**, force-pushed from a private source repo by an automated
sanitizer (see [`publish/README.md`](publish/README.md)). Pull requests and pushes to this
repo directly aren't accepted — any sync from the private repo overwrites the branch outright.

## Reporting an issue

If you spot something that looks like it might be real (a credential, a coordinate, a name
that shouldn't be here — the sanitizer is thorough but not infallible), please
[open an issue](../../issues/new) rather than a public discussion, or use GitHub's
[private vulnerability reporting](../../security/advisories/new) if you'd rather it not be
visible until addressed. Either way, it'll get fixed at the source and the next sync will
carry the fix here.

## Scope

This repo describes a personal home automation setup. There's no hosted service, API, or
user data involved — "security" here means "did the sanitizer actually strip everything it
should have," not application security in the usual sense.
