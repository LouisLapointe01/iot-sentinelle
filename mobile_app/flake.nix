{
  description = "Minimal React Native (Expo) development shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true;
          config.android_sdk.accept_license = true;
        };

        androidComposition = pkgs.androidenv.composeAndroidPackages {
          buildToolsVersions = [ "34.0.0" "35.0.0" "36.1.0" ];
          platformVersions = [ "34" "35" "36" ];
          includeEmulator = true;
          includeSources = false;
          includeSystemImages = true;
          systemImageTypes = [ "google_apis" ];
          abiVersions = [ "armeabi-v7a" "arm64-v8a" "x86_64" ];
          includeExtras = [ "extras;google;m2repository" "extras;android;m2repository" ];
          # Adding NDK and CMake
          includeNDK = true;
          ndkVersions = [ "27.1.12297006" "29.0.14206865" ];
          includeCmake = true;
          cmakeVersions = [ "3.22.1" "4.1.2" ];
        };

        androidSdk = androidComposition.androidsdk;
      in {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            nodejs_22
            jdk17
            jdk8
            androidSdk
            androidComposition.ndk-bundle
            direnv
            nix-direnv
            go-task
            watchman
            git
            github-cli
            unzip
            cmake
            nspr
            nss
            dbus
            at-spi2-core
            glib
            libglvnd
            xorg.libX11
            xorg.libXi
          ];

          shellHook = ''
            export LD_LIBRARY_PATH="${pkgs.nspr}/lib:${pkgs.nss}/lib:${pkgs.dbus.lib}/lib:${pkgs.at-spi2-core}/lib:${pkgs.glib.out}/lib:${pkgs.libglvnd}/lib:${pkgs.xorg.libX11}/lib:${pkgs.xorg.libXi}/lib:$LD_LIBRARY_PATH"
            export JAVA_HOME=${pkgs.jdk17}/lib/openjdk
            export JAVA8_HOME=${pkgs.jdk8}/lib/openjdk
            export ANDROID_HOME=${androidSdk}/libexec/android-sdk
            export ANDROID_SDK_ROOT=$ANDROID_HOME
            export ANDROID_NDK_HOME=${androidComposition.ndk-bundle}/libexec/android-sdk/ndk-bundle
            export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/tools:$ANDROID_HOME/tools/bin:$PATH
            echo "React Native dev shell ready"
            echo "Node: $(node --version)"
            echo "Java: $(java -version 2>&1 | head -n 1)"
            echo "Android SDK: $ANDROID_HOME"
          '';
        };
      });
}