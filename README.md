# NASTool Cloud115

This image is based on `kleinersource/nastool` and adds a new transfer mode:

```text
115云端移动
```

NASTool still handles recognition, classification and renaming. The new transfer mode maps the local source path to a 115 cloud path, then moves and renames the file directly inside 115 cloud storage.

## Build

```bash
docker build -t your-dockerhub-name/nastool-cloud115:latest .
```

## Publish

```bash
docker login
docker push your-dockerhub-name/nastool-cloud115:latest
```

## Publish with GitHub Actions

This repository includes `.github/workflows/dockerhub.yml`.

Create two GitHub repository secrets:

```text
DOCKERHUB_USERNAME=your Docker Hub username
DOCKERHUB_TOKEN=your Docker Hub access token
```

Then push this project to GitHub and run the workflow:

```text
Actions -> Build and Push Docker Image -> Run workflow
```

The workflow publishes:

```text
your-dockerhub-name/nastool-cloud115:latest
```

## Pull

```bash
docker pull your-dockerhub-name/nastool-cloud115:latest
```

## Runtime configuration

Put your 115 cookie in:

```text
./config/115.cookie
```

Use these environment variables:

```text
NASTOOL_AUTO_UPDATE=false
CLOUD115_COOKIE_FILE=/config/115.cookie
CLOUD115_SRC_PREFIX=/root/NASTOOL/NASTOOL/nastool
CLOUD115_REMOTE_SRC_ROOT=/nastool
CLOUD115_ON_CONFLICT=fail
```

Path mapping example:

```text
Local source:
/root/NASTOOL/NASTOOL/nastool/Shows/Test.S01E01.mkv

115 source:
/nastool/Shows/Test.S01E01.mkv
```

NASTool target paths should use 115 cloud paths, for example:

```text
/Media/TV/Test (2026)/Season 1/Test - S01E01.mkv
```

## Notes

- Keep `NASTOOL_AUTO_UPDATE=false`; auto-update may overwrite patched files.
- Test with a small folder first.
- `CLOUD115_ON_CONFLICT=fail` stops when the target file already exists.
- `CLOUD115_ON_CONFLICT=skip` treats existing target files as success.
