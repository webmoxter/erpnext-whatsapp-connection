# GCP test runner

Ordinary CI requires a repository-authorized Linux x64 runner carrying all of
`self-hosted`, `linux`, `x64`, `gcp`, `whatsapp-ci`. A runner registered only to
another repository is not eligible. Keep any existing runner/service intact;
register an additional service in a separate directory and OS account, or use
an approved organization runner group explicitly accessible to this repository.

An administrator must open this repository's Settings → Actions → Runners →
New self-hosted runner, select Linux x64, and follow GitHub's current versioned,
checksummed installation commands **on the approved GCP CI host**. Configure
the runner with `gcp,whatsapp-ci` custom labels and a distinct service name,
such as `whatsapp-gcp-ci-01`. Registration uses GitHub's short-lived runner
registration token; do not create/store a new PAT, reuse another runner's
credentials, print the token, or place it in source/logs/artifacts.

The host needs Docker with Compose, Git, curl, Python/Node setup-action
prerequisites and sufficient free disk for one isolated Frappe image/site.
Run as a dedicated non-root CI account with its own writable home/tool cache.
Do not copy production databases, keys, WhatsApp authentication, signing keys
or live credentials to this account. Limit its access to this repository's
trusted CI workflows. Public fork pull requests are deliberately not executed
on the self-hosted lane; missing fork validation is not a passing check.

The three ordinary jobs may queue sequentially on a single runner. Docker
projects remain unique to run/attempt, with guarded project-scoped cleanup;
never prune another project's volumes, stop an existing repository's runner,
or run the tests against live sites. The production release workflow and its
signing, exact-commit CI, token and immutable publication controls are unchanged.
Do not assign publication privileges to this ordinary test lane.

Before declaring CI ready, verify the service is online for **this repository**,
all selected checks actually execute, and the real Frappe integration passes.
Workflow labels alone are not evidence of a registered/working runner.
