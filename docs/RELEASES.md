# Release standard

Production releases use signed annotated tags named `vMAJOR.MINOR.PATCH`.

The release workflow:

1. verifies the tag against `release/trusted-release-signers`;
2. reruns Python, repository, gateway, syntax, package, and secret checks;
3. builds the Python wheel, source distribution, and tagged source archive;
4. publishes the gateway under a unique semantic version and source-commit tag;
5. records the gateway digest and every asset SHA-256 in `release-manifest.json`;
6. creates a draft release with every asset, then publishes it atomically.

Repository-level immutable releases must remain enabled. GitHub then locks the
tag and assets and generates a release attestation. A release fails closed if the
tag or image identity was previously used.

Consumers must verify the GitHub release attestation, manifest commit, artifact
checksums, and gateway digest before installation.
