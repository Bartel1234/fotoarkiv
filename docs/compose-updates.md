# Compose updates from published releases

In your existing single-container stack, change the image and add a pull policy:

```yaml
services:
  fotoarkiv:
    image: ghcr.io/bartel1234/fotoarkiv:beta
    pull_policy: always
    # Keep the remaining settings, ports, environment and persistent mounts.
```

The beta tag follows the newest published beta release with a matching prebuilt image. Publishing source commits alone does not advance it. GitHub Actions verifies that the image revision matches the release tag before updating the alias; a missing or invalid image leaves the previous alias intact. Numbered image tags remain available.

Save the existing stack in Unraid Compose Manager and choose Update. If your plugin only shows Compose Pull and Compose Up, use them in that order. Updates briefly restart the container; finish or stop active backups first. Your existing .env, Google profiles and backup paths must be retained.

Terminal equivalent:

```sh
docker compose pull
docker compose up -d
```

To pin a version or roll back, replace beta with an available numbered image tag, such as 0.2.0-beta.2, and pull/recreate the stack. Container updates do not fetch new compose settings. Any future release requiring new settings must document them separately.
