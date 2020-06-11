#!/usr/bin/env bash

set -e

if [ "$TRAVIS_PULL_REQUEST" == "true" ]; then
  echo "We should not deploy pull requests!"
  exit 1
fi

cat <<'HEREDOC'
Build great build script is taken from https://github.com/KEINOS/Dockerfile_of_Alpine/blob/master/build-image.sh
===============================================================================
  Image builder for Paradox Alarm Interface Alpine image.
===============================================================================
This script builds Docker image for AMD64, ARM v6 and ARM v7 architecture. Then
pushes to Docker Hub the images made.
- Requirements:
    1. Experimental option must be enabled. (buildx command must be available to use as well)
    2. When running "docker buildx ls", the below platforms must be listed:
        - linux/arm/v6
        - linux/arm/v7
        - linux/arm64
        - linux/amd64
        - linux/386
===============================================================================
HEREDOC

export DOCKER_CLI_EXPERIMENTAL=enabled

[ 'true' = $(docker version --format {{.Client.Experimental}}) ] || {
   echo 'Docker daemon not in experimental mode.'
   exit 1
}

# -----------------------------------------------------------------------------
#  Common Variables
# -----------------------------------------------------------------------------
NAME_IMAGE='paradoxalarminterface/pai'
VERSION_ALPINE=3.11
VERSION_PYTHON=3.7

# -----------------------------------------------------------------------------
#  Functions
# -----------------------------------------------------------------------------

function build_push_pull_image () {
    echo "- BUILDING ${NAME_PLATFORM}"
    docker buildx build \
        --build-arg NAME_BASE=$NAME_BASE \
        --build-arg VERSION_ALPINE="${VERSION_ALPINE}" \
        --build-arg VERSION_PYTHON="${VERSION_PYTHON}" \
        --platform $NAME_PLATFORM \
        -t "${NAME_IMAGE}:${NAME_TAG}" \
        --push . && \
    echo "  PULLING BACK: ${NAME_IMAGE}:${NAME_TAG}" && \
    docker pull "${NAME_IMAGE}:${NAME_TAG}"

    return $?
}

function create_manifest () {
    echo '- Removing image from local:'
    docker image rm --force $1 2>/dev/null 1>/dev/null
    echo "- Creating manifest for: $1"
    echo "  With images: ${2}"
    docker manifest create $1 $2 --amend

    return $?
}

function login_docker () {
    echo -n '- Login to Docker: '
    echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin || {
        echo 'You need to login Docker Cloud/Hub first.'
        exit 1
    }
    echo 'OK'
}

function rewrite_variant_manifest () {
    echo "- Re-writing variant to: $3"
    docker manifest annotate $1 $2 --variant $3

    return $?
}

# -----------------------------------------------------------------------------
#  Main
# -----------------------------------------------------------------------------

# Current Alpine version info
echo '- Current Alpine version:' $VERSION_ALPINE

if [ -z "$TRAVIS_TAG" ]; then
  DOCKER_IMAGE_TAG=$(if [ "$TRAVIS_BRANCH" == "master" ]; then echo "latest"; else echo "$TRAVIS_BRANCH-latest"; fi)
else
  DOCKER_IMAGE_TAG="$TRAVIS_TAG"
fi

login_docker

docker buildx create --use

echo '- Start build:'
docker buildx inspect --bootstrap

# Build ARMv6
NAME_BASE='arm32v6/python'
NAME_TAG="${DOCKER_IMAGE_TAG}-armv6"
NAME_PLATFORM='linux/arm/v6'
build_push_pull_image

# Build ARMv7
NAME_BASE='arm32v7/python'
NAME_TAG="${DOCKER_IMAGE_TAG}-armv7"
NAME_PLATFORM='linux/arm/v7'
build_push_pull_image

# Build ARM64
NAME_BASE='arm64v8/python'
NAME_TAG="${DOCKER_IMAGE_TAG}-arm64"
NAME_PLATFORM='linux/arm64'
build_push_pull_image

# Build AMD64
NAME_BASE='python'
NAME_TAG="${DOCKER_IMAGE_TAG}-amd64"
NAME_PLATFORM='linux/amd64'
build_push_pull_image

# Build i386
NAME_BASE='i386/python'
NAME_TAG="${DOCKER_IMAGE_TAG}-i386"
NAME_PLATFORM='linux/386'
build_push_pull_image

echo "- Inspect built image of: ${NAME_IMAGE}"
docker buildx imagetools inspect $NAME_IMAGE

# Create manifest
LIST_IMAGE_INCLUDE="$NAME_IMAGE:${DOCKER_IMAGE_TAG}-armv6 $NAME_IMAGE:${DOCKER_IMAGE_TAG}-armv7 $NAME_IMAGE:${DOCKER_IMAGE_TAG}-arm64 $NAME_IMAGE:${DOCKER_IMAGE_TAG}-amd64 $NAME_IMAGE:${DOCKER_IMAGE_TAG}-i386"

echo "- Creating manifest for image: ${NAME_IMAGE} with: ${DOCKER_IMAGE_TAG} tag"
NAME_IMAGE_AND_TAG="${NAME_IMAGE}:${DOCKER_IMAGE_TAG}"
create_manifest  $NAME_IMAGE_AND_TAG "$LIST_IMAGE_INCLUDE"

rewrite_variant_manifest $NAME_IMAGE_AND_TAG $NAME_IMAGE:armv6 v6l
rewrite_variant_manifest $NAME_IMAGE_AND_TAG $NAME_IMAGE:armv7 v7l

docker manifest inspect $NAME_IMAGE_AND_TAG && \
docker manifest push $NAME_IMAGE_AND_TAG --purge
