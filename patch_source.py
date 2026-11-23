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
new = """            // WebRTC is HTML, not a DLNA media resource. Try launching the TV browser via DIAL.
            val selectedHost = controlUrl?.let { runCatching { java.net.URL(it).host }.getOrNull() }
            scope.launch {
                val launched = selectedHost != null && runCatching {
                    Dial.launchBrowserUrl(this@MediaProjectionService, selectedHost, webRtcUrl)
                }.getOrDefault(false)
                StreamState.transportStatus.value = if (launched) {
                    "WebRTC receiver opened on TV · accept the connection there"
                } else {
                    "WebRTC ready · TV browser launch unavailable; open the link in its browser"
                }
            }
"""
if old not in source:
    raise SystemExit("Expected WebRTC/DLNA block not found; refusing partial patch.")
source = source.replace(old, new, 1)
old_stop = "        controlUrl?.let { runBlocking(Dispatchers.IO) { withTimeoutOrNull(1500) { Dlna.stop(it) } } }"
new_stop = '        if (sessionConfig.transport == "MSE") controlUrl?.let { runBlocking(Dispatchers.IO) { withTimeoutOrNull(1500) { Dlna.stop(it) } } }'
if old_stop not in source:
    raise SystemExit("Expected shutdown block not found; refusing partial patch.")
source = source.replace(old_stop, new_stop, 1)
service.write_text(source, encoding="utf-8")

dial = Path("app/src/main/java/com/example/screencast/Dial.kt")
dial.write_text(r'''package com.example.screencast

import android.content.Context
import android.net.wifi.WifiManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.SocketTimeoutException
import java.net.URL

/** DIAL browser launch attempt. URL payload handling depends on TV firmware support. */
object Dial {
    private const val DIAL_ST = "urn:dial-multiscreen-org:service:dial:1"

    suspend fun launchBrowserUrl(context: Context, targetHost: String, receiverUrl: String): Boolean =
        withContext(Dispatchers.IO) {
            val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            val lock = wifi.createMulticastLock("dial-discovery").apply {
                setReferenceCounted(false)
                acquire()
            }
            try {
                for (location in discover(targetHost)) {
                    val base = applicationBase(location)?.trimEnd('/') ?: continue
                    for (name in listOf("Browser", "browser", "Internet")) {
                        val appUrl = "$base/$name"
                        val available = request(appUrl, "GET", null) ?: continue
                        if (available !in 200..299) continue
                        val launched = request(appUrl, "POST", receiverUrl.toByteArray(Charsets.UTF_8))
                        if (launched == 201 || launched == 200 || launched == 202) return@withContext true
                    }
                }
                false
            } finally {
                lock.release()
            }
        }

    private fun discover(targetHost: String): List<String> {
        val found = linkedSetOf<String>()
        DatagramSocket().use { socket ->
            socket.soTimeout = 700
            val query = ("M-SEARCH * HTTP/1.1\r\n" +
                "HOST: 239.255.255.250:1900\r\n" +
                "MAN: \"ssdp:discover\"\r\n" +
                "MX: 2\r\nST: $DIAL_ST\r\n\r\n").toByteArray()
            socket.send(DatagramPacket(query, query.size, InetAddress.getByName("239.255.255.250"), 1900))
            val deadline = System.currentTimeMillis() + 3500
            val buffer = ByteArray(4096)
            while (System.currentTimeMillis() < deadline) {
                try {
                    val packet = DatagramPacket(buffer, buffer.size)
                    socket.receive(packet)
                    val response = String(packet.data, 0, packet.length, Charsets.UTF_8)
                    val location = Regex("(?im)^location:\\s*(https?://[^\\r\\n]+)")
                        .find(response)?.groupValues?.get(1)?.trim() ?: continue
                    if (runCatching { URL(location).host.equals(targetHost, true) }.getOrDefault(false)) {
                        found.add(location)
                    }
                } catch (_: SocketTimeoutException) {
                    // Keep listening until the bounded discovery window ends.
                }
            }
        }
        return found.toList()
    }

    private fun applicationBase(location: String): String? {
        val connection = (URL(location).openConnection() as HttpURLConnection).apply {
            connectTimeout = 3500
            readTimeout = 3500
        }
        return try {
            connection.responseCode
            connection.getHeaderField("Application-URL")
        } finally {
            connection.disconnect()
        }
    }

    private fun request(url: String, method: String, body: ByteArray?): Int? {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 3500
            readTimeout = 4500
            requestMethod = method
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "text/plain; charset=utf-8")
                setFixedLengthStreamingMode(body.size)
            }
        }
        return try {
            if (body != null) connection.outputStream.use { it.write(body) }
            connection.responseCode
        } catch (_: Exception) {
            null
        } finally {
            connection.disconnect()
        }
    }
}
''', encoding="utf-8")
dial_source = dial.read_text(encoding="utf-8")
dial_source = dial_source.replace(r"\\r\\n", r"\r\n")
dial_source = dial_source.replace(r"\\\\s", r"\\s").replace(r"\\\\r", r"\\r").replace(r"\\\\n", r"\\n")
dial.write_text(dial_source, encoding="utf-8")

activity = Path("app/src/main/java/com/example/screencast/MainActivity.kt")
source = activity.read_text(encoding="utf-8")
old_label = 'Text("Open on the TV browser · secret code included", fontSize = 13.sp, color = cs.onSurfaceVariant)'
new_label = 'Text(if (config.transport == "WEBRTC") "WebRTC receiver · automatic TV launch when supported" else "Open on the TV browser · secret code included", fontSize = 13.sp, color = cs.onSurfaceVariant)'
if old_label in source:
    source = source.replace(old_label, new_label, 1)
elif "automatic TV launch when supported" not in source:
    raise SystemExit("Expected browser-link label not found; refusing partial patch.")
activity.write_text(source, encoding="utf-8")

gradle = Path("app/build.gradle.kts")
source = gradle.read_text(encoding="utf-8")
if 'versionCode = 6' not in source or 'versionName = "2.1.2"' not in source:
    raise SystemExit("Unexpected base version; refusing release version patch.")
source = source.replace('versionCode = 6', 'versionCode = 8', 1)
source = source.replace('versionName = "2.1.2"', 'versionName = "2.1.4"', 1)
gradle.write_text(source, encoding="utf-8")
print("Applied 2.1.4 DIAL browser-launch attempt. MSE implementation left unchanged.")


# Temporary source audit for WebRTC low-latency tuning and VIDAA permissions.
import re
for p in Path(".").rglob("*"):
    if not p.is_file() or p.suffix.lower() not in {".kt", ".java", ".html", ".js", ".xml", ".gradle", ".kts"}:
        continue
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        continue
    hits = [i for i, line in enumerate(lines) if re.search(
        r"webrtc|jitter|buffer|latency|bitrate|framerate|frame.?rate|key.?frame|icecandidate|peerconnection|videocapturer|CHANGE_WIFI_MULTICAST_STATE|uses-permission",
        line, re.I)]
    if hits:
        print("\n=== AUDIT", p, "===")
        shown = set()
        for i in hits:
            for j in range(max(0, i-2), min(len(lines), i+3)):
                if j not in shown:
                    print(f"{j+1}: {lines[j]}")
                    shown.add(j)

# Dump the WebRTC-only implementation for a targeted low-latency patch.
for name in [
    "app/src/main/java/com/example/screencast/WebRtcTransport.kt",
    "app/src/main/java/com/example/screencast/LiveServer.kt",
    "app/src/main/java/com/example/screencast/WebRtcProjectionCapturer.kt",
]:
    p = Path(name)
    print("\n=== FULL SOURCE", name, "===")
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        print(f"{n}: {line}")


# WebRTC-only low-latency tuning. MSE code paths and MSE HTML are intentionally untouched.
webrtc = Path("app/src/main/java/com/example/screencast/WebRtcTransport.kt")
source = webrtc.read_text(encoding="utf-8")

def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one {label} target, found {count}; refusing build.")
    return text.replace(old, new, 1)

source = replace_once(
    source,
    'source = factory!!.createVideoSource(false)',
    'source = factory!!.createVideoSource(true)',
    "WebRTC screen-content source mode"
)
source = replace_once(
    source,
    'val ice = listOf(PeerConnection.IceServer.builder("stun:stun.l.google.com:19302").createIceServer())',
    'val ice = emptyList<PeerConnection.IceServer>() // Same-LAN casting: host ICE candidates only; no Internet STUN dependency.',
    "WebRTC local-only ICE configuration"
)
source = replace_once(
    source,
    'val dcInit = DataChannel.Init().apply { ordered = true }',
    'val dcInit = DataChannel.Init().apply { ordered = false; maxRetransmits = 0 }',
    "WebRTC real-time audio data channel"
)
source = replace_once(
    source,
    'setBufferSizeInBytes(maxOf(minBuffer * 4, 32_768))',
    'setBufferSizeInBytes(maxOf(minBuffer, 8_192))',
    "WebRTC playback audio capture buffer"
)
source = replace_once(
    source,
    'channel.bufferedAmount() < 256_000',
    'channel.bufferedAmount() < 12_000',
    "WebRTC audio queue ceiling"
)
webrtc.write_text(source, encoding="utf-8")

live = Path("app/src/main/java/com/example/screencast/LiveServer.kt")
source = live.read_text(encoding="utf-8")
source = replace_once(
    source,
    "pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});",
    "pc=new RTCPeerConnection({iceServers:[],bundlePolicy:'max-bundle',rtcpMuxPolicy:'require'});",
    "WebRTC receiver local-only ICE configuration"
)
source = replace_once(
    source,
    "audioCtx=new (window.AudioContext||window.webkitAudioContext)({sampleRate:48000});",
    "audioCtx=new (window.AudioContext||window.webkitAudioContext)({sampleRate:48000,latencyHint:'interactive'});",
    "WebRTC interactive audio output"
)
source = replace_once(
    source,
    "pc.ontrack=e=>{video.srcObject=e.streams[0];video.play().catch(()=>{});status.textContent='Connected · WebRTC';};",
    "pc.ontrack=e=>{try{e.receiver.playoutDelayHint=0;}catch(_){}try{e.receiver.jitterBufferTarget=0;}catch(_){}video.srcObject=e.streams[0];video.play().catch(()=>{});status.textContent='Connected · WebRTC';};",
    "WebRTC minimum receiver playout buffering"
)
source = replace_once(
    source,
    "const now=audioCtx.currentTime;if(nextAudioTime<now+0.025||nextAudioTime>now+0.25)nextAudioTime=now+0.06;",
    "const now=audioCtx.currentTime;if(nextAudioTime<now+0.01||nextAudioTime>now+0.10)nextAudioTime=now+0.02;",
    "WebRTC audio scheduling horizon"
)
live.write_text(source, encoding="utf-8")

# Bump version while retaining the original 2.1.2 source archive as the build base.
gradle = Path("app/build.gradle.kts")
source = gradle.read_text(encoding="utf-8")
if 'versionCode = 6' in source and 'versionName = "2.1.2"' in source:
    source = source.replace('versionCode = 6', 'versionCode = 9', 1)
    source = source.replace('versionName = "2.1.2"', 'versionName = "2.1.5"', 1)
elif 'versionCode = 8' in source and 'versionName = "2.1.4"' in source:
    source = source.replace('versionCode = 8', 'versionCode = 9', 1)
    source = source.replace('versionName = "2.1.4"', 'versionName = "2.1.5"', 1)
elif not ('versionCode = 9' in source and 'versionName = "2.1.5"' in source):
    raise SystemExit("Unexpected base version; refusing release version patch.")
gradle.write_text(source, encoding="utf-8")
print("Applied 2.1.5 WebRTC local-network and low-latency tuning. MSE implementation left unchanged.")
