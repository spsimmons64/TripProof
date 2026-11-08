#!/usr/bin/env bash
# Build the TripProofDriver store app for Android.
#
#   ./deploy/app.sh            the server is dev.tripproofonline.com
#   API=https://app.tripproofonline.com ./deploy/app.sh
#
# Produces, in web/release/:
#   TripProofDriver-<version>.apk   installs directly on an Android phone (for testing)
#   TripProofDriver-<version>.aab   what Google Play takes
#
# Needs JDK 21 and the Android SDK (~/Android/jdk, ~/Android/Sdk) and the upload key named by
# web/android/keystore.properties. Without the key the files come out unsigned and Play refuses them.
#
# Notifications are built in only when web/android/app/google-services.json is there (downloaded
# from the Firebase console). Without it the app still runs; drivers are texted instead.
#
# iPhone builds are made in the cloud by Codemagic (codemagic.yaml), there being no Mac here.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB="$ROOT/web"
API="${API:-https://dev.tripproofonline.com}"
export JAVA_HOME="${JAVA_HOME:-$HOME/Android/jdk}"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mSTOPPED: %s\033[0m\n' "$*"; exit 1; }

[ -x "$JAVA_HOME/bin/javac" ] || die "No JDK at $JAVA_HOME"
[ -d "$ANDROID_HOME/platforms" ] || die "No Android SDK at $ANDROID_HOME"

PUSH=0
[ -s "$WEB/android/app/google-services.json" ] && PUSH=1
# The version the stores show, from package.json; the build number always goes up, so Play never
# refuses one as older than the last: year, month, day, hour and ten-minute, Eastern time. (Play
# allows up to 2100000000, so the full minute would not fit.)
VERSION="$(node -p "require('$WEB/package.json').appVersion || '1.0.0'")"
BUILD="$(TZ=America/New_York date +%y%m%d%H%M | cut -c1-9)"

say "Building the driver app for $API (notifications: $([ $PUSH = 1 ] && echo on || echo 'off - no google-services.json'))"
cd "$WEB"
VITE_API_BASE="$API" VITE_PUSH="$PUSH" npx vite build -c vite.app.config.js --logLevel warn
npx cap sync android >/dev/null

say "Compiling version $VERSION ($BUILD)"
cd "$WEB/android"
./gradlew -q --console=plain assembleRelease bundleRelease -PversionCode="$BUILD" -PversionName="$VERSION"

mkdir -p "$WEB/release"
cp app/build/outputs/apk/release/app-release*.apk "$WEB/release/TripProofDriver-$VERSION-$BUILD.apk"
cp app/build/outputs/bundle/release/app-release.aab "$WEB/release/TripProofDriver-$VERSION-$BUILD.aab"
[ -f keystore.properties ] || say "WARNING: no keystore.properties - these are UNSIGNED and will not install or upload"
say "Done"
ls -lh "$WEB/release/"*"$BUILD"*
