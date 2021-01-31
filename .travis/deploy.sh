#!/usr/bin/env bash

set -e

if [ "$TRAVIS_PULL_REQUEST" == "true" ]; then
  echo "We should not deploy pull requests!"
  exit 1
fi

if [ -z "$TRAVIS_TAG" ]; then
  DOCKER_IMAGE_TAG=$(if [ "$TRAVIS_BRANCH" == "master" ]; then echo "latest"; else echo "$TRAVIS_BRANCH-latest"; fi)
else
  DOCKER_IMAGE_TAG="$TRAVIS_TAG"
  if grep -q "$TRAVIS_TAG" paradox/__init__.py
  then
    echo "Git tag $TRAVIS_TAG matches VERSION in paradox/__init__.py"
  else
    echo "Git tag $TRAVIS_TAG does not match VERSION in paradox/__init__.py"
    cat paradox/__init__.py
    exit 1
  fi
fi

echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin

export DOCKER_IMAGE_TAG
export DOCKER_CLI_EXPERIMENTAL=enabled

docker run --rm --privileged multiarch/qemu-user-static:4.2.0-7 --reset -p yes
docker buildx create --use
docker buildx build --progress plain --platform linux/386,linux/amd64,linux/arm/v6,linux/arm64/v8 -t "paradoxalarminterface/pai:$DOCKER_IMAGE_TAG" --push .
