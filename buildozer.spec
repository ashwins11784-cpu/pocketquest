[app]
title = Pocket Quest
package.name = pocketquest
package.domain = org.me
source.dir = .
source.include_exts = py,png,jpg,json
version = 0.1
requirements = python3,pygame
p4a.bootstrap = sdl2
orientation = landscape
fullscreen = 1
android.archs = arm64-v8a
android.api = 33
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
