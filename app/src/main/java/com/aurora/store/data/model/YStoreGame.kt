package com.aurora.store.data.model

import org.json.JSONObject

data class YStoreGame(
    val id: String,
    val title: String,
    val source: String,
    val iconUrl: String? = null,
    val screenshots: List<String> = emptyList(),
    val description: String = "",
    val developer: String = "",
    val downloadUrl: String? = null,
    val tags: List<String> = emptyList()
) {
    companion object {
        fun fromJson(json: JSONObject): YStoreGame {
            val screenshotsList = mutableListOf<String>()
            val screenshotsArray = json.optJSONArray("screenshots")
            if (screenshotsArray != null) {
                for (i in 0 until screenshotsArray.length()) {
                    val s = screenshotsArray.optString(i)
                    if (s.isNotBlank()) screenshotsList.add(s)
                }
            }

            val tagsList = mutableListOf<String>()
            val tagsArray = json.optJSONArray("tags")
            if (tagsArray != null) {
                for (i in 0 until tagsArray.length()) {
                    val t = tagsArray.optString(i)
                    if (t.isNotBlank()) tagsList.add(t)
                }
            }

            val rawIcon = if (json.isNull("icon_url")) null else json.optString("icon_url")
            val rawDownload = if (json.isNull("download_url")) null else json.optString("download_url")

            return YStoreGame(
                id = json.optString("id"),
                title = json.optString("title"),
                source = json.optString("source", "fdroid"),
                iconUrl = rawIcon?.takeIf { it.isNotBlank() && it != "null" },
                screenshots = screenshotsList,
                description = json.optString("description"),
                developer = json.optString("developer"),
                downloadUrl = rawDownload?.takeIf { it.isNotBlank() && it != "null" },
                tags = tagsList
            )
        }
    }
}
