# ScreenCast Ultimate 2.1.0

Maintenance update to the 2.0 source archive; Android versionCode 3 / versionName 2.1.0.

Android screen mirroring over the local Wi-Fi network. The existing browser-based playback path is retained: Android MediaProjection -> OpenGL -> H.264 MediaCodec -> fragmented MP4 -> HTTP/MSE in the TV browser. Optional app-audio capture uses AudioPlaybackCapture -> AAC.

## Improvements in this build

- Browser playback now applies read backpressure: it requests the next network chunk only after the current MSE append completes. This prevents an unbounded JavaScript queue from accumulating stale video during slow playback.
- Live-edge recovery is less aggressive: the player only jumps forward when it is more than 1.25 seconds behind, targeting a 300 ms live buffer.
- AAC fragments use the encoder-provided presentation timestamp for each frame instead of accumulating a synthetic timestamp, reducing long-session audio drift.
- Dropped PCM blocks advance the audio input timeline, so a temporarily busy AAC encoder does not make later audio play progressively slower.
- EGL renderer resources are released on the capture thread before the video encoder is torn down.
- Android package version is now 2.0.0 (versionCode 2) and the app is branded ScreenCast Ultimate.

- Select 480p, 720p or 1080p output, 30 or 60 FPS, and 1–15 Mbps video bitrate. Settings are saved and apply to the next session.
- Adaptive bitrate now steps down after client queue congestion and cautiously recovers by 5% every 10 seconds after 20 seconds without a new congestion event; resolution remains fixed for the session.
- Audio capture is optional. Denying/turning off audio does not prevent video casting. Some source apps intentionally disallow playback capture.
- Live diagnostics show measured video FPS, encoded video bitrate, connected browser viewers, and dropped fragments.
- Session access code expanded from 6 to 16 random characters.
- HTTP request read timeout, maximum of 3 simultaneous viewers, queue overflow accounting, and keyframe resynchronization for slow viewers.
- TV browser playback keeps the existing MSE/fMP4 compatibility route and the DLNA discovery/control flow.

## Important compatibility notes

- 60 FPS and 1080p are device/encoder dependent. If a phone cannot sustain the selected profile, choose 480p or 720p at 30 FPS and a lower bitrate.
- AudioPlaybackCapture requires Android 10+ and the user's runtime permission. The source app must permit playback capture; protected or restricted apps may remain silent.
- The TV browser must support Media Source Extensions with H.264 (and AAC when audio is enabled). DLNA renderer support varies by vendor/model.
- The app's HTTP stream is intended for a trusted local Wi-Fi network. The session code is a basic access barrier, not TLS encryption. Do not expose port 8080 to the public internet.

## WebRTC status

WebRTC is **not enabled in this source build**. It needs a real peer-connection implementation plus signaling (offer/answer and ICE exchange), browser-side receiver code, lifecycle/reconnect handling, and device/TV interoperability tests. Adding only a WebRTC dependency or a UI switch would not create a working WebRTC transport. The existing HTTP/MSE path is deliberately preserved as the tested fallback until that complete path can be implemented and validated.

## Build

Open the project in Android Studio with JDK 17 and Android SDK 34 installed, then build the `app` debug variant. The archive does not include the Gradle wrapper, so Android Studio/Gradle must supply the build tooling.


## Version 2.1.0 transport notes

- MSE remains the compatibility path and carries fragmented MP4 with AAC app-audio capture when Android permits it. Audio and video fragments are queued by their MediaCodec presentation timestamps with a short cross-track reorder window. AAC timestamps are no longer advanced by a fixed frame duration when a late/dropped input block occurs.
- WebRTC is an optional, separate video path. It uses a local WebSocket signaling endpoint on TCP 8081 and a browser receiver page served on TCP 8080. A STUN server is configured for ICE; this is intended for same-LAN testing and does not include TURN relay support.
- WebRTC currently sends video only. App-audio capture and A/V sync are supported on the MSE path; WebRTC audio is not claimed as implemented.
- Smart-TV WebRTC support varies. If the TV browser lacks RTCPeerConnection, switch back to MSE. Test on the target TV firmware before relying on it.
- Build with JDK 17, Android SDK 34, Gradle 8.7. Dependency resolution requires network access.
