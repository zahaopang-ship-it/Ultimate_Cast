from pathlib import Path

service = Path("app/src/main/java/com/example/screencast/MediaProjectionService.kt")
source = service.read_text(encoding="utf-8")
old = """            // Reuse the existing DLNA renderer selection to open the WebRTC receiver page
            // on the selected TV. The TV page itself asks the viewer to accept the session.
            controlUrl?.let { rendererUrl ->
                scope.launch {
                    runCatching { Dlna.play(rendererUrl, webRtcUrl) }
                        .onFailure { StreamState.transportStatus.value = "WebRTC ready · open TV link manually (${it.message})" }
                }
            }
"""
new = """            // This URL serves an HTML WebRTC receiver page, not playable media.
            // Do not pass it to DLNA AVTransport: many TVs then report "file not supported".
            // The user opens the displayed URL in the TV's browser instead.
            StreamState.transportStatus.value = "WebRTC ready · open receiver link in TV browser"
"""
if old not in source:
    raise SystemExit("Expected WebRTC DLNA block not found; refusing to apply an unsafe partial patch.")
service.write_text(source.replace(old, new, 1), encoding="utf-8")

activity = Path("app/src/main/java/com/example/screencast/MainActivity.kt")
source = activity.read_text(encoding="utf-8")
old_label = 'Text("Open on the TV browser · secret code included", fontSize = 13.sp, color = cs.onSurfaceVariant)'
new_label = 'Text(if (config.transport == "WEBRTC") "WebRTC receiver · open this link in the TV browser" else "Open on the TV browser · secret code included", fontSize = 13.sp, color = cs.onSurfaceVariant)'
if old_label not in source:
    raise SystemExit("Expected browser-link label not found; refusing to apply an unsafe partial patch.")
activity.write_text(source.replace(old_label, new_label, 1), encoding="utf-8")

gradle = Path("app/build.gradle.kts")
source = gradle.read_text(encoding="utf-8")
if 'versionCode = 6' not in source or 'versionName = "2.1.2"' not in source:
    raise SystemExit("Unexpected app version; refusing to apply release version patch.")
source = source.replace('versionCode = 6', 'versionCode = 7', 1)
source = source.replace('versionName = "2.1.2"', 'versionName = "2.1.3"', 1)
gradle.write_text(source, encoding="utf-8")
print("Applied ScreenCast Ultimate 2.1.3 WebRTC receiver-launch fix.")
