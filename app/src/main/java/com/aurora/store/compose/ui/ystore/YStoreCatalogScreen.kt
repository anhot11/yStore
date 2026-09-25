package com.aurora.store.compose.ui.ystore

import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Environment
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil3.compose.AsyncImage
import com.aurora.store.R
import com.aurora.store.data.model.YStoreGame
import com.aurora.store.data.network.YStoreApiClient
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun YStoreCatalogScreen(
    onNavigateBack: (() -> Unit)? = null
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()

    var games by remember { mutableStateOf<List<YStoreGame>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var selectedSource by remember { mutableStateOf("all") }
    var selectedTag by remember { mutableStateOf<String?>(null) }
    var searchQuery by remember { mutableStateOf("") }
    var showSearch by remember { mutableStateOf(false) }
    var showSettingsDialog by remember { mutableStateOf(false) }
    var showPublishInfoDialog by remember { mutableStateOf(false) }

    fun loadGames() {
        coroutineScope.launch {
            isLoading = true
            val isHot = selectedSource == "hot"
            val sourceParam = if (isHot) "itchio" else if (selectedSource == "all") null else selectedSource
            val sectionParam = if (isHot) "hot" else null

            val result = YStoreApiClient.fetchCatalog(
                context = context,
                source = sourceParam,
                section = sectionParam,
                tag = selectedTag
            )
            games = result.getOrDefault(emptyList())
            isLoading = false
        }
    }

    LaunchedEffect(selectedSource, selectedTag) {
        loadGames()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = "yStore - Catálogo de Juegos",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = "F-Droid • itch.io • Hot APKs • Comunidad",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                },
                actions = {
                    IconButton(onClick = { showSearch = !showSearch }) {
                        Icon(Icons.Default.Search, contentDescription = "Buscar")
                    }
                    IconButton(onClick = { loadGames() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Recargar")
                    }
                    IconButton(onClick = { showPublishInfoDialog = true }) {
                        Icon(Icons.Default.Info, contentDescription = "Publicar")
                    }
                    IconButton(onClick = { showSettingsDialog = true }) {
                        Icon(Icons.Default.Settings, contentDescription = "Configurar Servidor")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            // Search Bar
            if (showSearch) {
                OutlinedTextField(
                    value = searchQuery,
                    onValueChange = { searchQuery = it },
                    label = { Text("Buscar en el catálogo...") },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 6.dp),
                    singleLine = true
                )
            }

            // Source Filter Chips
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FilterChip(
                    selected = selectedSource == "all",
                    onClick = { selectedSource = "all" },
                    label = { Text("🌟 Todos") }
                )
                FilterChip(
                    selected = selectedSource == "fdroid",
                    onClick = { selectedSource = "fdroid" },
                    label = { Text("🤖 F-Droid") }
                )
                FilterChip(
                    selected = selectedSource == "itchio",
                    onClick = { selectedSource = "itchio" },
                    label = { Text("🎮 itch.io") }
                )
                FilterChip(
                    selected = selectedSource == "hot",
                    onClick = { selectedSource = "hot" },
                    label = { Text("🔥 Hot (APKs)") }
                )
                FilterChip(
                    selected = selectedSource == "community",
                    onClick = { selectedSource = "community" },
                    label = { Text("👥 Comunidad") }
                )
            }

            // Category / Tag Chips
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                val tags = listOf("Action", "Puzzle", "Board", "Casual", "Strategy", "Word Game")
                FilterChip(
                    selected = selectedTag == null,
                    onClick = { selectedTag = null },
                    label = { Text("Todas categorías", fontSize = 12.sp) }
                )
                tags.forEach { tag ->
                    FilterChip(
                        selected = selectedTag == tag,
                        onClick = { selectedTag = if (selectedTag == tag) null else tag },
                        label = { Text(tag, fontSize = 12.sp) }
                    )
                }
            }

            Spacer(modifier = Modifier.height(4.dp))

            // Games List
            if (isLoading) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else {
                val filteredGames = games.filter { game ->
                    if (searchQuery.isBlank()) true
                    else {
                        game.title.contains(searchQuery, ignoreCase = true) ||
                                game.developer.contains(searchQuery, ignoreCase = true) ||
                                game.tags.any { it.contains(searchQuery, ignoreCase = true) }
                    }
                }

                if (filteredGames.isEmpty()) {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text(
                            text = "No se encontraron juegos con estos filtros.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        items(filteredGames, key = { it.id }) { game ->
                            GameCard(game = game)
                        }
                    }
                }
            }
        }
    }

    // Server Config Dialog
    if (showSettingsDialog) {
        var currentUrl by remember { mutableStateOf(YStoreApiClient.getBackendUrl(context)) }
        AlertDialog(
            onDismissRequest = { showSettingsDialog = false },
            title = { Text("Servidor yStore Backend") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = "Configura la URL del backend FastAPI (agregador F-Droid + itch.io):",
                        style = MaterialTheme.typography.bodySmall
                    )
                    OutlinedTextField(
                        value = currentUrl,
                        onValueChange = { currentUrl = it },
                        label = { Text("URL del Backend") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = { currentUrl = "http://10.0.2.2:8000" }) {
                            Text("Emulador (10.0.2.2)")
                        }
                        TextButton(onClick = { currentUrl = "http://localhost:8000" }) {
                            Text("Localhost")
                        }
                    }
                }
            },
            confirmButton = {
                Button(onClick = {
                    YStoreApiClient.setBackendUrl(context, currentUrl)
                    showSettingsDialog = false
                    loadGames()
                    Toast.makeText(context, "Servidor actualizado", Toast.LENGTH_SHORT).show()
                }) {
                    Text("Guardar y Recargar")
                }
            },
            dismissButton = {
                TextButton(onClick = { showSettingsDialog = false }) {
                    Text("Cancelar")
                }
            }
        )
    }

    // Publish Info Dialog
    if (showPublishInfoDialog) {
        AlertDialog(
            onDismissRequest = { showPublishInfoDialog = false },
            title = { Text("Publicar Juegos en yStore") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = "Flujo de Publicación para Desarrolladores Externos:\n\n" +
                                "1. Conecta tu GitHub App con permisos de contenido y administración.\n" +
                                "2. yStore crea tu repo con estructura Fastlane (/metadata/android/en-US/*).\n" +
                                "3. Sube tu APK a un GitHub Release (no al repo).\n" +
                                "4. Nuestro Webhook sincroniza, escanea el APK con VirusTotal/ClamAV y lo aprueba automáticamente en el catálogo.",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            },
            confirmButton = {
                Button(onClick = {
                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse("https://github.com/anhot11/yStore"))
                    context.startActivity(intent)
                    showPublishInfoDialog = false
                }) {
                    Text("Ver Repositorio GitHub")
                }
            },
            dismissButton = {
                TextButton(onClick = { showPublishInfoDialog = false }) {
                    Text("Cerrar")
                }
            }
        )
    }
}

@Composable
fun GameCard(game: YStoreGame) {
    val context = LocalContext.current

    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Game Icon
                if (!game.iconUrl.isNullOrBlank()) {
                    AsyncImage(
                        model = game.iconUrl,
                        contentDescription = game.title,
                        modifier = Modifier
                            .size(54.dp)
                            .clip(RoundedCornerShape(12.dp)),
                        contentScale = ContentScale.Crop
                    )
                } else {
                    Box(
                        modifier = Modifier
                            .size(54.dp)
                            .clip(RoundedCornerShape(12.dp))
                            .background(MaterialTheme.colorScheme.primaryContainer),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = game.title.take(1),
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onPrimaryContainer
                        )
                    }
                }

                Spacer(modifier = Modifier.width(12.dp))

                // Title and Developer
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = game.title,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    if (game.developer.isNotBlank()) {
                        Text(
                            text = game.developer,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    Spacer(modifier = Modifier.height(2.dp))
                    // Source badge
                    SourceBadge(source = game.source)
                }
            }

            if (game.description.isNotBlank()) {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = game.description,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )
            }

            // Tags
            if (game.tags.isNotEmpty()) {
                Spacer(modifier = Modifier.height(8.dp))
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    game.tags.take(4).forEach { tag ->
                        Surface(
                            shape = CircleShape,
                            color = MaterialTheme.colorScheme.surfaceVariant,
                            modifier = Modifier.padding(vertical = 2.dp)
                        ) {
                            Text(
                                text = tag,
                                fontSize = 10.sp,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Action Button
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End
            ) {
                if (!game.downloadUrl.isNullOrBlank() && (game.downloadUrl.endsWith(".apk") || game.source == "fdroid" || game.source == "community")) {
                    Button(
                        onClick = {
                            downloadAndInstallApk(context, game.downloadUrl, "${game.title}.apk")
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
                    ) {
                        Text("📥 Descargar APK", fontSize = 12.sp)
                    }
                } else if (!game.downloadUrl.isNullOrBlank()) {
                    OutlinedButton(
                        onClick = {
                            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(game.downloadUrl))
                            context.startActivity(intent)
                        }
                    ) {
                        Text("🌐 Ver en itch.io", fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

@Composable
fun SourceBadge(source: String) {
    val (label, bgColor, textColor) = when (source.lowercase()) {
        "fdroid" -> Triple("F-Droid", Color(0xFF2E7D32), Color.White)
        "itchio" -> Triple("itch.io", Color(0xFFE53935), Color.White)
        "community" -> Triple("Comunidad", Color(0xFF1565C0), Color.White)
        else -> Triple(source.uppercase(), Color.Gray, Color.White)
    }

    Surface(
        shape = RoundedCornerShape(4.dp),
        color = bgColor
    ) {
        Text(
            text = label,
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
            color = textColor,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
        )
    }
}

fun downloadAndInstallApk(context: Context, url: String, filename: String) {
    try {
        val cleanName = filename.replace("[^a-zA-Z0-9.-]".toRegex(), "_")
        val request = DownloadManager.Request(Uri.parse(url))
            .setTitle(cleanName)
            .setDescription("Descargando desde yStore...")
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, cleanName)
            .setAllowedOverMetered(true)
            .setAllowedOverRoaming(true)

        val dm = context.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        dm.enqueue(request)
        Toast.makeText(context, "Iniciando descarga: $cleanName", Toast.LENGTH_SHORT).show()
    } catch (e: Exception) {
        // Fallback to browser intent if DownloadManager throws permissions/security error
        try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            context.startActivity(intent)
        } catch (ex: Exception) {
            Toast.makeText(context, "Error al descargar: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }
}
