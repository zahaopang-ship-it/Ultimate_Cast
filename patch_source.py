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
new_stop = "        if (sessionConfig.transport == \\"MSE\\") controlUrl?.let { runBlocking(Dispatchers.IO) { withTimeoutOrNull(1500) { Dlna.stop(it) } } }"
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
            val query = ("M-SEARCH * HTTP/1.1\\r\\n" +
                "HOST: 239.255.255.250:1900\\r\\n" +
                "MAN: \\"ssdp:discover\\"\\r\\n" +
                "MX: 2\\r\\nST: $DIAL_ST\\r\\n\\r\\n").toByteArray()
            socket.send(DatagramPacket(query, query.size, InetAddress.getByName("239.255.255.250"), 1900))
            val deadline = System.currentTimeMillis() + 3500
            val buffer = ByteArray(4096)
            while (System.currentTimeMillis() < deadline) {
                try {
                    val packet = DatagramPacket(buffer, buffer.size)
                    socket.receive(packet)
                    val response = String(packet.data, 0, packet.length, Charsets.UTF_8)
                    val location = Regex("(?im)^location:\\\\s*(https?://[^\\\\r\\\\n]+)")
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
